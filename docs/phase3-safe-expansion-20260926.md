# 第3次改善の根拠（2026-09-26）

Search Consoleは9/1〜9/25を要求し、9/24までの実績を取得。367表示・9クリック・CTR 2.45%・表示数加重の平均順位12.22。クエリを含む集計は匿名化等で全体件数と一致しません。

9/13〜9/25のクエリ×ページ取得分：ティッシュ「どこが安い」9表示/10.11位、「値段比較」6表示/9.17位、スペースなし「ティッシュ値段比較」2表示/7位。「洗濯洗剤 値段 比較」2表示/10位、「アタックゼロ どこが 安い」2表示/10.5位、「トイレットペーパー いくら なら 安い」9表示/11.56位。いずれもこの集計では0クリック。今回はティッシュのtitle/descriptionだけを調整しH1・既存本文・他の優先ページを維持します。

GA4 552907444（9/23〜9/25）：affiliate_click 14件のうちoperator_test=1が13件、0が1件。0の1件はgoogle / organic、ランディングページcategories/tissue/、conversion_source=category。テスト未設定の運営者も含み得るので一般ユーザー・成果とは断定しません。既存の流入元・ランディングページで集計でき、新イベントは不要です。

## A / B / C の判断

- A：電子タバコ清掃用品、ディスペンサー、ケース、床材、用途違い、選択式数量、送料未確認は除外を維持。食器用洗剤60件中54件、ハンドソープ60件中50件が周辺用品であり、候補集合の改善を優先。
- B：「キレイキレイ 薬用ハンドソープ 4リットル」「ミヨシ 泡のボディソープ 4リットル」の2タイトルは単位の日本語表記だけで解析に失敗。4Lと等価に正規化し100ml単価の分母40を確認。掲載には送料等を含む全ゲートの通過が別途必要。複数容量・曖昧な箱数等は引き続き除外。
- C：掲載5件未満のカテゴリにのみ、具体的な日用品語・ブランドで取得を追加。商品コード/商品URLで重複除去し全候補を既存の共通ゲートへ戻す。最大5リクエストで打ち切る。

## 表示名

元の楽天商品名を品質判定・数量解析・JSONに保存。画面の見出し・代替テキスト・対応する構造化データだけを整形します。旧処理の「先頭括弧をすべて削除」は廃止し、ブランドや「6個セット」「無添加 泡ハンドソープ 詰め替え」等を保ちます。日付限定・24時間限定・P5倍/P10倍・ポイント倍率・最大金額OFFクーポン等だけの先頭ラベルを除き、混在ラベルは安全のためそのまま残します。

## 修正前の品質レポート

Actions run 36235108214 / artifact 10903708305 と同ビルドのPagesデータを取得。取得候補1,110件、適合104件、掲載72件。理由は最初に該当した1理由を数えます。

実取得後の候補・掲載数と除外理由はPRのcandidate-quality-preview、公開後はproduct-quality-reportを参照。APIの商品集合は時間で変わるので同一ビルドのacquisition.baselineとの差も記録します。

