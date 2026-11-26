"""Find additional in-stock retail listings using the official product directory."""
from collections import Counter
from datetime import date
from http.client import HTTPException
import time
from urllib.error import HTTPError, URLError

from marketplace_discovery import source_evidence
from marketplace_offers import valid_jan
from product_quality import filter_items

# Spread the acquisition budget across categories, including categories with few reviews.
SEEDS_PER_CATEGORY = 20
FIELDS = "itemName,itemCaption,itemCode,itemPrice,shopName,affiliateUrl,availability,postageFlag,reviewCount"


def directory_products(payload):
    rows = payload.get("Products", payload.get("items"))
    if rows is None and payload.get("count") == 0:
        return []
    if not isinstance(rows, list):
        raise ValueError("product_directory_schema")
    return [row.get("Product", row) for row in rows if isinstance(row, dict)]


def ranked_seeds(raw, excluded):
    by_jan = {}
    for product in raw:
        if not isinstance(product, dict):
            continue
        jan = str(product.get("productCode") or "")
        name = product.get("productName")
        if (len(jan) != 13 or not valid_jan(jan) or jan in excluded or not isinstance(name, str)
                or not name.strip() or not product.get("salesItemCount")):
            continue
        by_jan[jan] = {"jan": jan, "name": name, "brand": str(product.get("brandName") or ""),
                       "sellers": int(product["salesItemCount"]), "reviews": int(product.get("reviewCount") or 0)}
    return sorted(by_jan.values(), key=lambda seed: (-seed["reviews"], -seed["sellers"], seed["jan"]))


def select_seeds(seeds, previous, limit, day):
    """Refresh confirmed JANs first and rotate a bounded slice of the other candidates."""
    by_jan = {seed["jan"]: seed for seed in seeds}
    kept = [by_jan.get(jan, {"jan": jan, "name": "", "brand": ""})
            for jan in sorted(previous) if valid_jan(jan)][:24]
    remaining = [seed for seed in seeds if seed["jan"] not in previous]
    available = min(24 - len(kept), max(3, limit - len(kept)))
    if len(remaining) <= available:
        return kept + remaining
    fixed = available // 2
    rotating = remaining[fixed:]
    offset = day * (available - fixed) % len(rotating)
    return kept + remaining[:fixed] + (rotating[offset:] + rotating[:offset])[:available-fixed]


def extend_pool(pool, include, *, directory, listings, normalize_item, categories, pause=time.sleep,
                per_category=SEEDS_PER_CATEGORY, previous=None, day=0):
    stats = {"product_searches": 0, "item_searches": 0, "categories": {}}
    for category, profiles in include.items():
        config = categories[category]
        info = {"seeds": 0, "queried": 0, "verified_rows": 0, "reasons": Counter()}
        stats["categories"][category] = info
        verified = []
        try:
            pause(1.2)
            stats["product_searches"] += 1
            raw = directory(config, 1)
            seeds = ranked_seeds(raw, {profile.jan for profile in profiles})
            info["seeds"] = len(seeds)
            historical = set((previous or {}).get(category, ())) - {profile.jan for profile in profiles}
            for seed in select_seeds(seeds, historical, per_category, day):
                pause(1.2)
                stats["item_searches"] += 1
                info["queried"] += 1
                for raw_item in listings(seed["jan"]):
                    source = raw_item.get("Item", raw_item)
                    row = normalize_item(raw_item, config)
                    proof = source_evidence(source, row)
                    if not proof or proof["jan"] != seed["jan"]:
                        info["reasons"]["unverified_listing"] += 1
                        continue
                    verified.append({**row, **proof, "master_name": seed["name"],
                                     "master_brand": seed["brand"]})
        except (HTTPError, HTTPException, OSError, URLError, TypeError, ValueError, KeyError, AttributeError) as error:
            info["error"] = f"http_{error.code}" if isinstance(error, HTTPError) else type(error).__name__
            # Stop on provider throttling/authentication failures. A malformed
            # category result or one transient outage need not starve later categories.
            if (isinstance(error, HTTPError) and error.code in (401, 403, 429)
                    or sum("error" in item for item in stats["categories"].values()) >= 3):
                stats["stopped"] = info["error"]
        accepted = filter_items(category, verified)
        info["verified_rows"] = len(accepted)
        info["reasons"]["catalog_quality"] += len(verified) - len(accepted)
        # The fresh JAN request wins when the reviewed category query returned the same item.
        rows = {row["item_code"]: row for row in pool.get(category, [])}
        rows.update((row["item_code"], row) for row in accepted)
        pool[category] = list(rows.values())
        if "stopped" in stats:
            break
    return stats


def extend_current(pool, include):
    from build_site_entry import core, fetch_search_items, normalize_item_with_correct_postage
    from build_site_products import PRODUCT_API_URL
    from rakuten_request import fetch_json
    from urllib.parse import urlencode
    from urllib.request import Request
    def directory(config, page):
        params = {"applicationId": core.APP_ID, "keyword": config["name"], "page": page,
                  "hits": 30, "formatVersion": 2, "format": "json",
                  "elements": "productCode,productName,brandName,salesItemCount,reviewCount"}
        req = Request(PRODUCT_API_URL + "?" + urlencode(params),
                      headers={"accessKey": core.ACCESS_KEY, "Origin": "https://stusaurus.github.io",
                               "Referer": core.SITE_URL, "User-Agent": "daily-cost-jp/0.8"})
        return directory_products(fetch_json(req))

    def listings(jan):
        return fetch_search_items({
            "applicationId": core.APP_ID, "affiliateId": core.AFFILIATE_ID,
            "keyword": jan, "availability": 1, "postageFlag": 1,
            "sort": "+itemPrice", "hits": 30, "formatVersion": 2, "format": "json", "elements": FIELDS,
        })
    # Prior publication supplies lookup keys only. All prices, stock, terms, titles
    # and affiliate destinations still come from this build's API responses.
    from price_observations import fetch_public
    previous = {}
    try:
        for key, entry in fetch_public("marketplace-coverage.json")["categories"].items():
            previous[key] = {row["jan"] for row in entry.get("discovery", {}).get("sources", [])
                             if valid_jan(row.get("jan"))}
    except (OSError, HTTPException, TypeError, KeyError, ValueError, AttributeError):
        previous = {}
    return extend_pool(pool, include, directory=directory, listings=listings,
                       previous=previous, day=date.today().toordinal(),
                       normalize_item=normalize_item_with_correct_postage,
                       categories={item["id"]: item for item in core.CATEGORIES})
