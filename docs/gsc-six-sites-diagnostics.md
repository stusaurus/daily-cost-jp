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

追加対象は洗剤1回費用、幼児食、犬用フード、食品宅配/水比較、きょうボド小学生/ito/デュエット。公開HTMLが取得できないURLはGoogle検査を行わず未取得として保持する。マージ時の対象診断ファイルpushで既存read-onlyジョブを実行し、週次診断も継続する。新たな認証・独立監視・自動SEO変更・登録リクエストは追加しない。当時はGA4を手動実行時の明示入力に限定していた（2026-11-05改訂案で既存週次scheduleにも併走する）。

## 2026-11-05｜5サイトGA4を既存の週次GSC診断へ併走（レビュー待ち）

これまでGA4の5サイト横断集計は `workflow_dispatch.include_five_site_ga4=true` の**手動実行時限定**で、週次GSCだけでは継続的な比較・楽天クリックの観測はできなかった。今回は同じ `GSC Six-Site Discovery Diagnostics` の**月曜09:45 JSTの既存schedule**で、既存の `ga4_page_diagnostics.py --five-sites` を実行する。日用品は別の既存 `GA4 Three-Day Read-Only Analysis` が取得するため、両者を分けて扱い、重複・新規ワークフローは作らない。手動実行時は引き続き明示オプトインが必要。mainへのマージ・定期取得の有効化にはユーザー承認が必要。

- 対象はベビー／ペット／食品／きょうボド／SOTOJITAKUの5サイトに厳密固定。公開済みGoogle測定IDを読み、既存OIDC・同じGA4読み取り専用権限を使用する。管理画面の設定・サイトコード・価格・SKU・インデックスは一切変更しない。
- 既存のAPI制限（property探索20件上限、Google API429なら直ちに停止、retryなし、7/28日のJST確定日窓、データ品質閾値・タイムゾーン・URLプレフィックス確認）を保持。1回の正常取得時に5サイト×2期間×4レポート＝**最大40件のGA4 Data API runReport**に加えて、既存のAdmin/Metadata参照が発生する。GSCには追加のAPI呼び出しを行わない。
- `ga4-five-sites.json` に `funnel_event_coverage`（`page_view`、`product_view`、`product_select`、`affiliate_click` 各7/28日）を追加。各イベントは運営者判定`1`、非運営者表示`0`（**本当の顧客とは未証明**）、区分不明を別集計。メタデータ未登録・未返却行・権限不足・レポート品質制限は**取得できない状態のまま保持**し、0と補完しない。
- `ga4-five-sites.md` は5サイトの28日のイベント取得状態を一覧化する。ただし**サイトごとに商品表示イベントの意味が異なる**。例えばCAMPの`product_view`はカテゴリ単位。他サイトのSKU単位と直接比較したり、個別のGSC検索者とGA4のセッションを紐付けたりしない。結果は**独立したイベント回数**であり、順序付きの流入→選択→楽天クリックファネルや離脱率ではない。楽天成果報酬の証明でもない。
- GA4取得エラーの場合は明示的に失敗／未取得と表示し、**公式GSCの正常な診断結果を巻き添えで失敗扱いにしない**。週次ジョブのGA4ステップを `continue-on-error` にし、別のSummaryで欠落を明示する。データ欠損を補う推測値は入れない。
- 週次実行の初回は承認後、既存の月曜実行に限る。現在の公式GSC 10/03〜10/30の28日実績、日用品GA4 10/30〜11/01の34セッション・楽天クリック1イベントは**異なる集計窓・母集団**なので「検索から楽天への転換率」を計算しない。

レビュー用テストは `tests/test_ga4_five_sites_readonly.py` で、未知の運営者フラグ、欠測・品質制限、同一行重複、週次scheduleと手動オプトインの排他条件を確認する。公開データを書き換えず、CIで回帰確認する。
