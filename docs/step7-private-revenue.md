# STEP7：非公開の月次収益計測

## 保存境界

本機能は公開サイトのビルドから独立したローカルCLI。**実CSV、注文情報、収益集計、DB、列対応設定、認証情報をGitHub、Actions、Pagesへアップロードしない。** Git管理された場所・その配下・symlinkを拒否する。GITHUB_ACTIONS/CI環境で金融CLIを拒否する。非公開フォルダ0700、入力ファイル/DB/出力0600が必要。この権限検証はPOSIX環境（Mac/Linux等）向けで、WindowsネイティブACLの検証は未実装。stdoutは固定の処理状態のみで金額・注文名・行内容・ファイル名を出さない。

DBに残すものはアカウント別・報告種別別・月別の集計、取得時刻、重複防止digest。注文ID/商品名/生CSVはDBにも保存しない。元CSVは利用者の非公開フォルダ内で管理し、バックアップ先も非公開にする。公開防止CIはCSV/DBや金融レポートのmarkerを検査する。gitignoreは追加防御であり、保存先をrepo内へ変える理由にならない。

コードと自動テストにある数値・注文ラベルは合成fixtureで、実アカウントの成果ではない。

## 楽天公式調査（2026-10-12）

- https://affiliate.rakuten.co.jp/guides/report/ : PCで表示項目を選び、CSVをダウンロードできる。選択項目により列が変わるため、未提供の実CSVヘッダーを推測しない。
- https://affiliate.faq.rakuten.net/detail/000001097 : 期間別成果は未確定、注文詳細は確定/未確定/破棄、成果報酬レポートは確定報酬という違いを確認する。
- https://affiliate.faq.rakuten.net/detail/000001098 : 確定と付与の時期は別。個別の遅延もあるため月の日付だけで確定と判定しない。
- https://webservice.rakuten.co.jp/documentation : 公開API一覧は商品/検索等。調査した公式公開資料に成果報酬取得APIを確認できなかった。APIが絶対に存在しない/自動取得が禁止という断定はしない。

今回は公式CSVの**手動取得**を選ぶ。ログインの自動化、認証Cookie収集、非公開内部APIの利用、秘密のGitHub Secret追加を行わない。

## 毎月の操作

1. 自分のPCで楽天公式へログインし、対象月の全件・全状態・全サービスを選ぶ。未確定の期間別CSVを成果報酬レポートと取り違えない。月末締めが終わった報告月を用いる。
2. 成果報酬（確定報酬）、注文詳細（3状態）、期間別クリックをそれぞれ取得。上限/フィルタ/分割/合計行混入がないことを画面で確認。ダウンロード項目と列名、日付書式、円の単位を確認する。公式側の列名・文字コードの固定保証は未確認。
3. CSV・列対応JSONをGit管理外の自分専用フォルダへ移す。チャットや公開Issueへ実CSVを添付しない。
4. 最初の実CSVに合わせて下のschemaを自分のPCで作る。未知列や形式は停止し、規則を緩めない。詳細明細の一意IDがない場合はdetail方式を使用せず、公式で確かめた月別状態合計を使うか実装者に安全な形式確認を依頼する。
5. 取り込み。再投入は重複防止。訂正や未確定→確定の変化は、全月を再取得したCSVと新しい取得時刻で `--replace` を使う。部分CSVを足し合わせない。
6. 3日分析の `ga4-three-day-report` artifactから **step7-google-monthly.jsonだけ**を対象月を含む名前で非公開フォルダへ保存・保持し、同じ暦月のレポートを生成。金融ファイルをActionsへ戻さない。
7. 月次JSON/Markdownと最大12か月の確定報酬履歴を自分のPCで確認。未取得月は0で補完せず、調査優先度は帰属/データ接続の確認として提示する。日用品サイト由来の報酬は、公式の確実な追跡根拠がないため常に未確認。アカウント全体の楽天報酬と、日用品だけのGoogle計測を同じ利用者の成約として扱わない。

例（環境変数名は専用。既存HOME等を上書きしない）：

