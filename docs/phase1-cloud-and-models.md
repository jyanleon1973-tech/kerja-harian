# フェーズ 1: GPU クラウドとサーバー側モデルの選定

対象: `ski-posture.html`（ブラウザ内 MediaPipe、GitHub Pages）を「Python + FastAPI、ジョブ実行時だけ GPU を使う」構成へ移す際のクラウド・モデル・ストレージの比較。調査日 2026-11-01。姿勢推定モデルの一般比較と板検出の方式比較は [ski-posture-audit.md](./ski-posture-audit.md) の §3・§4 を参照し、本書ではサーバー側で使う前提の情報だけを足す。

> **出典の信頼度について**: 本セッションの外向き通信は許可ドメインに限られ、runpod.io / modal.com / aws.amazon.com / developers.cloudflare.com / supabase.com / backblaze.com / huggingface.co / download.openmmlab.com / universe.roboflow.com / arxiv.org には到達できなかった（cloud.google.com は到達できるが料金ページは JS 描画で本文が取れなかった）。到達できたのは GitHub（raw）、AWS 公式価格リスト API（pricing.us-east-1.amazonaws.com）、WebSearch の検索抜粋である。各数値に **[一次]**（公式ページ・公式リポジトリ・公式 API を直接取得）/ **[検索抜粋]**（WebSearch が返した公式ページの抜粋。全文は未確認）/ **[二次]**（第三者サイト）/ **[推測]** を付ける。**[二次]・[推測] の料金は契約前に必ず公式ページで再確認すること。**

---

## 1. GPU クラウドの比較

前提: 単一 GPU、1 ジョブ 1〜3 分、月 100〜1,000 ジョブ、Python の推論コードを Docker か関数としてデプロイする。

