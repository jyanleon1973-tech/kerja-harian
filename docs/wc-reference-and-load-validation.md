# WC 参考映像・文献と荷重推定の検証方法（SL・GS）

作成日: 2026-11-01　関連: `docs/load-vector-plan.md`（荷重ベクトル可視化の分類と改修計画。本書はその §6「検証方法」の詳細版）

## 0. 本書の位置づけと調査上の注意

- 目的は、単眼動画解析アプリに「荷重の方向と強弱の矢印」を加える前に、(1) 分析手法の参考になる公開映像を整理し、(2) 映像の権利関係を確認し、(3) 公開文献で分かっている SL・GS の力学と、映像から近似できる量・できない量を切り分け、(4) 実測センサーによる検証計画を用意することである。
- 本書の調査は Web 検索と一部ページの取得で行った。この環境からは YouTube・fis-ski.com・EPFL・PMC・各センサーメーカーの公式ページ本体を直接取得できなかった（ネットワーク制限）ため、該当箇所は検索結果の表示（タイトル・抜粋）に基づく。**動画は一本も視聴していない**。映像の内容・撮影方向・スロー有無は、タイトルや説明文から読み取れた範囲だけを書き、それ以外は「不明」「未確認」とした。
- 「推測」と書いた数値は、文献の設計を参考にした本書の提案値であり、実測や規格ではない。

## 1. 参考映像リスト（SL・GS のみ）

用途はすべて「**分析手法の検討のための閲覧**」に限る。学習データ・評価データには使わない（理由は §2）。FIS 公式サイト（fis-ski.com）のニュース／ビデオページは FIS Alpine の YouTube クリップを埋め込んだ公式配信点なので、YouTube の直接 URL が確認できなかったものは fis-ski.com 側の URL を記した。放送由来のハイライトは一般に複数カメラの切替で構成されるため、撮影方向は「不明（混合）」としている。

