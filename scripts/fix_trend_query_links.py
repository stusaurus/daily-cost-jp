import html as html_lib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

PRODUCT_API = "https://openapi.rakuten.co.jp/ichibaproduct/api/Product/Search/20250801"
SITE = "https://stusaurus.github.io/daily-cost-jp/"
APP_ID = os.environ.get("RAKUTEN_APPLICATION_ID", "")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY", "")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
TRENDS = Path("site/trends/index.html")
PRODUCTS = Path("site/products/index.html")

PROMO_WORDS = (
    "送料無料", "送料込", "楽天1位", "ランキング1位", "ポイント", "クーポン",
    "セール", "SALE", "公式", "限定", "あす楽", "最安値", "お買い物マラソン",
)
INCLUDE_TERMS = (
    "トイレットペーパー", "ティッシュ", "洗濯洗剤", "液体洗剤", "ジェルボール", "柔軟剤",
    "食器用洗剤", "キュキュット", "ジョイ", "ヤシノミ洗剤", "シャンプー", "コンディショナー",
    "トリートメント", "ボディソープ", "ハンドソープ", "浴室洗剤", "お風呂用洗剤", "トイレ洗剤",
    "漂白剤", "ハイター", "マウスウォッシュ", "ペーパータオル", "キッチンペーパー", "ゴミ袋",
    "不織布マスク", "歯ブラシ", "綿棒", "フローリングシート", "ミネラルウォーター", "天然水",
    "ドリップコーヒー", "コーヒー豆", "コーヒー 粉",
)


def compact(value):
    return re.sub(r"[\s\u3000\-_/・.,!！?？()（）［］\[\]【】]", "", str(value or "").lower())


def clean_tokens(title):
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    tokens = [t for t in re.split(r"[\s｜|／/・:：]+", text) if t]
    result = []
    for token in tokens:
        if any(word.lower() in token.lower() for word in PROMO_WORDS):
            continue
        if re.fullmatch(r"[0-9,.%％倍]+", token):
            continue
        result.append(token)
    return result


def candidates(title, current):
    tokens = clean_tokens(title)
    rows = [current]
    if len(tokens) >= 2:
        rows.append(" ".join(tokens[:2])[:48].strip())
    if tokens and len(compact(tokens[0])) >= 2:
        rows.append(tokens[0][:48].strip())
    for term in INCLUDE_TERMS:
        if term in title and len(compact(term)) >= 2:
            rows.append(term)

    seen = set()
    result = []
    for value in rows:
        key = compact(value)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


_cache = {}


def has_products(query):
    key = compact(query)
    if key in _cache:
        return _cache[key]
    params = {
        "applicationId": APP_ID,
        "keyword": query,
        "hits": 1,
        "format": "json",
        "formatVersion": 2,
        "elements": "productId,productName",
    }
    if AFFILIATE_ID:
        params["affiliateId"] = AFFILIATE_ID
    req = urllib.request.Request(
        PRODUCT_API + "?" + urllib.parse.urlencode(params),
        headers={
            "accessKey": ACCESS_KEY,
            "Origin": "https://stusaurus.github.io",
            "Referer": SITE,
            "User-Agent": "daily-cost-jp-trend-link-check/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        source = payload.get("Products") or payload.get("items") or []
        found = bool(source) or int(payload.get("count") or 0) > 0
    except Exception as exc:
        print(f"Trend query validation failed for {query!r}: {exc}")
        found = False
    _cache[key] = found
    return found


def choose_query(title, current):
    for query in candidates(title, current):
        time.sleep(1.1)
        if has_products(query):
            return query
    return ""


def main():
    if not APP_ID or not ACCESS_KEY:
        print("Rakuten credentials unavailable; skipping trend query validation")
        return
    if not TRENDS.exists() or not PRODUCTS.exists():
        print("Trend/product pages unavailable; skipping trend query validation")
        return

    trend_html = TRENDS.read_text(encoding="utf-8")
    product_html = PRODUCTS.read_text(encoding="utf-8")

    card_pattern = re.compile(
        r'(<article class="card">.*?<div class="name">)(.*?)(</div>.*?<a class="search" href="../products/\?q=)([^"]+)(")',
        re.DOTALL,
    )

    replacements = {}
    dead_queries = set()

    for match in list(card_pattern.finditer(trend_html)):
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
        current = urllib.parse.unquote(match.group(4))
        if current in replacements or current in dead_queries:
            continue
        chosen = choose_query(title, current)
        if chosen:
            replacements[current] = chosen
            if chosen != current:
                print(f"Trend search query shortened: {current!r} -> {chosen!r}")
        else:
            dead_queries.add(current)
            print(f"No Product API result for trend query: {current!r}")

    for old, new in replacements.items():
        old_q = urllib.parse.quote(old)
        new_q = urllib.parse.quote(new)
        trend_html = trend_html.replace(f'../products/?q={old_q}', f'../products/?q={new_q}')
        product_html = product_html.replace(f'?q={old_q}', f'?q={new_q}')
        product_html = product_html.replace(f'>{old}</span>', f'>{new}</span>')
        product_html = product_html.replace(f'>{old}</a>', f'>{new}</a>')

    # If none of the progressively shorter queries resolve, keep the ranked item
    # visible on the trend page but remove only the search action that would lead to 0 results.
    for dead in dead_queries:
        dead_q = urllib.parse.quote(dead)
        chip_pattern = re.compile(
            rf'<a class="chip" href="\?q={re.escape(dead_q)}">.*?</a>'
        )
        trend_grid_pattern = re.compile(
            rf'<a href="\?q={re.escape(dead_q)}"><strong>.*?</strong><span>.*?</span></a>'
        )
        product_html = chip_pattern.sub("", product_html)
        product_html = trend_grid_pattern.sub("", product_html)
        trend_html = trend_html.replace(
            f'<a class="search" href="../products/?q={dead_q}">送料込み最安値を探す</a>',
            ""
        )

    TRENDS.write_text(trend_html, encoding="utf-8")
    PRODUCTS.write_text(product_html, encoding="utf-8")
    print(f"Validated {len(replacements)} trend search links; removed {len(dead_queries)} dead search links")


if __name__ == "__main__":
    main()
