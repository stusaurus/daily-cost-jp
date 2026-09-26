# daily-cost-jp
日用品を1単位あたりのコストで比較するサイト。GitHub Pagesで公開し、リアルタイム検索はCloudflare Workerを利用します。

## 運営者の動作確認

- ON: https://stusaurus.github.io/daily-cost-jp/?test=1
- OFF: https://stusaurus.github.io/daily-cost-jp/?test=0 （またはページ上部の「テストを解除」）

PC・スマホの各ブラウザで一度ONにしてください。localStorageに保存され、サイトから明示的に送るイベント（楽天クリック等）に `operator_test=1`、通常時には `operator_test=0` を付けます。IPアドレスは利用しません。ブラウザデータを消した場合・別ブラウザ・プライベートモードでは再設定が必要です。保存できないブラウザではタブ内の保存を試み、画面に注意を表示します。

ONのときだけ状態と直近イベントの確認欄を表示します。確認欄はGA4タグへ渡した値であり、Google側の受信・集計完了の証明ではありません。通常ユーザーに確認欄は表示しません。

## 楽天クリックの分析

共通イベントは `affiliate_click`。既存の `product_result_click` と `same_product_rakuten_click` も残し、同じクリックの補助イベントとして扱います。3イベントを合算しないでください。

`conversion_source` は `product_search`、`buy_judge`、`top_pick`、`category`、`trend`、`daily_pick`（today）、`ranking`、`same_product_compare`、`product_guide`、`price_guide`、`other`。ガイドから商品検索へ進んだ場合は発生元を引き継ぎ、新しく検索語を入力した場合は `product_search` に戻します。

GA4 Property: `552907444` / Measurement: `G-GFVSZ8YDQ5`。イベントスコープのカスタムディメンション「クリック発生元」=`conversion_source`、「運営者テスト」=`operator_test` を使います。収益導線の集計は `event_name=affiliate_click` かつ `operator_test != 1` を基本とし、`0`（テスト未設定）と `(not set)`（判別情報なし）は内訳を分けます。`0` も一般ユーザーと断定できません。過去の自己アクセスは遡って識別できません。恒久除外フィルタは設定しません。`page_view`・`session_start` 等のGA4自動イベントには、既定値を設定していても空欄が残る場合があります。全イベントへの付与は保証せず、収益導線の評価は上記の明示的なクリックイベントで行ってください。

## 価格・公開前検証

選択式の容量・販売個数は最低表示価格から単価を推測しません。カテゴリでは比較対象から除外し、リアルタイム検索では楽天で選択内容と価格を確認する導線を残します。

`python -m unittest discover -s tests` と `npm ci && npm test` で数量解析・計測・検索連携を確認します。Pagesの生成後には `python scripts/validate_generated_site.py` で内部リンク、アフィリエイトURLの二重エスケープ、canonical、sitemap、重複メタデータ、JSON-LD、GA4埋め込みを検証します。

全21カテゴリの適合条件・除外条件・数量と価格の整合性は `scripts/product_quality.py` に集約しています。取得候補をこの共通フィルタに通してからランキングを生成し、カテゴリ、買い判定、today、トップ推薦、商品ガイド、X投稿候補でも検証済みデータを使います。用途が違う商品、空容器、選択式数量、単位不一致、送料不明、孤立した極端な安値は掲載しません。条件を満たす候補が少ない場合は件数を減らし、誤商品で補完しません。

公開直前の `python scripts/validate_product_quality.py` は、21カテゴリのカタログ、today、X投稿データ、生成HTMLの楽天リンク、日用品の検索候補を照合し、未検証の商品が混入するとデプロイを止めます。Actionsの `product-quality-report` アーティファクトにはカテゴリ別の判定件数・除外理由を14日間保存します。実際に見つかった商品を含む回帰テストと確認結果は [商品品質の監査記録](docs/product-quality-20260923.md) を参照してください。

商品検索の候補は日用品の具体的な商品名・ブランドに限定し、総合トレンドから自動転記しません。総合TOP50は `/trends/` に残し、トップからは入口を案内します。既存の `trend_chip_click` イベント名は互換性のため維持し、日用品の検索候補からの楽天クリックには `conversion_source=product_search` を付けます。

優先カテゴリの本文・CTAと商品ガイドは `scripts/improve_purchase_pages.py` で生成します。朝の更新、19:00の再取得、19:30のX/Buffer投稿は既存ワークフローを維持します。

## 安全な候補拡充と自然検索の評価

取得1ページ目で品質適合のランキング候補が5件未満なら2ページ目を追加し、まだ不足するときだけ具体的な日用品・ブランドによる補助検索を最大3回行います。1カテゴリ最大5リクエスト、リクエスト間は1.15秒以上。商品コード・商品URLで重複を除き、全候補を同じ `product_quality.py` に通します。補助検索の失敗で取得済み候補を捨てません。掲載件数は最大5件のままで、未達でも条件を緩めません。

品質レポートの `acquisition.baseline` は同一ビルド内の元の取得範囲、`requests` は取得語・ページ・件数、`published` は最終掲載件数です。日本語単位（4リットル等）の表記だけを正規化し、単位・数量・送料の不明な商品は救済しません。`product_display.py` は販促だけで構成される先頭ラベルを表示時だけ除き、元の商品名・数量解析・価格・URL・today/Xの照合データを維持します。

「4個セット〜」「500ml〜」等の上限未確定の数量も選択式として除外します。法人限定・個人宅配送不可の商品は一般向け比較から外します（通常の業務用まとめ買いは対象）。

同一リポジトリのPRでは `audit_product_candidates.py` が楽天から実取得し、公開せずに品質を検証します。`candidate-quality-preview` アーティファクトで結果を確認後にマージできます。既存のPages公開直前の品質ゲートも引き続き動作します。

Windsor.ai / GA4では既存イベントだけで「Google自然検索 → 入り口ページ → 楽天クリック」を集計できます。使用項目は `landing_page_plus_query_string`、`session_source_medium`、`event_name`、`event_count`、`customevent_conversion_source`、`customevent_operator_test`。`session_source_medium = google / organic` と上記のクリック・テスト条件を使い、ランディングページとクリック発生元別に集計します。Search Consoleの検索語を個別ユーザーのクリックへ結び付けるものではありません。検索語はページ単位の流入改善に使い、楽天クリックを購入成果とみなしません。