| # | URL | 公開者 | 種目 | 撮影方向 | スロー | 用途（分析手法の参考） |
|---|---|---|---|---|---|---|
| 1 | https://www.fis-ski.com/alpine-skiing/news/2023-24/odermatt-delivers-giant-slalom-masterclass-at-val-d-isere-audi-fis-alpine-world-cup-23-24-pfspybiuibg | FIS（FIS Alpine クリップ埋め込み） | GS 男子（Val d'Isère 2023-12） | 不明（混合） | 未確認 | GS の中盤内傾・切り替えの見え方の確認 |
| 2 | https://www.fis-ski.com/alpine-skiing/news/2023-24/highlights-women-giant-slalom-tremblant-2023-audi-fis-alpine-world-cup-23-24-ia5_6gmucqg | FIS | GS 女子（Tremblant 2023-12） | 不明（混合） | 未確認 | 女子 GS の姿勢・ターン弧の参考 |
| 3 | https://www.fis-ski.com/alpine-skiing/news/2023-24/shiffrin-notches-record-extending-95th-world-cup-win-audi-fis-alpine-world-cup-23-24-do4obboqmmu | FIS | SL 女子（種目は本文未確認。95 勝目は SL と報道） | 不明（混合） | 未確認 | SL の切り替え頻度・上体の安定の参考 |
| 4 | https://www.fis-ski.com/alpine-skiing/news/2021-22/slalom-women-killington-1st-run-fis-alpine-lnsqic2n7gw | FIS | SL 女子（Killington 1 本目） | 不明（混合） | 未確認 | 同一セットでの選手間比較の構図 |
| 5 | https://www.fis-ski.com/alpine-skiing/news/2018-19/highlights-vlhova-edges-shiffrin-in-slalom-opener-at-levi-fis-alpine-44hrg2vkyay | FIS | SL 女子（Levi 2018） | 不明（混合） | 未確認 | 緩斜面 SL の参考 |
| 6 | https://www.fis-ski.com/alpine-skiing/news/2018-19/highlights-hirscher-storms-back-to-win-in-giant-slalom-at-beaver-fis-alpine-003fl8vmfoe | FIS | GS 男子（Beaver Creek 2018） | 不明（混合） | 未確認 | 急斜面 GS の参考 |
| 7 | https://www.fis-ski.com/alpine-skiing/news/2018-19/the-perfect-turn-by-ted-ligety-xok3hkzp3mc | FIS（2019-03 公開） | GS（1 ターンの技術クリップ） | 不明 | 未確認 | 1 ターンを分解して見る教材的クリップ |
| 8 | https://www.fis-ski.com/alpine-skiing/video/2026-03/scheib-brings-giant-slalom-crystal-globe-back-to-austria-after-10-years-highlights-154878473127204 | FIS | GS 女子（2026-03 ハイライト） | 不明（混合） | 未確認 | 直近シーズンの GS 用具・姿勢の参考 |
| 9 | https://www.youtube.com/watch?v=86yO2weaGWM | FIS Alpine（検索結果の表示より。未確認） | SL 男子（Alta Badia） | 不明（混合） | 未確認 | 急な切り替えの連続部分の参考 |
| 10 | https://www.youtube.com/watch?v=ekUpd7nGih0 | FIS Alpine（同上。未確認） | SL 男子（Schladming、Kristoffersen 5 勝目） | 不明（混合） | 未確認 | ナイター照明下の映像品質の確認 |
| 11 | https://www.youtube.com/watch?v=qJm5rA_sqfY | FIS Alpine（同上。未確認） | GS 女子（Sölden 開幕戦、Moltzan 初優勝） | 不明（混合） | 未確認 | 最新 GS の参考 |
| 12 | https://www.youtube.com/watch?v=hiJKNxZzHKw | FIS Alpine（同上。未確認） | GS 男子（Sölden 2025/26 開幕戦） | 不明（混合） | 未確認 | 氷河の硬い雪面での GS |
| 13 | https://www.youtube.com/watch?v=LPlj_nDK8iY | FIS Alpine（同上。未確認） | GS 男子（Adelboden） | 不明（混合） | 未確認 | 急斜面 GS の内傾・脚の伸展 |
| 14 | https://www.youtube.com/watch?v=VLOkSOVEsf4 | FIS Alpine（同上。未確認） | GS 男子（Copper Mountain） | 不明（混合） | 未確認 | ミス（スキーアウト）直前の姿勢の参考 |
| 15 | https://www.youtube.com/watch?v=A2ZF9pF2g9Q | FIS Alpine（同上。未確認） | GS 女子（Sara Hector） | 不明（混合） | 未確認 | 女子 GS の参考 |
| 16 | https://www.youtube.com/watch?v=HaeI4dG78T8 | 未確認（タイトルは FIS 形式「Highlights Women Giant Slalom Solden 2023 I Audi FIS Ski Alpine World Cup」） | GS 女子（Sölden 2023） | 不明（混合） | 未確認 | 同上 |
| 17 | https://www.youtube.com/watch?v=DwkjFObOrdw | 未確認 | SL 男子（Kitzbühel 2024） | 不明（混合） | 未確認 | 急斜面 SL の参考 |
| 18 | https://www.youtube.com/watch?v=NvEgkjJXl7U | 未確認 | GS（タイトル「Slow motion giant slalom … technique」） | 不明 | あり（タイトルより） | スロー映像でのエッジ切り替え・脚の屈伸の観察手順の検討 |
| 19 | https://www.youtube.com/watch?v=XgtFgXKTLks | 未確認（説明文では Schladming の WC ファイナルで撮影とされる） | SL・GS 女子 | 不明 | あり（10% 超スロー、説明文より） | 同上。高フレームレート時の関節追跡の難しさの確認 |
| 20 | https://www.youtube.com/watch?v=t36ufnNFSSM | 未確認（Ted Ligety の follow cam、2020） | GS（トレーニング） | 背面（追尾。タイトルの follow cam から推定） | 未確認 | 追尾カメラ（カメラ動作あり）での解析上の問題の確認 |

備考: 公開者が「未確認」の行は、YouTube を開けなかったためチャンネル名を確認できていない。導入前に各動画ページでチャンネル名と「ライセンス」欄（標準 YouTube ライセンスか CC BY か）を確認すること。#20 のように競技者本人または第三者が公開した訓練映像は、FIS 映像とは権利者が異なる。

## 2. 著作権・利用規約の整理

### 2.1 YouTube 利用規約

- YouTube 利用規約（2022-01-05 版の各国版を検索結果で確認。最新版は https://www.youtube.com/t/terms で要確認）は、「サービスまたはコンテンツのいかなる部分も、(a) サービスが明示的に許可する場合、(b) YouTube および該当する権利者から事前の書面による許可を得た場合を除き、**アクセス、複製、ダウンロード、配信、送信、放送、表示、販売、ライセンス供与、改変、修正、その他の方法で使用してはならない**」と定める。あわせて「ボット・スクレイパー等の自動化された手段によるアクセスの禁止（robots.txt に従う公開検索エンジンと書面許可を除く）」「コンテンツの複製を防ぐ機能の回避禁止」「**個人的・非商業的な目的以外での視聴の禁止**」がある。
- したがって yt-dlp 等でのダウンロードは、ダウンロードボタンが提示される場合や YouTube Premium のオフライン保存を除き、規約違反になる。CC BY で公開された動画でも、YouTube の規約上のダウンロード制限は別途かかる（CC ライセンスは著作権の許諾であって、プラットフォーム規約の免除ではない）。
- AI 学習について: 2024 年に YouTube の CEO が「YouTube 動画で AI を学習させることは規約の明確な違反」と述べたと報じられている。2024-12 以降、YouTube は制作者向けに「第三者による AI トレーニング」設定（https://support.google.com/youtube/answer/15509945 ）を用意し、**既定はオフ**、制作者が許可した企業にのみ YouTube が動画を共有する仕組みとした。したがって個別の動画をスクレイピングして学習に使う経路は公式には存在しない。

