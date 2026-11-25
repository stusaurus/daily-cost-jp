"""Verify credentialed API responses and exact pairs without visiting ad links."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path

from marketplace_comparison import PRODUCTS, select
from yahoo_shopping import YahooShopping, YahooUnavailable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    try:
        client = YahooShopping(os.getenv("YAHOO_APP_ID", ""), os.getenv("YAHOO_AFFILIATE_ID", ""))
        verified = 0
        for products in PRODUCTS.values():
            for product in products:
                hits = client.search(jan=product.jan)
                links = sum(bool(client.affiliate_link(hit)) for hit in hits if hit.get("janCode") == product.jan)
                shipping = Counter(str(hit["shipping"].get("code")) for hit in hits
                                   if isinstance(hit.get("shipping"), dict))
                verified += links
                print(f"JAN {product.jan}: hits={len(hits)} verified_ad_links={links} "
                      f"shipping_free={shipping['2']} shipping_conditional={shipping['3']}", flush=True)
        baseline = {"laundry", "softener", "dish", "toilet-cleaner"}
        missing_comparable = []
        for category in PRODUCTS:
            rows = catalog["categories"].get(category, {}).get("items", [])
            groups, candidates = select(category, rows, client)
            comparable = sum(all(offer.total is not None for offer in offers) for _, _, offers in groups)
            if category in baseline and not comparable:
                missing_comparable.append(category)
            print(f"{category}: matched_pairs={len(groups)} comparable_totals={comparable} "
                  f"counts={json.dumps(candidates, sort_keys=True)}", flush=True)
        if not verified:
            print("Yahoo connection succeeded but no verified ValueCommerce link was found.")
        elif missing_comparable:
            print("Missing comparable totals:", ", ".join(missing_comparable))
        else:
            return 0
    except YahooUnavailable as error:
        print(f"Yahoo verification unavailable: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
