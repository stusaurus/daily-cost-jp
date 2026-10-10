"""Conservative purchase-size choices for tissue, independent of bulk unit ranking.

Never infer the number of boxes from '5 boxes x N' without rechecking the
same shared quality rules used by the published ranking. A box is NOT the
same unit as a pack; do not mix them or invent a 5-box price.
"""
from __future__ import annotations

import math
from product_quality import item_rejection, filter_items, parsed_quantity

MAX_SMALL_BOXES = 10


def safe_box_count(item):
    if not isinstance(item, dict) or item.get("metric") != "box":
        return None
    if item_rejection("tissue", item) is not None:
        return None
    parsed = parsed_quantity("tissue", item.get("name", ""))
    if not parsed or parsed.get("metric") != "box":
        return None
    try:
        price, unit = float(item["price"]), float(item["unit_price"])
        qty = float(parsed["quantity"])
    except (TypeError, ValueError, KeyError):
        return None
    if not all(math.isfinite(v) and v > 0 for v in (price, unit, qty)):
        return None
    if (not qty.is_integer() or not 1 <= qty <= MAX_SMALL_BOXES or
            not math.isclose(price / unit, qty, rel_tol=0.0001, abs_tol=0.0001)):
        return None
    return int(qty)


def choose_small_tissue_offer(items):
    """Best unit price among currently safe 1–10-box offers, not a market best."""
    if not isinstance(items, list):
        return None
    safe = filter_items("tissue", items)
    candidates = [p for p in safe if safe_box_count(p) is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda p: (p["unit_price"], p["price"], p["name"]))


def small_offer_snapshot(items):
    offer = choose_small_tissue_offer(items)
    if offer is None:
        return {"status": "NO_VERIFIED_SMALL_OFFER", "boxes": None, "offer": None}
    return {
        "status": "VERIFIED_WITHIN_FETCHED_OFFERS",
        "boxes": safe_box_count(offer),
        "offer": offer,
    }
