"""Create high-intent SEO landing pages that lead into the site's comparison tools."""
from __future__ import annotations

from pathlib import Path

SITE = Path("site")
BASE = "https://stusaurus.github.io/daily-cost-jp/"

PAGES = [
    {
        "slug": "toilet-paper-price-per-meter",
        "title": "トイレットペーパーは1mいくらなら安い？単価の計算方法と比較",
        "h1": "トイレットペーパーは1mいくらなら安い？",
        "desc": "トイレットペーパーの価格を1mあたりに換算する方法を解説。ダブル・シングル・ロール数が違っても同じ基準で比較でき、楽天の送料込み価格検索にもつながります。",
        "intro": "トイレットペーパーはロール数だけを見ると、本当に安いか判断しにくい商品です。長さまでそろえて1mあたりの価格にすると、容量違いの商品も比較しやすくなります。",
        "formula": "価格 ÷（1ロールの長さm × ロール数）＝ 1mあたり価格",
        "labels": ("商品価格（円）", "1ロールの長さ（m）", "ロール数"),
        "mode": "toilet",
        "category": "../../categories/toilet-paper/",
        "search": "../../products/?q=トイレットペーパー",
        "tips": [
            "ダブルとシングルは、ロール数ではなく実際の長さを確認する",
            "大容量パックは単価が下がりやすいが、送料込みの最終価格で比べる",
            "クーポンやポイントは変動するため、まず通常価格の単価を基準にする",
        ],
    },
    {
        "slug": "tissue-price-per-box",
        "title": "ティッシュは1箱いくらなら安い？箱・組数をそろえてコスパ比較",
        "h1": "ティッシュは1箱いくらなら安い？",
        "desc": "ティッシュの箱数や組数が違う商品を同じ基準で比較する方法を紹介。1箱あたり価格を簡単に計算し、楽天の送料込み価格も検索できます。",
        "intro": "ティッシュは5箱、10箱、ソフトパックなど売り方がばらばらです。まず1箱あたり価格にそろえ、組数が大きく違う商品は1組あたりも確認すると比較しやすくなります。",
        "formula": "価格 ÷ 箱数 ＝ 1箱あたり価格",
        "labels": ("商品価格（円）", "箱・パック数", "1箱あたりの組数（任意）"),
        "mode": "tissue",
        "category": "../../categories/tissue/",
        "search": "../../products/?q=ティッシュ",
        "tips": [
            "5箱セット同士でも、1箱の組数が違うことがある",
            "ソフトパックは箱ティッシュと容量が違うため、組数も合わせて見る",
            "通販は本体価格ではなく送料込み価格で判断する",
        ],
    },
    {
        "slug": "laundry-detergent-cost-per-use",
        "title": "洗濯洗剤は1回いくら？1回あたりコストの計算と安い商品の探し方",
        "h1": "洗濯洗剤は1回いくら？",
        "desc": "洗濯洗剤の価格を1回あたりに換算する方法を解説。容量と1回使用量からコストを計算し、詰め替えや大容量商品を比較できます。",
        "intro": "洗濯洗剤は容量が大きいほど安く見えますが、濃縮タイプでは1回の使用量が違います。容量だけでなく、何回洗えるかで比較すると実際のコスパが分かります。",
        "formula": "価格 ÷（内容量 ÷ 1回使用量）＝ 1回あたり価格",
        "labels": ("商品価格（円）", "内容量（ml・g）", "1回使用量（ml・g）"),
        "mode": "laundry",
        "category": "../../categories/laundry/",
        "search": "../../products/?q=洗濯洗剤",
        "tips": [
            "通常タイプと濃縮タイプは、容量だけで比較しない",
            "ボトル本体と詰め替えは1回あたり価格で比べる",
            "大容量は送料や保管スペースも含めて判断する",
        ],
    },
]

STYLE = """
:root{--bg:#f6f7f9;--card:#fff;--text:#202124;--muted:#667085;--line:#e4e7ec;--accent:#252525}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif}
a{color:inherit}.wrap{max-width:760px;margin:0 auto;padding:22px 16px 54px}.back{display:inline-block;margin-bottom:14px;color:#475467;text-decoration:none;font-size:13px}.hero,.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px;margin-bottom:16px}.hero h1{font-size:26px;line-height:1.35;margin:0 0 10px}.hero p,.card p,.card li{color:var(--muted);line-height:1.8}.eyebrow{font-size:12px;font-weight:800;color:#475467;margin-bottom:8px}.formula{padding:12px 14px;border-radius:12px;background:#f2f4f7;font-weight:800;line-height:1.7}.calc{display:grid;gap:10px}.calc label{font-size:13px;font-weight:800}.calc input{width:100%;padding:12px;border:1px solid #d0d5dd;border-radius:10px;font-size:16px}.result{margin-top:12px;padding:14px;border-radius:12px;background:#f2f4f7;font-size:18px;font-weight:900}.cta{display:block;padding:13px 16px;border-radius:12px;text-align:center;text-decoration:none;font-weight:900;margin-top:10px}.primary{background:var(--accent);color:#fff}.secondary{background:#fff;border:1px solid var(--line)}h2{font-size:19px;margin:0 0 10px}.links{display:grid;gap:10px}@media(max-width:600px){.hero h1{font-size:23px}}
"""

