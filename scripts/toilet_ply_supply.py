"""Keep single and double toilet-paper offers in separate, evidenced rankings.

Every input must already pass the shared category quality gate. This helper
never creates price, length, ply or shipping evidence.
"""
from comparison_units import comparison_unit


def group_toilet_offers(items):
    groups = {"シングル10m": [], "ダブル10m": []}
    for item in items:
        unit = comparison_unit("toilet-paper", item)
        if unit and unit[0] in groups:
            groups[unit[0]].append(item)
    return groups


def select_toilet_rankings(items, choose_ranked, validate_group, limit=6):
    """Preserve the primary ranking, expose the other ply independently."""
    groups = group_toilet_offers(items)
    # Never remove existing verified, eligible category offers just to add
    # double-ply. The established ranking already groups confirmed 10m units
    # separately in its reader-facing presentation. Its other candidates stay.
    metric, ranked = choose_ranked(items)
    ranked_urls = {row.get("url") for row in ranked}
    candidates = sorted(
        (row for row in groups["ダブル10m"] if row.get("url") not in ranked_urls),
        key=lambda row: (comparison_unit("toilet-paper", row)[1], row["price"], row.get("name", "")),
    )
    # Additional links have independent per-10m evidence and the same safety
    # gate, without shrinking the existing 12-offer catalog.
    alternatives = validate_group("toilet-paper", candidates[:limit])
    primary = "シングル10m" if groups["シングル10m"] else (
        "ダブル10m" if groups["ダブル10m"] else None
    )
    return metric, ranked, alternatives, primary
