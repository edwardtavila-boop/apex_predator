from __future__ import annotations

from eta_engine.brain.avengers.base import DryRunExecutor, PersonaId, make_envelope
from eta_engine.brain.avengers.deadman import DeadmanSwitch
from eta_engine.brain.avengers.fleet import Fleet
from eta_engine.brain.avengers.hardened_fleet import HardenedFleet
from eta_engine.brain.model_policy import TaskCategory


class _SpyPushBus:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def push(self, **kwargs) -> dict[str, bool]:
        self.calls.append(kwargs)
        return {"spy": True}


def test_hardened_fleet_deadman_blocks_spend_before_dispatch(tmp_path) -> None:
    fleet = Fleet(executor=DryRunExecutor(), journal_path=tmp_path / "avengers.jsonl")
    deadman = DeadmanSwitch(
        sentinel_path=tmp_path / "missing.sentinel",
        journal_path=tmp_path / "activity.jsonl",
    )
    push_bus = _SpyPushBus()
    hardened = HardenedFleet(fleet, deadman=deadman, push_bus=push_bus)  # type: ignore[arg-type]
    envelope = make_envelope(
        category=TaskCategory.STRATEGY_EDIT,
        goal="edit a live strategy",
    )

    result = hardened.dispatch(envelope)

    assert result.success is False
    assert result.reason_code == "deadman_blocked"
    assert result.persona_id is PersonaId.ALFRED
    assert fleet.metrics().total_calls == 0
    assert push_bus.calls[0]["source"] == "hardened_fleet"


def test_hardened_fleet_dispatch_records_calibration_like_result(tmp_path) -> None:
    fleet = Fleet(executor=DryRunExecutor(), journal_path=tmp_path / "avengers.jsonl")
    hardened = HardenedFleet(fleet, push_bus=_SpyPushBus())  # type: ignore[arg-type]
    envelope = make_envelope(
        category=TaskCategory.LOG_PARSING,
        goal="summarize current logs",
    )

    result = hardened.dispatch(envelope)

    assert result.success is True
    assert result.reason_code == "ok"
    assert result.persona_id is PersonaId.ROBIN
    assert fleet.metrics().calls_by_persona == {PersonaId.ROBIN.value: 1}


def test_hardened_fleet_describe_includes_enabled_guards(tmp_path) -> None:
    fleet = Fleet(executor=DryRunExecutor(), journal_path=tmp_path / "avengers.jsonl")
    deadman = DeadmanSwitch(
        sentinel_path=tmp_path / "missing.sentinel",
        journal_path=tmp_path / "activity.jsonl",
    )
    hardened = HardenedFleet(fleet, deadman=deadman, push_bus=_SpyPushBus())  # type: ignore[arg-type]

    lines = hardened.describe()

    assert any("persona.jarvis" in line for line in lines)
    assert any("deadman: state=FROZEN" in line for line in lines)