### 2.2 FIS 映像の権利

- FIS ワールドカップの国際メディア権は Infront が集約的に管理している（2025-09 の FIS–Infront 合意の報道。スイス、2027 年までのオーストリア国内等は別契約）。FIS 公式 YouTube のクリップも Infront の制作部門が製作している（2013 年の発表）。
- FIS は選手・各国連盟向けに「FIS Content Exchange Platform」の利用規約（2025-10 版、スイス法準拠）を定め、登録・同意のうえで競技映像をダウンロードさせている。一般公開の利用規約ではなく、学習利用を許す条項があるかは**未確認**。
- 結論として、FIS 公式チャンネルの映像の権利者は FIS／Infront（および開催国の放送局）であり、YouTube での標準ライセンス配信は「視聴」の許諾に過ぎない。

### 2.3 「閲覧して分析手法を検討する」と「学習データに組み込む」の違い

| 行為 | 必要なもの | 評価 |
|---|---|---|
| YouTube 上でストリーミング視聴し、観察項目・UI の設計を検討する | なし（通常の視聴。ただし YouTube 規約は「個人的・非商業的」視聴を想定しているので、業務での閲覧も「ダウンロードしない・再配布しない」範囲に留める） | 可 |
| 静止画キャプチャを社内資料に貼る | 権利者の許諾（引用の要件を満たす場合は著作権法 32 条の引用で可。出所明示、必要最小限、主従関係） | 条件付き |
| 動画をダウンロードして姿勢推定を走らせ、手法の挙動を確認する | YouTube 規約上はダウンロード自体が不可。日本の著作権法 30 条の 4（情報解析）が著作権侵害を否定しうるとしても、**規約違反（契約上の問題）は別** | 不可（規約） |
| 動画やキャプチャを学習・評価データに組み込み、製品に反映する | (1) YouTube の書面許可または制作者の第三者 AI トレーニング許可、(2) 権利者（FIS／Infront・放送局）とのデータ利用ライセンス、(3) 映っている選手の肖像・パブリシティに関する同意（国・用途による）、(4) 学習済みモデルの配布形態に応じた条件 | 許諾なしでは不可 |

- 日本法について: 著作権法 30 条の 4 第 2 号は「情報解析（多数の著作物から言語・音・影像等の要素に係る情報を抽出し、比較、分類その他の解析を行うこと）」を享受目的でない利用として許容する（e-Gov 法令検索: https://elaws.e-gov.go.jp/document?lawid=345AC0000000048 ）。文化庁「AI と著作権に関する考え方について」（2024-03、https://www.bunka.go.jp/seisaku/chosakuken/aiandcopyright.html ）はただし書き（権利者の利益を不当に害する場合）の解釈を示している。しかし、**利用規約で禁じられたダウンロードを 30 条の 4 が正当化するわけではなく**、規約と権利制限規定の優劣（オーバーライド問題）は結論が確定していない。製品に組み込む用途では、権利者からの許諾を前提にする。

### 2.4 代替となる公開データセット

| データセット | 内容 | 入手条件 | ライセンス |
|---|---|---|---|
| Ski2DPose（EPFL CVLab; Bachmann et al. 2019） https://www.epfl.ch/labs/cvlab/data/ski-2dpose-dataset | 1,982 フレームの手作業 2D 関節アノテーション。元映像は YouTube で CC ライセンス公開されていた 16 本のアルペン動画（論文記載）。画像・ラベル・元 MP4 をページから配布 | ページからダウンロード。論文の引用を要請 | **未確認**（ページ本体を取得できず。元動画の CC 条件と配布条件を導入前に確認） |
| SkiPose-PTZ（EPFL CVLab; Rhodin et al. CVPR 2018） https://www.epfl.ch/labs/cvlab/data/ski-poseptz-dataset/ | 競技 SL をパン・チルト・ズーム複数カメラで撮影。約 2 万枚の画像に 3D 姿勢、2D 投影、フレーム毎のカメラ校正 | **申請制**。J. Spörri と H. Rhodin に連絡し、研究目的を記載 | 公開ライセンスなし（方法論研究目的での提供）。**商用利用の可否は未確認** |
| Injury Ski I / II（Innsbruck; Zwölfer et al. 2021 arXiv 2112.12193 / 2023 Sci Rep 10.1038/s41598-023-47875-2） https://sport1.uibk.ac.at/mz/cv | 転倒・受傷場面を含むアルペン競技の 2D 関節アノテーション（I: 533 枚、II: 930 枚追加） | 公開とされる（Innsbruck のページ） | **未確認** |
| SkiTB（Udine; Dunnhofer et al. WACV 2024 / CVIU 2024） https://github.com/matteo-dunnhofer/SkiTB-toolkit | 放送映像 300 本（AL・JP・FS 各 100、39.2 万フレーム）。アノテーションは**バウンディングボックス**のみで姿勢はない | Microsoft Forms で申請 | アノテーションとコードは **CC BY-NC 4.0**（README で確認）。フレーム画像自体の権利は放送局側にあり**未確認** |

