# Search Consoleの読み取り専用接続テスト（日用品サイト）

## 目的
すでに稼働中の GA4 3日ごと分析に、Google Search Consoleの検索表示・検索クリック・平均掲載順位を追加するための**初回接続テスト**。接続できてもこの段階でGA4へ統合したり、自動修正・自動公開したりしない。

対象プロパティは次のURLプレフィックスと**完全一致**するもののみとする。
https://stusaurus.github.io/daily-cost-jp/

このプロパティがSearch Consoleに存在しない場合、同じアカウントで見られる親の stusaurus.github.io プロパティやSOTOJITAKUへ自動切替しない。別サービスのデータ混入を防ぐ。

## 既存の認証を再利用
- Google Cloudプロジェクト: daily-cost-analytics
- GitHub ActionsからGoogle Cloudへの認証: GitHub OIDC + Workload Identity Federation
- サービスアカウント: daily-cost-ga4-reader@daily-cost-analytics.iam.gserviceaccount.com
- GitHub environment: ga4-readonly-pilot（mainブランチだけ実行可能）
- Google OIDCプロバイダーもmainブランチ限定。秘密鍵JSONの作成・GitHub Secretsへの貼り付け・プロジェクトEditor/Owner権限の付与は**不要**。
- GSCでは https://www.googleapis.com/auth/webmasters.readonly の読み取り専用OAuthスコープを使用する。

## 初回接続に必要な条件
1. Google Cloudプロジェクト daily-cost-analytics で **Google Search Console API** が有効になっている。
   Cloud Consoleの公式APIページ: https://console.cloud.google.com/apis/library/searchconsole.googleapis.com?project=daily-cost-analytics
   注: Google Cloud Search APIと取り違えないこと。
2. Search Consoleに正しい**URLプレフィックスプロパティ** https://stusaurus.github.io/daily-cost-jp/ が存在し、所有権が確認されている。
3. 当該プロパティの「設定 → ユーザーと権限」で上記サービスアカウントを**制限付きユーザー**として追加している。所有者権限は不要。
4. 初回の手動起動またはworkflowファイルのmainへの反映でGitHub Actionsの
   Search Console Read-Only Pilotが実行される。

必要な設定を確認するまでは「接続済み」と表現しない。

## 失敗時は読み取り専用で安全に保留
ワークフローのジョブが緑色でも、結果の status を必ず確認する。
- NOT_CONNECTED / PROPERTY_ACCESS_MISSING: Search Consoleに正しいプロパティがあるか、サービスアカウントを追加したか確認。
- NOT_CONNECTED / SEARCH_CONSOLE_API_DISABLED_OR_FORBIDDEN: Cloud ConsoleのSearch Console API有効化や権限を確認。
- NOT_CONNECTED / MISSING_WORKLOAD_IDENTITY: GitHub environment/main認証を再確認。ただしGA4がすでに動いていればむやみに設定を変更しない。
- NO_SEARCH_DATA: まだ集計対象のデータが取得できない。**検索0回の証拠ではない**。
- PROVISIONAL: 読み取りに成功。検索トラフィック分析の準備ができた。
- TOP_ROW_COVERAGE_UNCERTAIN: APIの上位行制限の可能性。全件網羅として扱わない。

権限がない、APIが使えない場合もJSONとMarkdownのステータスを保存し、0件を捏造しない。

## 取得するもの
検索実績のサイト全体とページ別の
- 直近7日とその前の7日
- 直近28日とその前の28日
を各期間の最後が実行3日前となるよう集計。Google Search Console APIでは、上位のページ・クエリ行がすべて返るとは限らないことに注意。

参考: 直近28日の検索表示が少ないページを調査候補にする。50回以上検索表示され、平均順位が4〜30位でCTRが2%未満なら検索タイトル・説明文の調査候補にする。この閾値は**仮のルール**であり、自動的にタイトル・本文を書き換える許可ではない。

検索クエリは、28日で20表示以上の集計行に限り、最大20行だけ記録する。低頻度の個別検索を公開リポジトリのGitHub Actions成果物に載せないための制限。

## 結果の確認
GitHub → Actions → Search Console Read-Only Pilot → 該当のrun → Summary。
出力ファイルは gsc-search-pilot artifact（JSON / 日本語Markdown、30日保存）。

GA4の楽天クリック、GSCの検索クリック、楽天アフィリエイトの確定売上は**別の指標**。
検索0・クリック0・売上0を同一視しない。

## 接続が成功した後の段階
1. 読み取り結果のプロパティ名、期間、データ量、各ページの数字を確認。
2. GA4のページ別データと同じURL単位で照合。Google検索と他流入を混同しない。
3. 3日ごとの同一レポートへ安全に統合し、優先ページの調査を高度化。
4. 適切なデータが揃って初めて、改善提案の自動作成と回帰検証を検討する。
5. 自動公開・楽天リンクの書換え・Search Consoleのサイトマップ再送信等は実行しない。
