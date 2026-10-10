# 自動運営 STEP 2：安全な改善準備

既存の3日分析と単一Issue更新は変更せず、同じrunのSTEP 1 JSONを後続ジョブが読む。main上の分類・テストは、この実装PRを人が承認・マージした後に有効になる。PRの書き込みは初期状態で無効とし、実トークン検証後に人が明示的に有効化する。今回の作業ではmainや本番を更新しない。

## 判定と対応範囲

- AUTO_FIX：ローカルで独立検証した、運営ドキュメントの安全方針欠落のみ。対象は `docs/autonomous-operations-step1.md`、一意の既知見出し、固定の追記文。既存の同等方針があれば変更しない。サイトに影響しない最小の復元処理。
- INVESTIGATE：GA4の区分不明、稼働やブラウザ異常、未取得情報、未知のコード。Issue本文・指示・auto_fix_allowed=true・外部提供recipeは実行許可にしない。
- HUMAN_ONLY：商品品質・価格・送料・数量・楽天リンク・SEOコピー・安全判定。今回のCTR仮説も保守的にこちらに置き、人が調査・変更を判断する。

サイトコードの自動修正レシピはまだ登録していない。問題ごとに原因・最小差分・回帰テストを人が確認した別PRで追加する必要がある。単に未知コードをAUTO_FIXに昇格させる設定は設けない。

## 実行順と安全装置

1. 同一runの `autonomous-operations-triage` artifactを読む。欠落・異種サイト・形式不正・6時間超の古いレポート・未来時刻は失敗として停止する。
2. 構造化された問題コードを分類し、固定レシピの前提をローカルで確認する。候補なしならPRなし。
3. 変更後に全Python/JS単体・回帰テスト、Python/JS/Worker構文検査を実行。価格、送料、数量、商品照合、楽天リンクの既存テストを含む。成功時だけbase SHAと候補ハッシュに結び付いたreceiptを出力する。
4. 公開工程は対象ファイル、固定変換の再計算、差分、未知の未追跡ファイル、receiptを再検証。テスト用tokenはなく、GitHub tokenは公開ステップにだけ渡す。
5. 全PR履歴をページングし、固定fingerprint/branchで閉じたPRも重複抑止。既存の孤立ブランチは上書きせず人の確認へ。mainが動いたら次の分析まで見送る。
6. mainのSHAから専用ブランチを作成し、最大1件のDraft PRを生成する。main・デプロイ・マージAPIは呼ばない。既存のworkflow concurrencyで生成処理を直列化する。
7. 分類、テストreceipt、公開結果を30日artifactに残す。失敗時はjobが失敗し、本番は維持。成功したフリや空PRは作らない。

`contents:write / pull-requests:write / actions:read` は定期生成ジョブだけ。手動トークン検証はcontents:write / pull-requests:writeのみ。既存の分析・Issueジョブの権限は維持。リポジトリでActionsのPR作成が禁止されている場合は生成APIが失敗し、実行結果で確認が必要。追加PATは要求しない。

GITHUB_TOKENでのPRイベントから通常CIが即時に走ると仮定しない。GitHub公式仕様ではopened/synchronize/reopenedが承認待ちで生成される場合もある。候補の全テストはPR作成前の生成ジョブで実行済みにし、run URLと候補ハッシュをPR本文に掲載する。既存pull_request CIはそのまま残す。

UIの変更を扱うレシピは未登録。文書だけの修正にはPlaywrightは不要。将来サイト変更レシピを追加する際は、PC/390px/320pxの候補画面検証を必須にしてから登録する。

公式参照：https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow

## 初回調査：Issue #74

実データはmain `b3984879496960a6ed00422472c12eab581c5ace` のrun `38051374404` のGA4/GSC・STEP 1 artifactを取得して確認。

- operator_testカスタムディメンションは登録済み。2026-10-06〜08の3日集計は楽天クリック3件、3件すべて運営者テスト、区分不明0件。
- 一方で28日ページ集計はトップの区分不明11件。クライアントの全イベントwrapperはoperator_test=0/1を付与し、読み取り側はGA4 metadataの登録状況を確認済み。過去のイベント・登録/実装時期・28日窓の違いの追加照合が必要。未登録とも現在のコード不具合とも断定しない。過去イベントの属性を推測で補正しない。
- 最新公開quality-status.jsonはエラー0・警告1。maskの取得候補で数量不明が半数超という警告。正しく除外している候補の警告を、掲載商品の誤表示と混同しない。判定の緩和、価格や数量の補正はしない。
- 検索CTRは2026-09-10〜10-07の暫定値。laundry 117表示/2クリック/1.71%/平均13.32位、tissue 124/2/1.61%/12.02位、toilet-paper 81/1/1.23%/12.36位。公開可能なクエリ行は0件で、需要や特定クエリとの不一致は断定できない。GA4とGSCは期間・母集団が違うため購入率として結合しない。タイトル変更には人の判断が必要。

