"""Regression checks for the price-reversal insight in the standard unittest CI."""
import unittest
from decimal import Decimal

from scripts.payment_insights import payment_insight


def offer(id, checkout, unit, key="1枚", verified=True):
    return {
        "id": id, "unit_key": key, "checkout_yen": checkout,
        "unit_yen": unit, "shipping_verified": verified,
    }


class TestPaymentInsights(unittest.TestCase):
    def test_reversal(self):
        result = payment_insight([offer("bulk", 1800, 8), offer("small", 950, 12)])
        self.assertEqual(result["type"], "checkout_unit_reversal")
        self.assertEqual(result["checkout_winner_id"], "small")
        self.assertEqual(result["unit_winner_id"], "bulk")
        self.assertEqual(result["checkout_difference_yen"], Decimal("850"))

    def test_no_claim_when_same_winner(self):
        self.assertIsNone(payment_insight([offer("a", 800, 8), offer("b", 1000, 10)]))

    def test_no_claim_across_units(self):
        self.assertIsNone(payment_insight([
            offer("a", 800, 8, "1枚"), offer("b", 1000, 10, "100g")
        ]))

    def test_unverified_shipping_excluded(self):
        self.assertIsNone(payment_insight([
            offer("a", 800, 8, verified=False), offer("b", 1000, 10)
        ]))

    def test_missing_or_nonfinite_price_excluded(self):
        self.assertIsNone(payment_insight([offer("a", "NaN", 8), offer("b", 1000, 10)]))
        self.assertIsNone(payment_insight([offer("a", -1, 8), offer("b", 1000, 10)]))

    def test_deterministic_ties(self):
        self.assertIsNone(payment_insight([offer("b", 1000, 10), offer("a", 1000, 10)]))


if __name__ == "__main__":
    unittest.main()
