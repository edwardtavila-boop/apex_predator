from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import eta_engine.obs.operator_override as operator_override
import eta_engine.obs.slippage_tracker as slippage_tracker
from eta_engine.core.live_shadow import (
    BookLevel,
    BookSnapshot,
    ShadowOrder,
    simulate_fill,
)
from eta_engine.obs.operator_override import OverrideLevel, get_state, is_paused, set_state
from eta_engine.obs.slippage_tracker import daily_summary, record_expected, record_realized

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_slippage_tracker_records_round_trip_and_daily_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(slippage_tracker, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(slippage_tracker, "PENDING_PATH", tmp_path / "pending.json")
    now = datetime.now(UTC).timestamp()

    record_expected(order_id="B-1", symbol="MNQ", side="buy", expected_price=100.0, ts=now)
    buy_event = record_realized(order_id="B-1", realized_price=100.2, ts=now + 0.25)
    record_expected(order_id="S-1", symbol="MNQ", side="sell", expected_price=100.0, ts=now + 1.0)
    sell_event = record_realized(order_id="S-1", realized_price=99.9, ts=now + 1.5)

    assert buy_event is not None
    assert buy_event.slippage_abs == 0.2
    assert buy_event.slippage_bps == 20.0
    assert buy_event.latency_ms == 250.0
    assert sell_event is not None
    assert sell_event.slippage_abs == 0.1
    assert sell_event.slippage_bps == 10.0
    assert record_realized(order_id="unknown", realized_price=101.0, ts=now + 2.0) is None

    summary = daily_summary(since_hours=24.0)
    assert summary["n"] == 2
    assert summary["mean_slippage_bps"] == 15.0
    assert summary["max_slippage_bps"] == 20.0
    assert summary["by_symbol"]["MNQ"]["n"] == 2


def test_operator_override_state_pause_resume_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(operator_override, "OVERRIDE_PATH", tmp_path / "operator_override.json")

    assert get_state().level == OverrideLevel.NORMAL
    assert is_paused() is False

    set_state(OverrideLevel.HARD_PAUSE, reason="news event", set_by="operator")
    state = get_state()
    assert state.level == OverrideLevel.HARD_PAUSE
    assert state.reason == "news event"
    assert is_paused() is True
    assert is_paused(hard_only=True) is True

    set_state(
        OverrideLevel.SOFT_PAUSE,
        reason="expired",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    assert get_state().level == OverrideLevel.NORMAL


def test_live_shadow_simulates_buy_sell_exhaustion_and_invalid_orders() -> None:
    book = BookSnapshot(
        symbol="MNQ",
        venue="paper",
        ts_iso="2026-04-29T16:30:00Z",
        bids=(BookLevel(price=99.9, size=1.0), BookLevel(price=99.8, size=2.0)),
        asks=(BookLevel(price=100.1, size=1.0), BookLevel(price=100.2, size=2.0)),
        mid=100.0,
    )

    buy = simulate_fill(ShadowOrder(symbol="MNQ", side="BUY", size=2.0, requested_px=100.1), book)
    sell = simulate_fill(
        ShadowOrder(symbol="MNQ", side="SELL", size=1.5, requested_px=99.9, taker_fee_bps=1.0),
        book,
    )
    exhausted = simulate_fill(ShadowOrder(symbol="MNQ", side="BUY", size=10.0, requested_px=100.1), book)
    invalid = simulate_fill(ShadowOrder(symbol="MNQ", side="BUY", size=0.0, requested_px=100.1), book)

    assert buy.ok is True
    assert buy.size_filled == 2.0
    assert buy.levels_consumed == 2
    assert buy.slippage_bps > 0.0
    assert sell.ok is True
    assert sell.slippage_bps > 1.0
    assert exhausted.ok is False
    assert exhausted.reason == "book_exhausted"
    assert exhausted.size_filled == 3.0
    assert invalid.ok is False
    assert invalid.reason == "invalid_order"
