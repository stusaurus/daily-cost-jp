import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

SITE = "https://stusaurus.github.io/daily-cost-jp/"
OUT = Path("site")
RANKING_API = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
APP_ID = os.environ.get("RAKUTEN_APPLICATION_ID", "")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY", "")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")

# Keep the trend surface focused on products that fit this site's daily-use purpose.
INCLUDE_TERMS = (
    "トイレットペーパー", "ティッシュ", "洗濯洗剤", "液体洗剤", "ジェルボール", "柔軟剤",
    "食器用洗剤", "キュキュット", "ジョイ", "ヤシノミ洗剤", "シャンプー", "コンディショナー",
    "トリートメント", "ボディソープ", "ハンドソープ", "浴室洗剤", "お風呂用洗剤", "トイレ洗剤",
    "漂白剤", "ハイター", "マウスウォッシュ", "ペーパータオル", "キッチンペーパー", "ゴミ袋",
    "不織布マスク", "歯ブラシ", "綿棒", "フローリングシート", "ミネラルウォーター", "天然水",
    "ドリップコーヒー", "コーヒー豆", "コーヒー 粉",
)
EXCLUDE_TERMS = (
    "ケース", "ホルダー", "収納", "ディスペンサー", "ポーチ", "カバー", "詰め替え容器",
    "ウォーターサーバー", "コーヒーメーカー", "ドリッパー", "マグカップ", "ふるさと納税",
)
PROMO_WORDS = (
    "送料無料", "送料込", "楽天1位", "ランキング1位", "ポイント", "クーポン", "セール", "SALE",
    "公式", "限定", "あす楽", "最安値", "お買い物マラソン",
)


def compact(value: str) -> str:
    return re.sub(r"[\s\u3000\-_/・.,!！?？()（）［］\[\]【】]", "", str(value or "").lower())


