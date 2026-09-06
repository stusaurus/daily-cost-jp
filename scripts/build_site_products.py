"""Product-search layer for daily-cost-jp.

Builds the existing buy-decision site, then adds a searchable product catalog
from Rakuten Product Search API. The catalog is refreshed on every scheduled
build and lets users choose a specific product/brand (rather than comparing
unlike products only by unit price).

This is intentionally a static daily snapshot so Rakuten credentials remain
server-side in GitHub Actions. A future realtime backend can reuse the same UI.
"""
from __future__ import annotations

import html
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import build_site_decision as decision

core = decision.core

PRODUCT_API_URL = "https://openapi.rakuten.co.jp/ichibaproduct/api/Product/Search/20250801"
APP_ID = os.environ.get("RAKUTEN_APPLICATION_ID")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
PAGES_PER_CATEGORY = 3


def safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fetch_product_page(category, page):
    params = {
        "applicationId": APP_ID,
        "keyword": category["name"],
        "hits": 30,
        "page": page,
        "format": "json",
        "formatVersion": 2,
        "elements": ",".join([
            "productId", "productCode", "productName", "productNo", "brandName",
            "productUrlPC", "affiliateUrl", "mediumImageUrl", "salesItemCount",
            "usedExcludeSalesMinPrice", "salesMinPrice", "averagePrice",
            "reviewCount", "reviewAverage", "genreName"
        ]),
    }
    if AFFILIATE_ID:
        params["affiliateId"] = AFFILIATE_ID

    url = PRODUCT_API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "accessKey": ACCESS_KEY,
            "Origin": "https://stusaurus.github.io",
            "Referer": core.SITE_URL,
            "User-Agent": "daily-cost-jp/0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("items", [])


def normalize_product(raw, category):
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("productName") or "").strip()
    product_id = str(raw.get("productId") or "").strip()
    if not name or not product_id:
        return None

    min_price = safe_int(raw.get("usedExcludeSalesMinPrice")) or safe_int(raw.get("salesMinPrice"))
    if min_price <= 0:
        return None

    average_price = safe_int(raw.get("averagePrice"))
    url = raw.get("affiliateUrl") or raw.get("productUrlPC") or ""
    image = str(raw.get("mediumImageUrl") or "").replace("http://", "https://")

    return {
        "product_id": product_id,
        "product_code": str(raw.get("productCode") or ""),
        "name": name,
        "product_no": str(raw.get("productNo") or ""),
        "brand": str(raw.get("brandName") or ""),
        "category_id": category["id"],
        "category_name": category["name"],
        "category_emoji": category["emoji"],
        "genre": str(raw.get("genreName") or ""),
        "min_price": min_price,
        "average_price": average_price,
        "seller_count": safe_int(raw.get("salesItemCount")),
        "review_count": safe_int(raw.get("reviewCount")),
        "review_average": safe_float(raw.get("reviewAverage")),
        "image": image,
        "url": str(url),
    }


def build_catalog():
    products = {}
    failures = []
    for category in core.CATEGORIES:
        for page in range(1, PAGES_PER_CATEGORY + 1):
            try:
                raws = fetch_product_page(category, page)
                for raw in raws:
                    product = normalize_product(raw, category)
                    if not product:
                        continue
                    existing = products.get(product["product_id"])
                    if not existing or product["min_price"] < existing["min_price"]:
                        products[product["product_id"]] = product
                print(f"Product catalog {category['name']} p{page}: {len(raws)} rows")
            except Exception as exc:
                failures.append(f"{category['name']} p{page}: {exc}")
                print(f"Product catalog fetch failed {category['name']} p{page}: {exc}")
            time.sleep(1.15)
    result = list(products.values())
    result.sort(key=lambda p: (-p["review_count"], p["min_price"], p["name"]))
    return result, failures


