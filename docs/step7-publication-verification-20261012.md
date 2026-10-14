# STEP7着手時の公開確認（2026-10-12）

- #93: 00:34:35 UTCに人間がマージ、commit 8a46640a2ce0c1130ec51307fdc68f0748d0009e。#92: 00:50:47 UTCに人間がマージ、commit be10487ca396089bf4da99aa15e3db9a4fa11944。
- #93は運用コード/ledger変更であり、新しいSEO表示を公開する変更ではない。#92の公開buildは https://github.com/stusaurus/daily-cost-jp/actions/runs/38189575377 で成功。
- 公開build-info.jsonを直接取得しcommit be10487ca396089bf4da99aa15e3db9a4fa11944と照合。トイレットペーパーの公開HTMLにSTEP6 comparison-help-v1枠があることを直接確認。merge/CI成功だけを公開の根拠にしていない。
- トイレットペーパーの実公開日はJST 2026-10-12 / GSC Pacific 2026-10-11。release ledgerへrecipe comparison-help-v1:toilet-paper、公開commit、Pacific日付を追加する（レビュー待ち）。
- #77は未変更・未マージ。金融データを本書/公開repoに記録しない。
