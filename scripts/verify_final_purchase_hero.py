"""Verify final user-facing art hero after all earlier homepage rewrites."""
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path("site")
BASE="/daily-cost-jp/"
ROUTES=("laundry","tissue","toilet-paper")

def validate(root=ROOT):
    errors=[]
    home=root/"index.html"
    if not home.is_file():
        return ["final homepage missing"]
    soup=BeautifulSoup(home.read_text(encoding="utf-8"),"html.parser")
    cover=soup.select_one("header.art-cover")
    if cover is None:
        return ["art cover missing from final homepage"]
    title=cover.select_one("h1")
    if not title or "単価も総額も" not in title.get_text(" ",strip=True):
        errors.append("final art headline does not explain unit vs total")
    intro=cover.select_one("p.lead")
    if not intro or "支払額" not in intro.get_text(" ",strip=True):
        errors.append("final art hero does not explain checkout total")
    nav=cover.select_one('nav.art-purchase-links[aria-label]')
    if nav is None:
        errors.append("final art purchase shortcuts are missing")
    else:
        for route in ROUTES:
            href=BASE+"categories/"+route+"/"
            links=nav.select('a[href="'+href+'"]')
            if len(links)!=1: errors.append("missing/duplicate real category shortcut: "+route)
            elif "category-page-link" not in links[0].get("class",[]) or links[0].get("data-conversion-source")!="category":
                errors.append("shortcut missing existing GA4 category tracking: "+route)
            if not (root/"categories"/route/"index.html").is_file():
                errors.append("shortcut destination missing: "+route)
    css=root/"assets"/"art-purchase-entry.css"
    if not css.is_file() or ".art-purchase-links" not in css.read_text(encoding="utf-8"):
        errors.append("final art shortcut style missing")
    links=soup.select('link[rel="stylesheet"][href^="/daily-cost-jp/assets/art-purchase-entry.css"]')
    if len(links)!=1:
        errors.append("final art shortcut stylesheet link missing or duplicate")
    if len(soup.select("h1"))!=1:
        errors.append("homepage must retain exactly one h1")
    return errors

if __name__=="__main__":
    problems=validate()
    if problems:raise SystemExit("\n".join(problems))
    print("Final art hero value and purchase routes verified.")
