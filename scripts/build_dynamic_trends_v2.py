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

# Trend candidates must map to one of the site's actual repeat-purchase categories.
CATEGORY_RULES = [
    ("トイレットペーパー", ("トイレットペーパー",)),
    ("ティッシュ", ("ティッシュペーパー", "ボックスティッシュ", "箱ティッシュ", "ソフトパックティッシュ")),
    ("洗濯洗剤", ("洗濯洗剤", "液体洗剤", "ジェルボール", "アタック", "アリエール", "ボールド", "ナノックス")),
    ("食器用洗剤", ("食器用洗剤", "キュキュット", "チャーミー", "ヤシノミ洗剤")),
    ("ミネラルウォーター", ("ミネラルウォーター", "天然水", "飲料水")),
    ("コーヒー", ("ドリップコーヒー", "コーヒー豆", "レギュラーコーヒー", "インスタントコーヒー")),
    ("柔軟剤", ("柔軟剤", "レノア", "ハミング", "ソフラン")),
    ("シャンプー", ("シャンプー",)),
    ("コンディショナー", ("コンディショナー", "リンス")),
    ("ボディソープ", ("ボディソープ", "ボディウォッシュ")),
    ("ハンドソープ", ("ハンドソープ", "キレイキレイ")),
    ("お風呂用洗剤", ("お風呂用洗剤", "浴室洗剤", "バスマジックリン")),
    ("トイレ用洗剤", ("トイレ用洗剤", "トイレ洗剤", "トイレマジックリン")),
    ("衣料用漂白剤", ("衣料用漂白剤", "酸素系漂白剤", "ワイドハイター")),
    ("マウスウォッシュ", ("マウスウォッシュ", "洗口液", "モンダミン", "リステリン")),
    ("ペーパータオル", ("ペーパータオル", "キッチンペーパー")),
    ("45Lゴミ袋", ("45l ゴミ袋", "45lごみ袋", "45リットル ゴミ袋", "45リットルごみ袋")),
    ("不織布マスク", ("不織布マスク",)),
    ("歯ブラシ", ("歯ブラシ",)),
    ("綿棒", ("綿棒",)),
    ("フローリングシート", ("フローリングシート", "フロアシート", "ウェットシート 床")),
]

# Explicitly exclude durable goods, accessories, and adjacent beauty products that are
# not one of the site's comparison categories even if their titles contain a matching word.
EXCLUDE_TERMS = (
    "タイルカーペット", "カーペット", "ラグ", "玄関マット", "バスマット", "ヨガマット",
    "ヘアオイル", "ヘアミルク", "ヘアワックス", "スタイリング", "アウトバス", "ヘアブラシ",
    "トリートメント", "ヘアマスク", "美容液", "化粧水", "乳液", "クリーム", "クレンジング",
    "ケース", "ホルダー", "収納", "ディスペンサー", "ポーチ", "カバー", "詰め替え容器",
    "ウォーターサーバー", "水筒", "タンブラー", "コーヒーメーカー", "ドリッパー", "コーヒーミル", "マグカップ",
    "ティッシュケース", "ティッシュカバー", "ゴミ箱", "歯ブラシスタンド", "歯ブラシホルダー",
    "ふるさと納税", "返礼品", "お試しセット", "福袋",
)

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


def category_for(title: str):
    raw = str(title or "")
    low = raw.lower()
    if any(term.lower() in low for term in EXCLUDE_TERMS):
        return None
    for category, terms in CATEGORY_RULES:
        if any(term.lower() in low for term in terms):
            # Avoid false positives around paper/tissue products.
            if category == "ティッシュ" and any(x in low for x in ("ウェットティッシュ", "おしりふき", "ティッシュケース")):
                continue
            if category == "歯ブラシ" and any(x in low for x in ("電動歯ブラシ", "替えブラシ", "歯ブラシホルダー")):
                continue
            return category
    return None