## 初回検証の範囲

- 実STEP 1レポートの読み取り・全5件の分類・安全な候補0件で修正PRを作らない挙動を実行確認。
- 一時Gitリポジトリと模擬GitHub APIで、安全方針欠落→固定差分→Draft作成payload→再実行の重複抑止を検証。closed PR、2ページ目の履歴、孤立ブランチ、main更新、receipt不正、危険差分、非main、run ID不正も検証。
- 模擬APIによる機構検証は、実GitHubでGITHUB_TOKENのPR書き込み成功を証明するものではない。実データからの自動修正PRは未生成。実装PRの通常CIと、main反映後の生成ジョブは区別する。
- 実装PRは最終確認後にレビュー可能へ移行するが、マージは人の承認待ち。生成する修正PR・トークン検証PRは常にDraft。mainへ反映後、最初の3日分析で分類artifact・生成job・権限結果を確認する。今回、自動マージや本番公開は行わない。


## 最終監査：2026-10-11 JST

監査開始時点のPR #75 headは `702831e23b4fef3120d9fe290893ecfdc28a024f`、mainは `b3984879496960a6ed00422472c12eab581c5ace`。

| 証拠 | 状態 | 意味 |
|---|---|---|
| Actions run 38054288463 | success | 全単体・構文・実商品ビルド・生成画面QA・Lighthouse実行成功 |
| Actions run 38054288426 | success | STEP 1回帰・公開4カテゴリ×1440/390/320pxの12画面PASS |
| commit status netlify/daily-cost-api/deploy-preview | failure | 旧サービスの公開ディレクトリnetlify-publicが存在しない |
| Netlify deploy 6aca37b9731a5900087f115b | error / published_at=null | Preview失敗で、公開中deployは置き換えていない |
| GET branches/main | protected=false、enforcement_level=off、contexts=[] | Netlifyの赤いステータスは必須チェックではない |
| GET rulesets | [] | このAPIで取得できるルールセットなし |
| repository metadata | allow_auto_merge=false | リポジトリの自動マージ機能は無効 |
| raw PR metadata | mergeable=true、mergeable_state=unstable、auto_merge=null | 差分競合なし。赤い旧外部statusはあるが、自動マージ予約なし |

branch-protection専用APIは接続の管理権限不足で403。そのため権限を変更せず、一般branches/main APIの保護情報で必須チェック状態を確認した。GitHubによる必須レビューの強制は設定されていないため、承認待ちはこの作業の運用方針とDraft生成により維持する。保護設定を弱めたり成功statusで失敗を偽装したりしない。

Netlifyは現行のGitHub Pages/Cloudflare Workerとは別の旧プロジェクト。PR #75の題名に公式の `[skip netlify]` を追加し、新しいPreviewの実行を抑止する。旧失敗の履歴は削除・偽装しない。旧連携全体の停止はこの接続の書き込みツールでは扱えず、管理画面は認証待ちのため未実施。ログイン済み管理者がdaily-cost-apiのBuild settingsでStop buildsを選択する場合も、サイト削除、環境変数削除、ドメイン変更、アプリ全体のアンインストールは不要。このPRではそれらの操作を行わない。同じNetlify専用スキップをSTEP 2が生成する両種類のDraftの題名・コミットにも付与し、旧Preview/buildの起動を抑止する。GitHub Actionsをスキップする指定は付けない。STEP 2以外のPRやpushに対する旧連携は残る。

公式参照：https://docs.netlify.com/deploy/manage-deploys/manage-deploys-overview/

### マージ後の実GITHUB_TOKEN検証と有効化

この手順はmain反映後に実施する。PRブランチから本番トークン検証を動かす必要はない。

