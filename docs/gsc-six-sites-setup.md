# 6サイト共通 Search Console 直接API監視

## 範囲
以下のURLプレフィックスプロパティを完全一致で照合して、検索表示・クリック・CTR・平均順位を取得します。

- https://stusaurus.github.io/daily-cost-jp/
- https://stusaurus.github.io/baby-cost-jp/
- https://stusaurus.github.io/pet-cost-jp/
- https://stusaurus.github.io/food-cost-jp/
- https://stusaurus.github.io/kyo-bodo-jp/
- https://stusaurus.github.io/sotojitaku/

週次（月曜9時JST目安）と手動で実行し、直近7日/前7日・直近28日/前28日・上位5ページを日本語で出力します。Search Consoleの集計日は太平洋時間（America/Los_Angeles）です。直近3日分は暫定値を避けるため除外します。月曜9時JSTは日曜の太平洋時間に相当するため、API期間もその暦日を基準にします。XやGA4、楽天の実績とは混同しません。

## 認証：既存Google OIDCを再利用、秘密鍵JSON不要

- Google Cloudプロジェクト：daily-cost-analytics
- Workload Identity Provider：projects/557507311026/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions
- サービスアカウント：daily-cost-ga4-reader@daily-cost-analytics.iam.gserviceaccount.com
- GitHub environment：ga4-readonly-pilot（mainブランチのみの既存保護を維持）
- 読み取り専用スコープ：https://www.googleapis.com/auth/webmasters.readonly

### 初回設定チェック
1. [Google Cloud APIページ](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com?project=daily-cost-analytics) で Search Console API が有効になっているか確認。有効なら何もしない。
2. [Search Console](https://search.google.com/search-console)で上記の各URLプレフィックスプロパティを選択し、「設定」→「ユーザーと権限」→「ユーザーを追加」でサービスアカウントのメールアドレスを「制限付きユーザー」にする。すでに付与済みなら何もしない。所有者権限や秘密鍵の共有は不要。
3. Draft PRをレビューし、問題がなければ手動マージする。マージ前は新しい週次監視は稼働しない。
4. GitHubの日用品リポジトリ → Actions → GSC Six-Site Direct API (Read Only) → Run workflow（main）を実行する。
5. Summaryとgsc-six-sites-readonly成果物（JSON・Markdown、30日保存）で全6サイトの数値と状態を検証する。日用品の数値を同一期間のSearch Console画面と突き合わせる。

### 状態
- READY：6サイトへの問い合わせが完了した。行なしはNO_ROWSとして不明を維持し、検索0回と断定しない。
- PARTIAL：一部だけ問い合わせ完了。取得できた数値のみ信頼する。
- UNAVAILABLE：全部接続失敗。0回ではない。
- PROPERTY_ACCESS_MISSING：該当URLプロパティに閲覧権限がない。
- AUTH_OR_PROPERTY_LIST_FAILED：認証・権限一覧取得が失敗。
- SEARCH_CONSOLE_API_UNAVAILABLE：APIの取得に失敗。

Windsor.aiで6サイトが見えることは、このサービスアカウントにも同じ権限がある証明にはなりません。6サイトで照合できるまで既存のWindsor.ai設定を削除しないでください。

## 安全制約
- Search Consoleへの書込み、サイトマップ再送信、商品・価格・楽天リンク・SEOページの変更は実施しない。
- 既存のGA4 3日ごと自動分析、楽天API、X投稿、GitHub Pagesを維持する。
- ワークフローのpull_requestではオフラインテストのみ。Google認証はmain上でのみ実行。
- 検索クエリ明細、秘密鍵、認証トークンを出力しない。
- 28日間の少量データを根拠に検索順位の急落やペナルティを断定しない。
- APIは一部のデータ行を匿名化・省略する可能性がある。サイト全体の集計とページ別の上位行を混同しない。

## 切替完了条件
- 6サイトすべて正しいプロパティと読み取り権限で取得できる。
- GitHub Actionsの週次実行と手動再実行が確認できる。
- 28日間の実測値を少なくとも日用品サイトのSearch Console画面と照合できる。
- 既存のページやGoogle Analyticsへの影響がない。
