"""Build daily-cost-jp with a realtime Rakuten product finder.

The main comparison pages are generated normally. The product finder page itself
contains no large static catalog; searches are served live by the Cloudflare
Worker API, so we avoid crawling dozens of Product Search API pages during
every scheduled build.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import build_site_products as products


def main():
    products.decision.main()
    updated_at = datetime.now(ZoneInfo("Asia/Tokyo"))

    directory = products.core.OUTPUT_DIR / "products"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_text(
        products.product_page([], updated_at), encoding="utf-8"
    )

    products.add_home_product_search()
    products.add_products_to_sitemap(updated_at)
    print("Generated realtime product finder shell.")


if __name__ == "__main__":
    main()
