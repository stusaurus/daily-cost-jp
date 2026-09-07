import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = "https://stusaurus.github.io/daily-cost-jp/"
OUT = Path("site")
RANKING_API = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
APP_ID = os.environ.get("RAKUTEN_APPLICATION_ID", "")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY", "")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
LIMIT = 50
REQUEST_GAP = 1.2

PROMO_WORDS = (
    "送料無料", "送料込", "楽天1位", "ランキング1位", "ポイント", "クーポン", "セール", "sale",
    "公式", "限定", "あす楽", "最安値", "お買い物マラソン", "スーパーsale", "タイムセール",
)


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
    text = clean_title(title)
    if not text:
        return ""
    tokens = [t.strip() for t in re.split(r"[\s｜|／/・:：]+", text) if t.strip()]
    useful = []
    for token in tokens:
        low = token.lower()
        if any(word.lower() in low for word in PROMO_WORDS):
            continue
        if re.fullmatch(r"[0-9,.%％倍]+", token):
            continue
        if re.search(r"\d{1,2}/\d{1,2}|\d{1,2}:\d{2}", token):
            continue
        useful.append(token)
        if len(" ".join(useful)) >= 38 or len(useful) >= 5:
            break
    return (" ".join(useful).strip() or text)[:72].strip()


def first_image(raw) -> str:
    values = raw.get("mediumImageUrls") or []
    if not isinstance(values, list) or not values:
        return ""
    first = values[0]
    if isinstance(first, dict):
        return str(first.get("imageUrl") or first.get("url") or "")
    return str(first or "")


def fetch_page(page: int, retries: int = 3):
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
    req = urllib.request.Request(
        RANKING_API + "?" + urllib.parse.urlencode(params),
        headers={
            "accessKey": ACCESS_KEY,
            "Origin": "https://stusaurus.github.io",
            "Referer": SITE,
            "User-Agent": "daily-cost-jp-rakuten-top50/1.1",
        },
    )

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("Items") or payload.get("items") or []
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                wait = REQUEST_GAP * (attempt + 1)
                print(f"Ranking API page {page} rate limited; retrying in {wait:.1f}s")
                time.sleep(wait)
                continue
            raise


def collect_rows():
    if not APP_ID or not ACCESS_KEY:
        return []

    # build_dynamic_trends_v2.py calls the same Ranking API immediately before
    # this script. Respect Rakuten's QPS=1 limit before the first request here.
    time.sleep(REQUEST_GAP)

    by_rank = {}
    for page in range(1, 5):
        try:
            batch = fetch_page(page)
        except Exception as exc:
            print(f"Ranking API page {page} failed: {exc}")
            break
        for raw in batch:
            if not isinstance(raw, dict):
                continue
            rank = int(raw.get("rank") or 0)
            name = str(raw.get("itemName") or "").strip()
            if rank < 1 or rank > LIMIT or not name:
                continue
            by_rank[rank] = {
                "rank": rank,
                "name": clean_title(name),
                "query": search_query(name),
                "price": int(raw.get("itemPrice") or 0),
                "shop": str(raw.get("shopName") or ""),
                "image": first_image(raw),
                "url": str(raw.get("affiliateUrl") or raw.get("itemUrl") or ""),
                "postage_included": str(raw.get("postageFlag")) == "0",
            }
        if len(by_rank) >= LIMIT:
            break
        time.sleep(REQUEST_GAP)
    return [by_rank[k] for k in sorted(by_rank) if k <= LIMIT]


CSS = """
:root{--bg:#faf8f6;--card:#fff;--text:#252525;--muted:#6b7280;--line:#e7e1dc;--accent:#b3261e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.7}.wrap{max-width:900px;margin:auto;padding:0 18px}header{padding:30px 0 18px}.crumb{font-size:12px;color:var(--muted);margin-bottom:12px}.crumb a{color:inherit}.eyebrow{font-size:11px;font-weight:800;color:var(--accent)}h1{font-size:29px;margin:5px 0 8px}.lead{font-size:14px;color:#555}.top10-note{font-size:12px;font-weight:800;color:var(--accent);margin:12px 0 0}.grid{display:grid;gap:11px;margin:16px 0 28px}.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px;display:grid;grid-template-columns:82px minmax(0,1fr);gap:12px}.pic{width:82px;height:82px;border:1px solid var(--line);border-radius:11px;overflow:hidden;display:grid;place-items:center;background:#fff}.pic img{width:100%;height:100%;object-fit:contain}.rank{font-size:12px;font-weight:900;color:var(--accent)}.rank b{display:inline-grid;place-items:center;min-width:34px;height:24px;padding:0 7px;border-radius:999px;background:#f7e9e7;margin-right:5px}.name{font-size:13px;font-weight:800;line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.meta{font-size:10px;color:var(--muted);margin-top:4px}.actions{display:flex;gap:6px;margin-top:8px}.actions a{min-width:0;flex:1;text-align:center;text-decoration:none;border-radius:9px;padding:9px 5px;font-size:10px;font-weight:800}.search{background:var(--accent);color:#fff}.rakuten{border:1px solid var(--line);color:var(--text)}.divider{grid-column:1/-1;margin:5px 0;padding:9px 12px;border-radius:12px;background:#f5f1ee;font-size:12px;font-weight:900;color:#5f5550}.note{font-size:11px;color:var(--muted);margin:16px 0 34px}@media(min-width:760px){.grid{grid-template-columns:1fr 1fr}}
"""


def render(rows):
    cards = []
    for row in rows:
        if row["rank"] == 11:
            cards.append('<div class="divider" id="rank-11" style="scroll-margin-top:16px">11位〜50位</div>')
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
    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "楽天総合リアルタイムランキング TOP50",
        "itemListElement": [
            {"@type": "ListItem", "position": r["rank"], "name": r["name"], "url": r["url"] or f"{SITE}trends/"}
            for r in rows
        ],
    }, ensure_ascii=False)
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>楽天総合リアルタイムランキング TOP50 | 今売れている商品</title><meta name="description" content="楽天市場の総合リアルタイムランキング1位から50位を順位どおり表示。日用品に限定せず、その時点で楽天で売れている商品を確認できます。"><meta name="robots" content="index,follow"><link rel="canonical" href="{SITE}trends/"><style>{CSS}</style><script type="application/ld+json">{schema}</script></head><body><header><div class="wrap"><div class="crumb"><a href="../">日用品コスパ比較</a> › 楽天総合ランキング</div><span class="eyebrow">楽天ランキングから自動更新</span><h1>楽天で今売れている商品 TOP50</h1><p class="lead">トップページでは見やすく1位〜10位を表示。ここではその続きも含めて、楽天市場の総合リアルタイムランキングを50位まで順位順に確認できます。</p><p class="top10-note">1位〜10位はトップページにも掲載中</p></div></header><main class="wrap"><section class="grid">{card_html}</section><p class="note">ランキング順位・価格・商品情報は取得時点の楽天市場データです。ランキング表示価格の送料条件は商品ごとに異なるため、送料込み最安値は商品検索画面で改めて確認します。当サイトは楽天アフィリエイトを利用しています。</p></main></body></html>'''


def main():
    rows = collect_rows()
    ranks = {row["rank"] for row in rows}
    if 11 not in ranks:
        print(f"Rank 11 unavailable ({len(rows)} rows); keeping existing TOP10 page")
        return
    target = OUT / "trends" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(rows), encoding="utf-8")
    print(f"Expanded ranking detail page to top {len(rows)}")


if __name__ == "__main__":
    main()
