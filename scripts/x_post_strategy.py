"""Weighted selection for automated X copy variants.

Weights live in x_post_strategy.json so the weekly optimizer can adjust traffic
allocation without rewriting posting logic. Selection is deterministic for a
given slot/date and strategy version, which keeps retries idempotent.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONFIG = Path(__file__).with_name("x_post_strategy.json")
DEFAULT_COUNT = 5


def load_config() -> dict:
    try:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def strategy_version() -> int:
    try:
        return max(1, int(load_config().get("version", 1)))
    except (TypeError, ValueError):
        return 1


def weights_for(slot: str, count: int = DEFAULT_COUNT) -> list[float]:
    raw = load_config().get(f"{slot}_weights")
    if not isinstance(raw, list) or len(raw) != count:
        return [1.0] * count

    weights: list[float] = []
    for value in raw:
        try:
            weight = float(value)
        except (TypeError, ValueError):
            weight = 1.0
        # Never eliminate exploration and never let one variant monopolize.
        weights.append(min(3.0, max(0.25, weight)))
    return weights


def choose_variant(slot: str, seed: str, count: int = DEFAULT_COUNT) -> int:
    weights = weights_for(slot, count)
    total = sum(weights)
    if total <= 0:
        return 0

    version = strategy_version()
    digest = hashlib.sha256(f"{slot}:{seed}:v{version}".encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:8], "big") / float(2**64)
    target = fraction * total

    running = 0.0
    for index, weight in enumerate(weights):
        running += weight
        if target < running:
            return index
    return count - 1
