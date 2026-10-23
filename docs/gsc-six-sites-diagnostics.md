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