SCRIPT = r"""
<script>
(function(){
  const mode=document.body.dataset.mode;
  const a=document.getElementById('a'),b=document.getElementById('b'),c=document.getElementById('c'),out=document.getElementById('result');
  function num(el){return parseFloat(el.value)}
  function calc(){
    const A=num(a),B=num(b),C=num(c);
    if(!(A>0)||!(B>0)){out.textContent='数値を入力するとここに結果が出ます';return}
    let value, text;
    if(mode==='toilet'){
      if(!(C>0)){out.textContent='ロール数も入力してください';return}
      value=A/(B*C); text='1mあたり 約'+value.toFixed(2)+'円';
    }else if(mode==='tissue'){
      value=A/B; text='1箱あたり 約'+value.toFixed(1)+'円';
      if(C>0){text+=' ／ 1組あたり 約'+(A/(B*C)).toFixed(3)+'円'}
    }else{
      if(!(C>0)){out.textContent='1回使用量も入力してください';return}
      value=A/(B/C); text='1回あたり 約'+value.toFixed(1)+'円';
    }
    out.textContent=text;
  }
  [a,b,c].forEach(x=>x.addEventListener('input',calc));
})();
</script>
"""


def page_html(p: dict) -> str:
    tips = "".join(f"<li>{x}</li>" for x in p["tips"])
    l1,l2,l3 = p["labels"]
    canonical = BASE + "guides/" + p["slug"] + "/"
    return f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{p['title']} | 日用品コスパ比較</title>
<meta name="description" content="{p['desc']}">
<link rel="canonical" href="{canonical}">
<style>{STYLE}</style>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"{p['h1']}","description":"{p['desc']}","url":"{canonical}","isPartOf":{{"@type":"WebSite","name":"日用品コスパ比較","url":"{BASE}"}}}}</script>
</head>
<body data-mode="{p['mode']}"><main class="wrap">
<a class="back" href="../../">← 日用品コスパ比較トップへ</a>
<section class="hero"><div class="eyebrow">日用品の安い基準を計算</div><h1>{p['h1']}</h1><p>{p['intro']}</p></section>
<section class="card"><h2>計算方法</h2><div class="formula">{p['formula']}</div></section>
<section class="card"><h2>かんたん単価計算</h2><div class="calc">
<label>{l1}<input id="a" inputmode="decimal" type="number" min="0" placeholder="例：500"></label>
<label>{l2}<input id="b" inputmode="decimal" type="number" min="0" placeholder="数値を入力"></label>
<label>{l3}<input id="c" inputmode="decimal" type="number" min="0" placeholder="数値を入力"></label>
</div><div id="result" class="result">数値を入力するとここに結果が出ます</div></section>
<section class="card"><h2>比較するときのポイント</h2><ul>{tips}</ul></section>
<section class="card"><h2>実際の商品価格を比べる</h2><p>計算した単価を目安に、今売られている商品の送料込み価格を確認できます。</p><div class="links">
<a class="cta primary" href="{p['search']}">楽天の送料込み価格を検索する →</a>
<a class="cta secondary" href="{p['category']}">カテゴリの安い順ランキングを見る</a>
<a class="cta secondary" href="../../#buy-judge">「この値段、買い？」で判定する</a>
</div></section>
</main>{SCRIPT}</body></html>'''


def add_home_links() -> None:
    path = SITE / "index.html"
    if not path.exists():
        return
    s = path.read_text(encoding="utf-8")
    if 'id="search-guides"' in s:
        return
    cards = "".join(
        f'<a href="guides/{p["slug"]}/" style="display:block;padding:12px 14px;border:1px solid #e4e7ec;border-radius:12px;text-decoration:none;background:#fff;font-weight:800">{p["h1"]}</a>'
        for p in PAGES
    )
    block = f'''<section id="search-guides" style="margin:20px 0;padding:16px;border:1px solid #e4e7ec;border-radius:16px;background:#f8fafc"><h2 style="margin:0 0 8px;font-size:18px">日用品の「安い基準」を計算</h2><p style="margin:0 0 12px;color:#667085;font-size:12px;line-height:1.7">容量や個数が違う商品を、同じ単位にそろえて比較できます。</p><div style="display:grid;gap:9px">{cards}</div></section>'''
    if "</main>" in s:
        s = s.replace("</main>", block + "\n</main>", 1)
    else:
        s = s.replace("</body>", block + "\n</body>", 1)
    path.write_text(s, encoding="utf-8")


def main() -> None:
    for p in PAGES:
        d = SITE / "guides" / p["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page_html(p), encoding="utf-8")
    add_home_links()
    print(f"Created {len(PAGES)} search landing pages and homepage links.")

if __name__ == "__main__":
    main()