PRODUCTS_CSS = r"""
  :root{--bg:#faf8f6;--card:#fff;--text:#252525;--muted:#6b7280;--line:#e7e1dc;--accent:#b3261e;--accent2:#8f1f19}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif}
  .wrap{max-width:900px;margin:auto;padding:0 16px}.hero{padding:28px 0 20px}.crumb{font-size:12px;color:var(--muted);margin-bottom:10px}.crumb a{color:inherit}.eyebrow{font-size:11px;font-weight:800;color:var(--accent)}
  h1{font-size:28px;margin:5px 0 8px}.lead{font-size:13px;line-height:1.7;color:#555}.search-box{position:sticky;top:0;z-index:5;background:rgba(250,248,246,.96);padding:10px 0 12px;backdrop-filter:blur(10px)}
  .search-row{display:flex;gap:8px}.search-row input{flex:1;min-width:0;height:50px;border:1px solid #d8d1cb;border-radius:14px;padding:0 14px;font-size:16px;background:#fff}.search-row button{border:0;border-radius:14px;background:var(--accent);color:#fff;font-weight:800;padding:0 16px}
  .examples{display:flex;gap:7px;overflow:auto;padding:8px 0 0}.chip{border:1px solid var(--line);border-radius:999px;background:#fff;padding:7px 10px;font-size:11px;white-space:nowrap;cursor:pointer}.status{font-size:12px;color:var(--muted);margin:10px 0}
  .grid{display:grid;gap:12px}.card{background:#fff;border:1px solid var(--line);border-radius:17px;padding:13px;display:grid;grid-template-columns:88px 1fr;gap:12px}.img{width:88px;height:88px;border:1px solid var(--line);border-radius:12px;display:grid;place-items:center;overflow:hidden;background:#fff}.img img{width:100%;height:100%;object-fit:contain}
  .brand{font-size:10px;color:var(--muted);font-weight:700}.name{font-size:14px;font-weight:800;line-height:1.45;margin:3px 0 7px}.price{font-size:22px;color:var(--accent);font-weight:900}.price small{font-size:10px;color:var(--muted);font-weight:600}.meta{font-size:10px;line-height:1.6;color:#555;margin-top:5px}.btn{display:flex;align-items:center;justify-content:center;margin-top:9px;min-height:40px;border-radius:10px;background:var(--accent);color:#fff;text-decoration:none;font-size:12px;font-weight:800}.btn:hover{background:var(--accent2)}
  .note{font-size:10px;line-height:1.6;color:var(--muted);margin:18px 0 28px}.empty{padding:24px;border:1px dashed #ccc;border-radius:14px;background:#fff;color:var(--muted)}
  @media(min-width:760px){.grid{grid-template-columns:1fr 1fr}}
"""