いずれも「研究目的・非商用」か「条件未確認」であり、製品モデルの学習にそのまま使える保証はない。製品用途では、自前で撮影し同意を得た映像（§4）を主データとし、公開データセットは手法の予備検証に限定する。

## 3. SL・GS の技術で映像から時系列で観察すべき項目

### 3.1 ターン局面の定義（文献）

- Spörri et al. 2012（Int J Sports Sci Coach 7(4):647–660, doi:10.1260/1747-9541.7.4.647）は GS のターンを重心（COM）の進行方向に基づき **Initiation → COM Direction Change I → COM Direction Change II → Completion** に分けた。多くの後続研究（Spörri 2016 BJSM など）がこの定義を踏襲している。
- Supej 2008（J Appl Biomech 24(2):121–129）は WC SL の 3D 計測から、重心高度に対する比力学的エネルギーの微分（差分比力学的エネルギー）を局面ごとの質指標として提案した。
- Reid 2010（NIH 博士論文 https://nih.brage.unit.no/nih-xmlui/handle/11250/171325 ）、Reid et al. 2020（Front Sports Act Living, doi:10.3389/fspor.2020.00025）は SL の 3D 計測で板のエッジ角・迎え角・ターン弧を局面別に記述している。

アプリ側のターン局面は、重心の左右移動のゼロ交差（切り替え）を基準に上記 4 局面へ対応づけると文献と比較しやすい。

### 3.2 観察項目と単眼映像での近似

