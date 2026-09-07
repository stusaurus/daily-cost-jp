from pathlib import Path

HOME = Path("site/index.html")
PRODUCTS = Path("site/products/index.html")


def replace_once(text: str, old: str, new: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    return text


def improve_home() -> None:
    if not HOME.exists():
        raise SystemExit("site/index.html not found")
    html = HOME.read_text(encoding="utf-8")
    html = replace_once(
        html,
        "<title>日用品コスパ比較 | 楽天市場の単価を自動計算</title>",
        "<title>楽天の日用品を送料込みで比較・商品名から最安値検索 | 日用品コスパ比較</title>",
    )
    html = replace_once(
        html,
        '<meta name="description" content="トイレットペーパー、ティッシュ、洗剤、水、コーヒーなどの日用品を、楽天市場の商品情報から単価換算して比較します。">',
        '<meta name="description" content="楽天市場の日用品を1ロール・1箱・100g・100ml・1Lなどの単価で比較。さらに欲しい商品名から、送料込みで確認できた購入候補の最安値をリアルタイム検索できます。">',
    )
    html = replace_once(
        html,
        '<p class="lead">楽天市場の日用品を「1個あたり・100gあたり・1Lあたり」で比較。送料込み商品の中から安い順に表示します。</p>',
        '<p class="lead">送料込みの日用品を同じ単位で比較。さらに、いつも買っている商品名を入れるだけで楽天の送料込み最安値候補を探せます。</p>',
    )
    schema = '''<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"日用品コスパ比較","url":"https://stusaurus.github.io/daily-cost-jp/","potentialAction":{"@type":"SearchAction","target":"https://stusaurus.github.io/daily-cost-jp/products/?q={search_term_string}","query-input":"required name=search_term_string"}}</script>'''
    if '"@type":"WebSite"' not in html:
        html = html.replace("</head>", schema + "\n</head>", 1)
    HOME.write_text(html, encoding="utf-8")


def improve_products() -> None:
    if not PRODUCTS.exists():
        raise SystemExit("site/products/index.html not found")
    html = PRODUCTS.read_text(encoding="utf-8")
    html = replace_once(
        html,
        "<title>商品名から楽天の今日の最安値を探す | 日用品コスパ比較</title>",
        "<title>楽天の送料込み最安値を商品名で検索 | 日用品コスパ比較</title>",
    )
    html = replace_once(
        html,
        '<meta name="description" content="欲しい商品名・ブランド・JANコードから楽天価格ナビの購入可能な最低価格を検索。毎朝自動更新。">',
        '<meta name="description" content="アリエール・ボールド・おしりセレブなど、欲しい商品名・ブランド・JANコードから楽天市場を検索。同一商品と確認できた送料込み購入候補の最安値を表示します。">',
    )
    PRODUCTS.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    improve_home()
    improve_products()
    print("SEO metadata updated for homepage and product search")
