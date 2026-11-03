"""Build one question-first buying guide, without modifying catalog or prices."""
from __future__ import annotations

import shutil
import re
from pathlib import Path

SITE = Path("site")
SITE_URL = "https://stusaurus.github.io/daily-cost-jp/"
DEST = "tools/laundry-cost-per-wash/"
SCRIPT = "/daily-cost-jp/assets/laundry-per-wash.js"

PAGE = r'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>洗濯洗剤は何セット買う？1回費用・必要購入量・支払総額を比較 | 日用品コスパ比較</title>
<meta name="description" content="洗剤A・Bの使用量と月の洗濯回数から、1〜12か月分の必要セット数、購入支払額、使い残しを計算。1回単価が安くても買いすぎになるかを比較します。">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://stusaurus.github.io/daily-cost-jp/tools/laundry-cost-per-wash/">
<style>
:root{color-scheme:light;--bg:#f7f5f1;--ink:#242322;--muted:#625e5b;--accent:#b3261e;--line:#ded9d3;--card:#fff}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;color:var(--ink);background:var(--bg);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif}
a{color:#81291f;text-underline-offset:3px}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #166f81;outline-offset:3px}
.wrap{width:min(940px,calc(100% - 32px));margin:auto}
.skip{position:absolute;top:-100px;left:12px;background:#fff;padding:8px;z-index:5}
.skip:focus{top:8px}
.site-nav{background:#fff;border-bottom:1px solid var(--line)}
.site-nav .wrap{min-height:64px;display:flex;justify-content:space-between;align-items:center;gap:16px}
.site-nav a{font-weight:700;text-decoration:none}
.site-nav nav{display:flex;flex-wrap:wrap;gap:18px;font-size:13px}
.hero{padding:46px 0 32px;background:radial-gradient(circle at 90% 0%,#f4d8c6 0%,transparent 43%),#f2eee9}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:.09em;color:#9b281e}
h1{font-size:clamp(30px,5vw,48px);line-height:1.27;margin:12px 0 18px;letter-spacing:-.04em}
.hero p{max-width:660px;color:#48433f;margin:0;font-size:16px}
.crumb{font-size:12px;color:var(--muted);margin-bottom:18px}
main{padding:30px 0 60px}
section{margin-bottom:28px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:24px}
h2{font-size:clamp(21px,3vw,27px);line-height:1.35;margin:0 0 12px}
h3{font-size:18px;margin:0 0 12px}
p{margin:8px 0 12px}
.intro-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.intro-grid p{background:#fff;padding:14px;border:1px solid var(--line);border-radius:12px;margin:0;font-size:13px}
.intro-grid b{display:block;color:#89271f;margin-bottom:3px}
.editor-note{font-size:13px;color:var(--muted)}
.calc-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px}
.secondary{border:1px solid #c6b8ae;border-radius:9px;background:#fff;padding:8px 14px;color:#6b2c21;cursor:pointer;font-size:14px;font-weight:700}
.offer-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.offer{background:#fcfaf8;padding:18px;border:1px solid var(--line);border-radius:14px}
.offer:nth-child(2){background:#f9fbfa}
.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}
.field{min-width:0}
.field label{display:block;font-size:13px;font-weight:700;margin-bottom:4px}
.field input,.field select{width:100%;min-height:46px;border:1px solid #b7b0a8;border-radius:9px;padding:8px 10px;background:white;font:inherit}
.field small{display:block;color:var(--muted);font-size:11px;margin-top:4px}
.wide{grid-column:1/-1}
.calc-actions{display:flex;align-items:end;flex-wrap:wrap;gap:12px;margin-top:18px}
.calc-actions .field{flex:1 1 180px;max-width:220px}
.primary{background:var(--accent);color:#fff;border:0;border-radius:11px;font:inherit;font-weight:800;padding:13px 20px;min-height:48px;cursor:pointer}
.results{border-left:5px solid var(--accent);background:#fffaf6}
.purchase-horizon{border-top:1px solid var(--line);margin-top:20px;padding-top:20px}
.purchase-horizon .purchase-note{font-size:13px;color:var(--muted)}
.purchase-horizon .result-item span{display:block;font-size:14px}
.purchase-horizon .verdict{font-size:18px}
.result-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}
.result-item{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px}
.result-item strong{font-size:clamp(24px,4vw,34px);display:block;color:#84251e}
.result-item small{color:var(--muted)}
.verdict{font-size:20px;font-weight:800}
.error{color:#a21e16;font-weight:700}
.hint{border:1px solid #ecd8ca;background:#fff8ef;padding:16px;border-radius:12px}
.steps{padding-left:1.3em}
.steps li{margin-bottom:8px}
footer{padding:28px 0;background:#2b2928;color:#e9e4e1;font-size:13px}
footer a{color:#fff}
@media(max-width:660px){.site-nav .wrap{align-items:flex-start;flex-direction:column;padding:12px 0}.hero{padding:30px 0}.panel{padding:17px}.offer-grid,.intro-grid{grid-template-columns:1fr}.offer{padding:14px}.calc-actions{display:block}.calc-actions .field{max-width:none;margin-bottom:12px}.primary{width:100%}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style>
<script src="/daily-cost-jp/assets/laundry-per-wash.js" defer></script>
</head>
<body>
<a class="skip" href="#main">本文へ移動</a>
<header class="site-nav"><div class="wrap"><a href="/daily-cost-jp/">日用品コスパ比較</a><nav aria-label="主なページ"><a href="/daily-cost-jp/categories/laundry/">洗剤の価格比較</a><a href="/daily-cost-jp/categories/">カテゴリ一覧</a></nav></div></header>
<div class="hero"><div class="wrap">
<div class="crumb"><a href="/daily-cost-jp/">ホーム</a> ／ <a href="/daily-cost-jp/categories/laundry/">洗濯洗剤</a> ／ 1回の費用</div>
<div class="eyebrow">HOW MUCH PER WASH?</div>
<h1>洗濯洗剤は<br>何セット買うとお得？</h1>
<p>「単価は安いのに、まとめ買いで支払いが高い」。そんな買いすぎを防ぐため、<strong>洗濯回数から必要なセット数・支払額・余り</strong>まで計算します。洗剤A・Bをあなたの条件で比較できます。</p>
</div></div>
<main id="main" class="wrap">
<section class="intro-grid" aria-label="このページで分かること">
<p><b>01｜1回の費用</b>濃縮度による使用量の違いを反映</p>
<p><b>02｜実際に買うセット数</b>1〜12か月分の使用量から算出</p>
<p><b>03｜買いすぎの防止</b>見積支払額と使い残しを表示</p>
</section>
<section class="panel" aria-labelledby="calc-title">
<div class="calc-head"><div><div class="eyebrow">自分の条件で比べる</div><h2 id="calc-title">洗剤A・洗剤Bを比較</h2></div><button id="wash-sample" type="button" class="secondary">架空の入力例を試す</button></div>
<p class="editor-note">税込セット価格、送料、1個分の内容量とセット入り数、製品の表示にある1回使用量を入力。gとmLは換算せず、各製品の表示単位をそのまま使います。</p>
<form id="wash-calc" novalidate>
<div class="offer-grid">
<fieldset class="offer"><legend><h3>洗剤A</h3></legend><div class="fields">
<div class="field"><label for="wash-a-price">セットの税込価格（円）</label><input id="wash-a-price" type="number" min="0.01" max="1000000000" step="any" inputmode="decimal" required placeholder="例：598"></div>
<div class="field"><label for="wash-a-shipping">追加送料（円）</label><input id="wash-a-shipping" type="number" min="0" step="any" inputmode="decimal" placeholder="0なら空欄"></div>
<div class="field"><label for="wash-a-content">1個の内容量</label><input id="wash-a-content" type="number" min="0.01" step="any" inputmode="decimal" required placeholder="例：1000"></div>
<div class="field"><label for="wash-a-packs">セット入り数</label><input id="wash-a-packs" type="number" min="1" max="100000" step="1" value="1" required></div>
<div class="field"><label for="wash-a-unit">使用量の単位</label><select id="wash-a-unit"><option value="mL">mL</option><option value="g">g</option><option value="個">個</option></select></div>
<div class="field"><label for="wash-a-dose">1回の使用量</label><input id="wash-a-dose" type="number" min="0.01" step="any" inputmode="decimal" required placeholder="ラベル表示量"></div>
</div></fieldset>
<fieldset class="offer"><legend><h3>洗剤B</h3></legend><div class="fields">
<div class="field"><label for="wash-b-price">セットの税込価格（円）</label><input id="wash-b-price" type="number" min="0.01" max="1000000000" step="any" inputmode="decimal" required placeholder="例：1880"></div>
<div class="field"><label for="wash-b-shipping">追加送料（円）</label><input id="wash-b-shipping" type="number" min="0" step="any" inputmode="decimal" placeholder="0なら空欄"></div>
<div class="field"><label for="wash-b-content">1個の内容量</label><input id="wash-b-content" type="number" min="0.01" step="any" inputmode="decimal" required placeholder="例：900"></div>
<div class="field"><label for="wash-b-packs">セット入り数</label><input id="wash-b-packs" type="number" min="1" max="100000" step="1" value="1" required></div>
<div class="field"><label for="wash-b-unit">使用量の単位</label><select id="wash-b-unit"><option value="mL">mL</option><option value="g">g</option><option value="個">個</option></select></div>
<div class="field"><label for="wash-b-dose">1回の使用量</label><input id="wash-b-dose" type="number" min="0.01" step="any" inputmode="decimal" required placeholder="ラベル表示量"></div>
</div></fieldset>
</div>
<div class="calc-actions"><div class="field"><label for="wash-monthly">月の洗濯回数（回）</label><input id="wash-monthly" type="number" min="1" max="1000" step="1" value="20" required></div>
<div class="field"><label for="wash-period">何か月分を買う？（1〜12か月）</label><input id="wash-period" type="number" min="1" max="12" step="1" value="3" required></div>
<button type="submit" class="primary">必要セット数と購入額を比較する</button><button type="reset" class="secondary">入力をクリア</button></div>
<p id="wash-example-note" class="editor-note" hidden>※これは計算を試すための架空の金額・使用量です。実売価格ではありません。</p>
<p id="wash-error" role="alert" class="error" aria-live="polite"></p>
</form>
</section>
<section class="panel results" id="wash-result" aria-live="polite" aria-labelledby="result-title" hidden>
<h2 id="result-title">あなたの条件での計算結果</h2>
<div class="verdict" id="wash-verdict"></div>
<div class="result-grid"><div class="result-item"><small>洗剤A／1回あたり</small><strong id="wash-a-cost"></strong><span id="wash-a-uses"></span></div><div class="result-item"><small>洗剤B／1回あたり</small><strong id="wash-b-cost"></strong><span id="wash-b-uses"></span></div></div>
<p>同じ洗濯回数で使うと、差額は<strong id="wash-month-diff"></strong>／月、<strong id="wash-year-diff"></strong>／年（概算）です。</p>
<p class="editor-note">※1回単価と月・年の差は、購入した洗剤を使い切る前提の理論値です。洗浄力・香り・使い勝手は別途確認してください。</p>
<div class="purchase-horizon"><h3>指定期間に必要な分だけ買った場合</h3><p>比較条件：<strong id="wash-purchase-count"></strong>。洗剤を使い切れるまでの単価と、今必要な分を買う支払額は別です。</p>
<div class="result-grid"><div class="result-item"><small>洗剤A／購入見積（送料一定の場合）</small><strong id="wash-a-payment"></strong><span id="wash-a-sets"></span><span id="wash-a-unused"></span></div><div class="result-item"><small>洗剤B／購入見積（送料一定の場合）</small><strong id="wash-b-payment"></strong><span id="wash-b-sets"></span><span id="wash-b-unused"></span></div></div>
<p class="verdict" id="wash-purchase-verdict"></p><p id="wash-purchase-tradeoff" class="hint"></p>
<p class="purchase-note">計算方法：必要量＝月の洗濯回数×月数×1回使用量。購入セット数は必要量÷セット総内容量を切り上げ、支払見積＝税込セット価格×必要セット数＋追加送料（同一注文で1回だけ加算）。余りは購入総内容量から必要量を引いています。gとmLは換算しません。価格・送料は購入数・配送先・クーポン・在庫によって変わる場合があるため、最終額は販売店で確認してください。</p>
<p><a href="/daily-cost-jp/categories/laundry/" data-conversion-source="product_guide">洗濯洗剤の現在の購入候補を見る →</a></p></div>
</section>
<section class="panel" aria-labelledby="math-title">
<h2 id="math-title">計算の仕組み</h2>
<p>セット総内容量 ＝ 1個の内容量 × 入り数。使える回数 ＝ セット総内容量 ÷ 1回の使用量。期間の必要量は、洗濯回数×1回使用量で求めます。</p>
<p><strong>1回あたりの洗剤代 ＝（税込セット価格 ＋ 追加送料）÷ 使える回数</strong>。月額・年額の差は、この1回単価の差にご家庭の洗濯回数を掛けています。</p>
<p class="hint">濃縮タイプと通常タイプは、同じ100mLの価格だけでは比べられません。製品ラベルに記載された<strong>同じ水量・洗濯物量の標準使用量</strong>をそれぞれ入力してください。</p>
</section>
<section class="panel" aria-labelledby="mistakes-title">
<h2 id="mistakes-title">比較するときの3つの注意点</h2>
<ol class="steps"><li><strong>追加送料はセット全体へ加算。</strong>送料無料条件のために不要な商品を追加した費用は無視しないでください。</li>
<li><strong>単位は各製品の表示に合わせる。</strong>gとmLを勝手に同じ量とみなさず、洗剤ごとに内容量・使用量の単位を一致させます。</li>
<li><strong>差額だけで選ばない。</strong>仕上がり・用途・肌への適合性・保管場所・実際の洗濯条件は別途確認してください。</li></ol>
<div class="hint"><strong>商品価格も探したい場合</strong><p>楽天市場で送料込みの洗濯洗剤を比較できるページを用意しています。現在の掲載候補から商品を探し、確認できた価格・使用量をこの計算に入れてください。</p>
<a href="/daily-cost-jp/categories/laundry/">洗濯洗剤の送料込み商品を比較する →</a></div>
</section>
</main>
<footer><div class="wrap"><p>日用品コスパ比較／暮らしの価格研究所</p><p>この計算はブラウザ内で処理し、入力した価格・使用量は送信・保存しません。ページ閲覧のアクセス解析は別途実施しています。</p><p>当サイトは楽天アフィリエイトを利用しています。紹介先で購入すると運営者に報酬が発生する場合があります。楽天市場の公式サイトではありません。</p><a href="/daily-cost-jp/">トップページへ戻る</a></div></footer>
</body></html>
'''


def build(site: Path = SITE) -> None:
    category = site / "categories/laundry/index.html"
    if not category.is_file():
        raise RuntimeError("laundry category missing; do not publish orphan page")
    page = site / DEST / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(PAGE, encoding="utf-8")
    script = Path(__file__).resolve().parent / "assets/laundry-per-wash.js"
    assets = site / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(script, assets / "laundry-per-wash.js")

    raw = category.read_text(encoding="utf-8")
    if 'id="wash-cost-link"' not in raw:
        # Do not reserialize the source: STEP6 protects exact approved FAQ bytes.
        main = re.search(r"<main\b[^>]*>", raw, flags=re.IGNORECASE)
        if main is None:
            raise RuntimeError("category page main missing")
        link = (
            '<section id="wash-cost-link" style="padding:18px;margin:16px 0;border:1px solid #dcd3ca;'
            'border-radius:14px;background:#fff8f1">'
            '<h2 style="font-size:19px;margin:0 0 7px">洗剤は何セット買う？家庭の洗濯回数で比較</h2>'
            '<p>濃縮タイプやまとめ買いは使用量も含めて比べましょう。'
            '洗剤A・Bの必要セット数・支払総額・使い残しまで計算できます。</p>'
            '<a href="/daily-cost-jp/tools/laundry-cost-per-wash/">'
            '何セット買うとお得か計算する →</a></section>'
        )
        category.write_text(raw[:main.end()] + "\n" + link + "\n" + raw[main.end():],
                            encoding="utf-8")
    print("Built question-first laundry comparison with verified internal link.")


if __name__ == "__main__":
    build()