| 項目 | 公開文献で分かっていること（出典） | 単眼映像のどの観測量で近似するか | 近似の限界 |
|---|---|---|---|
| ターン前半（Initiation）の姿勢 | Spörri 2012 BJSM（46:1072, doi:10.1136/bjsports-2012-091425）: ゲート横幅を広げると内傾が増し、ゲート通過後に前後位置が後ろ寄りになる傾向。Falda-Buscaiot 2017（PLoS ONE, doi:10.1371/journal.pone.0176975）: 力は第 2 操舵相と急斜面で大きい | 体幹角・下腿角（側面・正面）、重心の板に対する前後位置（側面）、切り替え直後の重心—支持点の水平距離 | 前後位置は側面カメラ以外では信頼できない。カメラ俯角で傾きの絶対値がずれる |
| 中盤の最大内傾 | 準静的なカービングでは傾き角 φ、速度 v、ターン半径 R が tan φ ≈ v²/(gR) で結びつく（Jentschura & Fahrbach 2004, arXiv:physics/0310086; Komissarov 2018, arXiv:1812.02539）。Spörri 2016 BJSM（50:14, doi:10.1136/bjsports-2015-095737）: サイドカット半径を変えてもエッジ角は変わらず、GRF の差は重心ターン半径の差で説明された | 重心と支持点（ブーツ中点）を結ぶ線の画像鉛直に対する角度（正面・背面）、その最大値の時刻 | 画像の鉛直 ≠ 重力方向（斜度・俯角）。エッジ角（板と雪面の角）は内傾角と一致しない（アンギュレーション）。斜め方向からは過小・過大評価 |
| 後半の脚の伸展・屈曲 | Spörri 2016 OJSM（4(2), doi:10.1177/2325967116630719）: SL は GS よりターンが短く、ゲート通過後の体幹屈曲が小さく、総 GRF ピークが大きい傾向。Kröll 2015 ISBS: 平均 GRF は GS > SL、最大値は同程度（1 名の事例） | 外脚・内脚の膝屈曲角と角速度、股関節高さの変化 | 2D 関節角は面外回転で歪む。雪煙・ゲートで膝・足首が隠れる |
| 切り替え時の重心移動 | Fasel 2016（Remote Sens 8:671, doi:10.3390/rs8080671）: dGNSS + IMU で重心位置を精度 0.08 m、速度 0.04 m/s で推定。Gilgien 2013（Sensors 13:9821, doi:10.3390/s130809821）: 1 台の dGNSS から GRF・雪面摩擦・空気抵抗を推定、GRF 誤差 −26 ± 152 N | 推定重心の左右位置の時系列と板の中点との交差時刻、重心の水平移動速度 | 固定カメラでなければ「見かけの移動」。重心は質量比モデルの推定で、装備・前傾で誤差 |
| 外脚と内脚 | Falda-Buscaiot 2017: 外足の法線方向力が内足より大きく、外足が操舵、内足は安定の役割。文献値として内足 0.2 BW〜外足 1.2–2 BW の範囲が引用されている。Nakazato 2011（JSSM 10:754）、Stricker 2010（EJSS 10, doi:10.1080/17461390903108141）: インソールは力板より過小評価（1 名で内足 54%、外足 21%） | ターン方向から外脚・内脚を判定し、両膝の屈曲差、両脚の開き、重心から各ブーツまでの距離 | **荷重配分そのものは決まらない**。姿勢が同じでも配分は変えられる（内脚荷重を意図的に増やす技術）。モード B の検証対象 |
| 上体と骨盤 | Spörri 2016 OJSM: 仙骨と胸骨の IMU で、GS・SL とも荷重相で前屈・側屈・回旋の複合が生じる。Supej 2020（Appl Sci 10:7288, doi:10.3390/app10207288）: 下腿角と外脚股関節屈曲の非対称がパフォーマンスの非対称と最も関連 | 肩線と骨盤線の角度差（正面・背面）、体幹の側屈角、肩—骨盤の回旋差 | 骨盤の 2D 推定は精度が低い。回旋は正面・背面以外で読めない |
| 板の方向変化 | Spörri 2016 BJSM: ski turn radius とスキッド角を 3D で算出。Reid 2020: SL のエッジ角・迎え角の局面変化 | 板（トップ・テール）の画像上の向きとその角速度、ターン弧の曲率 | 板検出は現状不安定（`load-vector-plan.md` §2B）。遠近で向きが歪む。スキッド角は 3D なしでは出ない |
| 左右差 | Supej 2020: 9 名の SL で、技術・GRF の左右非対称がターン半径・パフォーマンスの非対称に影響。Ogrin 2021（Front Physiol 12:577698）: GRF の左右差は筋力の左右差とは一致しない | 左ターン・右ターンで同じ指標（内傾、膝屈曲、切り替え時間）を分けて集計 | 片側のカメラでは左右ターンで見え方が違うため、撮影方向を揃えないと差の原因が技術かカメラか区別できない |
| エッジ切り替えのタイミング | Martínez 2019（Sensors 19:902, doi:10.3390/s19040902）: ブーツ IMU の角速度（3 Hz フィルタ）で切り替え検出、精度約 0.06 s。2021 Sensors の比較では映像（Klous）、インソール（Spörri）、ブーツ IMU、Yamagiwa IMU の方法が高精度。Frontiers 2020（doi:10.3389/fspor.2020.00002）: 力板とインソールで切り替え検出を比較 | 重心—支持点線が鉛直を横切る時刻、両板の向きが揃う時刻、膝屈曲の左右反転 | 映像のフレームレート（30 fps なら ±33 ms）が精度の下限。雪面に近い部位の遮蔽 |
| 荷重が増減すると推測される局面 | Falda-Buscaiot 2017: 第 2 操舵相（フォールライン後）と急斜面で力が大きい。Spörri 2012 BJSM: ターン終盤で力が有意に大きい。Supej 2015（IJSPP 10:361, doi:10.1123/ijspp.2014-0200）: 急斜面で GRF ピークが特定局面に集中する傾向（P = .06） | 重心の鉛直方向の加速（屈曲→伸展の反転）、内傾角と推定速度・曲率から求める見かけの遠心加速度 | 加速度の 2 階微分はノイズが大きい。空気抵抗・雪面摩擦・雪面の反発（吸収）は映像から出ない。「増減の傾向」までで、大きさ（N、BW）は出せない |

## 4. 荷重推定の検証方法の提案

### 4.1 基準となる実測手段

| 手段 | 製品・仕様（公式ページ／文献） | 測れる量 | 注意 |
|---|---|---|---|
| 圧力インソール | **Moticon OpenGo**（https://moticon.com/opengo/sensor-insoles ）: 1 足 16 個の静電容量式圧力センサー、分解能 0.25 N/cm²、サンプリング 10/25/50/100 Hz、6 軸 IMU、内蔵メモリでスタンドアロン記録。**novel pedar**（https://novel.de/products/pedar/ ）: 1 足 99 個の静電容量式センサー、最大 400 Hz、Bluetooth で PC へ。同社 loadsol は 1〜3 センサーで足底法線力のみ（最大 200 Hz）。**XSENSOR Intelligent Insoles Pro**（https://www.xsensor.com/solutions-and-platform/human-performance/gait-motion-insoles ）: 最大 235 センセル、精度 ±5% FS、0.7–88.3 N/cm²、150 Hz、IMU 内蔵 | ブーツ内の足底圧分布、その総和（足底法線力）、COP | 剪断力は測れない。ブーツのシェル・カフを通る力は足底に出ないため総和は GRF を過小評価（Stricker 2010、Nakazato 2011）。左右比・時系列の形の検証には使えるが絶対値の基準にはしにくい |
| 力センサー付きビンディング（研究用） | 板とビンディングの間に Kistler 製 3 分力圧電式ダイナモメーターをトウ・ヒール各 1 枚（Nakazato 2011、Stricker 2010: 低負荷域で誤差 4.6%、292 N 超で 0.3%）。Meyer 2019（Sensors 19:4324, doi:10.3390/s19194324）: ブーツとビンディングの間に収める 6 軸ダイナモメーター、誤差 1.3–12.8%。Kistler 公式のスキー向け製品ページは**未確認** | 3 方向の力とモーメント（ブーツ—板間） | 市販品はなく研究機関との共同が前提。板の撓みの影響、温度ドリフトのため測定前後でゼロ合わせが必要 |
| 外力の間接推定 | dGNSS（Gilgien 2013）、dGNSS + IMU（Fasel 2016） | 重心軌跡から総 GRF・摩擦・空気抵抗 | 左右配分は出ない。高価で大掛かり |

