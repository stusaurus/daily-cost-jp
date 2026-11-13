"""Fail closed when a toilet-paper buying card no longer matches its offer.

The page must contain both comparison choices, including a truthful search-only
empty state. This checks generated HTML independently of the presentation code.
"""
from bs4 import BeautifulSoup
from comparison_units import comparison_unit

LABELS = {"single": "シングル10m", "double": "ダブル10m"}


def audit_page(category, html_text):
    groups = category.get("toilet_ply_groups") or {}
    soup = BeautifulSoup(html_text, "html.parser")
    errors = []
    if len(soup.select(".toilet-ply-compare")) != 1:
        errors.append("Missing or repeated ply comparison")
    for family, label in LABELS.items():
        section = soup.select_one(f"#toilet-{family}-offers")
        nav = soup.select(f'.toilet-ply-links a[href="#toilet-{family}-offers"]')
        if len(nav) != 1 or section is None:
            errors.append(f"{family}: comparison navigation missing")
            continue
        expected = groups.get(family, [])
        if not isinstance(expected, list):
            errors.append(f"{family}: malformed comparison data")
            continue
        actual = section.select(".toilet-ply-card")
        if len(actual) != len(expected):
            errors.append(f"{family}: rendered offer count does not match catalog")
            continue
        for n, (card, offer) in enumerate(zip(actual, expected), start=1):
            cta = card.select_one("a.toilet-ply-buy")
            unit = comparison_unit("toilet-paper", offer)
            if not cta or not unit or unit[0] != label:
                errors.append(f"{family}/{n}: missing purchase link or invalid unit")
                continue
            if (cta.get("href") != offer["url"] or
                cta.get("data-category-id") != "toilet-paper" or
                cta.get("data-conversion-source") != "category" or
                cta.get("data-id") != offer.get("item_code", "") or
                cta.get("data-shipping-price") != str(offer["price"]) or
                cta.get("data-unit-price-label") != f"¥{unit[1]:.2f}／{label}"):
                errors.append(f"{family}/{n}: purchase data mismatches trusted offer")
            amount = card.select_one(".toilet-ply-amount")
            unit_label = card.select_one(".toilet-ply-unit")
            if (not amount or amount.get_text(strip=True) != f"¥{unit[1]:.2f}" or
                not unit_label or unit_label.get_text(strip=True) != f"／{label}" or
                f"¥{offer['price']:,}" not in card.get_text(" ", strip=True)):
                errors.append(f"{family}/{n}: displayed price mismatches trusted offer")
        if not expected:
            if section.select("a.toilet-ply-buy"):
                errors.append(f"{family}: invented checkout in empty state")
            if not section.select_one("a.toilet-ply-search"):
                errors.append(f"{family}: empty-state search unavailable")
    return errors
