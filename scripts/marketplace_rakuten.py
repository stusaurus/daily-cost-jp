"""Refresh specific, previously verified Rakuten products for marketplace pages."""
import os
from http.client import HTTPException
from time import sleep
from urllib.error import HTTPError, URLError

from marketplace_offers import known_shipping, rakuten_offer
from product_quality import VERSION, parsed_quantity


def exact_rakuten_row(category, code, source, product):
    if not isinstance(source, dict) or source.get("itemCode") != code:
        return None
    price = source.get("itemPrice")
    name = source.get("itemName")
    caption = source.get("itemCaption")
    if (source.get("availability") != 1 or source.get("postageFlag") != 0
            or type(price) is not int or price <= 0 or not isinstance(name, str)
            or not isinstance(caption, str) or not known_shipping(f"{name} {caption}")):
        return None
    quantity = parsed_quantity(category, name)
    if not quantity or quantity["confidence"] < 0.84:
        return None
    row = {"name": name, "price": price, "postage": "送料込み", "item_code": code,
           "shop": source.get("shopName"), "url": source.get("affiliateUrl"),
           "metric": quantity["metric"], "unit_price": price / quantity["quantity"],
           "category_id": category, "quality_version": VERSION}
    return row if rakuten_offer(category, row, product) else None


def refresh_exact(category, products, *, fetch=None, pause=sleep):
    if fetch is None:
        if not all(os.getenv(key) for key in ("RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY", "RAKUTEN_AFFILIATE_ID")):
            return [], "missing_credentials"
        from build_site_entry import fetch_exact_marketplace_item
        fetch = fetch_exact_marketplace_item
    rows, status = [], "ok"
    needs_pause = False
    for product in products:
        for code, _ in product.rakuten_evidence:
            if needs_pause:
                pause(1.2)
            needs_pause = True
            try:
                items = fetch(code)
            except HTTPError as error:
                status = f"http_{error.code}"
                if error.code in (401, 403, 429):
                    return rows, status
                continue
            except (URLError, OSError, HTTPException, ValueError, AttributeError):
                status = "network_or_response"
                continue
            if not isinstance(items, list):
                status = "response_schema"
                continue
            for raw in items:
                if isinstance(raw, dict) and (row := exact_rakuten_row(category, code, raw.get("Item", raw), product)):
                    rows.append(row)
    return rows, status