**推奨**: 第 1 段階は圧力インソール（左右比と時系列形状の検証）。片足ずつ総和を出す点で Moticon OpenGo（IMU 内蔵、ケーブルレス、100 Hz）か pedar（空間分解能が高い、400 Hz）。第 2 段階で、絶対値（BW）の検証が必要になれば力センサー付きビンディングを研究機関と共同で用いる。

### 4.2 同期方法

- **LED フラッシュ**: カメラ画角内に置いた LED を、インソールのロガー（または IMU）へ同時に電気トリガを送る回路で点灯させる。映像側はフレーム、センサー側はイベント列で一致点を得る。最も確実。
- **動作イベント**: スタート前に両足で雪面を強く踏む／ジャンプする。映像の重心鉛直加速と足底力のピークを相互相関で合わせる。機材不要だが精度は 1 フレーム程度。
- **音**: スタートゲートの発信音（またはクラッカー）をカメラのマイクと、音を拾える IMU／録音機で記録。距離による音の遅れ（約 3 ms/m）を補正する。
- **タイムコード**: GNSS の UTC（PPS）を持つロガーとカメラ（タイムコード入力対応機）で絶対時刻を揃える。複数カメラのときに有用。
- 検証では最低 2 方法を併用し、同期誤差を記録する（推測: ±1 フレーム以内が目標）。

### 4.3 試技数とデータ量の目安（推測）

文献の規模: Spörri 2016 OJSM は 10 名 × 240 ターン（GS・SL 各 2 セット）、Falda-Buscaiot 2017 は 11 名、Supej 2020 は 9 名 × 20 旗門。これを踏まえた本書の提案値は次のとおり。

- 被験者: 8〜12 名（SL・GS 両方を滑れる FIS ポイント保持者または同等レベル）。左右差の解析には同一人物の左右ターンが必要。
- コース: SL・GS 各 1 セット以上、緩斜面と急斜面を含む（斜度で荷重局面が変わるため）。
- 試技: 1 人あたり各種目 6 本以上、1 本あたり解析ターン 10〜20。合計 1,000 ターン以上（モデルの当てはめ 70%、検証 30% に分ける）。
- 撮影: 正面・側面・背面のうち少なくとも 2 方向を固定三脚で同時撮影、60 fps 以上（120 fps 推奨）、1080p 以上、シャッター 1/1000 s 以上。カメラ位置・雪面の校正点（ゲート位置、ストック長）を記録。
- センサー: インソール 100 Hz 以上、IMU 同時記録、各本の前後で静止立位（体重校正）を記録。

### 4.4 評価指標

| 指標 | 定義 | 判定の目安（推測） |
|---|---|---|
| 左右荷重比の時系列相関 | ターンを 0–100% に時間正規化し、アプリの「左右荷重傾向スコア」と実測の左右比（外足力 ÷ 両足合計）のピアソン相関と一致相関係数（CCC）をターン毎に算出、中央値と四分位で報告 | 中央値 r ≥ 0.7 で「傾向表示」可。r < 0.5 の局面では矢印を出さない |
| ピークのタイミング誤差 | 実測の外足力ピーク時刻とアプリ推定ピーク時刻の差（ms とターン周期の %） | 絶対誤差の中央値 ≤ 50 ms（または周期の 5%） |
| ターン局面ごとの一致率 | 4 局面（Initiation / Change I / Change II / Completion）の荷重増減の符号（増・減・保持）が実測と一致した割合、Cohen の κ | 一致率 ≥ 80%、κ ≥ 0.6 |
| 切り替え検出誤差 | 実測（両足力の交差）とアプリ（重心—支持点線の鉛直交差）の時刻差 | 中央値 ≤ 2 フレーム。Martínez 2019 の IMU 精度 0.06 s を参考値とする |
| 大きさの Bland–Altman | （力センサー付きビンディングがある場合）推定 GRF（BW）と実測の差の平均と一致限界 | 限界 ±0.3 BW 以内でなければ数値表示をしない |
| 撮影条件別の層別 | 上記を撮影方向、斜度、種目、左右ターン、選手別に層別 | 条件により成績が落ちる場合は、その条件で機能を無効化 |

