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
    primary = "シングル10m" if groups["シングル10m"] else (
        "ダブル10m" if groups["ダブル10m"] else None
    )
    if primary is None:
        metric, ranked = choose_ranked(items)
        return metric, ranked, [], None

    metric, ranked = choose_ranked(groups[primary])
    secondary = "ダブル10m" if primary == "シングル10m" else "シングル10m"
    candidates = sorted(
        groups[secondary],
        key=lambda row: (comparison_unit("toilet-paper", row)[1], row["price"], row.get("name", "")),
    )
    # Never bypass the same outlier and offer-eligibility recheck as published ranking.
    alternatives = validate_group("toilet-paper", candidates[:limit])
    return metric, ranked, alternatives, primary
