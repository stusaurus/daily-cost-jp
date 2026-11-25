"""Read-only connection check with aggregate output and no tracker requests."""
import os
from collections import Counter

from yahoo_shopping import YahooShopping, YahooUnavailable


def main():
    try:
        client = YahooShopping(os.getenv("YAHOO_APP_ID", ""), os.getenv("YAHOO_AFFILIATE_ID", ""))
        for jan in ("4901301440815", "4901301466235", "4987176304834"):
            hits = client.search(jan=jan)
            shipping = Counter(str(hit.get("shipping", {}).get("code")) for hit in hits
                               if isinstance(hit.get("shipping"), dict))
            print(f"JAN {jan}: hits={len(hits)} exact_jan={sum(hit.get('janCode') == jan for hit in hits)} "
                  f"verified_ad_links={sum(bool(client.affiliate_link(hit)) for hit in hits)} "
                  f"taxable_true={sum(isinstance(hit.get('priceLabel'), dict) and hit['priceLabel'].get('taxable') is True for hit in hits)} "
                  f"shipping_free={shipping['2']} shipping_conditional={shipping['3']}", flush=True)
            if any(client.affiliate_link(hit) for hit in hits):
                return 0
        print("Yahoo connection succeeded but no verified ValueCommerce link was found.")
    except YahooUnavailable as error:
        print(f"Yahoo verification unavailable: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
