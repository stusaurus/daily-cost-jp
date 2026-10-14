import html as html_lib
import re
from pathlib import Path

HOME = Path("site/index.html")
TRENDS = Path("site/trends/index.html")


def strip_tags(value: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def extract_rows(markup: str):
    pattern = re.compile(
        r'<article class="card"><div class="pic">(.*?)</div><div>'
        r'<div class="rank"><b>(\d+)位</b>.*?</div>'
        r'<div class="name">(.*?)</div>'
        r'<div class="meta">(.*?)</div>'
        r'<div class="actions">(.*?)</div></div></article>',
        re.DOTALL,
    )
    rows = []
    for match in pattern.finditer(markup):
        image_match = re.search(r'<img[^>]+src="([^"]+)"', match.group(1))
        rakuten_match = re.search(r'<a class="rakuten" href="([^"]+)"', match.group(5))
        search_match = re.search(r'<a class="search" href="([^"]+)"', match.group(5))
        rank = int(match.group(2))
        if rank < 1 or rank > 10:
            continue
        rows.append({
            "rank": rank,
            "image": html_lib.unescape(image_match.group(1)) if image_match else "",
            "name": strip_tags(match.group(3)),
            "meta": strip_tags(match.group(4)),
            "rakuten": html_lib.unescape(rakuten_match.group(1)) if rakuten_match else "",
            "search": html_lib.unescape(search_match.group(1)) if search_match else "",
        })
    rows.sort(key=lambda row: row["rank"])
    return rows


def item_link(row):
    # Ranking clicks express intent to view the ranked product itself, so prefer
    # Rakuten's affiliate product URL. The comparison search remains available
    # from the detailed ranking page as an explicit secondary action.
    if row["rakuten"]:
        return row["rakuten"]
    if row["search"]:
        return row["search"].replace("../products/", "products/")
    return "trends/"


def missing_item(rank: int) -> str:
    return (
        '<div class="home-rank-missing">'
        f'<span class="home-rank-no">{rank}位</span>'
        '<span class="home-rank-missing-icon">—</span>'
        '<span><strong>商品情報を取得できませんでした</strong>'
        '<small>順位は詰めず、次回更新で再取得します</small></span>'
        '</div>'
    )


def build_block(rows=None):
    # General-market products keep their original affiliate links on /trends/.
    # Homepage product recommendations come only from the checked daily catalog.
    return '''<style id="home-ranking-hero-style">
#home-ranking-hero{margin:16px 0;padding:14px;border:1px solid #eadfd9;border-radius:14px;background:#fff}
#home-ranking-hero p{font-size:13px;color:#6b7280;margin:0 0 8px}
#home-ranking-hero .home-rank-all{display:inline-flex;align-items:center;min-height:44px;font-size:14px;font-weight:700}
</style>
<section id="home-ranking-hero">
  <p>日用品以外も含む楽天市場全体の人気商品は、別ページで確認できます。</p>
  <a class="home-rank-all" href="trends/">楽天総合ランキングTOP50を見る →</a>
</section>'''

def main():
    if not HOME.exists() or not TRENDS.exists():
        print("Homepage or trend page unavailable; skipping homepage ranking promotion")
        return

    home = HOME.read_text(encoding="utf-8")

    # Remove the old small ranking teaser and any previous hero generated in this build.
    home = re.sub(r'<section id="trend-home-link".*?</section>', "", home, flags=re.DOTALL)
    home = re.sub(r'<style id="home-ranking-hero-style">.*?</style>\s*<section id="home-ranking-hero">.*?</section>', "", home, flags=re.DOTALL)

    block = build_block()
    if "</header>" in home:
        home = home.replace("</header>", "</header>\n" + block, 1)
    else:
        main_match = re.search(r'<main[^>]*>', home)
        if main_match:
            pos = main_match.end()
            home = home[:pos] + "\n" + block + home[pos:]
        else:
            home = home.replace("<body>", "<body>\n" + block, 1)

    HOME.write_text(home, encoding="utf-8")
    print("Homepage general ranking reduced to /trends/ entry; daily categories stay primary")


if __name__ == "__main__":
    main()
