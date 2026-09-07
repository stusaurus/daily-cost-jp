from pathlib import Path
from urllib.parse import quote

SITE = "https://stusaurus.github.io/daily-cost-jp/"
OUT = Path("site")

PAGES = [
    {
        "slug": "oshiri-celebrity",
        "query": "おしりセレブ",
        "title": "おしりセレブの楽天送料込み最安値を検索 | 日用品コスパ比較",
        "description": "おしりセレブを楽天市場から検索し、同一商品と確認できた送料込み購入候補の最安値を確認できます。ロール数や仕様違いは別商品として扱います。",
        "h1": "おしりセレブの送料込み最安値を探す",
        "lead": "同じ『おしりセレブ』でも、ロール数や仕様が違えば価格は変わります。このページから商品検索を開き、楽天市場で送料込みと確認できた同一商品の候補だけを比較できます。",
        "tips": [
            "検索結果では、送料込み／送料無料と確認できた購入候補を優先して表示します。",
            "ロール数などの商品仕様が一致しない候補は、安くても同一商品として採用しません。",
            "購入候補の画像は、実際に価格確認した楽天市場側の商品画像へ切り替わります。",
        ],
    },
    {
        "slug": "ariel",
        "query": "アリエール",
        "title": "アリエールの楽天送料込み最安値を検索 | 日用品コスパ比較",
        "description": "アリエールを楽天市場から検索。容量や商品名を照合し、同一商品と確認できた送料込み購入候補の最安値を表示します。",
        "h1": "アリエールの送料込み最安値を探す",
        "lead": "アリエールは本体・詰め替え・容量違いなど商品候補が多いため、単純な価格順だけでは比較しにくい商品です。このサイトでは、商品名・ブランド・容量などを照合してから送料込み価格を表示します。",
        "tips": [
            "検索結果では、容量や個数が違う商品を同じ商品として扱わないよう照合します。",
            "送料別の安い価格を『最安値』として見せず、送料込みで確認できた候補を表示します。",
            "候補が十分に一致しない場合は、無理に価格を出さず楽天側での確認を案内します。",
        ],
    },
    {
        "slug": "bold",
        "query": "ボールド",
        "title": "ボールドの楽天送料込み最安値を検索 | 日用品コスパ比較",
        "description": "ボールドを楽天市場から検索。香り・容量・商品名などを照合し、同一商品と確認できた送料込み購入候補の最安値を探せます。",
        "h1": "ボールドの送料込み最安値を探す",
        "lead": "ボールドはシリーズや容量違いが多く、タイトルに関連語が多く含まれる出品もあります。そのため、このサイトでは検索語が入っているだけで価格を採用せず、商品名や容量なども確認します。",
        "tips": [
            "商品タイトルに『ボールド』が含まれていても、別商品と判断した候補は価格採用しません。",
            "実際に価格確認した楽天購入候補の画像を表示するため、クリック前にも内容を確認しやすくしています。",
            "送料込み候補が確認できない場合は、価格を推測せず『楽天で価格を確認』と表示します。",
        ],
    },
    {
        "slug": "kireikirei",
        "query": "キレイキレイ",
        "title": "キレイキレイの楽天送料込み最安値を検索 | 日用品コスパ比較",
        "description": "キレイキレイを楽天市場から検索。商品名・ブランド・容量を照合し、同一商品と確認できた送料込み購入候補の最安値を確認できます。",
        "h1": "キレイキレイの送料込み最安値を探す",
        "lead": "キレイキレイはハンドソープなど複数の商品タイプや容量があります。商品名だけでなく、ブランド・容量なども確認して、同一商品と判断できた送料込み候補を表示します。",
        "tips": [
            "容量や本体・詰め替えなどが違う候補を、同じ商品として安値比較しないようにしています。",
            "送料込み価格を確認できた候補は、その価格と楽天購入候補の画像を一緒に表示します。",
            "楽天側の商品情報が曖昧な場合は、安全のため価格未取得として扱います。",
        ],
    },
]

CSS = """
:root{--bg:#faf8f6;--card:#fff;--text:#252525;--muted:#6b7280;--line:#e7e1dc;--accent:#b3261e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.75}.wrap{max-width:760px;margin:auto;padding:0 18px}header{padding:30px 0 18px}.crumb{font-size:12px;color:var(--muted);margin-bottom:12px}.crumb a{color:inherit}.eyebrow{font-size:11px;font-weight:800;color:var(--accent)}h1{font-size:29px;line-height:1.35;margin:5px 0 10px}.lead{font-size:14px;color:#555}.cta{display:block;text-align:center;margin:20px 0;padding:15px;border-radius:14px;background:var(--accent);color:#fff;text-decoration:none;font-weight:900}.box{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:17px;margin:16px 0}.box h2{font-size:18px;margin:0 0 8px}.box ul{margin:8px 0 0;padding-left:1.2em}.box li{margin:7px 0;font-size:13px}.note{font-size:11px;color:var(--muted);margin:22px 0 36px}.related{display:grid;grid-template-columns:1fr 1fr;gap:8px}.related a{border:1px solid var(--line);border-radius:12px;background:#fff;padding:10px;text-decoration:none;font-size:12px;font-weight:700}
"""


def render(page):
    q = quote(page["query"])
    canonical = f"{SITE}products/{page['slug']}/"
    tips = "".join(f"<li>{item}</li>" for item in page["tips"])
    related = "".join(
        f'<a href="../{other["slug"]}/">{other["query"]}を検索</a>'
        for other in PAGES if other["slug"] != page["slug"]
    )
    schema = (
        '{"@context":"https://schema.org","@type":"WebPage",'
        f'"name":"{page["h1"]}","url":"{canonical}",'
        f'"description":"{page["description"]}"'
        '}'
    )
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page["title"]}</title><meta name="description" content="{page["description"]}"><meta name="robots" content="index,follow"><link rel="canonical" href="{canonical}"><style>{CSS}</style><script type="application/ld+json">{schema}</script></head>
<body><header><div class="wrap"><div class="crumb"><a href="../../">日用品コスパ比較</a> › <a href="../">商品検索</a> › {page["query"]}</div><span class="eyebrow">楽天市場をリアルタイム確認</span><h1>{page["h1"]}</h1><p class="lead">{page["lead"]}</p><a class="cta" href="../?q={q}">{page["query"]}を今すぐ検索する</a></div></header>
<main class="wrap"><section class="box"><h2>この検索で確認すること</h2><ul>{tips}</ul></section><section class="box"><h2>価格表示について</h2><p>表示する価格は、楽天市場で送料込み／送料無料と確認でき、同一商品と判断できた購入候補を対象にしています。クーポン・ポイント条件・地域別の追加送料などは最終購入画面で変わることがあるため、購入前に楽天市場の商品ページでご確認ください。</p></section><section class="box"><h2>ほかのよく検索される商品</h2><div class="related">{related}</div></section><p class="note">当サイトは楽天アフィリエイトを利用しています。掲載リンクを経由した購入により、運営者に報酬が発生する場合があります。</p></main></body></html>'''


def inject_product_links():
    page = OUT / "products" / "index.html"
    if not page.exists():
        return
    html = page.read_text(encoding="utf-8")
    marker = 'id="popular-search-pages"'
    if marker in html:
        return
    links = "".join(f'<a class="chip" href="./{p["slug"]}/">{p["query"]}の最安値ページ</a>' for p in PAGES)
    block = f'<section id="popular-search-pages" style="margin:18px 0 6px"><div class="status">よく検索される商品</div><div class="examples">{links}</div></section>'
    html = html.replace('</main>', block + '\n</main>', 1)
    page.write_text(html, encoding="utf-8")


def update_sitemap():
    sitemap = OUT / "sitemap.xml"
    if not sitemap.exists():
        return
    text = sitemap.read_text(encoding="utf-8")
    additions = []
    for p in PAGES:
        url = f"{SITE}products/{p['slug']}/"
        if url not in text:
            additions.append(f'<url><loc>{url}</loc></url>')
    products_url = f"{SITE}products/"
    if products_url not in text:
        additions.insert(0, f'<url><loc>{products_url}</loc></url>')
    if additions:
        text = text.replace('</urlset>', ''.join(additions) + '</urlset>', 1)
        sitemap.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    for page in PAGES:
        target = OUT / "products" / page["slug"] / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(page), encoding="utf-8")
    inject_product_links()
    update_sitemap()
    print(f"Built {len(PAGES)} focused product landing pages")