def product_page(products, updated_at):
    safe_json = json.dumps(products, ensure_ascii=False).replace("</", "<\\/")
    count = len(products)
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>商品名から楽天の今日の最安値を探す | 日用品コスパ比較</title>
<meta name="description" content="欲しい商品名・ブランド・JANコードから楽天価格ナビの購入可能な最低価格を検索。毎朝自動更新。">
<link rel="canonical" href="{core.SITE_URL}products/">
<style>{PRODUCTS_CSS}</style></head><body>
<header class="hero"><div class="wrap"><div class="crumb"><a href="../">日用品コスパ比較</a> › 商品検索</div><span class="eyebrow">毎朝自動更新</span><h1>欲しい商品、そのまま検索</h1><p class="lead">安い商品に乗り換えるのではなく、<strong>欲しいブランド・製品そのもの</strong>の楽天価格を探せます。商品名・ブランド名・JANコードで検索してください。</p></div></header>
<main class="wrap"><section class="search-box"><div class="search-row"><input id="q" type="search" enterkeyhint="search" autocomplete="off" placeholder="例：おしりセレブ / アリエール / JANコード"><button id="searchBtn" type="button">検索</button></div><div class="examples"><button class="chip" data-q="おしりセレブ">おしりセレブ</button><button class="chip" data-q="アリエール">アリエール</button><button class="chip" data-q="ボールド">ボールド</button><button class="chip" data-q="キレイキレイ">キレイキレイ</button></div></section><div class="status" id="status">本日の検索対象：{count:,}製品</div><section class="grid" id="results"></section><p class="note">最終更新：{updated_at.strftime('%Y年%m月%d日 %H:%M')}（日本時間）<br>※表示する「最低価格」は楽天の商品価格ナビ製品検索APIの購入可能な最低価格（中古を除く値を優先）です。送料・クーポン・ポイント条件は含めていないため、最終的な支払額はリンク先で必ず確認してください。現在は日用品カテゴリから毎朝取得した製品スナップショットを検索しています。</p></main>
<script>
const PRODUCTS={safe_json}; const q=document.getElementById('q'), results=document.getElementById('results'), status=document.getElementById('status');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const yen=n=>'¥'+Number(n||0).toLocaleString('ja-JP');
function card(p){{const avg=p.average_price?`平均 ${{yen(p.average_price)}}`:'平均価格なし';const sellers=p.seller_count?`${{p.seller_count}}店舗で購入可`:'販売数情報なし';const review=p.review_count?`★ ${{p.review_average.toFixed(2)}}（${{p.review_count.toLocaleString('ja-JP')}}件）`:'レビュー情報なし';return `<article class="card"><div class="img">${{p.image?`<img src="${{esc(p.image)}}" alt="" loading="lazy">`:''}}</div><div><div class="brand">${{esc(p.brand||p.category_name)}}</div><div class="name">${{esc(p.name)}}</div><div class="price">${{yen(p.min_price)}} <small>楽天価格ナビの購入可能な最低価格</small></div><div class="meta">${{esc(avg)}} ・ ${{esc(sellers)}}<br>${{esc(review)}}${{p.product_code?`<br>JAN: ${{esc(p.product_code)}}`:''}}</div><a class="btn product-result-link" data-id="${{esc(p.product_id)}}" href="${{esc(p.url)}}" target="_blank" rel="nofollow sponsored noopener">楽天でこの製品を確認</a></div></article>`}}
function run(){{const term=q.value.trim().toLowerCase();let rows;if(!term) rows=PRODUCTS.slice(0,24); else rows=PRODUCTS.filter(p=>[p.name,p.brand,p.product_code,p.product_no,p.genre].join(' ').toLowerCase().includes(term)).slice(0,60);status.textContent=term?`「${{q.value.trim()}}」の候補：${{rows.length}}件`:`本日の検索対象：${{PRODUCTS.length.toLocaleString('ja-JP')}}製品`;results.innerHTML=rows.length?rows.map(card).join(''):'<div class="empty">一致する製品が見つかりませんでした。商品名を短くして試してください。</div>';if(term&&typeof window.gtag==='function')window.gtag('event','product_search',{{search_term:q.value.trim(),result_count:rows.length}});}}
document.getElementById('searchBtn').addEventListener('click',run);q.addEventListener('keydown',e=>{{if(e.key==='Enter')run()}});document.querySelectorAll('.chip').forEach(b=>b.addEventListener('click',()=>{{q.value=b.dataset.q;run()}}));results.addEventListener('click',e=>{{const a=e.target.closest('.product-result-link');if(a&&typeof window.gtag==='function')window.gtag('event','product_result_click',{{product_id:a.dataset.id,search_term:q.value.trim()}});}});const initial=new URLSearchParams(location.search).get('q');if(initial)q.value=initial;run();
</script></body></html>"""


def add_home_product_search():
    path = core.OUTPUT_DIR / "index.html"
    markup = path.read_text(encoding="utf-8")
    if 'id="product-finder-home"' in markup:
        return
    css = r"""
    .product-finder-home{margin:14px 0 18px;padding:15px;border:1px solid #ded7d1;border-radius:17px;background:#fff}.product-finder-home .pf-kicker{font-size:10px;font-weight:900;color:#b3261e}.product-finder-home h2{font-size:20px;margin:3px 0 5px}.product-finder-home p{font-size:11px;line-height:1.55;color:#626262;margin:0 0 10px}.pf-row{display:flex;gap:7px}.pf-row input{min-width:0;flex:1;height:46px;border:1px solid #d7d0ca;border-radius:11px;padding:0 11px;font-size:16px}.pf-row button{border:0;border-radius:11px;background:#252525;color:#fff;font-weight:800;padding:0 13px}.pf-link{display:inline-block;margin-top:9px;font-size:11px;font-weight:700}
    """
    block = """
<section class="product-finder-home" id="product-finder-home"><div class="pf-kicker">欲しい商品を変えずに比較</div><h2>商品名から今日の楽天価格を探す</h2><p>「おしりセレブ」「アリエール」など、欲しい製品そのものを選んで楽天価格ナビの購入可能な最低価格を確認できます。</p><form class="pf-row" action="products/" method="get"><input name="q" type="search" placeholder="商品名・ブランド・JANコード"><button type="submit">探す</button></form><a class="pf-link" href="products/">商品検索を開く →</a></section>
"""
    markup = markup.replace("</style>", css + "\n</style>", 1)
    marker = '<section class="decision-tool"'
    if marker in markup:
        markup = markup.replace(marker, block + "\n" + marker, 1)
    else:
        markup = markup.replace('<main class="container">', '<main class="container">\n' + block, 1)
    path.write_text(markup, encoding="utf-8")


def add_products_to_sitemap(updated_at):
    path = core.OUTPUT_DIR / "sitemap.xml"
    if not path.exists():
        return
    markup = path.read_text(encoding="utf-8")
    url = core.SITE_URL + "products/"
    if url in markup:
        return
    entry = f"<url><loc>{url}</loc><lastmod>{updated_at.date().isoformat()}</lastmod></url>"
    markup = markup.replace("</urlset>", entry + "</urlset>")
    path.write_text(markup, encoding="utf-8")


def main():
    decision.main()
    updated_at = datetime.now(ZoneInfo("Asia/Tokyo"))
    products, failures = build_catalog()
    if products:
        directory = core.OUTPUT_DIR / "products"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.html").write_text(product_page(products, updated_at), encoding="utf-8")
        (core.OUTPUT_DIR / "product-catalog.json").write_text(json.dumps({"updated_at": updated_at.isoformat(), "count": len(products), "products": products, "failures": failures}, ensure_ascii=False, indent=2), encoding="utf-8")
        add_home_product_search()
        add_products_to_sitemap(updated_at)
        print(f"Generated searchable product catalog with {len(products)} products ({len(failures)} failed API pages).")
    else:
        print("Product catalog unavailable; base site was still generated.")


if __name__ == "__main__":
    main()
