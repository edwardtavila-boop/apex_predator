from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eta_engine.brain.avengers.base import make_envelope
from eta_engine.brain.avengers.deadman import DeadmanState, DeadmanSwitch
from eta_engine.brain.model_policy import TaskCategory


def test_deadman_records_activity_and_returns_live_status(tmp_path) -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    switch = DeadmanSwitch(
        sentinel_path=tmp_path / "operator.sentinel",
        journal_path=tmp_path / "operator_activity.jsonl",
        clock=lambda: now,
    )

    switch.record_activity(source="cli", note="unit test")
    status = switch.status()

    assert status.state is DeadmanState.LIVE
    assert status.hours_since == 0.0
    assert "operator.sentinel" in status.sentinel_path
    assert (tmp_path / "operator_activity.jsonl").read_text(encoding="utf-8")


def test_deadman_freezes_spend_actions_when_operator_never_touched(tmp_path) -> None:
    switch = DeadmanSwitch(
        sentinel_path=tmp_path / "missing.sentinel",
        journal_path=tmp_path / "activity.jsonl",
    )
    envelope = make_envelope(
        category=TaskCategory.STRATEGY_EDIT,
        goal="tighten live strategy sizing",
    )

    decision = switch.decide(envelope)

    assert decision.state is DeadmanState.FROZEN
    assert decision.allow is False
    assert decision.hours_since == float("inf")
    assert "all spend actions denied" in decision.reason


def test_deadman_allows_grunt_work_in_frozen_mode(tmp_path) -> None:
    switch = DeadmanSwitch(
        sentinel_path=tmp_path / "missing.sentinel",
        journal_path=tmp_path / "activity.jsonl",
    )
    envelope = make_envelope(
        category=TaskCategory.LOG_PARSING,
        goal="summarize logs",
    )

    decision = switch.decide(envelope)

    assert decision.state is DeadmanState.FROZEN
    assert decision.allow is True
    assert "allow-list" in decision.reason


def test_deadman_rejects_invalid_threshold_order(tmp_path) -> None:
    with pytest.raises(ValueError, match="0 < soft < hard < freeze"):
        DeadmanSwitch(
            sentinel_path=tmp_path / "operator.sentinel",
            soft_stale_hours=24,
            hard_stale_hours=12,
            freeze_hours=72,
        )
