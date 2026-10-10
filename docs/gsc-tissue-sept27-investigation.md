# ティッシュページ：9月27日前後の検索表示変化を追加調査

## 調査する理由

2026年10月10日に取得したSearch Consoleデータでは、ティッシュページの検索表示は9月24〜30日の30回に対し10月1〜7日は1回。日別では9月24日12回、25日8回、26日9回、27日1回という変化が観測された。

ただし、表示回数が少なく、検索需要の変化、検索結果の順位の変化、インデックスの状態の変化、Google側の処理などのどれが理由か**断定できない**。

今回の追加調査は「データに基づく原因の絞り込み」であり、SEOタイトルや商品情報の書き換えは実行しない。

## 調査項目

- Search ConsoleのSearch Analytics APIから、9/20〜26と9/27〜10/3の7日間を、ティッシュページに絞って同一条件で比較する。
- スマホ・PC・タブレット別の検索表示数、検索クリック、平均掲載順位を見る。行が返らない端末は0回と断定せず「不明」とする。
- Google検索クエリの行数や合計表示数を比較する。ただし**検索語の生文字列はGitHubログ・成果物・日本語レポートに一切保存しない**。匿名化や少数検索語の除外によって、クエリ別合計と実際の表示数は一致しない場合がある。
- URL Inspection APIの読み取り専用エンドポイントで、ティッシュページの**Googleに記録された現在のインデックス情報**を確認。インデックスの総合判定、クロール日時、canonical、noindex/robots、ページ取得状態などを取得する。
- URL検査では**9月27日の過去のインデックス状態は取得できない**。現在Googleに把握されている状態だけを確認し、過去にいつ変化したかを推測で断定しない。

## セキュリティと既存機能の保護

- 既存Google Cloud daily-cost-analytics、サービスアカウント daily-cost-ga4-reader、GitHub環境 ga4-readonly-pilotを流用。main限定OIDC認証とSearch Console読み取り専用スコープを維持。
- GitHub Actions権限はcontents: readとGoogle認証用id-token: writeのみ。静的サービスアカウントキー不要。
- 調査対象プロパティ https://stusaurus.github.io/daily-cost-jp/ とページURL https://stusaurus.github.io/daily-cost-jp/categories/tissue/ を完全固定。
- 他サイトの調査、サーバーへの更新、サイトマップ送信、URLインデックス登録リクエスト、商品や楽天リンクの変更、GitHubへの自動コミット・公開は実行しない。
- まず一度だけ本番でスモークテストを実施。日々のAPI呼び出しや定期的なURL Inspectionは現時点で組み込まない。結果を見てから必要性を判断する。
- APIへのアクセスが拒否された場合には、結果を「未取得・不明」と記録し、0回や正常と偽らない。調査レポートのジョブが緑色でもJSON内の状態を必ず確認する。

## 操作・確認先

GitHub → Actions → GSC Tissue Read-Only Forensics → 初回実行のSummary。
30日間保存のgsc-tissue-sept27-readonly成果物にJSONとMarkdownの集計表を保存。

Search Console API公式情報：
https://developers.google.com/webmaster-tools/v1/searchanalytics/query
https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect
