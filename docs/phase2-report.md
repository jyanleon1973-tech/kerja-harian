# Phase 2 完了報告 — GPU 解析基盤（API・ジョブ・ストレージ・段階別パイプライン）

作成日: 2026-11-01

## 1. 実装した内容

- **FastAPI サーバー**（`server/`）。§13 の API（ジョブ作成・状態・結果・コマ単位データ・手動修正・書き出し）に加え、ローカル用アップロード、署名付き URL の発行口、段階出力の取得、キャンセル、稼働確認、保持期間切れの削除。
- **ジョブ管理**（SQLite）。キュー、進捗・段階・メッセージの更新、タイムアウト、失敗時の再試行（上限回数）、同時実行数の制限、古いジョブ・動画の自動削除、推論モデルのバージョン記録（`model_versions`）とパイプライン版（`pipeline_version`）。
- **ストレージ抽象**。ローカル（開発・テスト）と S3 互換（R2 / S3、署名付き URL）。S3 側は接続先がなく**未検証**。
- **段階別パイプライン**（各段階の出力を `jobs/<id>/stages/NN_<name>.json` に保存し、所要時間と要約を DB に記録）:
  `decode`（実タイムスタンプ基準のサンプリング、可変フレームレートの疑い検出）→ `perframe`（対象選手の追跡付き切り出し検出・姿勢推定・板検出・カメラ動作、探索方法と棄却理由をコマごとに記録）→ `temporal`（左右入替修正、1 コマ外れ値補修、補間フラグ付きの短い欠落補間、One Euro 前後方向平均）→ `camera`（撮影方向の自動判定/指定、カメラ動作を差し引いた軌跡）→ `turns`（骨盤向きの回転速度・軌跡の進行方向変化・横傾きの多数決。矛盾は 0、手掛かりなしは「不明」）→ `metrics`（撮影方向ごとの 観測/推定/不可、関節の確からしさで信頼度）→ `confidence`（コマごとの総合信頼度、品質要約、警告）→ `results`。
- **姿勢推定バックエンドの差し替え構造**。既定は CPU の MediaPipe（BlazePose GHUM 33 点）。GPU 用に RTMPose（ONNX、SimCC 復号）の雛形を用意（**未検証**）。
- **板検出**（古典 CV、信頼度付き、足首位置からは作らない）をサーバー側に移植。左右の窓が同じ板を拾った場合は 1 本として扱う。
- **骨格入り動画の書き出し**（OpenCV 描画 + FFmpeg H.264、区間・速度・表示項目を指定）。
- **手動修正の保存**（関節・板・左右入替・対象選手・ターン・切り替えの種別、コマ番号、任意データ。`training_consent` は既定 false）。
- **精度検証ツール**（`server/tools/eval.py`）。検証フレームの抽出と正解入力ひな形の生成、正解と推定の比較（関節誤差、PCK、左右識別正解率、板角度正解率、ターン方向正解率、切り替えコマ誤差、検出不能率、時系列ジッタ）。
- **フロントエンド**（`ski-posture.html`）にサーバー解析モードを追加。API URL を保存し、アップロード → ジョブ進捗の表示 → 結果を既存の表示（骨格・板・数値・グラフ・ターン表・書き出し）に流し込む。サーバーが計算した指標を優先して表示する。

## 2. 変更したファイル

| ファイル | 内容 |
|---|---|
| `server/app/main.py` | FastAPI アプリと API |
| `server/app/config.py` | 設定（環境変数） |
| `server/app/db.py` | SQLite（jobs / stage_outputs / corrections / exports） |
| `server/app/storage.py` | ローカル / S3 互換ストレージ |
| `server/app/jobs.py` | ジョブ実行（ワーカースレッド、タイムアウト、再試行、書き出し） |
| `server/app/pipeline/base.py` | 段階実行と段階出力の保存 |
| `server/app/pipeline/decode.py` | 動画メタ情報・実タイムスタンプ抽出 |
| `server/app/pipeline/pose.py` | 姿勢推定バックエンド（MediaPipe / RTMPose 雛形） |
| `server/app/pipeline/perframe.py` | 追跡・検出・板・カメラ動作のコマ処理 |
| `server/app/pipeline/ski.py` | 板検出 |
| `server/app/pipeline/temporal.py` | 時系列補正 |
| `server/app/pipeline/camera.py` | 撮影方向・軌跡 |
| `server/app/pipeline/turns.py` | ターン判定 |
| `server/app/pipeline/metrics.py` | 指標（観測/推定/不可、信頼度） |
| `server/app/pipeline/render.py` | 書き出し動画の描画 |
| `server/app/pipeline/run.py` | 段階の組み立て、信頼度、結果保存 |
| `server/tests/test_pipeline.py`, `server/tests/test_api.py` | テスト |
| `server/tools/eval.py` | 精度検証 |
| `server/README.md`, `server/requirements.txt`, `server/pytest.ini`, `server/.gitignore` | 運用 |
| `ski-posture.html` | サーバー解析モード、`computeMetrics` が進行方向なしのデータでも動くように |
| `docs/phase1-diagnosis.md`, `docs/phase1-cloud-and-models.md` | Phase 1 の報告 |

