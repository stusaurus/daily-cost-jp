"""Find additional in-stock retail listings using the official product directory."""
from collections import Counter
from http.client import HTTPException
import time
from urllib.error import HTTPError, URLError

from marketplace_discovery import source_evidence
from marketplace_offers import valid_jan
from product_quality import filter_items

# Spread the acquisition budget across categories, including categories with few reviews.
SEEDS_PER_CATEGORY = 12
FIELDS = "itemName,itemCaption,itemCode,itemPrice,shopName,affiliateUrl,availability,postageFlag,reviewCount"


def directory_products(payload):
    rows = payload.get("Products", payload.get("items"))
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


def extend_pool(pool, include, *, directory, listings, normalize_item, categories, pause=time.sleep,
                per_category=SEEDS_PER_CATEGORY):
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
            for seed in seeds[:per_category]:
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
            stats["stopped"] = f"http_{error.code}" if isinstance(error, HTTPError) else "network_or_response"
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
    return extend_pool(pool, include, directory=directory, listings=listings,
                       normalize_item=normalize_item_with_correct_postage,
                       categories={item["id"]: item for item in core.CATEGORIES})
