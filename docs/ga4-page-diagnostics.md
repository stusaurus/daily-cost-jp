# 日用品コスパ比較｜ページ別7日・28日間の自動調査

## 目的
3日ごとのGA4読み取り専用ワークフローの中で、日用品サイトのページ別状況を比較し、次に調査すべき場所を根拠とともに提示する。実サイトの更新・自動購入・クリック生成・楽天リンク変更は**行わない**。

## データの出典と限界
- Google Analytics Data API、GA4プロパティ552907444。
- screenPageViews と date/pagePath によるページ表示数。これは**ユーザー数でもセッション数でもない**。
- affiliate_click と pageLocation をページ単位に集計。既存の scripts/report_daily_clicks.py を使用し、operator_test=1を運営者テスト、0を暫定テスト外クリック、未設定を区分不明として扱う。
- クリックと表示数の比率を**購入率・成約率として表示しない**。楽天アフィリエイトの確定報酬データは連携していない。
- Search Console（検索表示・検索クエリ・掲載順位）はまだ連携していない。GA4の表示数減少を検索順位低下の証拠としない。
- stusaurus.github.io/daily-cost-jp/ のHTTPSページのみ対象。開発環境・別サイトやURLパラメータを混ぜない。
- 指定した日付は日本時間に基づく。GA4プロパティのタイムゾーンが異なる場合は暫定結果となる。

## 比較期間
実行日の2日前までの直近7日／前7日／直近28日／前28日のページ表示数とクリックを集計する。データが欠けた日を勝手に0と扱わない。直近28日でサイトの表示記録がない日がある場合、CTAの問題を断定せず CHECK_DATA_COVERAGE とする。

## 自動で提示する調査仮説
- CHECK_OPERATOR_DIMENSION / CHECK_UNKNOWN_TEST_EVENTS：運営者テストの区別が不十分。計測設定の確認を優先。
- CHECK_DATA_COVERAGE：表示データの欠落があり比較を保留。
- CHECK_MEASUREMENT_SCOPE：クリックはあるのに表示がない。計測範囲を調査。
- INVESTIGATE_PAGEVIEW_DROP：直近7日の表示が減少した可能性。流入元を別途確認。検索順位低下とは断定しない。
- AUDIT_CTA_AND_LINKS：28日で一定の表示があるのにテスト外クリックがない。購入導線の調査仮説。
- REVIEW_PRODUCT_FIT：表示に比べクリックが少ない場合の商品適合性とCTAの調査仮説。
- OBSERVE_LOW_TRAFFIC：アクセスが少なく結論を出せないため、データ蓄積を優先。

これらは**仮説**であり、コード変更・自動公開の許可ではない。

## 確認場所
GitHub stusaurus/daily-cost-jp → Actions → GA4 Three-Day Read-Only Analysis → Summary。日本語表と30日保存される ga4-three-day-report 成果物の ga4-page-diagnostics.json / .md を確認。

## 次段階（今回未実装）
1. Search Console連携で流入ページと検索意図を確認。
2. ページ別の導線をPC・スマホで検証し、不具合と仮説を切り分ける。
3. 軽微で許可済みの改善のみ、独立PRに変更と回帰テストを作る。
4. 十分な証拠・安全条件とロールバックを満たす場合だけ自動公開候補にする。価格・商品判定・楽天タグ・計測設定は対象外。