## 3. 使用した AI モデルとバージョン

| 用途 | モデル | 版 |
|---|---|---|
| 姿勢推定（既定・CPU） | MediaPipe Pose Landmarker（BlazePose GHUM）lite / full / heavy | `mediapipe==1.2.0`（Python）、モデルは `.../float16/latest/...`（結果 JSON に `model_versions.pose` としてファイルサイズ付きで記録。`latest` は更新で変わりうるため本番では固定版を同梱する） |
| 板検出 | 古典 CV（エッジ方向 + 裏付け率 + 暗部連続長） | `classical_edge_v2` |
| 姿勢推定（GPU 用雛形） | RTMPose ONNX | **未検証**（モデル未配置） |

推奨 GPU 構成（RunPod Serverless、RTMDet + ByteTrack + RTMPose-m Halpe26、Apache 2.0 系）は `docs/phase1-cloud-and-models.md` に記載。**有料リソースは作成していない（承認待ち）**。

## 4. 実際に実行したテスト

環境: この開発コンテナ（CPU のみ、GPU なし、Python 3.13、FFmpeg あり）。

| テスト | 内容 | 結果 |
|---|---|---|
| `pytest`（15 件） | 単体: 左右入替修正、外れ値補修、補間の上限、One Euro が段差を残し揺れを減らすこと、平滑化が欠落をまたがないこと、撮影方向ごとの 観測/推定/不可、低信頼度の非表示、板未検出時に板指標が不可になること、重心位置、軌跡の回転方向、SimCC 復号。結合: 形式違反のアップロード拒否、存在しないアップロードの拒否、**人物のいない合成動画**でジョブが完走し検出率 0 で結果・段階出力・修正保存・書き出しまで通ること、**人物の映った動画**（`SKI_TEST_VIDEO`）で検出率 > 80%、33 点、指標、撮影方向、スロー書き出し | **15 passed** |
| ブラウザ結合（Playwright、headless Chromium） | `ski-posture.html` から実際の API サーバー（uvicorn、lite モデル）へアップロード → ジョブ進捗 → 結果の読み込み → カードと数値パネルの表示 → コマ送り | 完走。4 秒の動画（10 コマ/秒）で所要 5 秒（perframe 3.0 s、他は 0.1 s 以下）。検出率 100%、エラーなし |
| 既存機能の回帰 | ブラウザ内解析（解析・コマ送り・区間ループ・グラフ・書き出し）の既存テスト | 変更後も通過（前回と同じスクリプト） |

## 5. 精度の比較結果

**比較していない。** 正解データ（人が付けた関節・板・ターンの座標とラベル）がまだないため、§11 の要求どおり、まず検証データ作成機能（`tools/eval.py extract` と正解ひな形）と比較機能（`tools/eval.py compare`）を実装した。したがって本 Phase では「精度が上がった」とは言えない。テスト動画は合成動画と人物写真から作った動画で、実際のスキー映像ではない。

## 6. 未解決の問題

- GPU ワーカーは未接続。パイプラインは CPU の MediaPipe で完走するが、高精度モデル（RTMPose / ViTPose）はモデル未配置・未検証。
- S3 互換ストレージと署名付きアップロードは接続先がなく未検証。
- ターン判定の手掛かりのうち「板の向きの変化」は未使用（板検出の安定性が足りないため）。ズームの補正は未実装（カメラ動作は平行移動のみ）。
- 補間コマの指標は確からしさを下げて計算しており、null にはしていない。
- 手動修正は保存のみ（Phase 6 で UI と再計算への反映）。
- MediaPipe のモデル URL が `latest`。本番では固定版を同梱する。
- 同時実行はスレッドベースで、プロセス分離・別マシンのワーカー（external モード）は未実装。

## 7. 次の Phase で改善する内容

- **Phase 3（人体骨格）**: 実際の SL/GS 映像（側面・正面・背面）から検証フレームを抽出して正解を付け、MediaPipe heavy と RTMPose-m（GPU）を同じ検証セットで比較する。GPU 接続（RunPod Serverless または Modal）は構成と費用の承認後。
- **Phase 4（板）**: 検証セットに板の両端を含め、現行の古典 CV の検出率・角度誤差を測った上で、専用検出器の学習データ作成に入る。
- **Phase 5**: ターン判定に板の向き変化と切り替えの検出を加え、補間コマの指標を null にし、ズーム補正を入れる。
- **Phase 6**: 手動修正 UI（関節ドラッグ、板の両端、左右入替、ターン修正）と修正後の再計算。
