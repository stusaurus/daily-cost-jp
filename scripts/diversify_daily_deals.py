"""Diversify the trusted daily-deals selection across rebuilds.

The core builder deliberately applies strict quality filters. This step keeps
those eligibility rules, always retains the strongest current candidate, and
rotates the other four positions through the next-best trusted categories.
The rotation changes between the morning and evening refresh windows so an
X-time rebuild can surface fresh candidates without weakening price quality.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import build_daily_deals as base

JST = ZoneInfo("Asia/Tokyo")
ROTATING_POOL_SIZE = 9


def all_trusted_rows(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for category_id, category in (payload.get("categories") or {}).items():
        row = base.choose_category(category_id, category or {})
        if row:
            rows.append(row)
    rows.sort(key=lambda row: (-row["discount"], row["unit_price"]))
    return rows


def select_diverse(rows: list[dict], now: datetime) -> list[dict]:
    """Keep the strongest deal and rotate four other high-quality candidates."""
    if len(rows) <= 5:
        return rows[:5]

    anchor = rows[0]
    pool = rows[1 : 1 + ROTATING_POOL_SIZE]
    if len(pool) <= 4:
        return rows[:5]

    # Use two deterministic windows per JST day. A rebuild before the evening
    # X post therefore gets a different rotation from the morning build while
    # remaining stable within each window and requiring no persisted database.
    refresh_slot = 0 if now.hour < 12 else 1
    seed = now.date().toordinal() * 2 + refresh_slot
    offset = (seed * 3) % len(pool)
    rotated = pool[offset:] + pool[:offset]
    selected = [anchor] + rotated[:4]

    selected.sort(key=lambda row: (-row["discount"], row["unit_price"]))
    return selected


def main() -> None:
    if not base.DATA.exists():
        raise SystemExit("site/data.json not found")

    payload = json.loads(base.DATA.read_text(encoding="utf-8"))
    trusted = all_trusted_rows(payload)
    if not trusted:
        print("No trusted daily deals available for diversified selection")
        return

    now = datetime.now(JST)
    rows = select_diverse(trusted, now)

    base.TODAY_DIR.mkdir(parents=True, exist_ok=True)
    base.SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
    (base.TODAY_DIR / "index.html").write_text(base.render_page(rows, now), encoding="utf-8")

    social = base.build_social(rows, now)
    social["selection_mode"] = "twice_daily_diversified"
    social["eligible_count"] = len(trusted)
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
        f"from {len(trusted)} eligible categories",
        f"slot={social['refresh_slot']}",
    )


if __name__ == "__main__":
    main()