def search_query(title: str, category: str) -> str:
    text = clean_title(title)
    if not text:
        return category
    tokens = [t.strip() for t in re.split(r"[\s｜|／/・:：]+", text) if t.strip()]
    useful = []
    for token in tokens:
        token_low = token.lower()
        if any(word.lower() in token_low for word in PROMO_WORDS):
            continue
        if re.fullmatch(r"[0-9,.%％倍]+", token):
            continue
        # Skip leading date/time/campaign clutter.
        if re.search(r"\d{1,2}/\d{1,2}|\d{1,2}:\d{2}", token):
            continue
        useful.append(token)
        if len(" ".join(useful)) >= 28 or len(useful) >= 4:
            break
    query = " ".join(useful).strip() or category
    return query[:56].strip()


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
            "User-Agent": "daily-cost-jp-trends/2.0",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("Items") or payload.get("items") or []


def collect_trends(limit=10):
    if not APP_ID or not ACCESS_KEY:
        return []
    rows = []
    seen_queries = set()
    per_category = {}
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
            category = category_for(name)
            if not name or not category:
                continue
            # Keep the list varied instead of allowing one category to dominate.
            if per_category.get(category, 0) >= 2:
                continue
            query = search_query(name, category)
            key = compact(query)
            if len(key) < 2 or key in seen_queries:
                continue
            seen_queries.add(key)
            per_category[category] = per_category.get(category, 0) + 1
            rows.append({
                "rank": int(raw.get("rank") or 0),
                "category": category,
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
        time.sleep(1.1)
    return rows


CSS = """
:root{--bg:#faf8f6;--card:#fff;--text:#252525;--muted:#6b7280;--line:#e7e1dc;--accent:#b3261e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.7}.wrap{max-width:900px;margin:auto;padding:0 18px}header{padding:30px 0 18px}.crumb{font-size:12px;color:var(--muted);margin-bottom:12px}.crumb a{color:inherit}.eyebrow{font-size:11px;font-weight:800;color:var(--accent)}h1{font-size:29px;margin:5px 0 8px}.lead{font-size:14px;color:#555}.grid{display:grid;gap:11px;margin:16px 0 28px}.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px;display:grid;grid-template-columns:82px minmax(0,1fr);gap:12px}.pic{width:82px;height:82px;border:1px solid var(--line);border-radius:11px;overflow:hidden;display:grid;place-items:center;background:#fff}.pic img{width:100%;height:100%;object-fit:contain}.rank{font-size:11px;font-weight:800;color:var(--accent)}.category{display:inline-block;margin-left:5px;padding:2px 6px;border-radius:999px;background:#f5f1ee;color:#5f5550;font-size:9px}.name{font-size:13px;font-weight:800;line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.meta{font-size:10px;color:var(--muted);margin-top:4px}.actions{display:flex;gap:6px;margin-top:8px}.actions a{min-width:0;flex:1;text-align:center;text-decoration:none;border-radius:9px;padding:9px 5px;font-size:10px;font-weight:800}.search{background:var(--accent);color:#fff}.rakuten{border:1px solid var(--line);color:var(--text)}.note{font-size:11px;color:var(--muted);margin:16px 0 34px}@media(min-width:760px){.grid{grid-template-columns:1fr 1fr}}
"""


def render_trends(rows):
    cards = []
    for row in rows:
        q = urllib.parse.quote(row["query"])
        image = f'<img src="{html.escape(row["image"], quote=True)}" alt="" loading="lazy">' if row["image"] else ""
        price = f'¥{row["price"]:,}' if row["price"] > 0 else "価格は楽天で確認"
        postage = "送料込み" if row["postage_included"] else "送料は検索画面で再確認"
        direct = f'<a class="rakuten" href="{html.escape(row["url"], quote=True)}" target="_blank" rel="nofollow sponsored noopener">楽天の商品を見る</a>' if row["url"] else ""
        cards.append(
            f'<article class="card"><div class="pic">{image}</div><div><div class="rank">楽天リアルタイム {row["rank"]}位<span class="category">{html.escape(row["category"])}</span></div><div class="name">{html.escape(row["name"])}</div><div class="meta">{price} ・ {postage}</div><div class="actions"><a class="search" href="../products/?q={q}">送料込み最安値を探す</a>{direct}</div></div></article>'
        )
    card_html = "".join(cards) if cards else '<p class="note">現在、比較対象の日用品トレンドを十分に取得できませんでした。次回更新で再取得します。</p>'
    item_schema = [
        {"@type":"ListItem","position":i+1,"name":r["name"],"url":f"{SITE}products/?q={urllib.parse.quote(r['query'])}"}
        for i, r in enumerate(rows)
    ]
    schema = json.dumps({"@context":"https://schema.org","@type":"ItemList","name":"楽天で今人気の日用品","itemListElement":item_schema}, ensure_ascii=False)
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>楽天で今人気の日用品 | 送料込み最安値検索</title><meta name="description" content="楽天市場のリアルタイムランキングから、このサイトで比較している消耗品・日用品だけを自動抽出。人気商品から送料込み最安値を検索できます。"><meta name="robots" content="index,follow"><link rel="canonical" href="{SITE}trends/"><style>{CSS}</style><script type="application/ld+json">{schema}</script></head><body><header><div class="wrap"><div class="crumb"><a href="../">日用品コスパ比較</a> › 今人気の日用品</div><span class="eyebrow">楽天ランキングから自動更新</span><h1>今、楽天で人気の日用品</h1><p class="lead">楽天市場のリアルタイムランキングから、当サイトで比較している消耗品・日用品だけを抽出しています。家具・収納用品・ヘアオイルなど隣接カテゴリは除外し、気になる商品は送料込み最安値検索へ進めます。</p></div></header><main class="wrap"><section class="grid">{card_html}</section><p class="note">ランキング順位・価格・商品情報は取得時点の楽天市場データです。送料込み最安値は商品検索画面で改めて同一商品を照合して確認します。当サイトは楽天アフィリエイトを利用しています。</p></main></body></html>'''


def inject_trends(rows):
    page = OUT / "products" / "index.html"
    if not page.exists() or not rows:
        return
    markup = page.read_text(encoding="utf-8")
    links = "".join(
        f'<a href="?q={urllib.parse.quote(r["query"])}"><strong>{html.escape(r["category"])}</strong><span>{html.escape(r["query"])}</span></a>'
        for r in rows[:6]
    )
    block = f'''<style>
#trend-searches{{margin:20px 0 8px}}#trend-searches .trend-title{{font-size:12px;color:#6b7280;margin-bottom:8px}}#trend-searches .trend-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}#trend-searches .trend-grid a{{min-width:0;border:1px solid #e7e1dc;border-radius:12px;background:#fff;padding:9px 10px;text-decoration:none;overflow:hidden}}#trend-searches .trend-grid strong{{display:block;font-size:9px;color:#b3261e;margin-bottom:2px}}#trend-searches .trend-grid span{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px;color:#252525}}#trend-searches .trend-more{{margin-top:9px;font-size:11px}}@media(max-width:380px){{#trend-searches .trend-grid{{grid-template-columns:1fr}}}}
</style><section id="trend-searches"><div class="trend-title">今、楽天で人気の日用品</div><div class="trend-grid">{links}</div><div class="trend-more"><a href="../trends/">ランキングからもっと見る →</a></div></section>'''
    markup = markup.replace('</main>', block + '\n</main>', 1)
    page.write_text(markup, encoding="utf-8")


def inject_home_link(rows):
    if not rows:
        return
    page = OUT / "index.html"
    if not page.exists():
        return
    markup = page.read_text(encoding="utf-8")
    block = '<section id="trend-home-link" style="margin:14px 0 20px;padding:14px;border:1px solid #e5e7eb;border-radius:16px;background:#fff"><strong>🔥 今、楽天で人気の日用品</strong><p style="margin:5px 0 8px;font-size:12px;color:#6b7280">楽天ランキングから、比較対象の消耗品だけを自動抽出して入れ替えています。</p><a href="trends/" style="font-size:12px;font-weight:800">今日の人気商品を見る →</a></section>'
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
    # Old fixed-brand landing pages are intentionally not part of the new dynamic model.
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
    print(f"Built dynamic trend hub with {len(rows)} filtered products")