1. 人がPR #75の最新headのActionsを確認して承認・マージする。本作業ではマージしない。
2. マージで起動する3日分析の初回runを確認する。既存GA4/GSC、健康監査、単一Issue #74、STEP 2分類/全テストが維持されていることを確認。未取得データは未取得として報告される。PR書き込みはデフォルトで `PR_WRITES_DISABLED_PENDING_TOKEN_VERIFICATION` となる。ここで失敗したら書き込みを有効化しない。
3. GitHub Actions → `STEP 2 Token Verification (manual, never merge)` → Run workflow、branch=main、`confirm_documentation_only_draft=true` で一度実行する。falseのままなら実行されず、検証成功とは扱わない。
4. 全Python/JavaScript/商品照合/送料/数量/楽天リンク/構文テスト後、同じ固定publisherで実 `secrets.GITHUB_TOKEN` が専用ブランチと1件のDraft PRを作成する。差分は `docs/step2-token-verification.md` の固定検証文書だけ。既存文書を削除したり模擬の不具合をmainへ入れたりしない。
5. `step2-token-verification` artifactの `step2-tests.json` がPASS、`step2-result.json` がDRAFT_CREATEDであることを確認。publisherは実PRを再取得し、作者github-actions[bot]・draft=true・auto_merge=null・base=main・head SHA・差分が固定新規文書1件のみ・実行中のmain SHA不変を検証する。runが緑でもverify-token jobがskipped/結果artifactがない場合は未検証。
6. 検証PRは **DO NOT MERGE**。人が差分とrun URL/候補ハッシュを確認する。必要なら人が閉じる。自動マージ・自動削除はしない。二度目の手動検証では同じfingerprintとブランチによりDUPLICATE_OR_DISMISSEDとなり、新規PRを追加しない。これが重複抑止の実トークン検証になる。閉じた後も再作成しない。
7. 実トークン検証が成功したときだけ、repository Settings → Secrets and variables → Actions → Variablesに `STEP2_ENABLE_PR_WRITES`=`true` を設定する（secretではない）。未設定/falseでは定期分類・テストだけを続け、PRを書かない。この値は人の有効化判断であり、検証成功を自動的に証明するものではない。
8. 既存 `GA4 Three-Day Read-Only Analysis` をmainで手動実行し、STEP 1 JSON読み取り、分類、候補なし時のNO_SAFE_FIX、Issueの単一維持を確認する。現在のIssue #74はAUTO_FIXに該当しない。次の3日周期でも同じ条件を確認する。
9. 初回修正PRが生じた場合はDraft、1 run最大1件、同一問題で重複なし、固定文書以外の変更なし、作成前テストrunの成功を確認する。商品・SEO・Google設定は人の別判断が必要。
10. Pagesの最新公開run/公開コミット、トップと重点3カテゴリ/quality-status.json、両Workerの `/health` を読み取りで確認する。通常の日次更新が動いた場合はSTEP 2による変更と区別し、公開履歴のactor/runを確認。楽天への実クリック・Googleイベント送信・手動デプロイは不要。

403（PR作成禁止）ならartifactにGITHUB_API_FAILURE/http_status=403を残し、書き込み無効を維持する。管理者はrepository Settings → Actions → General → Workflow permissionsの「Allow GitHub Actions to create and approve pull requests」が組織方針上許可されるか確認する。この設定はPR作成だけでなく承認も許可するため、無断で変更せず、人が判断する。publisherはレビュー/承認APIを呼ばない。PAT追加、管理権限追加、チェックの強制スキップでは解決しない。

API途中失敗で専用ブランチだけ残った場合は次回EXISTING_BRANCH_REQUIRES_REVIEWで停止する。人が枝とcommit/test evidenceを調べるまで上書きしない。main変更を検知したときは次回まで見送り、トークン検証中なら成功とは扱わない。

### 停止手順

問題があれば `STEP2_ENABLE_PR_WRITES` をfalseに戻す。定期分析と単一Issueは継続し、STEP 2のPR書き込みだけ停止する。トークン検証workflowは手動専用なので未実行なら書き込みなし。既存Pages/Worker設定や商品判定を変更する必要はない。

### 今回のローカル確認

Python 269件、JavaScript 71件、Python/JavaScript/Worker構文検証は全成功。Pagesのトップ・洗濯洗剤・ティッシュ・トイレットペーパー・quality-status.jsonはHTTP 200で監査前の内容を保存した。両Workerの直接health取得はこの実行環境からCloudflare 403 / error code 1010となり、正常とは認定していない。既存Workerコード・設定・公開先は変更せず、マージ後に既存の読み取り監査runまたは通常の利用環境から再確認する。
