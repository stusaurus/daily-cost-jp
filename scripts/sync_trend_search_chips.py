import html as html_lib
import re
import urllib.parse
from pathlib import Path

PRODUCTS = Path("site/products/index.html")
TRENDS = Path("site/trends/index.html")
HOME = Path("site/index.html")
MAX_CHIPS = 4

GENERIC_WORDS = {
    "トイレットペーパー", "ティッシュ", "ティッシュペーパー", "洗濯洗剤", "液体洗剤",
    "食器用洗剤", "ミネラルウォーター", "天然水", "コーヒー", "柔軟剤", "シャンプー",
    "コンディショナー", "リンス", "ボディソープ", "ハンドソープ", "お風呂用洗剤",
    "浴室洗剤", "トイレ用洗剤", "トイレ洗剤", "漂白剤", "衣料用漂白剤", "洗口液",
    "マウスウォッシュ", "ペーパータオル", "キッチンペーパー", "ゴミ袋", "不織布マスク",
    "歯ブラシ", "綿棒", "フローリングシート", "フロアシート",
}

SPEC_RE = re.compile(
    r"^(?:\d+(?:[.,]\d+)?(?:ml|mL|L|g|kg|枚|個|本|袋|箱|ロール|巻|個入|枚入|本入)|"
    r"\d+[袋箱本個枚ロール巻]?セット|\d+個パック|詰替(?:え)?|つめかえ|本体)$",
    re.IGNORECASE,
)


def strip_tags(value: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def compact(value: str) -> str:
    return re.sub(r"[\s\u3000\-_/・.,!！?？()（）［］\[\]【】]", "", str(value or "").lower())


GENERIC_KEYS = {compact(value) for value in GENERIC_WORDS}


def major_label(query: str, name: str) -> str:
    """Prefer the shortest recognizable product/brand name, not the ranking title."""
    base = re.sub(r"\s+", " ", query or "").strip() or re.sub(r"\s+", " ", name or "").strip()
    tokens = [t.strip() for t in re.split(r"[\s｜|／/・:：]+", base) if t.strip()]

    useful = []
    for token in tokens:
        key = compact(token)
        if not key or key in GENERIC_KEYS or SPEC_RE.fullmatch(token):
            continue
        if re.fullmatch(r"[0-9,.%％倍]+", token):
            continue
        useful.append(token)

    if not useful:
        useful = tokens[:1] or [base]

    # One strong token is usually the major product/brand name (e.g. アリエール, キレイキレイ).
    # Use a second token only when the first alone is extremely short or clearly incomplete.
    label = useful[0]
    if len(label) <= 3 and len(useful) >= 2:
        label = f"{label} {useful[1]}"

    if len(label) > 16:
        label = label[:16].rstrip() + "…"
    return label


def collect_searchable_trends(markup: str):
    card_pattern = re.compile(r'<article class="card">(.*?)</article>', re.DOTALL)
    rows = []
    seen = set()
    for card_match in card_pattern.finditer(markup):
        card = card_match.group(1)
        rank_match = re.search(r'<div class="rank"><b>(\d+)位</b>', card)
        name_match = re.search(r'<div class="name">(.*?)</div>', card, re.DOTALL)
        search_match = re.search(r'<a class="search" href="../products/\?q=([^"]+)"', card)
        if not (rank_match and name_match and search_match):
            continue
        rank = int(rank_match.group(1))
        query = urllib.parse.unquote(search_match.group(1)).strip()
        name = strip_tags(name_match.group(1))
        key = re.sub(r"\s+", "", query.lower())
        if not query or not name or key in seen:
            continue
        seen.add(key)
        rows.append({"rank": rank, "name": name, "query": query})
    rows.sort(key=lambda row: row["rank"])
    return rows[:MAX_CHIPS]


def replace_product_chips(markup: str, rows):
    if not rows:
        return markup
    buttons = []
    for row in rows:
        q = html_lib.escape(row["query"], quote=True)
        label = html_lib.escape(major_label(row["query"], row["name"]))
        buttons.append(f'<button class="chip" data-q="{q}" data-trend-rank="{row["rank"]}" title="{html_lib.escape(row["name"], quote=True)}">{label}</button>')
    block = '<div class="examples" aria-label="今の人気商品">' + ''.join(buttons) + '</div>'
    markup = re.sub(r'<div class="examples"(?:[^>]*)>.*?</div>', block, markup, count=1, flags=re.DOTALL)
    markup = markup.replace(
        'placeholder="例：おしりセレブ / アリエール / JANコード"',
        'placeholder="今人気の商品名・ブランド・JANコード"',
        1,
    )
    # Undo the prior two-line chip styling; short major names fit naturally in one compact row.
    markup = re.sub(
        r'<style id="trend-chip-two-line">.*?</style>',
        '',
        markup,
        flags=re.DOTALL,
    )
    return markup


def clean_home_fixed_examples(markup: str):
    markup = markup.replace(
        '「おしりセレブ」「アリエール」など、欲しい製品そのものを選んで楽天価格ナビの購入可能な最低価格を確認できます。',
        '欲しい商品名やブランド名を入れて、楽天で確認できる送料込み価格を探せます。',
    )
    return markup


def main():
    if not PRODUCTS.exists() or not TRENDS.exists():
        print("Product/trend page unavailable; skipping dynamic trend chips")
        return

    trend_html = TRENDS.read_text(encoding="utf-8")
    rows = collect_searchable_trends(trend_html)
    if not rows:
        print("No validated searchable trend items found; keeping current search chips")
        return

    product_html = PRODUCTS.read_text(encoding="utf-8")
    product_html = replace_product_chips(product_html, rows)
    PRODUCTS.write_text(product_html, encoding="utf-8")

    if HOME.exists():
        home_html = HOME.read_text(encoding="utf-8")
        HOME.write_text(clean_home_fixed_examples(home_html), encoding="utf-8")

    print("Synced short major-name search chips from Rakuten trends: " + ", ".join(major_label(r["query"], r["name"]) for r in rows))


if __name__ == "__main__":
    main()
