"""Direct tests for Wyckoff and level-based Sage schools."""

from __future__ import annotations

import pytest

from eta_engine.brain.jarvis_v3.sage.base import Bias, MarketContext
from eta_engine.brain.jarvis_v3.sage.schools.support_resistance import (
    SupportResistanceSchool,
    _find_pivots,
)
from eta_engine.brain.jarvis_v3.sage.schools.weis_wyckoff import WeisWyckoffSchool
from eta_engine.brain.jarvis_v3.sage.schools.wyckoff import WyckoffSchool


def _bars_from_closes(closes: list[float], *, volume: float = 1_000.0) -> list[dict[str, float]]:
    return [
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": volume,
        }
        for close in closes
    ]


def test_wyckoff_detects_spring_against_prior_range() -> None:
    bars = _bars_from_closes([101.0] * 29, volume=1_000.0)
    bars.append({"open": 100.5, "high": 101.0, "low": 99.0, "close": 100.75, "volume": 1_500.0})

    verdict = WyckoffSchool().analyze(MarketContext(bars=bars, side="long"))

    assert verdict.bias == Bias.LONG
    assert verdict.aligned_with_entry is True
    assert verdict.signals["spring"] is True
    assert verdict.signals["range_low"] == 100.5


def test_wyckoff_detects_upthrust_against_prior_range() -> None:
    bars = _bars_from_closes([101.0] * 29, volume=1_000.0)
    bars.append({"open": 101.0, "high": 102.0, "low": 100.5, "close": 101.25, "volume": 1_500.0})

    verdict = WyckoffSchool().analyze(MarketContext(bars=bars, side="short"))

    assert verdict.bias == Bias.SHORT
    assert verdict.aligned_with_entry is True
    assert verdict.signals["upthrust"] is True
    assert verdict.signals["range_high"] == 101.5


def test_support_resistance_pivot_detection_and_validation() -> None:
    values = [1.0, 2.0, 5.0, 2.0, 1.0, 3.0, 1.0]

    assert _find_pivots(values, lookback=1, kind="high") == [(2, 5.0), (5, 3.0)]
    assert _find_pivots(values, lookback=1, kind="low") == [(4, 1.0)]
    with pytest.raises(ValueError, match="kind"):
        _find_pivots(values, kind="middle")


def test_support_resistance_returns_neutral_when_pivots_are_missing() -> None:
    verdict = SupportResistanceSchool().analyze(
        MarketContext(bars=_bars_from_closes([100.0 + i for i in range(30)]), side="long")
    )

    assert verdict.bias == Bias.NEUTRAL
    assert verdict.conviction <= 0.1


def test_weis_wyckoff_detects_seller_exhaustion() -> None:
    closes = (
        [100.0]
        + [101.0, 102.0, 103.0, 104.0]
        + [103.0, 102.0, 101.0, 100.0, 99.0]
        + [100.0, 101.0, 102.0, 103.0]
        + [102.5, 102.0, 101.5, 101.0, 100.5, 100.0]
    )
    volumes = [100.0] + [100.0] * 4 + [500.0] * 5 + [120.0] * 4 + [100.0] * 6
    bars = [
        {"open": close, "high": close + 0.25, "low": close - 0.25, "close": close, "volume": volume}
        for close, volume in zip(closes, volumes, strict=True)
    ]

    verdict = WeisWyckoffSchool().analyze(MarketContext(bars=bars, side="long"))

    assert verdict.bias == Bias.LONG
    assert verdict.aligned_with_entry is True
    assert verdict.signals["sellers_exhausted"] is True
