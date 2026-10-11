# STEP 4-A — 購買適合性の読み取り専用監査（Issue #79）

## 実装済み範囲

- 既存の公開 `data.json` を固定URLから読み、`source`、`ranking_basis`、時刻、入力形状を検証。72時間超の古いデータ、失敗、欠落は `UNAVAILABLE` / `STALE_SNAPSHOT` 等の状態にし、0件や成果なしと混同しない。
- 全21カテゴリを横断し、`product_quality.filter_items` / `item_rejection` / `parsed_quantity` を**再利用**。別の品質基準を設けたり、もとのランキング・価格・送料・URLを書き換えたりしない。
- ティッシュ箱数・トイレットペーパーロール数・洗濯洗剤の100ml/100g換算値のみ、固定された説明用のサイズ区分を記録。他カテゴリや単位違いから推測しない。量は商品名由来の数量を単価と支払総額で検証した場合だけ使う。
- `5箱×12パック` は60箱。ティッシュの既存 `small_pack_offer` はランキングとは別枠で独立検査する。固定の少量推奨商品が存在しない場合は作らない。
- 同一`item_code`を3件の選択肢とみなさない。コード未取得はURLベースの**オファー参照**にとどめ、同一SKU・ブランド一致を断定しない。
- 各カテゴリと各商品について数量、比較単位、送料、単価、総支払額、除外理由、サイズ区分、不足する区分をJSONで記録。商品名、生検索語、販売先URL、個人情報を監査artifactへ出さない。
- `STEP 4 Purchase Fitness Read-Only Audit` が毎日11:13 JSTに公開スナップショットを監査。手動実行と該当PR時の実行も可能。既存Python/JS全回帰・Worker構文検査を先に実施し、JSON/Markdownを30日保管。
- GA4/GSC/楽天成果をこのJSONだけから推測しない。販売確定は `NOT_CONNECTED`、実利用者CVは `NOT_EVALUATED`、検索価格付き失敗の原因別内訳は `NOT_IN_PUBLISHED_SNAPSHOT`。

## 説明用サイズ閾値（販売可否や順位の基準ではない）

| 対象 | 少量 | 普段使い | まとめ買い |
|---|---:|---:|---:|
| ティッシュ（box） | 1〜10箱 | 11〜29箱 | 30箱以上 |
| トイレットペーパー（roll） | 1〜12ロール | 13〜47ロール | 48ロール以上 |
| 洗濯洗剤（100ml/100g比較量） | 10単位以下 | 11〜59単位 | 60単位以上 |

少量商品は「普段使い（少量を含む）」のカバレッジにも計上する。金額だけの任意閾値で品質・購入可否を決めない。比較単位の違いを混合しない。洗剤では1単位=100mlまたは100gで、mlとgを横断比較しない。

## 安全境界

このPRは **読み取り専用の第1段階**。日次の推薦表示変更、商品入替、コードの自動生成、SEO、楽天URL、GA4/GSC、Pages、Cloudflare、STEP 1/2/3 publisher、マージ・デプロイは一切変更しない。公開URLにアクセスできなければ、根拠のない商品や価格を表示する代わりに`UNAVAILABLE`として記録する。予定された監査を稼働させるためにはこのPRの人間によるレビュー・マージが必要。

## 未実装（Issue #79の次の独立PR）

1. **STEP 4-B**：取得済み安全な商品から「少量／普段使い／単価重視」の表示枠を選ぶ固定ルール。元ランキングを不変とし、同一SKU不明・送料不明・変動数量は推奨しない。旧UIへの安全フォールバック。1440/390/320pxの検索・比較・保存・クリック遮断QA。選択ルールが承認されるまでは日次商品変更を有効化しない。
2. **STEP 4-C**：検索/API由来0件の原因分類を、認証済み取得実績に接続。クリックと楽天確定売上を厳密に分離し、GA4 operator_test と28日集計の不明を維持する。
3. **STEP 4-D**：3日分析・既存単一Issue・STEP 2/3共通publisherにHUMAN_ONLY/INVESTIGATE/AUTO_CONTENTの根拠を接続。1実行最大1 Draft、重複防止、人の承認、必要時に元表示へロールバック。

## 確認方法

- `python3 -m unittest discover -s tests -p 'test_step4_purchase_audit.py'`
- `python3 scripts/step4_purchase_audit.py`（公開スナップショットの監査、公開変更なし）
- `python3 scripts/step4_purchase_audit.py --input site/data.json`（日次ビルド済みローカルスナップショット）
- Actions `STEP 4 Purchase Fitness Read-Only Audit` の実行と `step4-purchase-fitness` artifact
- 既存の `Validate GitHub Pages and Cloudflare Worker` の未公開ビルド、実画面QA、Lighthouse

この監査が成功しても楽天成果や売上改善の証拠にはならない。公開データにない商品検索失敗の原因やブランド要求への一致は実装済みと報告しない。