```bash
REVENUE_PRIVATE_DIR="$HOME/daily-cost-private"
python scripts/step7_private_revenue.py --private-dir "$REVENUE_PRIVATE_DIR" init
# PC上でCSV/schema/Google月次JSONをこのフォルダに置き、chmod 600 を設定する。
python scripts/step7_private_revenue.py --private-dir "$REVENUE_PRIVATE_DIR" import-csv \
  --csv "$REVENUE_PRIVATE_DIR/official-report.csv" \
  --schema "$REVENUE_PRIVATE_DIR/schema.json" --account main \
  --month 2026-09 --exported-at 2026-10-12T01:00:00Z --complete-official-month
python scripts/step7_private_revenue.py --private-dir "$REVENUE_PRIVATE_DIR" report \
  --month 2026-09 --google "$REVENUE_PRIVATE_DIR/step7-google-monthly.json"
```

CLIの `--complete-official-month` は画面で全月・全件を確認した宣言であり、コードがCSVの由来を認証するものではない。実運用の正確性には、この確認が必須。ファイル内容も金額もCLIに表示させない。

## 列対応（この例の列名は仮であり、公式の実CSV形式と断定しない）

```json
{
  "kind": "confirmed_reward",
  "columns": {"period": "実CSVの報酬対象月列", "amount": "実CSVの確定成果報酬円列"},
  "period_format": "month_iso",
  "encoding": "utf-8-sig",
  "row_format": "summary"
}
```

- `confirmed_reward`: 公式成果報酬レポートの月次1行だけ。報酬対象月を使い、成果発生日/入金日へ置き換えない。日付書式はmonth_iso (`YYYY-MM`)/month_slash (`YYYY/MM`)/month_jp (`YYYY年MM月`)。
- `order_status`: `columns`はperiod/amount/statusと、detailならrow_id。row_formatはdetail（明細一意ID・同一IDの矛盾は拒否）またはstatus_totals（確定/未確定/破棄ごとに月次1行）。date_iso/date_slashは成果発生日で集計する。報酬レポートの確定額とは加算しない。欠落状態は未確認であり0で埋めない。
- `rakuten_clicks`: period/clicksの列対応。summary方式。日別なら同じ日を2回含めない。未取得日は不明として日別カバレッジを残す。月次合計は1行のみ。
- encodingはUTF-8 BOMまたはCP932を明示する。負数、数式、科学表記、小数、未確定日付、合計/明細混在、未知状態、空CSVは拒否する。0円はCSVに明示された0だけを保存する。

## Google月次集計と公開範囲

既存の3日分析・同じOIDC/readonly権限で直前の**暦月全体**を取得する。28日を暦月へ換算しない。GA4のproperty timezoneがAsia/TokyoであることをData API応答で確認し、sampling/thresholding/truncationは使用しない。GSCはPacific時間・finalデータ・3日待機。1日〜末日の同じ月ラベルで比較するが、時間帯が違うことを明示する。

公開artifactへ出すのは既存と同様のサイト単位Google集計のみ。検索語・商品名・Google認証情報・楽天報酬は出さない。クリックはoperator/非operatorフラグ/不明に分け、非operatorでも一般利用者の確認とはしない。空行・欠測・未接続を0や正常と扱わない。

新しいGoogle月次取得は任意段階で、失敗しても既存STEP1〜6を止めない。finance CLIは既存build・publisher・Pagesへ接続しない。自動PR書込の既存最大1件/停止スイッチを変更しない。

## 改善判断

月次レポートは確定報酬、注文詳細の確定/未確定/破棄、楽天クリック、独立したGSC/GA4の月次値を横に並べる。全ての金額は非公開。未接続は未確認。

アカウント全体の報酬が増えても、日用品のSEOやおすすめが成功したとは断定しない。帰属・期間・サンプルが揃わなければ評価保留。金融実績を公開Issue #74や自動Draft本文へ混ぜない。人間が非公開月次レポートを見て、商品品質を維持した改善の優先度を決める。

## 承認後の初回確認

1. 実装DraftとCI・匿名の合成fixture結果をレビューし、人間がマージする。
2. mainの通常3日分析でGoogle月次artifactの認証済み取得を確認する（PRでGoogle認証はしない）。
3. 初めての実CSVでヘッダー/文字コード/対象月/全件を自分のPC上で検証する。未提供のため、この部分は今回未検証。
4. 全月の確定報酬・他状態・クリックを取り込み、同一CSV再投入と訂正の置換を確認する。
5. 公開サイトには金融表示を追加しない。停止する場合はローカルCLIを実行しない。既存STEP1〜6は継続する。
