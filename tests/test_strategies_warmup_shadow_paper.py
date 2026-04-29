"""Direct strategy tests for warm-up sizing and shadow-paper reinstatement."""

from __future__ import annotations

from datetime import date

import pytest

from eta_engine.strategies.per_bot_registry import StrategyAssignment
from eta_engine.strategies.shadow_paper_tracker import ShadowPaperTracker
from eta_engine.strategies.warmup_policy import (
    WarmupPolicy,
    warmup_risk_multiplier,
)


def _assignment(extras: dict[str, object] | None) -> StrategyAssignment:
    return StrategyAssignment(
        bot_id="test_bot",
        strategy_id="test_strategy",
        symbol="TEST",
        timeframe="1h",
        scorer_name="global",
        confluence_threshold=0.0,
        block_regimes=frozenset(),
        window_days=30,
        step_days=10,
        min_trades_per_window=1,
        rationale="unit-test fixture",
        extras=extras or {},
    )


def test_warmup_policy_parses_and_expires_without_amplifying_risk() -> None:
    assignment = _assignment(
        {
            "warmup_policy": {
                "promoted_on": "2026-04-01",
                "warmup_days": 30,
                "risk_multiplier_during_warmup": 0.5,
            },
        }
    )

    assert warmup_risk_multiplier(assignment, today=date(2026, 4, 1)) == 0.5
    assert warmup_risk_multiplier(assignment, today=date(2026, 4, 30)) == 0.5
    assert warmup_risk_multiplier(assignment, today=date(2026, 5, 1)) == 1.0
    assert warmup_risk_multiplier(assignment, today=date(2026, 3, 31)) == 1.0


@pytest.mark.parametrize(
    "extras",
    [
        None,
        {},
        {"warmup_policy": "invalid"},
        {"warmup_policy": {"promoted_on": "bad-date", "warmup_days": 30, "risk_multiplier_during_warmup": 0.5}},
        {"warmup_policy": {"promoted_on": "2026-04-01", "warmup_days": -1, "risk_multiplier_during_warmup": 0.5}},
        {"warmup_policy": {"promoted_on": "2026-04-01", "warmup_days": 30, "risk_multiplier_during_warmup": 0.0}},
        {"warmup_policy": {"promoted_on": "2026-04-01", "warmup_days": 30, "risk_multiplier_during_warmup": 2.1}},
    ],
)
def test_warmup_policy_malformed_extras_default_to_one(extras: dict[str, object] | None) -> None:
    assert WarmupPolicy.from_extras(extras) is None
    assert warmup_risk_multiplier(_assignment(extras), today=date(2026, 4, 10)) == 1.0


def test_shadow_paper_tracker_requires_consecutive_qualifying_windows() -> None:
    tracker = ShadowPaperTracker(window_size=3, reinstate_windows=2, win_rate_floor=2 / 3)

    for pnl_r, is_win in [(1.0, True), (0.5, True), (-0.25, False)]:
        tracker.record_shadow_trade("orb", "trend", pnl_r=pnl_r, is_win=is_win)

    assert tracker.should_reinstate("orb", "trend") is False
    assert tracker.recent_window_stats("orb", "trend")[0].qualifies is True

    for pnl_r, is_win in [(0.25, True), (-0.75, False), (-0.25, False)]:
        tracker.record_shadow_trade("orb", "trend", pnl_r=pnl_r, is_win=is_win)

    assert tracker.should_reinstate("orb", "trend") is False
    assert tracker.recent_window_stats("orb", "trend")[-1].qualifies is False

    for pnl_r, is_win in [(1.0, True), (0.25, True), (-0.1, False)]:
        tracker.record_shadow_trade("orb", "trend", pnl_r=pnl_r, is_win=is_win)

    assert tracker.should_reinstate("orb", "trend") is False

    for pnl_r, is_win in [(0.75, True), (0.75, True), (-0.1, False)]:
        tracker.record_shadow_trade("orb", "trend", pnl_r=pnl_r, is_win=is_win)

    assert tracker.should_reinstate("orb", "trend") is True
    tracker.reinstate("orb", "trend")
    assert tracker.recent_window_stats("orb", "trend") == []
    assert tracker.should_reinstate("orb", "trend") is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_size": 0},
        {"reinstate_windows": 0},
        {"win_rate_floor": -0.1},
        {"win_rate_floor": 1.1},
    ],
)
def test_shadow_paper_tracker_rejects_unsafe_config(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        ShadowPaperTracker(**kwargs)