| カテゴリ | 取得 | 適合 | 掲載 | 除外理由 |
| --- | ---: | ---: | ---: | --- |
| トイレットペーパー | 60 | 4 | 4 | wrong_use_or_type: 33、missing_price_or_quantity: 9、unconfirmed_shipping: 10、accessory: 2、missing_category_evidence: 1、selectable_quantity: 1 |
| ティッシュ | 60 | 4 | 2 | wrong_use_or_type: 44、missing_category_evidence: 3、accessory: 5、unconfirmed_shipping: 2、missing_price_or_quantity: 2 |
| 洗濯洗剤 | 60 | 7 | 5 | accessory: 6、wrong_use_or_type: 24、selectable_quantity: 11、missing_price_or_quantity: 5、unconfirmed_shipping: 4、mixed_bundle: 2、missing_category_evidence: 1 |
| 食器用洗剤 | 60 | 1 | 1 | accessory: 54、selectable_quantity: 1、wrong_use_or_type: 1、missing_price_or_quantity: 2、unconfirmed_shipping: 1 |
| 水・ミネラルウォーター | 30 | 7 | 5 | wrong_use_or_type: 6、selectable_quantity: 8、unconfirmed_shipping: 8、missing_price_or_quantity: 1 |
| コーヒー | 60 | 8 | 5 | mixed_bundle: 20、unconfirmed_shipping: 3、missing_price_or_quantity: 8、selectable_quantity: 17、wrong_use_or_type: 3、missing_category_evidence: 1 |
| 柔軟剤 | 60 | 9 | 5 | wrong_use_or_type: 20、selectable_quantity: 7、missing_price_or_quantity: 9、accessory: 3、unconfirmed_shipping: 6、mixed_bundle: 4、missing_category_evidence: 2 |
| シャンプー | 60 | 4 | 4 | selectable_quantity: 9、wrong_use_or_type: 18、accessory: 17、unconfirmed_shipping: 3、missing_category_evidence: 3、missing_price_or_quantity: 6 |
| コンディショナー | 60 | 1 | 1 | accessory: 23、wrong_use_or_type: 25、unconfirmed_shipping: 4、selectable_quantity: 5、missing_category_evidence: 1、mixed_bundle: 1 |
| ボディソープ | 60 | 5 | 3 | accessory: 20、selectable_quantity: 3、wrong_use_or_type: 13、missing_price_or_quantity: 5、missing_category_evidence: 4、unconfirmed_shipping: 9、mixed_bundle: 1 |
| ハンドソープ | 60 | 1 | 1 | accessory: 50、selectable_quantity: 2、unconfirmed_shipping: 6、missing_price_or_quantity: 1 |
| お風呂用洗剤 | 30 | 7 | 5 | unconfirmed_shipping: 10、selectable_quantity: 1、missing_category_evidence: 6、missing_price_or_quantity: 6 |
| トイレ用洗剤 | 60 | 1 | 1 | unconfirmed_shipping: 36、wrong_use_or_type: 11、missing_price_or_quantity: 3、selectable_quantity: 2、missing_category_evidence: 7 |
| 衣料用漂白剤 | 30 | 9 | 5 | unconfirmed_shipping: 12、mixed_bundle: 1、missing_category_evidence: 3、selectable_quantity: 2、missing_price_or_quantity: 3 |
| マウスウォッシュ | 30 | 11 | 5 | unconfirmed_shipping: 7、missing_price_or_quantity: 5、selectable_quantity: 4、wrong_use_or_type: 2、missing_category_evidence: 1 |
| ペーパータオル | 60 | 8 | 5 | wrong_use_or_type: 28、missing_price_or_quantity: 9、accessory: 6、missing_category_evidence: 1、selectable_quantity: 2、mixed_bundle: 1、unconfirmed_shipping: 5 |
| 45Lゴミ袋 | 60 | 2 | 2 | wrong_use_or_type: 51、missing_category_evidence: 3、unconfirmed_shipping: 1、selectable_quantity: 2、missing_price_or_quantity: 1 |
| 不織布マスク | 30 | 7 | 5 | missing_price_or_quantity: 21、selectable_quantity: 1、unconfirmed_shipping: 1 |
| 歯ブラシ | 60 | 5 | 5 | wrong_use_or_type: 23、mixed_bundle: 5、unconfirmed_shipping: 18、missing_price_or_quantity: 5、selectable_quantity: 4 |
| 綿棒 | 60 | 1 | 1 | wrong_use_or_type: 13、missing_category_evidence: 13、accessory: 25、missing_price_or_quantity: 2、unconfirmed_shipping: 3、selectable_quantity: 3 |
| フローリングシート | 60 | 2 | 2 | missing_category_evidence: 7、wrong_use_or_type: 40、missing_price_or_quantity: 8、accessory: 1、selectable_quantity: 2 |

除外計：1006件。理由合計：{"wrong_use_or_type": 355, "missing_price_or_quantity": 111, "unconfirmed_shipping": 149, "accessory": 212, "missing_category_evidence": 57, "selectable_quantity": 87, "mixed_bundle": 35}。

ambiguous_quantity / unit_mismatch / quantity_price_mismatch / isolated_price_outlier は旧レポートでは0件。数量解析失敗が missing_price_or_quantity に集約されていたため、新レポートでは ambiguous_quantity を先に判別します（採用基準は同じ）。

## 9/27 公開前の実データ検証

PR #18のActions run 36279051894で1,359件を取得、重複13件を除く1,346候補を検査。251件が適合し、全21カテゴリで各5件に達しました。個別確認で「綿棒200本×4個セット〜」と「法人限定ゴミ袋」を見つけたため、公開前に共通ゲートを強化。上限未確定の数量・一般消費者が購入できない限定商品を除外し、回帰テストを追加しました。この105件は初回検査の件数であり、最終公開件数は再検査後のレポートで確認します。

追加候補に多かった「P最大13倍★9/25限定」「セール中 9/28 23:59迄」「P5倍☆彡〜28日9:59迄」も販促だけのラベルとして表示時に除去します。ブランド・数量などとの混在ラベルは削除しません。

9/27再取得：Search Consoleは9/26まで要求しても最新実績は9/24のまま。GA4は9/23〜9/26のaffiliate_clickが17件（operator_test=1が16件、0が1件）。0の1件は同じティッシュページへのgoogle / organic流入です。
