"""Explain the difference between unit-price and checkout-price choices.

Uses verified comparison groups supplied by the caller. Does not infer pack
size from an item title, or claim that different products are interchangeable.
"""
from decimal import Decimal, InvalidOperation


def _money(value):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d > 0 else None


def payment_insight(offers):
    """Return a grounded insight or None.

    Each offer: id, unit_key, checkout_yen, unit_yen, shipping_verified.
    Only items with the SAME unit_key are compared. Caller must ensure product
    suitability and comparability before passing a group.
    """
    clean = []
    for item in offers:
        if not isinstance(item, dict) or item.get("shipping_verified") is not True:
            continue
        unit_key = item.get("unit_key")
        if not isinstance(unit_key, str) or not unit_key.strip():
            continue
        checkout = _money(item.get("checkout_yen"))
        unit = _money(item.get("unit_yen"))
        if checkout is None or unit is None or not item.get("id"):
            continue
        clean.append({"id": str(item["id"]), "unit_key": unit_key, "checkout": checkout, "unit": unit})
    if len(clean) < 2 or len({x["unit_key"] for x in clean}) != 1:
        return None
    by_checkout = min(clean, key=lambda x: (x["checkout"], x["unit"], x["id"]))
    by_unit = min(clean, key=lambda x: (x["unit"], x["checkout"], x["id"]))
    if by_checkout["id"] == by_unit["id"]:
        return None
    extra = by_unit["checkout"] - by_checkout["checkout"]
    if extra <= 0:
        return None
    return {
        "type": "checkout_unit_reversal",
        "title": "単価最安と支払総額最安は違います",
        "checkout_winner_id": by_checkout["id"],
        "unit_winner_id": by_unit["id"],
        "checkout_difference_yen": extra,
        "detail": "単価が安い商品を選ぶと、今回の支払総額はより高くなります。購入量と必要量を確認してください。",
    }