def clean_title(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    previous = None
    while text != previous:
        previous = text
        text = re.sub(r"^\s*[【\[].{1,80}?[】\]]\s*", "", text)
    for word in PROMO_WORDS:
        text = re.sub(rf"^\s*{re.escape(word)}\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def is_daily_use(title: str) -> bool:
    text = str(title or "")
    if any(term in text for term in EXCLUDE_TERMS):
        return False
    return any(term in text for term in INCLUDE_TERMS)


def search_query(title: str) -> str:
    """Create a short, stable search phrase from a noisy Rakuten listing title."""
    text = clean_title(title)
    if not text:
        return ""
    tokens = [t for t in re.split(r"[\s｜|／/・:：]+", text) if t]
    useful = []
    for token in tokens:
        if any(word.lower() in token.lower() for word in PROMO_WORDS):
            continue
        if re.fullmatch(r"[0-9,.%％倍]+", token):
            continue
        useful.append(token)
        if len(" ".join(useful)) >= 24 or len(useful) >= 3:
            break
    query = " ".join(useful).strip()
    if not query:
        query = text[:24]
    return query[:48].strip()


def first_image(raw) -> str:
    values = raw.get("mediumImageUrls") or []
    if not isinstance(values, list) or not values:
        return ""
    first = values[0]
    if isinstance(first, dict):
        return str(first.get("imageUrl") or first.get("url") or "")
    return str(first or "")


def fetch_rank_page(page: int):
    params = {
        "applicationId": APP_ID,
        "format": "json",
        "formatVersion": 2,
        "period": "realtime",
        "page": page,
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
            "User-Agent": "daily-cost-jp-trends/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("Items") or payload.get("items") or []


def collect_trends(limit=10):
    if not APP_ID or not ACCESS_KEY:
        return []
    rows = []
    seen = set()
    # Look through the current top 300 overall. This changes throughout the day,
    # while still using Rakuten's own ranking rather than a hand-picked brand list.
    for page in range(1, 11):
        try:
            batch = fetch_rank_page(page)
        except Exception as exc:
            print(f"Ranking API p{page} failed: {exc}")
            break
        for raw in batch:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("itemName") or "").strip()
            if not name or not is_daily_use(name):
                continue
            query = search_query(name)
            key = compact(query)
            if len(key) < 2 or key in seen:
                continue
            seen.add(key)
            rows.append({
                "rank": int(raw.get("rank") or 0),
                "name": clean_title(name),
                "query": query,
                "price": int(raw.get("itemPrice") or 0),
                "shop": str(raw.get("shopName") or ""),
                "image": first_image(raw),
                "url": str(raw.get("affiliateUrl") or raw.get("itemUrl") or ""),
                "postage_included": str(raw.get("postageFlag")) == "0",
            })
            if len(rows) >= limit:
                return rows
        if len(rows) >= limit:
            break
        time.sleep(1.1)
    return rows


CSS = """
:root{--bg:#faf8f6;--card:#fff;--text:#252525;--muted:#6b7280;--line:#e7e1dc;--accent:#b3261e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.7}.wrap{max-width:900px;margin:auto;padding:0 18px}header{padding:30px 0 18px}.crumb{font-size:12px;color:var(--muted);margin-bottom:12px}.crumb a{color:inherit}.eyebrow{font-size:11px;font-weight:800;color:var(--accent)}h1{font-size:29px;margin:5px 0 8px}.lead{font-size:14px;color:#555}.grid{display:grid;gap:11px;margin:16px 0 28px}.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px;display:grid;grid-template-columns:82px 1fr;gap:12px}.pic{width:82px;height:82px;border:1px solid var(--line);border-radius:11px;overflow:hidden;display:grid;place-items:center;background:#fff}.pic img{width:100%;height:100%;object-fit:contain}.rank{font-size:11px;font-weight:800;color:var(--accent)}.name{font-size:13px;font-weight:800;line-height:1.45}.meta{font-size:10px;color:var(--muted);margin-top:4px}.actions{display:flex;gap:6px;margin-top:8px}.actions a{flex:1;text-align:center;text-decoration:none;border-radius:9px;padding:9px 6px;font-size:11px;font-weight:800}.search{background:var(--accent);color:#fff}.rakuten{border:1px solid var(--line);color:var(--text)}.note{font-size:11px;color:var(--muted);margin:16px 0 34px}@media(min-width:760px){.grid{grid-template-columns:1fr 1fr}}
"""


def render_trends(rows):
    cards = []
    for row in rows:
        q = urllib.parse.quote(row["query"])
        image = f'<img src="{html.escape(row["image"], quote=True)}" alt="" loading="lazy">' if row["image"] else ""
        price = f'¥{row["price"]:,}' if row["price"] > 0 else "価格は楽天で確認"
        postage = "送料込み" if row["postage_included"] else "送料は商品検索で再確認"
        direct = f'<a class="rakuten" href="{html.escape(row["url"], quote=True)}" target="_blank" rel="nofollow sponsored noopener">楽天の商品を見る</a>' if row["url"] else ""
        cards.append(f'''<article class="card"><div class="pic">{image}</div><div><div class="rank">楽天リアルタイムランキング {row["rank"]}位</div><div class="name">{html.escape(row["name"])}</div><div class="meta">{price} ・ {postage}</div><div class="actions"><a class="search" href="../products/?q={q}">送料込み最安値を探す</a>{direct}</div></div></article>''')
    card_html = "".join(cards) if cards else '<p class="note">現在、日用品に該当するランキング商品を十分に取得できませんでした。次回更新で再取得します。</p>'
    item_schema = [{"@type":"ListItem","position":i+1,"name":r["name"],"url":f"{SITE}products/?q={urllib.parse.quote(r['query'])}"} for i,r in enumerate(rows)]
    schema = json.dumps({"@context":"https://schema.org","@type":"ItemList","name":"楽天で今人気の日用品","itemListElement":item_schema}, ensure_ascii=False)
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>楽天で今人気の日用品 | 送料込み最安値検索</title><meta name="description" content="楽天市場のリアルタイムランキングから、日用品コスパ比較の対象に合う商品を自動抽出。固定ブランドではなく、その時点で人気の商品から送料込み最安値を検索できます。"><meta name="robots" content="index,follow"><link rel="canonical" href="{SITE}trends/"><style>{CSS}</style><script type="application/ld+json">{schema}</script></head><body><header><div class="wrap"><div class="crumb"><a href="../">日用品コスパ比較</a> › 今人気の日用品</div><span class="eyebrow">楽天ランキングから自動更新</span><h1>今、楽天で人気の日用品</h1><p class="lead">固定の商品をおすすめするのではなく、楽天市場のリアルタイムランキングから日用品に当てはまる商品を自動で入れ替えています。気になる商品は、そのまま送料込み最安値検索へ進めます。</p></div></header><main class="wrap"><section class="grid">{card_html}</section><p class="note">ランキング順位・価格・商品情報は取得時点の楽天市場データです。送料込み最安値は商品検索画面で改めて同一商品を照合して確認します。当サイトは楽天アフィリエイトを利用しています。</p></main></body></html>'''


def inject_trends(rows):
    page = OUT / "products" / "index.html"
    if not page.exists() or not rows:
        return
    markup = page.read_text(encoding="utf-8")
    if 'id="trend-searches"' in markup:
        return
    links = "".join(
        f'<a class="chip" href="?q={urllib.parse.quote(r["query"])}">{html.escape(r["query"])}</a>'
        for r in rows[:8]
    )
    block = f'<section id="trend-searches" style="margin:18px 0 6px"><div class="status">今、楽天で人気の日用品</div><div class="examples">{links}</div><div style="margin-top:8px;font-size:11px"><a href="../trends/">ランキングからもっと見る →</a></div></section>'
    markup = markup.replace('</main>', block + '\n</main>', 1)
    page.write_text(markup, encoding="utf-8")


def inject_home_link(rows):
    if not rows:
        return
    page = OUT / "index.html"
    if not page.exists():
        return
    markup = page.read_text(encoding="utf-8")
    if 'id="trend-home-link"' in markup:
        return
    block = '<section id="trend-home-link" style="margin:14px 0 20px;padding:14px;border:1px solid #e5e7eb;border-radius:16px;background:#fff"><strong>🔥 今、楽天で人気の日用品</strong><p style="margin:5px 0 8px;font-size:12px;color:#6b7280">固定商品ではなく、楽天ランキングから自動で入れ替わります。</p><a href="trends/" style="font-size:12px;font-weight:800">今日の人気商品を見る →</a></section>'
    markup = markup.replace('<details class="info-box">', block + '\n<details class="info-box">', 1)
    page.write_text(markup, encoding="utf-8")


def update_sitemap():
    sitemap = OUT / "sitemap.xml"
    if not sitemap.exists():
        return
    text = sitemap.read_text(encoding="utf-8")
    trend_url = f"{SITE}trends/"
    products_url = f"{SITE}products/"
    additions = []
    if products_url not in text:
        additions.append(f'<url><loc>{products_url}</loc></url>')
    if trend_url not in text:
        additions.append(f'<url><loc>{trend_url}</loc></url>')
    if additions:
        text = text.replace('</urlset>', ''.join(additions) + '</urlset>', 1)
        sitemap.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    trends = collect_trends()
    target = OUT / "trends" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_trends(trends), encoding="utf-8")
    inject_trends(trends)
    inject_home_link(trends)
    update_sitemap()
    print(f"Built dynamic trend hub with {len(trends)} Rakuten ranking items")
