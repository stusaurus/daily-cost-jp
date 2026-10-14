from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import diversify_daily_deals as diversify

JST = ZoneInfo("Asia/Tokyo")


def row(index: int, discount: float) -> dict:
    return {
        "id": f"cat{index}",
        "name": f"Category {index}",
        "discount": discount,
        "unit_price": float(index + 1),
    }


class DailyDealDiversityTests(unittest.TestCase):
    def test_adjacent_days_change_the_selected_set_when_pool_is_large_enough(self):
        broad = [row(i, 30 - i) for i in range(8)]
        strict = broad[:3]
        first = diversify.select_diverse(strict, broad, datetime(2026, 9, 19, 6, tzinfo=JST))
        second = diversify.select_diverse(strict, broad, datetime(2026, 9, 20, 6, tzinfo=JST))
        # The top slot now rotates too (production change on September 19).
        self.assertNotEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(len(first), 5)
        self.assertEqual(len(second), 5)
        self.assertNotEqual({r["id"] for r in first}, {r["id"] for r in second})

    def test_no_duplicate_categories(self):
        broad = [row(i, 30 - i) for i in range(7)]
        broad.append(dict(broad[2]))
        selected = diversify.select_diverse(broad[:2], broad, datetime(2026, 9, 19, 6, tzinfo=JST))
        ids = [r["id"] for r in selected]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
