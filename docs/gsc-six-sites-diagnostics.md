# 6サイト・検索キーワード／URL登録状態の読み取り専用診断

既存の GSC Six-Site Direct API (Read Only) は6サイトの検索表示・クリック・上位ページを毎週集計する。この追加ジョブは、その結果を変更せずに**原因調査に必要な内訳**だけ収集する。

## 対象

- 6つのURLプレフィックスを厳密一致で確認し、制限付き閲覧ユーザーの権限で読み取る。
- Search Analytics API: 確定データ（太平洋時間の直近3日を除外）で、直近7/28日の検索キーワードと28日の日別表示・クリック。検索キーワードは上位最大1000行の**非網羅的な内訳**。非表示の匿名検索語や低頻度クエリをゼロと見なさず、サイト全体の数値と合算しない。
- URL Inspection API: 6サイトのトップページ／代表比較ページのGoogleインデックスの**保存済みスナップショット**。ライブURLテストではない。verdict、coverageState、クロール時刻、canonical等の証拠を保存する。未取得は未登録と断定しない。
- 対象ページの指定はプログラム内で固定。サイト間のパス混在と、操作・インデックス登録の要求はしない。

## 安全性

- Search Consoleへの書き込み、サイトの公開、タイトル変更、sitemap更新、インデックス登録リクエスト、商品・価格・楽天リンク変更はしない。
- Google OIDC（既存 ga4-readonly-pilot）の読み取り専用権限を使用。秘密鍵JSONは追加不要。
- API失敗は UNAVAILABLE、レスポンス未掲載は NO_ROWS、APIから実測数値が返った場合だけ OBSERVED_ROWS を使用。未取得と実測0回を混同しない。
- 各サイトの一部が失敗してもほかのサイトの根拠は残し、全件成功前にREADYにしない。
- マージ前はPR専用のオフラインテストのみ。人間の承認後にマージし、**月曜日09:45 JST（遅延の可能性あり）**の定期ジョブまたはActionsの手動実行で本番認証を検証する。

## 調査順序

1. 登録状態を調べる（indexed / discovered / crawled but not indexed / unknown）。
2. 検索キーワードと、その語句が実際に表示したページ、ページタイトルの整合性を比較する。検索語が無い場合は不足として扱う。
3. 日用品の既存上位ページ3件と同じ指標で、他サイトのページ別の状況を比較する。
4. 10/12に公開したSEO改善の評価は、新しいデータ期間が十分に含まれてから判断する。

GitHub PagesとSEOの本番コードには触れないため、10/19まで観察する方針と矛盾しない。

## 2026-10-19の追加監査

- `query_pages_28d` は `dimensions: [query, page]` の1回/サイトだけ追加。検索語×表示URL、CTR、平均順位をJSON・Summaryに保存する。サイトの厳密なプレフィックスから外れる行は診断失敗とし、他サイトへ転用しない。
- Googleの返却行はクリック数順で、最大1000行を取得したあと表示回数順に並べる。「全検索語の表示回数上位」とは限らない。1000行到達は `TOP_ROWS_LIMIT_POSSIBLE`。ページングなし。匿名化・少数データの省略は1000行未満でも起こりうる。検索語単独、検索語×ページ、サイト合計を足し合わせない。
- query×pageは負荷の大きい組合せなので28日窓だけ、週1回に制限。Google APIはプロパティ一覧1回、Search Analytics 24回、URL Inspection最大17回。既存集計への追加はなく、診断の従来比は6回増。別途17回の匿名HTTP GETで公開HTMLを確認する。
- URL Inspectionはサイトあたり2,000回/日・600回/分の公式上限に対し2〜4回/サイト。APIの負荷・割当エラーはUNAVAILABLE/PARTIALと非ゼロ終了で残す。無限再試行しない。
- 公開GETにはGoogleのAuthorizedSessionを使わない。200・HTML・リダイレクトなし・2MB以下のページのみGoogle検査へ進む。404/410、リダイレクト、非HTML、通信失敗は未取得とし、未登録とは判定しない。対象の置換を自動で推測せず、明示的な対象修正を促す。
- SummaryにもGoogle/指定canonical、最終クロール、coverage、indexing/robots/fetch状態とAPI失敗理由を残す。HTTP確認はGoogleによるライブURLテストではない。
- 既存集計・新診断とも失敗時にerror annotationとSummaryを残す。artifactアップロード自体の失敗も失敗として扱う。
- 既存日次 `autonomous-health-audit.yml` に既存週次集計の実行履歴監査を追加。schedule/mainのみを判定し、手動成功では代用しない。月曜予定時刻から24時間は遅延猶予、以後欠落・失敗・監査取得失敗で日次ジョブが失敗する。cron時刻自体は変更しない。
- 新診断の初回scheduleの欠落監視は未実装。承認・マージ前の日付を欠落扱いしないため、初回本番実行を確認した後に既存監査へ対象追加する。新診断自体の失敗記録は実装済み。
- 日次監査もGitHub上なのでGitHub全体停止中の外部通知は保証しない。メール/アプリ通知の到達は個人のGitHub設定に依存し未検証。

公式仕様：
- https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- https://developers.google.com/webmaster-tools/limits
- https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs
# STEP23: existing identity, manual five-site GA4 read

The existing manual workflow has an optional `include_five_site_ga4` input
(default false). It calls `ga4_page_diagnostics.py --five-sites`, preserving the
default daily-only report, weekly schedule, OIDC provider/service account,
environment, and permissions. No Google keys or browser login are required.
The food 24-serving guide is now an exact URL Inspection snapshot target.

