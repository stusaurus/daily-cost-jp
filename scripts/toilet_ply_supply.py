"""Canonical single/double toilet-paper supply for the daily catalog.

The existing category top-12 remains an independent compatibility surface.
This module never infers ply from 2x-longer rolls or from search keywords,
and never adds price, shipping, quantity or link evidence.
"""
from __future__ import annotations

from candidate_acquisition import identity
from comparison_units import comparison_unit
from product_quality import filter_items

MAX_PER_PLY = 6
FAMILY_LABELS = {"single": "シングル10m", "double": "ダブル10m"}


def group_toilet_offers(items):
    """Use only source-title verified 1-roll length and single/double ply."""
    groups = {"single": [], "double": []}
    for item in items:
        if not isinstance(item, dict):
            continue
        unit = comparison_unit("toilet-paper", item)
        if unit and unit[0] in FAMILY_LABELS.values():
            key = "single" if unit[0] == "シングル10m" else "double"
            groups[key].append(item)
    return groups


def build_toilet_ply_groups(items, limit=MAX_PER_PLY):
    """Choose up to six independently sorted verified offers per ply.

    The buyer sees two distinct sets of offers; the legacy top-12 catalog
    and its automated purchase-purpose features remain unchanged.
    """
    if not isinstance(items, list) or not 1 <= limit <= MAX_PER_PLY:
        raise ValueError("invalid toilet-paper comparison pool or limit")
    eligible = filter_items("toilet-paper", items)
    grouped = group_toilet_offers(eligible)
    result = {}
    for key in ("single", "double"):
        ordered = sorted(
            grouped[key],
            key=lambda row: (
                comparison_unit("toilet-paper", row)[1],
                row["price"],
                row.get("item_code", ""),
                row["name"],
            ),
        )
        chosen, seen = [], set()
        for offer in ordered:
            key_id = identity(offer)
            if key_id in seen:
                continue
            seen.add(key_id)
            chosen.append(offer)
            if len(chosen) >= limit:
                break
        # Apply exactly the same whole-selection safety filter as all published
        # product links. Return no unvalidated fallback for a rejected item.
        verified = filter_items("toilet-paper", chosen)
        result[key] = sorted(
            verified,
            key=lambda row: (
                comparison_unit("toilet-paper", row)[1],
                row["price"],
                row.get("item_code", ""),
            ),
        )
    return result


def supply_diagnostics(groups, acquisition):
    """Display status is evidence about the *snapshot*, not shop availability."""
    requests = acquisition.get("requests", []) if isinstance(acquisition, dict) else []
    status = {}
    for key, token in (("single", "シングル"), ("double", "ダブル")):
        matched = [r for r in requests if token in str(r.get("query", ""))]
        status[key] = {
            "verified": len(groups.get(key, [])),
            "search_attempted": bool(matched),
            "search_failed": any(r.get("error") for r in matched),
            "state": ("VERIFIED" if groups.get(key) else
                      "INCOMPLETE_ACQUISITION" if any(r.get("error") for r in matched) else
                      "NO_VERIFIED_SNAPSHOT_OFFER"),
        }
    return {"version": 1, "families": status}
