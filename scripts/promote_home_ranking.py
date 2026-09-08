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
            "image": image_match.group(1) if image_match else "",
            "name": strip_tags(match.group(3)),
            "meta": strip_tags(match.group(4)),
            "rakuten": rakuten_match.group(1) if rakuten_match else "",
            "search": search_match.group(1) if search_match else "",
        })
    rows.sort(key=lambda row: row["rank"])
    return rows


def item_link(row):
    # Keep users inside the site when a comparison search is available; otherwise
    # use the affiliate product link returned by Rakuten.
    if row["search"]:
        return row["search"].replace("../products/", "products/")
    return row["rakuten"] or "trends/"


def missing_item(rank: int) -> str:
    return (
        '<div class="home-rank-missing">'
        f'<span class="home-rank-no">{rank}位</span>'
        '<span class="home-rank-missing-icon">—</span>'
        '<span><strong>商品情報を取得できませんでした</strong>'
        '<small>順位は詰めず、次回更新で再取得します</small></span>'
        '</div>'
    )


def build_block(rows):
    if not rows:
        return ""

    by_rank = {row["rank"]: row for row in rows}
    first = by_rank.get(1)

    if first:
        first_image = (
            f'<img src="{html_lib.escape(first["image"], quote=True)}" alt="" loading="eager">'
            if first["image"] else ""
        )
        first_link = html_lib.escape(item_link(first), quote=True)
        first_external = ' target="_blank" rel="nofollow sponsored noopener"' if first_link.startswith("http") else ""
        first_html = f'''<a class="home-rank-first" href="{first_link}"{first_external}>
    <span class="home-rank-first-pic"><span class="home-rank-first-badge">1位</span>{first_image}</span>
    <span><span class="home-rank-first-label">現在の総合1位</span><span class="home-rank-first-name">{html_lib.escape(first["name"])}</span><span class="home-rank-first-meta">{html_lib.escape(first["meta"])}</span></span>
  </a>'''
    else:
        first_html = '''<div class="home-rank-first-missing">
    <span class="home-rank-first-missing-badge">1位</span>
    <span><strong>1位の商品情報を取得できませんでした</strong><small>楽天の公式順位は変えず、次回更新で再取得します。</small></span>
  </div>'''

    rest = []
    for rank in range(2, 11):
        row = by_rank.get(rank)
        if not row:
            rest.append(missing_item(rank))
            continue
        image = (
            f'<img src="{html_lib.escape(row["image"], quote=True)}" alt="" loading="lazy">'
            if row["image"] else ""
        )
        link = html_lib.escape(item_link(row), quote=True)
        external = ' target="_blank" rel="nofollow sponsored noopener"' if link.startswith("http") else ""
        rest.append(
            f'<a class="home-rank-item" href="{link}"{external}>'
            f'<span class="home-rank-no">{rank}位</span>'
            f'<span class="home-rank-thumb">{image}</span>'
            f'<span class="home-rank-name">{html_lib.escape(row["name"])}</span>'
            f'</a>'
        )

    return f'''<style id="home-ranking-hero-style">
#home-ranking-hero{{margin:10px auto 26px;padding:18px;border:1px solid #eadfd9;border-radius:22px;background:linear-gradient(180deg,#fff 0%,#fffaf7 100%);box-shadow:0 10px 28px rgba(60,35,25,.07)}}
#home-ranking-hero *{{box-sizing:border-box}}
#home-ranking-hero .home-rank-kicker{{font-size:11px;font-weight:900;letter-spacing:.04em;color:#b3261e}}
#home-ranking-hero h2{{font-size:24px;line-height:1.25;margin:3px 0 4px;color:#252525}}
#home-ranking-hero .home-rank-lead{{font-size:12px;color:#6b7280;margin:0 0 14px}}
#home-ranking-hero .home-rank-first{{display:grid;grid-template-columns:116px minmax(0,1fr);gap:14px;align-items:center;padding:14px;border-radius:18px;background:#fff;border:2px solid #e7c5bf;text-decoration:none;color:#252525}}
#home-ranking-hero .home-rank-first-pic{{position:relative;width:116px;height:116px;display:grid;place-items:center;border-radius:14px;background:#fff;overflow:hidden}}
#home-ranking-hero .home-rank-first-pic img{{width:100%;height:100%;object-fit:contain}}
#home-ranking-hero .home-rank-first-badge{{position:absolute;left:5px;top:5px;display:grid;place-items:center;width:45px;height:45px;border-radius:50%;background:#b3261e;color:#fff;font-size:15px;font-weight:900;box-shadow:0 4px 12px rgba(179,38,30,.25)}}
#home-ranking-hero .home-rank-first-label{{font-size:11px;font-weight:900;color:#b3261e}}
#home-ranking-hero .home-rank-first-name{{font-size:16px;font-weight:900;line-height:1.45;margin-top:3px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
#home-ranking-hero .home-rank-first-meta{{font-size:11px;color:#6b7280;margin-top:7px}}
#home-ranking-hero .home-rank-first-missing{{display:grid;grid-template-columns:54px minmax(0,1fr);gap:12px;align-items:center;padding:14px;border:1px dashed #d9cbc3;border-radius:18px;background:#fbfaf9;color:#6b625e}}
#home-ranking-hero .home-rank-first-missing-badge{{display:grid;place-items:center;width:45px;height:45px;border-radius:50%;background:#eee7e2;color:#7c6f68;font-size:14px;font-weight:900}}
#home-ranking-hero .home-rank-first-missing strong{{display:block;font-size:13px}}
#home-ranking-hero .home-rank-first-missing small{{display:block;margin-top:3px;font-size:10px;color:#8a817c}}
#home-ranking-hero .home-rank-list{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px}}
#home-ranking-hero .home-rank-item,#home-ranking-hero .home-rank-missing{{min-width:0;display:grid;grid-template-columns:34px 44px minmax(0,1fr);gap:7px;align-items:center;padding:7px;border:1px solid #ebe4df;border-radius:12px;background:#fff;text-decoration:none;color:#252525}}
#home-ranking-hero .home-rank-no{{font-size:10px;font-weight:900;color:#b3261e;text-align:center}}
#home-ranking-hero .home-rank-thumb{{width:44px;height:44px;border-radius:8px;overflow:hidden;display:grid;place-items:center;background:#fff}}
#home-ranking-hero .home-rank-thumb img{{width:100%;height:100%;object-fit:contain}}
#home-ranking-hero .home-rank-name{{font-size:10px;font-weight:750;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
#home-ranking-hero .home-rank-missing{{border-style:dashed;background:#fbfaf9;color:#7c736e}}
#home-ranking-hero .home-rank-missing-icon{{display:grid;place-items:center;width:44px;height:44px;border-radius:8px;background:#f2eeeb;color:#9a918c;font-weight:900}}
#home-ranking-hero .home-rank-missing strong{{display:block;font-size:10px;line-height:1.35}}
#home-ranking-hero .home-rank-missing small{{display:block;margin-top:2px;font-size:8px;line-height:1.35;color:#9a918c}}
#home-ranking-hero .home-rank-all{{display:block;margin-top:12px;padding:12px;border-radius:12px;background:#b3261e;color:#fff;text-align:center;text-decoration:none;font-size:12px;font-weight:900}}
@media(max-width:520px){{#home-ranking-hero{{margin-left:14px;margin-right:14px;padding:14px}}#home-ranking-hero h2{{font-size:22px}}#home-ranking-hero .home-rank-first{{grid-template-columns:96px minmax(0,1fr);padding:11px}}#home-ranking-hero .home-rank-first-pic{{width:96px;height:96px}}#home-ranking-hero .home-rank-list{{grid-template-columns:1fr}}}}
</style>
<section id="home-ranking-hero">
  <div class="home-rank-kicker">🔥 楽天総合リアルタイムランキング</div>
  <h2>今、楽天で売れている TOP10</h2>
  <p class="home-rank-lead">楽天の公式順位をそのまま表示。取得できない順位は詰めずに明示します。</p>
  {first_html}
  <div class="home-rank-list">{''.join(rest)}</div>
  <a class="home-rank-all" href="trends/">ランキングを詳しく見る →</a>
</section>'''


def main():
    if not HOME.exists() or not TRENDS.exists():
        print("Homepage or trend page unavailable; skipping homepage ranking promotion")
        return

    home = HOME.read_text(encoding="utf-8")
    trends = TRENDS.read_text(encoding="utf-8")
    rows = extract_rows(trends)
    if not rows:
        print("No TOP10 ranking rows found; keeping homepage unchanged")
        return

    # Remove the old small ranking teaser and any previous hero generated in this build.
    home = re.sub(r'<section id="trend-home-link".*?</section>', "", home, flags=re.DOTALL)
    home = re.sub(r'<style id="home-ranking-hero-style">.*?</style>\s*<section id="home-ranking-hero">.*?</section>', "", home, flags=re.DOTALL)

    block = build_block(rows)
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
    print(f"Promoted official TOP10 slots with {len(rows)} available items")


if __name__ == "__main__":
    main()
