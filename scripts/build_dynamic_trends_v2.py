import html
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

SITE = "https://stusaurus.github.io/daily-cost-jp/"
OUT = Path("site")
RANKING_API = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
APP_ID = os.environ.get("RAKUTEN_APPLICATION_ID", "")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY", "")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")

PROMO_WORDS = (
    "送料無料", "送料込", "楽天1位", "ランキング1位", "ポイント", "クーポン", "セール", "sale",
    "公式", "限定", "あす楽", "最安値", "お買い物マラソン", "スーパーsale", "タイムセール",
)


def compact(value: str) -> str:
    return re.sub(r"[\s\u3000\-_/・.,!！?？()（）［］\[\]【】]", "", str(value or "").lower())


def clean_title(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    previous = None
    while text != previous:
        previous = text
        text = re.sub(r"^\s*[【\[].{1,90}?[】\]]\s*", "", text)
    text = re.sub(r"^\s*\d{1,2}%\s*off\s*", "", text, flags=re.IGNORECASE)
    for word in PROMO_WORDS:
        text = re.sub(rf"^\s*{re.escape(word)}\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def search_query(title: str) -> str:
    """Create a useful search phrase without changing the visible product title."""
    text = clean_title(title)
    if not text:
        return ""
    tokens = [t.strip() for t in re.split(r"[\s｜|／/・:：]+", text) if t.strip()]
    useful = []
    for token in tokens:
        token_low = token.lower()
        if any(word.lower() in token_low for word in PROMO_WORDS):
            continue
        if re.fullmatch(r"[0-9,.%％倍]+", token):
            continue
        if re.search(r"\d{1,2}/\d{1,2}|\d{1,2}:\d{2}", token):
            continue
        useful.append(token)
        if len(" ".join(useful)) >= 38 or len(useful) >= 5:
            break
    query = " ".join(useful).strip() or text
    return query[:72].strip()


def first_image(raw) -> str:
    values = raw.get("mediumImageUrls") or []
    if not isinstance(values, list) or not values:
        return ""
    first = values[0]
    if isinstance(first, dict):
        return str(first.get("imageUrl") or first.get("url") or "")
    return str(first or "")


def fetch_ranking():
    params = {
        "applicationId": APP_ID,
        "format": "json",
        "formatVersion": 2,
        "period": "realtime",
        "page": 1,
        "elements": ",".join([
            "rank", "itemName", "itemPrice", "itemUrl", "affiliateUrl", "mediumImageUrls",
            "shopName", "postageFlag", "availability", "genreId"
        ]),
    }
    if AFFILIATE_ID:
        params["affiliateId"] = AFFILIATE_ID
    request = urllib.request.Request(
        RANKING_API + "?" + urllib.parse.urlencode(params),
        headers={
            "accessKey": ACCESS_KEY,
            "Origin": "https://stusaurus.github.io",
            "Referer": SITE,
            "User-Agent": "daily-cost-jp-rakuten-top10/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("Items") or payload.get("items") or []


def collect_trends(limit=10):
    if not APP_ID or not ACCESS_KEY:
        return []
    try:
        batch = fetch_ranking()
    except Exception as exc:
        print(f"Ranking API failed: {exc}")
        return []

    rows = []
    for raw in batch:
        if not isinstance(raw, dict):
            continue
        rank = int(raw.get("rank") or 0)
        name = str(raw.get("itemName") or "").strip()
        if rank < 1 or rank > limit or not name:
            continue
        rows.append({
            "rank": rank,
            "name": clean_title(name),
            "query": search_query(name),
            "price": int(raw.get("itemPrice") or 0),
            "shop": str(raw.get("shopName") or ""),
            "image": first_image(raw),
            "url": str(raw.get("affiliateUrl") or raw.get("itemUrl") or ""),
            "postage_included": str(raw.get("postageFlag")) == "0",
        })

    rows.sort(key=lambda row: row["rank"])
    return rows[:limit]


CSS = """
:root{--bg:#faf8f6;--card:#fff;--text:#252525;--muted:#6b7280;--line:#e7e1dc;--accent:#b3261e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.7}.wrap{max-width:900px;margin:auto;padding:0 18px}header{padding:30px 0 18px}.crumb{font-size:12px;color:var(--muted);margin-bottom:12px}.crumb a{color:inherit}.eyebrow{font-size:11px;font-weight:800;color:var(--accent)}h1{font-size:29px;margin:5px 0 8px}.lead{font-size:14px;color:#555}.grid{display:grid;gap:11px;margin:16px 0 28px}.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px;display:grid;grid-template-columns:82px minmax(0,1fr);gap:12px}.pic{width:82px;height:82px;border:1px solid var(--line);border-radius:11px;overflow:hidden;display:grid;place-items:center;background:#fff}.pic img{width:100%;height:100%;object-fit:contain}.rank{font-size:12px;font-weight:900;color:var(--accent)}.rank b{display:inline-grid;place-items:center;min-width:30px;height:24px;padding:0 7px;border-radius:999px;background:#f7e9e7;margin-right:5px}.name{font-size:13px;font-weight:800;line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.meta{font-size:10px;color:var(--muted);margin-top:4px}.actions{display:flex;gap:6px;margin-top:8px}.actions a{min-width:0;flex:1;text-align:center;text-decoration:none;border-radius:9px;padding:9px 5px;font-size:10px;font-weight:800}.search{background:var(--accent);color:#fff}.rakuten{border:1px solid var(--line);color:var(--text)}.note{font-size:11px;color:var(--muted);margin:16px 0 34px}@media(min-width:760px){.grid{grid-template-columns:1fr 1fr}}
"""


def render_trends(rows):
    cards = []
    for row in rows:
        q = urllib.parse.quote(row["query"])
        image = f'<img src="{html.escape(row["image"], quote=True)}" alt="" loading="lazy">' if row["image"] else ""
        price = f'¥{row["price"]:,}' if row["price"] > 0 else "価格は楽天で確認"
        postage = "送料込み" if row["postage_included"] else "送料は検索画面で再確認"
        direct = f'<a class="rakuten" href="{html.escape(row["url"], quote=True)}" target="_blank" rel="nofollow sponsored noopener">楽天の商品を見る</a>' if row["url"] else ""
        search = f'<a class="search" href="../products/?q={q}">送料込み最安値を探す</a>' if row["query"] else ""
        cards.append(
            f'<article class="card"><div class="pic">{image}</div><div><div class="rank"><b>{row["rank"]}位</b>楽天総合リアルタイム</div><div class="name">{html.escape(row["name"])}</div><div class="meta">{price} ・ {postage}</div><div class="actions">{search}{direct}</div></div></article>'
        )
    card_html = "".join(cards) if cards else '<p class="note">現在、楽天リアルタイムランキングを取得できませんでした。次回更新で再取得します。</p>'
    item_schema = [
        {"@type":"ListItem","position":r["rank"],"name":r["name"],"url":r["url"] or f"{SITE}trends/"}
        for r in rows
    ]
    schema = json.dumps({"@context":"https://schema.org","@type":"ItemList","name":"楽天総合リアルタイムランキング TOP10","itemListElement":item_schema}, ensure_ascii=False)
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>楽天総合リアルタイムランキング TOP10 | 今売れている商品</title><meta name="description" content="楽天市場の総合リアルタイムランキング1位から10位を順位どおり表示。日用品に限定せず、その時点で楽天で売れている商品を確認し、対応商品は送料込み最安値検索へ進めます。"><meta name="robots" content="index,follow"><link rel="canonical" href="{SITE}trends/"><style>{CSS}</style><script type="application/ld+json">{schema}</script></head><body><header><div class="wrap"><div class="crumb"><a href="../">日用品コスパ比較</a> › 楽天総合ランキング</div><span class="eyebrow">楽天ランキングから自動更新</span><h1>楽天で今売れている商品 TOP10</h1><p class="lead">楽天市場の総合リアルタイムランキングを1位から10位まで、そのまま順位順に表示します。日用品だけに限定せず、その時点で本当に人気の商品を見られます。商品検索に対応できるものは、送料込み最安値も確認できます。</p></div></header><main class="wrap"><section class="grid">{card_html}</section><p class="note">ランキング順位・価格・商品情報は取得時点の楽天市場データです。ランキング表示価格の送料条件は商品ごとに異なるため、送料込み最安値は商品検索画面で改めて確認します。当サイトは楽天アフィリエイトを利用しています。</p></main></body></html>'''


def inject_trends(rows):
    page = OUT / "products" / "index.html"
    if not page.exists() or not rows:
        return
    markup = page.read_text(encoding="utf-8")
    links = "".join(
        f'<a href="?q={urllib.parse.quote(r["query"])}"><strong>{r["rank"]}位</strong><span>{html.escape(r["name"])}</span></a>'
        for r in rows if r["query"]
    )
    block = f'''<style>
#trend-searches{{margin:20px 0 8px}}#trend-searches .trend-title{{font-size:12px;color:#6b7280;margin-bottom:8px}}#trend-searches .trend-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}#trend-searches .trend-grid a{{min-width:0;border:1px solid #e7e1dc;border-radius:12px;background:#fff;padding:9px 10px;text-decoration:none;overflow:hidden}}#trend-searches .trend-grid strong{{display:block;font-size:10px;color:#b3261e;margin-bottom:2px}}#trend-searches .trend-grid span{{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;white-space:normal;overflow:hidden;text-overflow:ellipsis;line-height:1.35;min-height:2.7em;font-size:11px;color:#252525}}#trend-searches .trend-more{{margin-top:9px;font-size:11px}}@media(max-width:380px){{#trend-searches .trend-grid{{grid-template-columns:1fr}}}}
</style><section id="trend-searches"><div class="trend-title">楽天総合リアルタイムランキング TOP10</div><div class="trend-grid">{links}</div><div class="trend-more"><a href="../trends/">1位から10位をランキングで見る →</a></div></section>'''
    markup = markup.replace('</main>', block + '\n</main>', 1)
    page.write_text(markup, encoding="utf-8")


def inject_home_link(rows):
    if not rows:
        return
    page = OUT / "index.html"
    if not page.exists():
        return
    markup = page.read_text(encoding="utf-8")
    block = '<section id="trend-home-link" style="margin:14px 0 20px;padding:14px;border:1px solid #e5e7eb;border-radius:16px;background:#fff"><strong>🔥 楽天で今売れている商品 TOP10</strong><p style="margin:5px 0 8px;font-size:12px;color:#6b7280">日用品に限定せず、楽天総合リアルタイムランキング1位〜10位を自動更新しています。</p><a href="trends/" style="font-size:12px;font-weight:800">今のランキングを見る →</a></section>'
    markup = markup.replace('<details class="info-box">', block + '\n<details class="info-box">', 1)
    page.write_text(markup, encoding="utf-8")


def update_sitemap():
    sitemap = OUT / "sitemap.xml"
    if not sitemap.exists():
        return
    text = sitemap.read_text(encoding="utf-8")
    url = f"{SITE}trends/"
    products_url = f"{SITE}products/"
    additions = []
    if products_url not in text:
        additions.append(f'<url><loc>{products_url}</loc></url>')
    if url not in text:
        additions.append(f'<url><loc>{url}</loc></url>')
    if additions:
        text = text.replace('</urlset>', ''.join(additions) + '</urlset>', 1)
        sitemap.write_text(text, encoding="utf-8")


def remove_legacy_landing_dirs():
    for slug in ("oshiri-celebrity", "ariel", "bold", "kireikirei"):
        target = OUT / "products" / slug / "index.html"
        if target.exists():
            target.unlink()


if __name__ == "__main__":
    rows = collect_trends(10)
    remove_legacy_landing_dirs()
    trends = OUT / "trends" / "index.html"
    trends.parent.mkdir(parents=True, exist_ok=True)
    trends.write_text(render_trends(rows), encoding="utf-8")
    inject_trends(rows)
    inject_home_link(rows)
    update_sitemap()
    print(f"Built Rakuten overall realtime top {len(rows)}")
