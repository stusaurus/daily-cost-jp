# daily-cost-jp
日用品を1単位あたりのコストで比較するサイト。GitHub Pagesで公開し、リアルタイム検索はCloudflare Workerを利用します。

## 運営者の動作確認

- ON: https://stusaurus.github.io/daily-cost-jp/?test=1
- OFF: https://stusaurus.github.io/daily-cost-jp/?test=0 （またはページ上部の「テストを解除」）

PC・スマホの各ブラウザで一度ONにしてください。localStorageに保存され、以後のイベントに `operator_test=1`、通常時には `operator_test=0` を付けます。IPアドレスは利用しません。ブラウザデータを消した場合・別ブラウザ・プライベートモードでは再設定が必要です。保存できないブラウザではタブ内の保存を試み、画面に注意を表示します。

ONのときだけ状態と直近イベントの確認欄を表示します。確認欄はGA4タグへ渡した値であり、Google側の受信・集計完了の証明ではありません。通常ユーザーに確認欄は表示しません。

## 楽天クリックの分析

共通イベントは `affiliate_click`。既存の `product_result_click` と `same_product_rakuten_click` も残し、同じクリックの補助イベントとして扱います。3イベントを合算しないでください。

`conversion_source` は `product_search`、`buy_judge`、`top_pick`、`category`、`trend`、`daily_pick`（today）、`ranking`、`same_product_compare`、`product_guide`、`price_guide`、`other`。ガイドから商品検索へ進んだ場合は発生元を引き継ぎ、新しく検索語を入力した場合は `product_search` に戻します。

GA4 Property: `552907444` / Measurement: `G-GFVSZ8YDQ5`。イベントスコープのカスタムディメンション「クリック発生元」=`conversion_source`、「運営者テスト」=`operator_test` を使います。新実装以後の通常クリックは `event_name=affiliate_click` かつ `operator_test=0` で分析できます。過去の `(not set)` は一般ユーザーと断定せず、別集計にしてください。恒久除外フィルタは設定しません。

## 価格・公開前検証

選択式の容量・販売個数は最低表示価格から単価を推測しません。カテゴリでは比較対象から除外し、リアルタイム検索では楽天で選択内容と価格を確認する導線を残します。

`python -m unittest discover -s tests` と `npm ci && npm test` で数量解析・計測・検索連携を確認します。Pagesの生成後には `python scripts/validate_generated_site.py` で内部リンク、アフィリエイトURLの二重エスケープ、canonical、sitemap、重複メタデータ、JSON-LD、GA4埋め込みを検証します。

優先カテゴリの本文・CTAと商品ガイドは `scripts/improve_purchase_pages.py` で生成します。朝の更新、19:00の再取得、19:30のX/Buffer投稿は既存ワークフローを維持します。
