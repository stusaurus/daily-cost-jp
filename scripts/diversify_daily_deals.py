"""Diversify the trusted daily-deals selection across days.

The core builder deliberately applies strict quality filters, but it previously
always took the same five highest-discount categories. When relative prices are
stable, that makes /today/ and automated X posts look unchanged for days.

This post-processing step keeps the exact same eligibility rules from
build_daily_deals.py, always retains the strongest current candidate, and
rotates the other four positions through a small pool of the next-best trusted
categories. The rotation is deterministic by JST date, so it needs no database
or persisted history and remains fully automatic on GitHub Actions.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
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

    # A stride of three changes most of the rotating slots each day while still
    # cycling predictably through the strongest eligible categories.
    offset = (now.date().toordinal() * 3) % len(pool)
    rotated = pool[offset:] + pool[:offset]
    selected = [anchor] + rotated[:4]

    # Display selected candidates strongest-first; selection itself still varies
    # by date. Every item already passed the same 8-55% conservative threshold.
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
    social["selection_mode"] = "daily_diversified"
    social["eligible_count"] = len(trusted)
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
    )


if __name__ == "__main__":
    main()
