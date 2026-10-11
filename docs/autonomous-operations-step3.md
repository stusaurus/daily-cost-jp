# 自動運営 STEP 3：固定UI改善と機能調査

この実装はSTEP 1の3日分析・Issue #74、STEP 2の実トークン検証・書き込みフラグ・単一Draft publisherを拡張する。mainへの変更、承認、マージ、公開APIは呼ばない。検証用PR #77はDO NOT MERGEのまま維持する。新しいAIサービス、APIキー、依存ロックファイル、Google権限は追加しない。画面QAには既存ビルドと同じNoto CJKフォントを使う。

## 現行稼働の証拠

- main: `f556368bb5e0a2e3a958cf7e8dd1ba9e18a818ca`
- 3日分析: [run 38095934430](https://github.com/stusaurus/daily-cost-jp/actions/runs/38095934430)。GA4/GSC、公開ブラウザQA、Issue集約、STEP 2テスト・publishがsuccess、候補なしはNO_SAFE_FIX。
- 実GITHUB_TOKEN検証: [run 38094769955](https://github.com/stusaurus/daily-cost-jp/actions/runs/38094769955)でDraft #77を作成。[再実行38094941918](https://github.com/stusaurus/daily-cost-jp/actions/runs/38094941918)はDUPLICATE_OR_DISMISSED。
- Bot作成PRの通常CIには承認待ちになる場合がある。生成ジョブ内の作成前テストを必須にし、PRチェックの自動起動に依存しない。#77の通常CIがaction_requiredでもマージしない。

## 初回の固定レシピ

`home-ranking-link-tap-v1` は `scripts/design/laboratory.css` の末尾に次だけ追加する。

```css
#home-ranking-hero .home-rank-all{display:inline-flex;align-items:center;min-height:44px}
```

トップ末尾の「楽天総合ランキングTOP50を見る」の元生成処理 `promote_home_ranking.py` には44pxの指定がある。最終CSSには同セレクタがなく、[公開実画面の18画面監査 run38098024641](https://github.com/stusaurus/daily-cost-jp/actions/runs/38098024641)が成功し、1440pxは高さ17px、390/320pxは16pxと再現した。トップの生活カテゴリ導線は既に44px以上であり、変更しない。同じ原因を確認したため、実装Draft PR #78にこのCSS候補だけを反映した。候補はブラウザ内で置換して検証し、本番へは公開しない。

44pxは本サイトの操作性の目標（WCAG 2.5.5の強化基準を参考）であり、24pxのWCAG 2.5.8最低基準への違反とは断定しない。色、書体、リンク先、商品データ、判定、計測は変えない。横スクロールを隠すレシピは登録していない。

このレシピが定期処理で許可済みになるのは、人が実装PRのテスト・画面・コードをレビューしてmainへ反映した後。既存 `STEP2_ENABLE_PR_WRITES` がtrueでも、未マージのSTEP 3コードは定期処理で使われない。

## 検出と判定

固定6ページ（トップ、洗濯洗剤、ティッシュ、トイレットペーパー、商品検索、今日のお得）×1440/390/320pxを検査する。各観測にURL、幅、DOMセレクタ、寸法・計算スタイル、再現手順、画面画像を残す。全viewport画像に加え、代表的な問題要素と固定対象を切り抜いて保存する。

- 横方向はみ出し：document幅と要素座標。設計された比較表内の横スクロールは文書全体のはみ出しと区別。
- タップ領域：44px未満を調査候補とし、唯一の登録対象の3幅再現だけAUTO_FIXになり得る。
- テキスト：非意図的クリッピング、画面内の重なり、コントラスト、名前のない操作対象、Tab移動時のフォーカスを診断。意図したline-clampは欠落と断定しない。
- 操作：検索の入力制約と固定空レスポンス、比較、保存、再読込後の保存、カテゴリ選択・未入力判定を検査。楽天リンクはクリックせず、Worker呼び出しは空の固定QA応答に置換。実APIの商品価格の検証とは区別する。
- 未取得・例外・CSSソース不一致・期間超過・画像欠落は正常/修正根拠として扱わない。

色背景の透過や複雑な重なりの機械判定には限界があり、これらはINVESTIGATE。画面内代表要素・最大700操作対象・140テキスト要素を調べ、各コードの代表3件と固定対象を記録する。全アクセシビリティ適合を保証する監査ではない。未取得のページや未実装の絞り込み・機能追加は人の判断が必要。

機能の候補はSTEP 1/GA4/GSC/QAからINVESTIGATEとして記録する。商品品質、価格・数量・送料・楽天URL、安全判定、SEO変更、機能追加、全面刷新はHUMAN_ONLY。CTRや利用数だけではAUTO_FIXにならない。

## 定期処理と安全性

既存safe-repair-preparationジョブにUI診断と候補JSONを追加する。UI取得が失敗した場合は未取得を記録し、既存ドキュメントレシピは維持。ドキュメント修復を優先し、なければ唯一のUIレシピを選ぶ。STEP 2/3合計で最大1件。

UI修正には、同一main SHA・6時間以内のlive監査・全18画面成功・公開CSSとmain CSSのSHA256一致・単一のA要素・固定href・既知のdisplay/min-height・3幅で再現した寸法が必要。Issueの文字列や渡されたrecipe/commandは権限にならない。既に同セレクタやレシピがある場合は追加しない。

作成前に全Python/JS/商品品質/リンク/構文回帰を実行。UI候補ではさらに公開ページのCSSだけを候補へ置換したブラウザ検証を行う。前後18画面、対象44px、色/書体/href不変、HTMLの価格・全リンク/data属性・SEO・計測スクリプト等の保護hash不変、操作成功、横はみ出しなし、新しい調査項目なしを必須にする。比較画像と寸法差分・hashをartifactへ保存。

receiptは候補CSS hash、base SHA、全テストPASS、ブラウザproof hashを結びつける。publisherはproof/report/difference hashとliveモードを再確認し、snapshot/mock結果では本番PRを書かない。固定パス以外の追跡済み/未追跡差分、symlink、main移動、孤立branchを拒否する。既存の全open/closed PRページング・fingerprint/branch重複抑止を共有する。生成コミットはmainを親とするCSS1ファイルだけ。Draft・人間承認待ちで、承認/マージ/デプロイAPIはない。

STEP 3のPR検証workflowはcontents:readだけ。定期publisherのcontents:write/pull-requests:write/actions:readを再利用し、Google認証やデプロイ権限は与えない。Netlify専用opt-outは既存publisherの固定指定を維持。Pages/Worker構成・商品データ・楽天URL・Googleイベントコードは変更しない。

## 収益改善の基準値と評価

同じ3日runの `search-affiliate-joint.json` から `step3-candidates.json` に施策前の基準値を保存する。2026-10-11 JST取得時：GSCは9/11–10/8、GA4は9/12–10/9で期間不一致。洗濯洗剤は検索表示111/クリック2、ティッシュ112/2、トイレットペーパー78/1。GA4は観測日不完全のため一般ユーザークリックは未確定。トップには区分不明11件がある。運営者テストは別記する。

検索表示→検索クリック→GA4表示→比較/保存→楽天クリックは同一ユーザー群ではない。クロスソース成約率は計算しない。比較・保存・絞り込みの利用数は今回の既存レポートでは未取得で、0とは記録しない。楽天クリックは売上ではなく、成約・報酬は未接続。

人が修正を公開した時刻・コミットを記録し、反映遅延を置いた同じ長さの完了28日間を、各ソース内で比較する。既知operator_testを除外し、unknown、未取得、少数サンプル、季節・端末・流入差を残す。改善後のスクリーン成功と収益増加は別に評価する。今回、収益増加は検証していない。

## 有効化後の確認・停止

1. 人がこのDraftのコード、全回帰、模擬、公開/候補の3幅画像を承認してマージする。本作業はマージしない。
2. mainで既存3日分析を手動実行。STEP 1/Issue #74、STEP 2、step3-candidates、18画面の結果を確認。現在対象が既に直っていれば修正PRは作らない。
3. 初回UI修正が発生したらartifactのbefore/after、comparison.html、differences.json、verification.json、step2-tests.jsonを確認。Draft差分はCSSの固定ブロック1件、main不変、同じ問題はopen/closedとも重複しない。
4. Bot PRの通常CIが承認待ちなら、人がCI実行を許可して確認する。作成前の生成ジョブのテストは既に必要条件として実行済み。#77は検証文書のためマージしない。
5. 停止は既存 `STEP2_ENABLE_PR_WRITES=false`。分析・Issueは継続。新しいレシピ追加には別の人間レビュー付きPRと原因再現・回帰が必要。

参照：
- https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced/
- https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum/
- https://docs.github.com/en/actions/concepts/security/github_token

## 検証範囲の区別

Python282件・JavaScript75件、商品照合/送料/数量/楽天安全性・構文の固定回帰、3幅の模擬レシピが成功。公開診断は上記runで全18画面成功。最終候補の18画面前後比較はPRのSTEP 3 UI verification artifactで確認する。画像・JSONは30日保持するため、レビュー時に保存する。

共通publisherの実GITHUB_TOKEN生成と重複抑止は#77の既存runで実証済み。新UIレシピの実トークンによる無人PR生成は、この未マージDraftからは実行しない。固定CSS生成・proof拒否・Draft API・重複抑止は模擬publisherで検証済み。マージ後の定期runでは、対象が本PRで解消済みならNO_SAFE_FIXが正しい。追加の実トークン確認には既存の手動検証workflowをcreate→再実行し、DO NOT MERGEの#77が再作成されないことを確認する。UIを故意に本番で壊して検証しない。

QAは固定6ページの機械診断であり、全ページのアクセシビリティ適合やUX原因を証明しない。楽天API検索は空応答を固定した操作確認で、購入・計測送信は行わない。重なり/コントラスト等の未確定項目はINVESTIGATEのまま。機能追加と収益向上は未実施。