| 項目 | RunPod Serverless | RunPod Pod | Modal | AWS EC2 g6 / g5 / g4dn（東京 ap-northeast-1） | Google Cloud Compute Engine（L4 / T4） |
|---|---|---|---|---|---|
| GPU 種別 | 階層制。24 GB 階層 = L4 / A5000 / RTX 3090、48 GB 階層 = L40 / L40S / 6000 Ada、80 GB = A100 / H100 [一次: runpod/docs `snippets/serverless-gpu-pricing-table.mdx`] | L4、A5000、RTX 4090、L40S、A100 ほか | T4、L4、A10、L40S、A100 40/80 GB、H100、H200、B200 [二次] | g6.xlarge = L4 24 GB、g5.xlarge = A10G 24 GB、g4dn.xlarge = T4 16 GB [一次: 価格リストの属性列] | L4（G2 系）、T4（N1 系） |
| 料金 | 秒課金。16 GB 階層 $0.00016/s、**24 GB 階層 $0.00019/s（=$0.684/h）**、4090 $0.00031/s、48 GB 階層 $0.00034〜0.00053/s、A100 80 GB $0.00076/s、H100 $0.00116/s。確認 2026-11-01 [一次: https://github.com/runpod/docs（`snippets/serverless-gpu-pricing-table.mdx`、公式 docs のソース）]。Active ワーカーは割引（営業問い合わせ） | 時間課金。L4 約 $0.39〜0.43/h、A5000 $0.22（Community）〜0.43（Secure）/h、RTX 4090 $0.34〜0.69/h [二次: hackceleration、computeprices 等、2026 年中の採取。Community/Secure で差がある]。**公式ページ未到達のため未確認** | 秒課金。T4 $0.000164/s（$0.59/h）、**L4 $0.000222/s（$0.80/h）**、A10 $0.000306/s、L40S $0.000542/s、A100 80 GB $0.000694/s、H100 $0.001097/s [二次: beam.cloud、xpay.sh、usagepricing の 2026 年採取。複数ソースで一致するが公式未到達]。Starter プラン $0/月で毎月 $30 分のクレジット [二次]。リージョン指定は基本料金 ×1.15〜1.75 の割増 [二次: usagepricing 2026-10-24 の変更記録] | オンデマンド Linux（東京）: **g6.xlarge $1.1672/h、g5.xlarge $1.4590/h、g4dn.xlarge $0.7100/h**。確認 2026-11-01 [一次: AWS Price List API `offers/v1.0/aws/AmazonEC2/current/ap-northeast-1/index.csv`（2026-10-29 版）]。スポット（東京、最安 AZ）: g6.xlarge 約 $0.42〜0.47/h、g5.xlarge 約 $0.57〜0.70/h、g4dn.xlarge 約 $0.25/h [二次: doit.com の採取、時点不明。中断率は g6.xlarge で「>20%」帯] | 東京の GPU 単価は **未確認**（料金ページ本文を取得できず）。参考: L4 1 基 約 $0.70/h（リージョン不明）[検索抜粋: cloud.google.com/products/compute/pricing/accelerator-optimized]、T4 $0.35/h（us-west8 の例）[検索抜粋: cloud.google.com GPU pricing]、g2-standard-4（L4×1 + 4 vCPU）東京 オンデマンド $0.9077/h・スポット $0.44〜0.54/h [二次: sparecores.com、gcloud-compute.com] |
| 起動（コールドスタート） | 公式 docs は秒数を明記せず。「イメージ取得とキャッシュ済みモデルのダウンロードはスケールダウン中に行われ課金されない。課金はハンドラが準備できるまでのモデル読込から」[一次: `serverless/pricing.mdx`]。FlashBoot は既定で有効 [一次: `endpoint-configurations.mdx`]。公称「200 ms 未満」は FlashBoot で状態保持できた場合の宣伝値 [検索抜粋: runpod.io 製品ページ]。低頻度エンドポイントの実測は 8〜30 秒、大モデル初回 50 秒超の報告あり [二次: premai.io 2026]。本用途（モデル合計 〜200 MB）では **5〜20 秒と見込む [推測]** | 起動 1〜3 分 [推測]。常時起動なら 0 | `scaledown_window` 既定 60 秒（2 秒〜20 分で変更可）[検索抜粋: modal.com/docs/guide/cold-start]。公式ブログの例: ViT 推論関数 8.5 秒 → メモリスナップショットで 2.25 秒、音声モデル 20 秒 → GPU スナップショットで 2 秒 [検索抜粋: modal.com/blog]。**本用途は 5〜15 秒と見込む [推測]** | インスタンス起動 + Docker 起動で 1〜3 分 [推測]。EC2 は秒課金（最低 60 秒）[一般知識・本セッション未確認] | VM 起動 1〜2 分 [推測]。Cloud Run GPU（L4、ゼロスケール可、$0.0001867/GPU 秒）があるが、公式 docs の L4 対応リージョンに asia-northeast1 は**見当たらない**（シンガポール等）[検索抜粋: docs.cloud.google.com/run/docs/configuring/services/gpu、cloud.google.com/run/pricing] |
| ジョブ実行時のみ課金 | **可**。Flex ワーカーはゼロスケール。待機（idle timeout 既定 5 秒）中も課金 [一次] | 不可（Pod を止めるまで課金） | **可**。コンテナ稼働秒のみ。`scaledown_window` 中は課金 [検索抜粋] | 自前で起動・停止を制御すれば近いことは可能（Lambda から起動、完了後 terminate）。AWS Batch でも可だが構築が重い | 同左。Cloud Run GPU は可だが東京未対応（上記） |
| ストレージ連携 | コンテナディスク ≈ $0.10/GB 月、ネットワークボリューム $0.07/GB 月（<1 TB）[一次: `serverless/pricing.mdx`]。ネットワークボリュームはエンドポイントをその DC に固定する [一次]。外部オブジェクトストレージへは HTTP で読み書き | 同左 | Volume（永続）あり。料金は未確認。S3 互換バケットの CloudBucketMount あり [一般知識・未確認] | S3 と同リージョンなら転送無料。EBS 必要 | GCS と同リージョン転送無料 |
| 保守性（Python / デプロイ） | `runpod` SDK でハンドラ関数を書き、Docker イメージを push → エンドポイント作成。REST `/run` `/status` で非同期ジョブ。結果保持 30 分 [一次]。Docker ビルド必須 | SSH / Jupyter。手動運用寄り | **最も簡単**: Python のデコレータだけでイメージ定義とデプロイ（Docker 不要）。ただし入出力は常に us-east-1 のコントロールプレーンを経由 [検索抜粋: modal.com/docs/guide/region-selection] | IAM・VPC・AMI・自動停止の作り込みが必要。最も重い | AWS と同程度 |
| 日本からの利用・支払い | クレジットカード（Stripe 経由、$10 から前払いクレジット、プリペイドカードは $100 以上推奨）、$5,000 超は請求書払い [検索抜粋: docs.runpod.io/accounts-billing/billing]。日本 DC「AP-JP-1（福島）」を 2025-03 に開設 [検索抜粋: runpod.io blog]。**Serverless が日本 DC で使えるかは未確認** | 同左 | クレジットカード。`jp` リージョン指定が可能（割増あり）[検索抜粋: modal.com/docs/guide/region-selection] | 日本法人契約・円建て請求可 [一般知識] | 同左 |

国外事業者（RunPod、Modal）への支払いは消費税の取扱い（リバースチャージ等）が国内事業者と異なる可能性があるため、経費計上の際は税理士に確認すること [一般知識]。

**推奨（ジョブ実行時のみ GPU を使う前提）**

1. **本番: RunPod Serverless の 24 GB 階層（L4 / A5000 / 3090）**。理由: 秒課金の単価が公式ソースで確認できる中で最安（$0.00019/s）、イメージ取得が課金対象外、`/run` の非同期キューと 30 分の結果保持がこの用途（1〜3 分のバッチ推論）に合う、GPU 種別を 3 つまで優先順位付きで指定でき在庫切れに強い [一次]。弱点は Docker ビルドが必須なこと、Active ワーカー割引が営業経由なこと、日本 DC での Serverless 可否が未確認なこと。
2. **試作・検証: Modal**。理由: Docker 不要で Python だけでデプロイでき、月 $30 のクレジット [二次] で月 100 本規模なら GPU 費用がほぼ 0 になる。弱点はデータが必ず米国のコントロールプレーンを経由すること、日本リージョン固定に割増がかかること。選手映像を国内に留めたい要件があるなら本番には向かない。
3. **AWS / GCP は今回は見送り**。理由: ジョブ単位課金を自前で組む必要があり、東京の L4 単価は RunPod の 1.7 倍（g6.xlarge $1.1672/h 対 $0.684/h）。企業契約・円建て請求・東京リージョンの保持要件が最優先になった時点で、EC2 g6 スポット + AWS Batch を再検討する。

---

## 2. 推定費用

**この環境では GPU を実行できないため、以下はすべて [推測] であり実測値は一つもない。** 根拠にした公開ベンチマークのみ出典付きで示す。導入後に最初にやるべきことは、1 本の動画で各段の所要秒数をログに出し、この表を実測で置き換えることである。

### 前提
- 入力: 1 分・30 fps・1,920×1,080・H.264、1,800 フレーム、200 MB。出力: 指標 JSON/CSV 5 MB、骨格オーバーレイ動画（任意、再エンコード 50 MB 程度と仮定）。
- 画面内の選手は 1 人（検出は全フレーム、姿勢推定は追跡 ID 1 人分）。
- GPU は L4 相当、推論は ONNX Runtime CUDA EP（FP16）。TensorRT 化すれば 1.5〜3 倍速くなる見込みだが初期は使わない。
- 課金はコンテナの稼働秒（GPU が遊んでいる前処理・エンコード時間も含む）。

### 処理段ごとの時間（1,800 フレーム）

| 段 | モデル / 手段 | 公開ベンチマーク（出典） | L4・ORT での 1 フレーム見込み [推測] | 1,800 フレーム [推測] |
|---|---|---|---|---|
| 動画デコード | OpenCV / PyAV（CPU） | — | 3〜5 ms | 6〜9 秒 |
| 人物検出 | RTMDet-m（640、person） | T4 TensorRT-FP16 6.41 ms、RTX 3090 1.62 ms [一次: mmdetection `configs/rtmdet/README.md`] | 6〜10 ms（ORT は TRT より遅い） | 11〜18 秒 |
| 姿勢推定 | RTMPose-m Halpe26（256×192） | GTX 1660 Ti TensorRT-FP16 2.29 ms（COCO 版）、CPU i7-11700 ORT 11.06 ms [一次: mmpose `projects/rtmpose/README.md`] | 3〜6 ms（1 人） | 5〜11 秒 |
| （代替）姿勢推定 | ViTPose-B（256×192） | A100・バッチ 64 で 944 fps [検索抜粋: arXiv 2204.12484 Table] | 10〜20 ms（単枚、L4 は A100 の 1/4〜1/5 の性能） | 18〜36 秒 |
| 板・ブーツ検出 | RTMDet-s または YOLOX-s をファインチューニング（640） | RTMDet-s T4 TRT-FP16 2.96 ms [一次: 同上]、YOLOX-s V100 9.8 ms [一次: YOLOX README] | 4〜8 ms | 7〜14 秒 |
| 追跡・後処理 | ByteTrack（CPU）＋ One Euro 等 | ByteTrack は検出器込みで V100 29.6 fps [一次: ByteTrack README]。追跡単体は 1 ms 未満 | 1〜3 ms（前後処理の Python 込み） | 2〜5 秒 |
| 動画生成 | FFmpeg libx264（CPU 4 コア）または h264_nvenc | libx264 medium 1080p で 100〜200 fps との記述 [二次: cincopa.com、検証方法不明] | 描画込みで 10〜20 ms | 18〜36 秒（NVENC なら 5〜10 秒） |
| モデル読込・コールドスタート | — | §1 参照 | — | 5〜20 秒 |
| ストレージ入出力 | 200 MB 取得 + 55 MB 書込 | — | — | 5〜15 秒 |
| **合計（課金される稼働秒）** | | | | **約 60〜160 秒。計算は 120 秒を標準、180 秒を悲観値とする** |

GPU の純粋な推論時間は合計 30〜50 秒で、残りは CPU 処理と入出力である。つまり**費用はフレーム数よりも「コンテナの稼働秒」で決まる**。費用を下げる最短経路は、TensorRT 化よりも、デコード・描画・エンコードの並列化と NVENC 利用である。

### 1 本あたりと月額（GPU 部分）

| 基盤 | 単価 | 120 秒 / 本 | 180 秒 / 本 | 月 100 本 | 月 1,000 本 |
|---|---|---|---|---|---|
| RunPod Serverless 24 GB 階層 | $0.00019/s [一次] | $0.023 | $0.034 | **$2.3〜3.4** | **$23〜34** |
| Modal L4 | $0.000222/s [二次]（日本リージョン固定なら ×1.15〜1.75 [二次]） | $0.027 | $0.040 | $2.7〜4.0（$30 クレジット内） | $27〜40（固定で最大 $70） |
| AWS g6.xlarge 東京 オンデマンド | $1.1672/h [一次]＋起動 2 分を毎回加算 | $0.078 | $0.097 | $7.8〜9.7 | $78〜97（常時起動なら月 $840） |
| AWS g6.xlarge 東京 スポット | 約 $0.45/h [二次]＋起動 2 分を毎回加算 | $0.030 | $0.038 | $3.0〜3.8 | $30〜38（中断対策が別途必要） |

### ストレージ費用（動画 200 MB + 結果 5 MB、30 日保存）

30 日保存なので保存量はほぼ「1 か月分の投入量」で定常化する: 月 100 本 → 約 20.5 GB、月 1,000 本 → 約 205 GB。

| サービス | 保存単価 | 月 100 本（20.5 GB） | 月 1,000 本（205 GB） |
|---|---|---|---|
| Cloudflare R2 | $0.015/GB 月、10 GB 無料 [検索抜粋: developers.cloudflare.com/r2/pricing] | $0.16 | $2.9 |
| AWS S3 Standard（東京） | $0.025/GB 月（最初の 50 TB）[一次: Price List API AmazonS3 ap-northeast-1、2026-10-15 版] | $0.51 | $5.1 |
| Backblaze B2 | $6.95/TB 月、10 GB 無料 [検索抜粋: backblaze.com blog「2026-05-01 から $6→$6.95」] | $0.07 | $1.4 |
| Supabase Storage（Pro） | $25/月に 100 GB 含む、超過 $0.021/GB [二次: 複数の 2026 年記事で一致。公式未到達] | $25（プラン料金のみ） | $25 + $2.2 |

### 通信費用

- アップロード（ブラウザ → ストレージ）: 4 社とも受信は無料 [R2・S3 は一次/検索抜粋、B2・Supabase は二次]。
- ダウンロード: 結果の閲覧（55 MB × 3 回/本と仮定）と、**GPU ワーカーが元動画 200 MB を取りに来る分**を合わせると、月 100 本で約 37 GB、月 1,000 本で約 365 GB。
  - R2: 転送料 $0 [検索抜粋]。
  - B2: 保存量の 3 倍まで無料、超過 $0.01/GB [検索抜粋]。月 1,000 本で保存 205 GB → 615 GB まで無料 → $0。
  - S3 東京 → インターネット: 最初の 10 TB は **$0.114/GB**、全サービス合算で月 100 GB 無料 [一次: Price List API AWSDataTransfer「APN1-DataTransfer-Out-Bytes」]。月 100 本で $0、月 1,000 本で約 **$30**。GPU を RunPod / Modal に置くと S3 からの取り出しが「インターネット向け転送」になる点に注意。
  - Supabase Pro: 250 GB 含む、超過 $0.09/GB [二次]。月 1,000 本で約 $10。

### まとめ（月額、GPU + ストレージ + 通信）

| | 月 100 本 | 月 1,000 本 |
|---|---|---|
| RunPod Serverless + R2 | **約 $2.5〜3.6** | **約 $26〜37** |
| Modal + R2 | $0（クレジット内）〜$4 | $30〜73 |
| RunPod Serverless + S3 東京 | 約 $3〜4 | 約 $58〜69（転送料が支配的） |

いずれも [推測]。加えて FastAPI を置く常時起動の小さな CPU ホスト（月 $5〜20 程度 [推測]）と DB（§4）が必要。

---

## 3. サーバー側で使う推奨モデルと取得先

ライセンス方針: 公開サービスとして動かすため、**Apache 2.0 / MIT に統一**し、AGPL-3.0（Ultralytics YOLO 系、boxmot）はサーバー側でも採用しない。AGPL はネットワーク越しの提供でもソース公開義務が生じうる（第 13 条）。

| 役割 | 推奨 | ライセンス | サイズ | 公式速度（GPU 種別） | 重み URL |
|---|---|---|---|---|---|
| 人物検出（主） | **RTMDet-m person**（640、COCO+Objects365 の人物のみで学習） | Apache 2.0 [一次: mmdetection / mmpose LICENSE] | 24.71 M params（COCO 版）[一次] | TRT-FP16: T4 6.41 ms、RTX 3090 1.62 ms（COCO 版、NMS 除く）[一次: mmdetection README] | `https://download.openmmlab.com/mmpose/v1/projects/rtmpose/rtmdet_m_8xb32-100e_coco-obj365-person-235e8209.pth` [一次: mmpose README。本セッションから到達不可] |
| 人物検出（軽量） | RTMDet-nano person（320） | Apache 2.0 | 4.8 M 級 [一次: tiny の値。nano は未確認] | tiny: T4 2.34 ms [一次] | `https://download.openmmlab.com/mmpose/v1/projects/rtmpose/rtmdet_nano_8xb32-100e_coco-obj365-person-05d8511e.pth`。設定 `projects/rtmpose/rtmdet/person/rtmdet_nano_320-8xb32_coco-person.py` [一次] |
| 人物検出（代替） | YOLOX-s / m（Human-Art 学習版が mmpose にあり、rtmlib の既定検出器は yolox_m humanart ONNX） | Apache 2.0 [一次: YOLOX リポジトリ] | s 9.0 M / m 25.3 M [一次] | V100: s 9.8 ms、m 12.3 ms [一次: YOLOX README] | `https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/yolox_s_8xb8-300e_humanart-3ef259a7.pth`、ONNX: `.../onnx_sdk/yolox_m_8xb8-300e_humanart-c2c7a14a.zip` [一次: mmpose README / rtmlib README] |
| 人物検出（検討） | RF-DETR Nano/Small/Medium | 「rfdetr パッケージと Apache 指定の重みは Apache 2.0、XL/2XL と rfdetr_plus は別ライセンス（PML 1.0）」[検索抜粋: github.com/roboflow/rf-detr README。LICENSE ファイルは取得できず] | 未確認 | 未確認 | https://github.com/roboflow/rf-detr |
| 不採用 | Ultralytics YOLO11 / YOLOv8（detect・pose・obb・seg） | **AGPL-3.0** [一次: ultralytics LICENSE]。商用は Enterprise License（価格非公開）[検索抜粋] | — | — | — |
| 姿勢推定（主） | **RTMPose-m Halpe26（body7 学習、256×192）**。26 点に踵・つま先を含む | Apache 2.0 [一次: mmpose LICENSE] | 13.93 M params、1.95 GFLOPs [一次]。ONNX は fp32 で約 56 MB、fp16 で約 28 MB [推測: params×4 B] | Halpe26 版の公式レイテンシは未掲載。COCO 版 RTMPose-m: GTX 1660 Ti TRT-FP16 2.29 ms、i7-11700 ORT 11.06 ms [一次] | ONNX SDK: `https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.zip`。pth: `.../rtmposev1/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth` [一次]。ミラー: huggingface.co/Tau-J/RTMPose [一次: rtmlib README。未到達] |
| 姿勢推定（高精度） | RTMPose-l Halpe26 384×288 | Apache 2.0 | 28.11 M params、4.19 GFLOPs（256×192 版）[一次] | COCO 版 l: 1660 Ti 3.46 ms [一次] | `.../onnx_sdk/rtmpose-l_simcc-body7_pt-body7-halpe26_700e-384x288-734182ce_20230605.zip` [一次] |
| 姿勢推定（全身 133 点） | RTMPose-m COCO-WholeBody 256×192（手指・顔は本用途では不要。ストック把持の解析用に将来検討） | Apache 2.0 | 2.22 GFLOPs [一次] | Whole AP 58.2、1660 Ti TRT-FP16 4.00 ms [一次] | `.../rtmposev1/rtmpose-m_simcc-coco-wholebody_pt-aic-coco_270e-256x192-cd5e845c_20230123.pth` [一次] |
| 姿勢推定（代替） | **ViTPose-B**（COCO+AIC+MPII 学習版 AP 77.1）。足先なし（17 点） | Apache 2.0 [一次: ViTPose リポジトリ表示、HF usyd-community も apache-2.0 [検索抜粋]] | 86 M params [検索抜粋: 論文]。HF safetensors 約 344 MB [検索抜粋] | A100・バッチ 64 で 944 fps [検索抜粋: 論文 Table]。GFLOPs は未確認 | 公式は OneDrive（README の表）。Transformers 版: https://huggingface.co/usyd-community/vitpose-base-simple [検索抜粋]。ONNX: `https://huggingface.co/JunkyByte/easy_ViTPose`（rtmlib が参照）[一次: rtmlib README] |
| 追跡 | **ByteTrack**（公式実装を取り込む。Kalman + IoU の 2 段マッチングで 300 行程度） | MIT [一次: ByteTrack リポジトリ] | モデルなし | MOT17 MOTA 80.3、検出器込み V100 29.6 fps [一次] | https://github.com/FoundationVision/ByteTrack |
| 追跡（不採用） | boxmot（ByteTrack / BoT-SORT の pip 実装） | **AGPL-3.0** [一次: boxmot LICENSE] | — | — | — |
| 板・ブーツ検出 | 既製モデルは**なし**（監査 §4 と同じ結論）。検出器は RTMDet-s / YOLOX-s を HBB（ski・boot・pole）でファインチューニングし、向きは姿勢の踵・つま先と板矩形の長軸から推定する。回転矩形が要るなら RTMDet-R（mmrotate、Apache 2.0） | Apache 2.0 | — | — | データ候補: Roboflow Universe「Skiers and Snowboarders」（YOLOv8 チェックポイント、クラス・ライセンス未確認）、「skidanalys」（クラス ski / board / skiers-snowboarders）、「Ski detection」（CC BY 4.0、skier・flag）、「Ski Snowboard 1」（CC BY 4.0）[検索抜粋]。EPFL Ski2DPose: 1,982 枚、24 点（板・ストック含む）、CC 動画由来、**利用条件は未確認** [検索抜粋: epfl.ch/labs/cvlab/data/ski-2dpose-dataset] |
| 動画生成 | FFmpeg（`libx264` または `h264_nvenc`）。`-movflags +faststart`、`-pix_fmt yuv420p` | FFmpeg 本体 LGPL 2.1+、libx264 組込ビルドは GPL。サーバー内で実行し配布しないため義務は生じないが、配布物に含めないこと [一般知識] | — | §2 参照 | OS パッケージまたは公式静的ビルド |

**変換手段（MMPose → ONNX / TensorRT）**
- MMDeploy（Apache 2.0 [一次: mmdeploy LICENSE]）: `tools/deploy.py` に `pose-detection_simcc_onnxruntime_dynamic.py` または `pose-detection_simcc_tensorrt_dynamic-256x192.py` を渡すと `end2end.onnx` / `end2end.engine` が出る [一次: mmpose rtmpose README「Step2. Convert Model」]。変換済み SDK モデルは OpenMMLab Deploee（platform.openmmlab.com/deploee）からも取得できる [一次]。
- **rtmlib**（Apache 2.0 [一次: rtmlib LICENSE]）: `pip install rtmlib` だけで mmcv / mmpose なしに RTMDet・YOLOX・RTMPose（17/26/133 点）・RTMO・ViTPose の ONNX 推論ができ、バックエンドは onnxruntime / openvino / opencv [一次: rtmlib README]。**サーバー側の最初の実装は rtmlib + onnxruntime-gpu で始め、速度が足りなければ MMDeploy で TensorRT 化する**のが最短。
- 板・ブーツのファインチューニング手順と必要データ量は監査 §4「推奨手順」を参照（HBB 1〜2k 枚で試作、キーポイント方式なら 2k 枚で試作・5〜10k 枚で実用）。学習は RunPod Pod（A5000 / 4090、数時間）で行い、Serverless には推論だけ置く。

---

## 4. オブジェクトストレージと DB の選択肢

| 項目 | Cloudflare R2 | AWS S3（東京） | Supabase Storage | Backblaze B2 |
|---|---|---|---|---|
| 保存 | $0.015/GB 月、10 GB 無料（Infrequent Access $0.01）[検索抜粋: 公式 docs] | $0.025/GB 月（最初の 50 TB）[一次] | Pro $25/月に 100 GB、超過 $0.021/GB [二次]。Free は 1 GB [二次] | $6.95/TB 月、10 GB 無料 [検索抜粋: 公式ブログ] |
| 転送（受信 / 送信） | 無料 / **無料** [検索抜粋] | 無料 / $0.114/GB（10 TB まで、月 100 GB 無料）[一次] | 無料 / Pro 250 GB 込み、超過 $0.09/GB [二次] | 無料 / 保存量の 3 倍まで無料、超過 $0.01/GB [検索抜粋] |
| 操作料金 | Class A $4.50/100 万、Class B $0.36/100 万 [検索抜粋] | PUT $4.70/100 万、GET $0.37/100 万 [一次] | 込み | 2026-05-01 から API 呼出無料 [検索抜粋] |
| 署名付き URL | S3 API で GET/HEAD/PUT/DELETE に対応、有効期限 1 秒〜7 日。presigned POST は非対応なので PUT を使う [検索抜粋: developers.cloudflare.com/r2/api/s3/presigned-urls] | 対応（S3 標準） | `createSignedUrl(path, expiresIn)` で対応 [一次: supabase/supabase リポジトリの docs ソース]。アップロード用署名 URL も SDK にある [一般知識] | S3 互換 API で対応 [一般知識] |
| 使い勝手 | boto3 がそのまま使える（endpoint 指定）。CORS 設定が要る。リージョンは自動配置 | boto3。IAM 設計が要る。EC2 と同リージョンなら GPU 側転送無料 | JS/Python SDK。DB・認証と同一基盤 | boto3（S3 互換） |

**選択**: GPU を RunPod / Modal に置くなら、ワーカーが元動画を取りに来る転送が課金されない **R2** が最も安く、構成も単純（§2 の試算で月 1,000 本時に S3 比で約 $30/月の差）。B2 も同等に安いが、エコシステムと将来の Workers 連携を考えて R2 を第一候補とする。AWS に GPU を置く場合のみ S3。

**DB**

| | Supabase（Postgres マネージド） | 自前 SQLite（FastAPI と同居） | 自前 Postgres（VPS / RDS） |
|---|---|---|---|
| 向く規模 | 月 100〜1,000 本・複数ユーザー・認証あり | 月 100 本・単一管理者・1 台運用 | 月 1,000 本超・バックアップ要件あり |
| 費用 | Free（DB 500 MB、1 週間無操作で一時停止 [二次]）か Pro $25/月 [二次] | $0（ホスト代のみ） | $10〜50/月 [推測] |
| 長所 | 認証・Row Level Security・Storage が一体。ダッシュボードあり | 依存ゼロ、バックアップはファイルコピー | 自由度 |
| 短所 | プラン料金が固定でかかる。1 プロジェクトの Compute は $10 クレジット内の最小構成 [二次] | 同時書込に弱い。ワーカーが外部（RunPod）にいると直接書けないため、状態更新は FastAPI 経由の HTTP にする必要がある | 運用（パッチ・バックアップ）を自分で持つ |

**推奨**: 初期は **SQLite + FastAPI**（ジョブ ID、状態、入出力のオブジェクトキー、指標サマリ）で始め、ユーザー認証と複数端末からの閲覧が要件になった時点で Supabase へ移す。ジョブ表は最初から「id / status / created_at / input_key / output_keys / metrics_json / error」の形にしておけば移行は SQL 1 本で済む。

---

## 5. 推奨構成と導入順序

```
 [iPhone / PC ブラウザ]  ski-posture.html（GitHub Pages、現行 MediaPipe 版は即時プレビュー用に残す）
        │ 1. POST /jobs（動画メタ）            ▲ 6. GET /jobs/{id} → 署名付き URL で結果取得
        ▼                                     │
 [FastAPI（常時起動の小さな CPU ホスト、SQLite）]
        │ 2. 署名付き PUT URL を返す ──▶ ブラウザが動画を R2 へ直接アップロード（200 MB）
        │ 3. RunPod /run に {job_id, input_key} を投げる
        ▼
 [RunPod Serverless ワーカー（24 GB 階層、Docker、rtmlib + onnxruntime-gpu + FFmpeg）]
        │ 4. R2 から動画取得 → デコード → RTMDet-m → ByteTrack → RTMPose-m Halpe26
        │    → 板/ブーツ検出（フェーズ 3 で追加）→ 指標計算（監査 §5 の 2D 指標）
        │    → JSON/CSV + オーバーレイ mp4 を R2 へ PUT
        ▼ 5. 完了を FastAPI へ Webhook（または FastAPI が /status をポーリング）
 [Cloudflare R2]  入力 30 日 / 出力 30 日のライフサイクル削除
```

**段階的な導入順序**

1. **ローカル検証（GPU 不要、1 週間）**: rtmlib + onnxruntime（CPU）で RTMDet-m → RTMPose-m Halpe26 を手元の動画に通し、現行 HTML の指標計算（`computeMetrics`）を Python に移植。出力 JSON の形式をここで固定する。
2. **Modal で GPU 動作と所要時間の実測（$30 クレジット内）**: 同じコードを Modal 関数にして、§2 の表を実測値で埋める。ここで「稼働秒のどこが長いか」を確認し、NVENC と並列デコードの要否を決める。
3. **FastAPI + R2 + SQLite の骨格**: 署名付き URL でのアップロード、ジョブ表、結果取得 API。GitHub Pages 側に「サーバー解析」ボタンを追加し、MediaPipe 版はフォールバックとして残す。
4. **RunPod Serverless へ本番配置**: Docker 化（CUDA ランタイム + onnxruntime-gpu + FFmpeg）、モデルはイメージに同梱（合計 200 MB 未満なので network volume 不要）。GPU 優先順位を L4 → A5000 → 3090 に設定し、execution timeout を 10 分、idle timeout を 5 秒のままにする。
5. **板・ブーツ検出の追加（フェーズ 3）**: 現場動画からの切り出しとアノテーション（監査 §4 の手順）を進め、RTMDet-s を RunPod Pod でファインチューニング。推論ワーカーにはモデルファイル差し替えだけで組み込めるよう、検出器をプラガブルにしておく。
6. **運用**: R2 のライフサイクル 30 日、RunPod の支出上限（既定 $80/時 [一次]）を $5/時程度に下げる、ジョブ失敗時の再実行ポリシー、月次で §2 の実測との差分を確認。

**本書で確認できなかった主な事項（導入前に公式ページで確認）**: RunPod Pod の時間単価と Serverless の日本 DC 対応、Modal の料金表とリージョン割増の現行値、Google Cloud 東京の L4/T4 単価、Supabase と Backblaze の料金全文、Ski2DPose の利用条件、Roboflow の各データセットのクラスとライセンス。
