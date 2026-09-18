from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import x_post_strategy as strategy


class XPostStrategyTests(unittest.TestCase):
    def test_choice_is_deterministic(self):
        first = strategy.choose_variant("morning", "2026-09-19")
        second = strategy.choose_variant("morning", "2026-09-19")
        self.assertEqual(first, second)
        self.assertIn(first, range(5))

    def test_weights_are_clamped_and_invalid_values_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "strategy.json"
            config.write_text(json.dumps({
                "version": 2,
                "morning_weights": [0, 100, "bad", 0.5, 1],
            }), encoding="utf-8")
            with mock.patch.object(strategy, "CONFIG", config):
                self.assertEqual(strategy.weights_for("morning"), [0.25, 3.0, 1.0, 0.5, 1.0])

    def test_missing_config_uses_equal_weights(self):
        with mock.patch.object(strategy, "CONFIG", Path("/definitely/missing.json")):
            self.assertEqual(strategy.weights_for("evening"), [1.0] * 5)


if __name__ == "__main__":
    unittest.main()
