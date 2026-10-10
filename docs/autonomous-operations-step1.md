# 日用品サイト：自動運営 STEP 1（改善判断キュー）

## 完成すること

既存の日次商品更新と3日ごとのGA4/Search Console監査に、**全体の改善優先順位を自動決定する工程**を追加する。

- GitHub Actions GA4 Three-Day Read-Only Analysis は約3日ごとに実行（従来通り）。
- 同じ実行で取得したGA4・Search Console統合レポート、PC/390px/320pxのブラウザ監査を利用。
- 公開中の quality-status.json（直近72時間以内）から商品品質のエラー・警告を取得。更新日時が古ければ「不明」とし、正常と誤判定しない。
- 公開サイトの5 URLをHTTP監査し、アクセス不能・商品品質エラー・購入導線異常を検索CTRより優先。
- P0=緊急確認、P1=計測や購入導線を優先点検、P2=改善調査候補として、日用品サイト専用の **最大20件の構造化リスト**を出力。
- GA4計測不明、Search Console不在、商品品質レポート未取得、ブラウザ監査中断はデータ未取得として扱う。
- audit-results/autonomous-operations.json と .md を実行サマリー・30日保管アーティファクトへ出力。

## 毎回「次」と言う必要を減らす仕組み

- 同じ問題をGitHub Issueとして何件も増やさない。**既存のIssueを探して1件だけ維持・更新**する。
- 優先順位・問題の種類・対象ページを構造的なIDで比較し、検索表示数などの小さな増減でIssueを更新しない。
- 優先度や問題の種類が変わった場合は既存Issueを更新。
- 同じ問題が続いていても、最後の更新から7日以上経てば最新の実行結果へのリンクを更新する。
- 何も検出されなければ新しいIssueを作らない。
- Issueの管理はGitHub Actionsの issues:write だけで行い、サイトの contents は read。権限不足ならIssue同期は失敗してもレポートは残る。

## 既存機能と安全性

- 既存の楽天価格取得、数量・送料判定、厳格な商品照合、サイト公開、GA4/GSC接続を変更しない。
- URLの安全な同一サイト検証を行い、商品名や検索語、生のメールアドレスをIssueに転載しない。
- Search Consoleのクリックと楽天のクリックは、同じユーザーが行ったとは仮定しない。売上確定や購入率は計算しない。
- **この段階では改善PRの自動作成・自動マージ・自動公開は有効化しない。**
- 自動化の次の段階で修正PRを作る場合でも、最初は人のレビューを必要とする。商品価格、送料、楽天リンク、SEOタイトル、安全判定やデザインの変更を無断で公開しない。

## 確認方法

GitHub → Actions → GA4 Three-Day Read-Only Analysis → Prioritize operations and maintain one rolling issue のSummary。

1件のGitHub Issueの題名：【自動運営】日用品サイトの改善判断（最新）。

## リリース前後のテスト

- オフラインの単体テストでP0/P1/P2、曖昧なGSC/GA4指標、同一Issueの重複抑止、PRブランチでの書き込み拒否を確認。
- PRのGitHub Actionsで既存のWebサイト全体QA・PC/スマホ監査・Lighthouseを通す。
- main反映後、認証済みのGA4/GSCとブラウザ監査の実データで初回 autonomous-operations-triage が出力できたか確認。
- 新しいIssueが初回から作成されるかは実際の発見内容とGitHub Issue権限による。緑色のworkflowだけでIssue作成成功と断定しない。
