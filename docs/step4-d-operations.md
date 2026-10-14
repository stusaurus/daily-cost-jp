# STEP 4-D：段階導入・停止とロールバック

依存順は #80（監査）→#81（B）→#82（C）→D。全てDraft、人間承認待ち。先行マージ後に各PRのbaseをmainへ変更して差分・CIを再確認する。#77は絶対にマージしない。

## 実装と許可範囲

既存の06:00 JST日次ビルドに固定表示レイヤーを接続する。公開先・公開スケジュール・Pages環境・Worker設定は変えない。取得した現在の安全な商品を固定ルールに従って選択するだけ。`STEP4_ENABLE_CONTENT=true`は人間による固定ルールv1の事前承認を表す。初期は未設定（false）で表示を追加しない。`STEP4_PAUSE_CONTENT=true`は全購買目的枠を停止し、当日の安全な従来ランキングに戻す。新しい価格は推測せず、古い価格・URLをロールバックに再利用しない。

日次には直近成功したmainの3日分析から`step4-operations-feedback` artifactの正確な`step4-control.json`だけを読む。最大300KB、JSON100KB、main/schedule/manual/push、成功run、固定version、発行から4日以内を確認。URLは固定リポジトリのActionsのみ。署名付きartifact URLへリダイレクトするときAuthorizationを取り除く。権限不足・artifact未取得・古い/不正なfeedbackなら推薦を停止し、通常のサイトビルドは続ける。read-only Actions権限を既存ビルドに追加する。新しい書き込み権限やデプロイ経路は作らない。

3日分析には既存Google read-only権限による前後28日集計と購買診断を追加し、単一の既存Issueへ不足と停止理由を統合する。AUTO_CONTENTは固定の検証済み商品選択。根拠不足はINVESTIGATE。品質・価格・送料・URL・SEO・コード・CSS・新機能・安全判定はHUMAN_ONLY。STEP4は新たなコード修正レシピを許可しない。既存STEP2/3のpublisher、1分析最大1件、既存停止スイッチ`STEP2_ENABLE_PR_WRITES`、closed/open PR重複検査、main移動/ブランチ衝突検査、作成前全テストをそのまま使う。Botの通常pull_request CIが必ず起動するとは仮定しない。

## 悪化・品質異常

数量/送料/リンクなどの拒否が監査3カテゴリに出た場合、対象カテゴリ不足/取得異常/鮮度異常、手動pause、main feedback停止指示で目的別枠を付けない。少量候補なしは正常な空状態であり、無理に枠を埋めない。

利用反応の自動停止は、連続する28日窓が2つ、各28日のpage_view観測、operator登録済み、不明区分なし、対象4ページ合算で一般利用者page_view各1000件以上、前期間affiliate_click30件以上の場合だけ。イベント数/表示数が前期間の60%未満なら次の日次ビルドで目的別枠を停止し人間確認へ。これは保守的な停止基準であり、原因・統計的有意性・売上悪化の証明ではない。少数サンプルや不明のまま順位変更・無意味な商品ローテーションはしない。自動停止は品質ルールを緩和する権限ではない。

## 人間による有効化

1. #80→B→C→Dを順にレビュー、先行マージ後にbaseをmainへ変更しCI再確認。マージは人間のみ。
2. 全てmain反映後に既存3日分析をmainで手動実行。STEP1のIssue・STEP2/3の停止/最大1件制限とSTEP4の匿名測定・control artifactを確認。追加修正がなければNO_SAFE_FIXが正常。#77は触らない。
3. 固定ルール・画面・最新結果を承認し、GitHub repository variable `STEP4_ENABLE_CONTENT=true`を設定。停止用`STEP4_PAUSE_CONTENT`は未設定/false。新規APIキーは不要。
4. もう一度3日分析をmainで実行し最新feedbackを保存。既存日次ビルドを待つ、または人間が既存Pagesビルドを手動実行（X投稿はfalse）。この実装作業では公開しない。
5. 公開の`step4-content-state.json`と`purchase-recommendations.json`を確認。feedback run ID・ルールversion・鮮度・display_enabledを確認。各カテゴリに架空の候補がなく、元data.json価格・URL・数量が維持されていることをQAする。
6. `?test=1`でGA4受信を確認しテスト区分を確認。新しい診断・目的別のカスタムディメンションは必要に応じ人が登録する。楽天確定成果は別接続が必要。

停止は`STEP4_PAUSE_CONTENT=true`または`STEP4_ENABLE_CONTENT=false`にして次回既存ビルドで従来表示へ。コード/デザインの巻き戻しはrevert PR→人間マージ。即時停止したい場合のビルド手動実行も人間操作。

## 検証の限界

実GITHUB_TOKENでのSTEP2既存publisherは先行STEP2で実証済み。STEP4による新しい自動コードPRは意図的に作らない。新しいフィードバックartifactの本番トークン読み取り・認証済み新イベント集計・本番初回日次表示は、全PRマージ後のmainで確認が必要。現時点で本番稼働/収益改善と報告しない。

ブラウザ検証は公開取得コピーに未公開コードを適用する18組と、既存CIの実データ未公開ビルド。Google/楽天遷移を遮断する。長い推薦枠の切り抜きだけ固定ナビを撮影時に非表示にし、別の全ページ画像に通常ナビを残す。取得コピーは本番データを使用するが、本番表示変更ではない。