The optional read uses the existing `analytics.readonly` scope. It checks the
five published Measurement IDs, accessible Admin API account summaries and web
streams, then Data API metadata and site-scoped 7/28 day reports. Admin discovery
is capped at 20 accessible properties. Unrelated account names/default URLs are
not saved. It never changes API enablement, property access, streams or Google
settings. A 429 stops further authenticated reads without retries.

Hostname, full HTTPS page-location prefix and slash-terminated page-path prefix
separate sites; verified stream IDs add a stream filter. The existing shared-ID
property correlation is explicitly labelled when Admin stream verification is
unavailable. Unknown properties are not guessed. Permission denial, disabled
API, missing mapping, empty observed rows and quality-withheld data remain
distinct. Thresholding, sampling, truncation or a non-JST property calendar
withhold counts. Periods end two JST days before execution, allowing latency;
these GA4 windows are not GSC final-data windows.

Session reports are aggregated once per site/channel, not summed across pages.
All-scope, marked-non-operator and marked-operator sessions are separate reports:
their populations can overlap and must not be added/subtracted to infer real
users. Unclassified event flags remain unclassified. Event counts are neither
unique users nor confirmed commissions. The JSON is stored in the existing
diagnostic artifact; there is no new scheduler, issue writer, or publication.

## STEP82（2026-11-03）：比較期間と新規公開URLの欠落を解消

既存キーを保持し、query / query×page / pageを各4期間（直近7日、前7日、直近28日、前28日）で収集する。各リクエストはfinal・最大1000行・ページングなし・再試行なし。1サイト13 Search Analytics取得（以前4）、URL Inspectionは既存18から26URLへ拡張。SOTOJITAKUのURLは変更しない。未返却をゼロ補完せず、異なる窓・集計軸の行を合算しない。

追加対象は洗剤1回費用、幼児食、犬用フード、食品宅配/水比較、きょうボド小学生/ito/デュエット。公開HTMLが取得できないURLはGoogle検査を行わず未取得として保持する。マージ時の対象診断ファイルpushで既存read-onlyジョブを実行し、週次診断も継続する。新たな認証・独立監視・自動SEO変更・登録リクエストは追加しない。GA4は従来通りmanual明示入力時のみ。


## 2026-11-05｜6サイトの検索成長判断を同じ表で確認する

週次`gsc-six-sites-diagnostics.yml`の**既存公式API原本・同一JSON**から、冒頭に6サイト横断の読み取り専用一覧を追加する。別のGSC認証・API・schedule・自動PR作成・SEO本文改変は追加しない。

- **表示／クリック**：`daily_28d`のAPI返却日別行を、同一28日窓内のユニーク日付でのみ足す。`pages_28d`、`queries_28d`、`query_pages_28d`を足した値で**サイト合計を代用しない**。実原本2026-11-03では日用品の日別合計111表示／1クリックとページ別行合計115表示が一致しない。差を勝手に補正しない。
- **欠測**：`NO_ROWS`／`UNAVAILABLE`、期間外日付、重複日付、負値、プロパティ取り違えは**不明**。確認されていない値を0にしない。
- **通常検索語の証拠**：返却クエリ内に`site:`演算子がある行を、購買・娯楽の通常検索意図の証拠から分離。`NO_ROWS`は「不明」であって検索需要ゼロの証拠ではない。APIの検索語は匿名化・省略されるため行数は非網羅。
- **登録状態**：URL Inspectionの保存済みスナップショットで`Submitted and indexed`と`URL is unknown to Google`を対象URL**だけ**で集計。後者はサイト公開失敗の意味ではない。同時の匿名HTTP公開200・正規canonical確認とGoogle登録状態も別々に保持。新規ページ公開直後の`unknown`を勝手にエラーと断定しない。
- **調査対象**：自然語の返却行があり28日表示20回以上なら検索語×表示ページの意図の照合候補。それ以外は「小標本」「検索語が不明」等のラベルに止める。統計的有意差やタイトル修正の許可ではない。
- **公開後評価**：11/03に公開した入口改善の結果は、取得期間に含まれてから判定する。原本as_of=2026-11-02（最終確定10/30）では、11/03以降の成果を判断できない。11/09の結果は暫定確認、11/16以降の確定7日窓で初回反応を見て、28日窓は11/04〜12/01後に別評価する。

テスト`tests/test_gsc_six_sites_scorecard.py`は日別111 vs ページ別999999の非加算、`site:`の隔離、NO_ROWS、期間外、重複、他プロパティ混入、Google未認識と公開200の区別を確認。週次レポート本文以外は書き込まない。


### 2026-11-05追加｜検索語→ランディングページを具体的に追う

スコアカードのサイト別数値の直後に、`query_pages_28d`で**Googleから実際に返ってきた検索語×ランディングページ最大3行/サイト**を表示する。表示・クリック・平均順位は個々の返却行の値であり、サイト合計や匿名化された検索需要を推測した値ではない。返却行はクリック数基準で選択されるため、必ずしも最多表示の全クエリではない。

`site:`・`-site:`演算子付き検索（通常の購買・娯楽ニーズではない）、URL・連絡先・長い数字、HTML風の記号を含む検索語は運用レポートに載せない。異なるプロパティや`../`を含むパス、非実測・無効な指標を除外する。取得失敗・非返却・フィルタ対象のみは**検索需要ゼロと扱わない**。

URL Inspectionが「URL is unknown to Google」と保存した対象のパスも一覧化する。ただし各URLがHTTP 200か、Google登録が可能かは**別の証拠**であり、一覧化だけでURL登録申請やSEO改修を実行しない。

**現在の観測対象**：日用品`/categories/laundry/`への通常検索語、きょうボド`/scenes/two-player/`への2人用検索語、8つの未認識ページ。2026-11-03の公式原本は改修後のデータを含まないため、11/09の暫定観測と11/16以降の初期反応確認を区別する。
