"""Diversify trusted daily deals across rebuilds and social posts."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import build_daily_deals as base

JST = ZoneInfo("Asia/Tokyo")
ROTATING_POOL_SIZE = 12
STRICT_MIN_DISCOUNT = 8.0
BROAD_MIN_DISCOUNT = 3.0
FALLBACK_MIN_DISCOUNT = 1.0
TARGET_POOL_SIZE = 7


def candidate_rows(payload: dict, min_discount: float) -> list[dict]:
    rows: list[dict] = []
    for category_id, category in (payload.get("categories") or {}).items():
        row = base.choose_category(
            category_id,
            category or {},
            min_discount=min_discount,
            max_discount=55.0,
        )
        if row:
            rows.append(row)
    rows.sort(key=lambda row: (-row["discount"], row["unit_price"]))
    return rows


def slot_seed(now: datetime) -> int:
    refresh_slot = 0 if now.hour < 12 else 1
    return now.date().toordinal() * 2 + refresh_slot


def select_diverse(strict_rows: list[dict], broad_rows: list[dict], now: datetime) -> list[dict]:
    """Keep the strongest strict deal and rotate four other safe categories."""
    if not broad_rows:
        return strict_rows[:5]

    anchor = strict_rows[0] if strict_rows else broad_rows[0]
    pool = [row for row in broad_rows if row["id"] != anchor["id"]][:ROTATING_POOL_SIZE]
    if not pool:
        return [anchor]

    # Pick four from a larger pool. With five or more alternatives, at least
    # one category changes between adjacent slots instead of freezing forever.
    offset = (slot_seed(now) * 3) % len(pool)
    rotated = pool[offset:] + pool[:offset]
    selected = [anchor] + rotated[:4]

    # Never duplicate a category even if upstream data changes unexpectedly.
    unique: list[dict] = []
    seen: set[str] = set()
    for row in selected:
        category_id = str(row.get("id") or "")
        if not category_id or category_id in seen:
            continue
        seen.add(category_id)
        unique.append(row)

    unique.sort(key=lambda row: (-row["discount"], row["unit_price"]))
    return unique[:5]


def social_order(rows: list[dict], now: datetime) -> list[dict]:
    """Keep the strongest pick, but vary the other X picks across refreshes."""
    if len(rows) <= 2:
        return rows
    anchor = rows[0]
    others = rows[1:]
    offset = slot_seed(now) % len(others)
    rotated = others[offset:] + others[:offset]
    return [anchor] + rotated


def main() -> None:
    if not base.DATA.exists():
        raise SystemExit("site/data.json not found")

    payload = json.loads(base.DATA.read_text(encoding="utf-8"))

    strict = candidate_rows(payload, STRICT_MIN_DISCOUNT)
    broad = candidate_rows(payload, BROAD_MIN_DISCOUNT)
    used_min_discount = BROAD_MIN_DISCOUNT

    # If the strict 8% rule leaves almost no room to rotate, widen only the
    # discount threshold. Confidence, postage, metric consistency, sample size
    # and outlier rejection remain exactly the same.
    if len(broad) < TARGET_POOL_SIZE:
        broad = candidate_rows(payload, FALLBACK_MIN_DISCOUNT)
        used_min_discount = FALLBACK_MIN_DISCOUNT

    if not broad:
        print("No safe daily deals available for diversified selection")
        return

    now = datetime.now(JST)
    rows = select_diverse(strict, broad, now)

    base.TODAY_DIR.mkdir(parents=True, exist_ok=True)
    base.SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
    (base.TODAY_DIR / "index.html").write_text(base.render_page(rows, now), encoding="utf-8")

    social = base.build_social(social_order(rows, now), now)
    social["items"] = rows
    social["selection_mode"] = "daily_rotating_safe_pool"
    social["strict_eligible_count"] = len(strict)
    social["eligible_count"] = len(broad)
    social["rotation_min_discount"] = used_min_discount
    social["refresh_slot"] = "morning" if now.hour < 12 else "evening"
    (base.TODAY_DIR / "data.json").write_text(
        json.dumps(social, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (base.SOCIAL_DIR / "latest.json").write_text(
        json.dumps(social, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (base.SOCIAL_DIR / "latest.txt").write_text(social["text"] + "\n", encoding="utf-8")

    base.inject_home(rows, now)
    base.update_sitemap()
    print(
        "Diversified daily deals:",
        ", ".join(f"{row['name']}({row['discount']:.0f}%)" for row in rows),
        f"from {len(broad)} safe categories",
        f"strict={len(strict)}",
        f"min_discount={used_min_discount:g}%",
        f"slot={social['refresh_slot']}",
    )


if __name__ == "__main__":
    main()