### 4.5 研究倫理・同意

- 人を対象とする研究として、所属機関または第三者の倫理審査委員会の承認を得る（引用文献はいずれもヘルシンキ宣言に沿った承認と同意を記載している）。
- 書面のインフォームド・コンセント: 計測内容、映像と足底圧データの保存期間・用途（アプリの検証・学習）、第三者提供の有無、公開時の匿名化、撤回の自由。未成年は保護者の同意と本人のアセント。
- 映像は顔・ゼッケンを含むため個人情報保護法および撮影国の法令に従う。選手が所属するチーム・連盟の規定（映像の二次利用）も確認する。
- 競技用具を改造（力センサー付きビンディング）する場合は、安全性（解放値、プレート高さ）の確認と、試技中の転倒リスクの説明を行う。
- データは測定値と推定値を分けて保存し、推定値を「実測」と表示しない（`load-vector-plan.md` §0）。

## 5. 映像から推定できる量 / できない量

| 量 | 単眼動画のみ | 校正・3D 復元があれば | センサーが必要 | 理由 |
|---|---|---|---|---|
| 身体重心の移動方向 | **可（画像上の方向）**。固定カメラまたはカメラ動作補正が前提 | 可（コース座標での方向と速さ） | 不要 | 関節位置と質量比モデルで重心を推定し時間微分する。追尾カメラでは見かけの移動になる |
| 身体重心の加速度 | 条件付き（向きの傾向のみ。2 階微分でノイズが大きい） | 可（m/s²。Fasel 2016 の dGNSS + IMU 相当の精度は単眼では出ない） | 高精度が要るなら dGNSS／IMU | 画素座標の加速度は距離・俯角で物理量に換算できない |
| 重力方向 | 不可（画像の鉛直で代用。斜度・カメラ俯角により数度〜十数度ずれる） | 可（雪面線・鉛直基準の校正） | 不要 | 斜面上では画像の縦軸と重力が一致しない |
| 雪面からスキーへの接触反力 | **不可** | 条件付き（質量、重心の 3D 加速度、重力、空気抵抗・摩擦の仮定から総 GRF を逆算。Gilgien 2013 で誤差 −26 ± 152 N） | 可（力センサー付きビンディング） | 単眼では加速度の大きさが出ず、外力の分解もできない |
| スキーから雪面への力 | **不可** | 同上（接触反力の反作用） | 可（同上） | 同上 |
| 左右荷重配分 | **不可**（内傾・膝屈曲と相関はあるが配分は一意に決まらない） | **不可**（総和が分かっても左右への分配は運動学から決まらない。不静定） | 可（圧力インソール、左右の力センサー） | 同じ姿勢でも内脚荷重を変えられる。文献でも配分の計測は常にインソールか力板（Falda-Buscaiot 2017、Nakazato 2011） |

**実装上の結論**: 単眼映像だけで出してよいのは「重心の移動方向と速さ」「姿勢・関節角・切り替え時刻」であり、荷重の矢印は §4 の検証で左右比の相関と局面一致率が目安を満たした条件でのみ「推定・未検証／検証済み」のラベル付きで表示する。接触反力の大きさ（N・BW）は、3D 復元と校正があっても仮定に依存し、左右配分はセンサーなしでは表示しない。

## 参考文献（URL）

