"""Conservative sale-quantity labels derived from explicit product-title evidence."""
from __future__ import annotations

import re
import unicodedata


COUNT_UNITS = "ロール|巻|個|本|箱|パック|袋|枚|組|セット"
CONTAINER_UNITS = "ロール|巻|個|本|箱|パック|袋|枚|セット"


def normalize(text: str) -> str:
    return (unicodedata.normalize("NFKC", str(text or ""))
            .replace("×", "x").replace("✕", "x").replace("*", "x")
            .replace(",", ""))


def _number(value: str) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _consistent(price, unit_price, expected: float) -> bool:
    try:
        actual = float(price) / float(unit_price)
    except (TypeError, ValueError, ZeroDivisionError):
        return False
    # Unit prices are displayed after rounding, while source data is not.  A
    # 12% relative allowance (and a tiny absolute allowance) covers that only.
    return actual > 0 and abs(actual - expected) <= max(0.12 * expected, 0.08)


def parse_sale_quantity(title: str):
    """Return one explicit, unambiguous sale quantity, or ``None``.

    Bare numbers are deliberately never considered.  The returned
    ``metric_quantity`` is expressed in the same units used by unit_price.
    """
    text = normalize(title)
    if re.search(r"(?:種類|タイプ|サイズ|容量|個数)を選べる", text):
        return None

    measure = list(re.finditer(
        rf"(?<![A-Za-z0-9.])(?P<n>\d+(?:\.\d+)?)\s*(?P<u>kg|g|ml|l)"
        rf"(?:\s*x\s*(?P<m>\d+)\s*(?P<c>{CONTAINER_UNITS}))?",
        text, re.IGNORECASE,
    ))
    if measure:
        # Multiple differing capacities commonly describe selectable variants.
        signatures = {(m.group("n"), m.group("u").lower(), m.group("m") or "1") for m in measure}
        if len(signatures) != 1:
            return None
        m = measure[0]
        amount = float(m.group("n")); unit = m.group("u").lower()
        multiplier = int(m.group("m") or 1)
        if amount <= 0 or multiplier <= 0:
            return None
        shown_unit = "L" if unit == "l" else unit
        label = f"{_number(m.group('n'))}{shown_unit}"
        if m.group("m"):
            container = "ロール" if m.group("c") == "巻" else m.group("c")
            label += f"×{multiplier}{container}"
        base = amount * multiplier * (1000 if unit in ("kg", "l") else 1)
        return {
            "label": label,
            "kind": "weight" if unit in ("kg", "g") else "volume",
            "base_amount": base,
            "confidence": 0.99 if m.group("m") else 0.90,
        }

    compound = list(re.finditer(
        rf"(?<![A-Za-z0-9.])(?P<n>\d+)\s*(?P<u>{COUNT_UNITS})\s*x\s*"
        rf"(?P<m>\d+)\s*(?P<c>{CONTAINER_UNITS})", text, re.IGNORECASE,
    ))
    if compound:
        values = {(m.group("n"), m.group("u"), m.group("m"), m.group("c")) for m in compound}
        if len(values) != 1:
            return None
        m = compound[0]
        unit = "ロール" if m.group("u") == "巻" else m.group("u")
        container = "ロール" if m.group("c") == "巻" else m.group("c")
        return {"label": f"{int(m.group('n'))}{unit}×{int(m.group('m'))}{container}",
                "kind": "count", "count_unit": unit,
                "total_count": int(m.group("n")) * int(m.group("m")),
                "outer_count": int(m.group("m")), "outer_unit": container,
                "confidence": 0.99}

    singles = list(re.finditer(rf"(?<![A-Za-z0-9.])(?P<n>\d+)\s*(?P<u>{COUNT_UNITS})(?:入り)?", text))
    if len(singles) != 1:
        return None
    m = singles[0]
    unit = "ロール" if m.group("u") == "巻" else m.group("u")
    return {"label": f"{int(m.group('n'))}{unit}入り", "kind": "count",
            "count_unit": unit, "total_count": int(m.group("n")),
            "confidence": 0.92}


def sale_quantity_for_item(title, price, unit_price, metric):
    """Parse and verify a label against an independently supplied unit price."""
    parsed = parse_sale_quantity(title)
    if not parsed or parsed["confidence"] < 0.90:
        return None
    expected = None
    if metric in ("piece", "sheet", "roll", "box", "pack") and parsed["kind"] == "count":
        metric_unit = {"piece": ("個", "本"), "sheet": ("枚",), "roll": ("ロール",),
                       "box": ("箱",), "pack": ("パック",)}[metric]
        if parsed.get("count_unit") in metric_unit:
            expected = parsed["total_count"]
        elif parsed.get("outer_unit") in metric_unit:
            expected = parsed["outer_count"]
    elif metric == "100g" and parsed["kind"] == "weight":
        expected = parsed["base_amount"] / 100
    elif metric == "100ml" and parsed["kind"] == "volume":
        expected = parsed["base_amount"] / 100
    elif metric == "1L" and parsed["kind"] == "volume":
        expected = parsed["base_amount"] / 1000
    if expected is None or not _consistent(price, unit_price, expected):
        return None
    return {"sale_quantity_label": parsed["label"],
            "sale_quantity_confidence": parsed["confidence"]}


def purchase_summary(item: dict) -> str:
    price = int(float(item.get("price") or 0))
    label = item.get("sale_quantity_label")
    prefix = f"{label}・" if label else "商品価格 "
    return f"{prefix}¥{price:,}（送料込み）"
