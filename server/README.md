# スキー動画解析 API サーバー（Phase 2）

Python + FastAPI。動画のアップロード → 解析ジョブ → 段階別パイプライン（CPU の MediaPipe でも完走、GPU モデルは差し替え）→ 結果 JSON → 手動修正の保存 → 骨格入り動画の書き出し。

## 起動（ローカル）

```bash
cd server
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# Linux のコンテナでは MediaPipe が libEGL / libGLES を要求する: apt-get install -y libegl1 libgles2 libgl1
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

ブラウザで `ski-posture.html` を開き、「サーバー解析」の API URL に `http://localhost:8000` を入れて「サーバーで解析」を押す。

## 環境変数

| 変数 | 既定 | 意味 |
|---|---|---|
| `SKI_DATA_DIR` | `./data` | DB（SQLite）とローカルストレージ |
| `SKI_MODEL_DIR` | `./models` | モデルファイルの置き場（MediaPipe は初回に自動取得） |
| `SKI_MAX_UPLOAD_MB` | 500 | アップロード上限 |
| `SKI_MAX_CONCURRENT_JOBS` | 1 | 同時解析数 |
| `SKI_JOB_TIMEOUT_S` | 1800 | 1 ジョブの上限時間（超えると失敗） |
| `SKI_JOB_MAX_ATTEMPTS` | 2 | 失敗時の再試行回数 |
| `SKI_RETENTION_DAYS` | 30 | 古いジョブと動画の自動削除（`POST /api/admin/cleanup`） |
| `SKI_S3_BUCKET` / `SKI_S3_ENDPOINT` / `SKI_S3_REGION` / `SKI_S3_PREFIX` | なし | 指定すると S3 互換ストレージ（R2 等）を使い、署名付き URL を返す（この環境では未検証） |
| `SKI_CORS_ORIGINS` | `*` | 許可するオリジン（本番では GitHub Pages のオリジンに限定） |

## API（§13 準拠）

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/uploads` | multipart で動画を受け付け `upload_key` を返す（ローカル用） |
| POST | `/api/uploads/presign?filename=&content_type=` | 署名付きアップロード URL（S3 では本物の署名付き URL、ローカルでは `PUT /api/uploads/{key}`） |
| POST | `/api/analysis/jobs` | `{upload_key, params}` で解析ジョブ作成（201） |
| GET | `/api/analysis/jobs/{id}` | 状態・進捗・段階別の所要時間と要約 |
| GET | `/api/analysis/jobs/{id}/results?include_frames=` | 結果（`frames` は省略可能） |
| GET | `/api/analysis/jobs/{id}/frames?start=&limit=&fields=` | コマ単位データ |
| GET | `/api/analysis/jobs/{id}/stages/{seq}` | 段階出力そのもの（誤差の追跡用） |
| PATCH | `/api/analysis/jobs/{id}/corrections` | 手動修正の保存（`training_consent` は既定 false） |
| GET | `/api/analysis/jobs/{id}/corrections` | 保存済み修正 |
| POST | `/api/analysis/jobs/{id}/exports` | 骨格入り動画の生成ジョブ（速度・区間・表示項目） |
| GET | `/api/analysis/jobs/{id}/exports/{eid}` | 書き出し状態と URL |
| DELETE | `/api/analysis/jobs/{id}` | キャンセル |
| GET | `/api/health` | 稼働確認 |

パラメータ: `fps`(1–240), `start_s`, `end_s`, `pose_backend`(mediapipe|rtmpose), `pose_model`(lite|full|heavy), `sensitivity`, `view`(auto|side|front|back|oblique), `target`([x,y] 0–1), `roll_deg`。

## パイプライン（段階出力は `jobs/<id>/stages/NN_<name>.json` に保存）

1. `decode` 動画メタ情報、可変フレームレートの疑い、サンプル時刻
2. `perframe` 追跡付き切り出し検出 → 姿勢推定 → 板検出 → カメラ動作（位相相関）。検出の探索方法・棄却理由をコマごとに記録
3. `temporal` 左右入替修正、1 コマ外れ値補修、最大 0.4 秒の補間（`src=interp`）、One Euro（前後方向平均）
4. `camera` 撮影方向（自動/指定）、カメラ動作を差し引いた軌跡
5. `turns` 骨盤の向きの回転速度・軌跡の進行方向変化・横傾きの多数決。矛盾は 0、手掛かりなしは null（不明）
6. `metrics` 撮影方向ごとの 観測/推定/不可、関節の確からしさで信頼度
7. `confidence` コマごとの総合信頼度、品質要約、警告
8. `results` フロントエンドが読む `results.json`

## 姿勢推定バックエンド

- `mediapipe`（既定、CPU）: BlazePose GHUM 33 点、2D + 3D world。
- `rtmpose`（GPU サーバー用）: `app/pipeline/pose.py` の `RTMPoseONNXBackend`。ONNX とモデル定数が必要。**この環境ではモデルがなく未検証**。

## テスト

```bash
pytest                                   # 合成データの単体テスト + 人物なし動画での結合テスト（MediaPipe lite を自動取得）
SKI_TEST_VIDEO=/path/to/person.mp4 pytest  # 人物の映った動画で検出・指標・書き出しまで確認
```

## 精度検証

```bash
python tools/eval.py extract VIDEO out_dir --every 1.0      # 検証フレームと正解入力ひな形を作る
python tools/eval.py compare out_dir/labels.json results.json --pck 0.2
```

正解座標は人が `labels.json` に記入する。モデル変更の前後で同じ検証動画と正解を使い、PCK・関節誤差・左右正解率・板角度正解率・ターン正解率・切り替え誤差・検出不能率・時系列ジッタを比較する。

## GPU ワーカー（未接続・承認待ち）

Phase 2 では同一プロセスのワーカースレッド（`SKI_WORKER_MODE=inline`）。GPU クラウド（推奨: RunPod Serverless、試作: Modal。`docs/phase1-cloud-and-models.md`）に載せる場合は、同じ `Database` のキューを別プロセスから `claim_next_job` で取りに行く external モードを追加し、ストレージを S3 互換にする。有料リソースの作成は承認後に行う。