- Spörri J, Kröll J, Schwameder H, Müller E. Turn characteristics of a top world class athlete in giant slalom. Int J Sports Sci Coach 2012;7(4):647–660. https://doi.org/10.1260/1747-9541.7.4.647
- Spörri J, Kröll J, Schwameder H, Schiefermüller C, Müller E. Course setting and selected biomechanical variables related to injury risk in alpine ski racing: an explorative case study. Br J Sports Med 2012;46:1072–1077. https://bjsm.bmj.com/content/46/15/1072
- Spörri J, Kröll J, Gilgien M, Müller E. Sidecut radius and the mechanics of turning. Br J Sports Med 2016;50:14–19. https://bjsm.bmj.com/content/50/1/14
- Spörri J, Kröll J, Fasel B, Aminian K, Müller E. Course setting as a prevention measure for overuse injuries of the back in alpine ski racing. Orthop J Sports Med 2016;4(2). https://journals.sagepub.com/doi/10.1177/2325967116630719
- Supej M. Differential specific mechanical energy as a quality parameter in racing alpine skiing. J Appl Biomech 2008;24(2):121–129. https://doi.org/10.1123/jab.24.2.121
- Supej M, Kipp R, Holmberg HC. Mechanical parameters as predictors of performance in alpine World Cup slalom racing. Scand J Med Sci Sports 2011;21(6):e72–e81. https://doi.org/10.1111/j.1600-0838.2010.01159.x
- Supej M, Hébert-Losier K, Holmberg HC. Impact of the steepness of the slope on the biomechanics of World Cup slalom skiers. Int J Sports Physiol Perform 2015;10(3):361–368. https://doi.org/10.1123/ijspp.2014-0200
- Supej M, Ogrin J, Šarabon N, Holmberg HC. Asymmetries in the technique and ground reaction forces of elite alpine skiers influence their slalom performance. Appl Sci 2020;10(20):7288. https://www.mdpi.com/2076-3417/10/20/7288
- Hébert-Losier K, Supej M, Holmberg HC. Biomechanical factors influencing the performance of elite alpine ski racers. Sports Med 2014;44:519–533. https://doi.org/10.1007/s40279-013-0132-z
- Reid RC. A kinematic and kinetic study of alpine skiing technique in slalom. 博士論文, Norwegian School of Sport Sciences, 2010. https://nih.brage.unit.no/nih-xmlui/handle/11250/171325
- Reid RC, Haugen P, Gilgien M, Kipp RW, Smith GA. Alpine ski motion characteristics in slalom. Front Sports Act Living 2020;2:25. https://doi.org/10.3389/fspor.2020.00025
- Gilgien M, Spörri J, Chardonnens J, Kröll J, Müller E. Determination of external forces in alpine skiing using a differential global navigation satellite system. Sensors 2013;13(8):9821–9835. https://doi.org/10.3390/s130809821
- Fasel B, Spörri J, Gilgien M, et al. Three-dimensional body and centre of mass kinematics in alpine ski racing using differential GNSS and inertial sensors. Remote Sens 2016;8(8):671. https://doi.org/10.3390/rs8080671
- Kröll J, Spörri J, et al. Kinetic and kinematic comparison of alpine ski racing disciplines as a base for specific conditioning regimes. ISBS Proceedings 2015. https://ojs.ub.uni-konstanz.de/cpa/article/view/6526
- Falda-Buscaiot T, Hintzy F, Rougier P, Lacouture P, Coulmy N. Influence of slope steepness, foot position and turn phase on plantar pressure distribution during giant slalom alpine ski racing. PLoS ONE 2017;12(5):e0176975. https://doi.org/10.1371/journal.pone.0176975
- Nakazato K, Scheiber P, Müller E. A comparison of ground reaction forces determined by portable force-plate and pressure-insole systems in alpine skiing. J Sports Sci Med 2011;10:754–762. https://www.jssm.org/jssm-10-754.xml-Fulltext
- Stricker G, Scheiber P, Lindenhofer E, Müller E. Determination of forces in alpine skiing and snowboarding: validation of a mobile data acquisition system. Eur J Sport Sci 2010;10. https://doi.org/10.1080/17461390903108141
- Meyer F, et al. Development of a new embedded dynamometer for the measurement of forces and torques at the ski-binding interface. Sensors 2019;19(19):4324. https://www.mdpi.com/1424-8220/19/19/4324
- Martínez A, Jahnel R, Buchecker M, Snyder C, Brunauer R, Stöggl T. Development of an automatic alpine skiing turn detection algorithm based on a simple sensor setup. Sensors 2019;19(4):902. https://doi.org/10.3390/s19040902
- Comparison of force plates and pressure insoles for turn switch detection. Front Sports Act Living 2020. https://www.frontiersin.org/articles/10.3389/fspor.2020.00002/full
- Jentschura UD, Fahrbach F. Physics of skiing: the ideal-carving equation and its applications. 2004. https://arxiv.org/abs/physics/0310086
- Komissarov SS. Modelling of carving turns in alpine skiing. 2018. https://arxiv.org/abs/1812.02539
- Bachmann R, Spörri J, Fua P, Rhodin H. Motion capture from pan-tilt cameras with unknown orientation. 3DV 2019. https://arxiv.org/abs/1908.11676（Ski2DPose）
- Rhodin H, Spörri J, et al. Learning monocular 3D human pose estimation from multi-view images. CVPR 2018. https://arxiv.org/abs/1803.04775（SkiPose-PTZ）
- Zwölfer M, et al. A graph-based approach can improve keypoint detection of complex poses. Sci Rep 2023. https://doi.org/10.1038/s41598-023-47875-2（Injury Ski II）
- Dunnhofer M, et al. Tracking skiers from the top to the bottom. WACV 2024. https://arxiv.org/abs/2312.09723（SkiTB）
- YouTube 利用規約 https://www.youtube.com/t/terms ／ 第三者による AI トレーニング設定 https://support.google.com/youtube/answer/15509945
- FIS Content Exchange Platform Terms of Use（2025-10）https://assets.fis-ski.com/f/252177/x/e85a03289e/21102025-fis-cxp-terms-of-use.pdf
- 文化庁「AI と著作権に関する考え方について」 https://www.bunka.go.jp/seisaku/chosakuken/aiandcopyright.html ／ 著作権法（e-Gov） https://elaws.e-gov.go.jp/document?lawid=345AC0000000048
