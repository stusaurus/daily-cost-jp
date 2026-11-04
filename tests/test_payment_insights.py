from decimal import Decimal

from scripts.payment_insights import payment_insight


def offer(id, checkout, unit, key="1枚", verified=True):
    return {"id": id, "unit_key": key, "checkout_yen": checkout, "unit_yen": unit, "shipping_verified": verified}


def test_reversal():
    result = payment_insight([offer("bulk", 1800, 8), offer("small", 950, 12)])
    assert result["type"] == "checkout_unit_reversal"
    assert result["checkout_winner_id"] == "small"
    assert result["unit_winner_id"] == "bulk"
    assert result["checkout_difference_yen"] == Decimal("850")


def test_no_claim_when_same_winner():
    assert payment_insight([offer("a", 800, 8), offer("b", 1000, 10)]) is None


def test_no_claim_across_units():
    assert payment_insight([offer("a", 800, 8, "1枚"), offer("b", 1000, 10, "100g")]) is None


def test_unverified_shipping_excluded():
    assert payment_insight([offer("a", 800, 8, verified=False), offer("b", 1000, 10)]) is None


def test_missing_or_nonfinite_price_excluded():
    assert payment_insight([offer("a", "NaN", 8), offer("b", 1000, 10)]) is None
    assert payment_insight([offer("a", -1, 8), offer("b", 1000, 10)]) is None


def test_deterministic_ties():
    assert payment_insight([offer("b", 1000, 10), offer("a", 1000, 10)]) is None
