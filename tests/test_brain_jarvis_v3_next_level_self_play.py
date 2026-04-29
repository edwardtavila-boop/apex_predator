from __future__ import annotations

from datetime import UTC, datetime

from eta_engine.brain.jarvis_v3.next_level.self_play import (
    EventKind,
    MarketEvent,
    RedMarket,
    SelfPlayLedger,
    default_policy,
    play_round,
)


def test_red_market_is_deterministic_for_same_seed() -> None:
    first = RedMarket(seed=7).emit()
    second = RedMarket(seed=7).emit()

    assert first.kind == second.kind
    assert first.regime_hint == second.regime_hint
    assert first.realized_r_if_trade == second.realized_r_if_trade


def test_play_round_scores_approve_deny_and_conditional_paths() -> None:
    event = MarketEvent(
        ts=datetime(2026, 4, 29, tzinfo=UTC),
        kind=EventKind.HIDDEN_MOMENTUM,
        regime_hint="NEUTRAL",
        truth_regime="RISK_ON",
        stress_pushed=0.2,
        realized_r_if_trade=2.0,
    )

    approve = play_round(event=event, jarvis_decide=lambda _event: "APPROVE", round_id=1)
    deny = play_round(event=event, jarvis_decide=lambda _event: "DENY", round_id=2)
    conditional = play_round(event=event, jarvis_decide=lambda _event: "CONDITIONAL", round_id=3)

    assert approve.realized_r == 2.0
    assert approve.correct is True
    assert deny.realized_r == 0.0
    assert deny.correct is False
    assert conditional.realized_r == 1.0
    assert conditional.correct is False


def test_self_play_ledger_summary_groups_by_event_kind() -> None:
    ledger = SelfPlayLedger()
    market = RedMarket(seed=3)
    for round_id in range(5):
        event = market.emit()
        ledger.record(play_round(event=event, jarvis_decide=default_policy, round_id=round_id))

    summary = ledger.summary()

    assert summary.rounds == 5
    assert summary.approve_count + summary.deny_count <= 5
    assert 0.0 <= summary.win_rate <= 1.0
    assert summary.by_event
