"""Direct coverage for small JARVIS v3 policy/helper modules."""

from __future__ import annotations


def _req():
    from eta_engine.brain.jarvis_admin import ActionRequest, ActionType, SubsystemId

    return ActionRequest(
        subsystem=SubsystemId.BOT_MNQ,
        action=ActionType.ORDER_PLACE,
        payload={"side": "long", "qty": 1},
        rationale="direct helper test",
    )


def _resp(verdict_value: str, *, binding: str = "vol", cap: float | None = 0.5):
    from eta_engine.brain.jarvis_admin import ActionResponse, ActionSuggestion, Verdict
    from eta_engine.brain.jarvis_context import SessionPhase

    return ActionResponse(
        request_id="direct-test",
        verdict=Verdict(verdict_value),
        reason="test",
        reason_code="test",
        jarvis_action=ActionSuggestion.TRADE,
        stress_composite=0.5,
        session_phase=SessionPhase.OPEN_DRIVE,
        binding_constraint=binding,
        size_cap_mult=cap,
    )


def _ctx(*, composite: float = 0.35, binding: str = "vol", session: str = "OPEN_DRIVE"):
    class _Stress:
        composite = 0.0
        binding_constraint = ""

        def __init__(self) -> None:
            self.composite = composite
            self.binding_constraint = binding

    class _Macro:
        hours_until_next_event = None
        next_event_label = None

    class _Ctx:
        stress_score = _Stress()
        macro = _Macro()
        session_phase = session

    return _Ctx()


def test_v17_champion_delegates_to_evaluate_request(monkeypatch) -> None:
    from eta_engine.brain.jarvis_v3.policies import v17_champion as v17_mod
    from eta_engine.brain.jarvis_v3.policies.v17_champion import evaluate_v17

    sentinel = _resp("APPROVED", binding="none", cap=None)
    monkeypatch.setattr(v17_mod, "evaluate_request", lambda req, ctx: sentinel)

    assert evaluate_v17(_req(), _ctx()) is sentinel


def test_v21_drawdown_proximity_defers_on_ctx_binding(monkeypatch) -> None:
    from eta_engine.brain.jarvis_admin import Verdict
    from eta_engine.brain.jarvis_v3.policies import v21_drawdown_proximity as v21_mod
    from eta_engine.brain.jarvis_v3.policies.v21_drawdown_proximity import evaluate_v21

    monkeypatch.setattr(v21_mod, "evaluate_request", lambda req, ctx: _resp("CONDITIONAL", binding="vol"))

    out = evaluate_v21(_req(), _ctx(binding="max_dd"))

    assert out.verdict == Verdict.DEFERRED
    assert out.size_cap_mult == 0.0
    assert "v21_dd_proximity_defer" in out.conditions


def test_last_report_cache_is_read_once_and_side_agnostic() -> None:
    from eta_engine.brain.jarvis_v3.sage.last_report_cache import (
        cache_size,
        clear_all,
        pop_last,
        set_last,
    )

    clear_all()
    set_last("MNQ", "long", {"id": 1})
    set_last("MNQ", "short", {"id": 2})

    assert cache_size() == 2
    assert pop_last("MNQ", "long") == {"id": 1}
    assert pop_last("MNQ", "long") is None
    assert pop_last("MNQ") == {"id": 2}
    assert cache_size() == 0


def test_horizons_helper_projects_current_keyword_api() -> None:
    from eta_engine.brain.jarvis_v3.horizons import Horizon
    from eta_engine.brain.jarvis_v3.horizons_helper import (
        projected_caps,
        shortest_horizon_cap,
    )

    ctx = _ctx(composite=0.35, binding="vol")

    caps = projected_caps(ctx, horizons=[Horizon.NOW, Horizon.NEXT_1H])

    assert caps == {Horizon.NOW: 0.65, Horizon.NEXT_1H: 0.65}
    assert shortest_horizon_cap(ctx) == 0.65
