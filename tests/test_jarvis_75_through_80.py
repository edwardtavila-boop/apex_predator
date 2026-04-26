"""Tests for #75 nightly_audit JARVIS step + #76 healer + #77 runtime
integration + #78 voyage seam + #79 transport factory + #80 approval queue."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


# ===========================================================================
# #75 nightly_audit jarvis_health step
# ===========================================================================
def test_nightly_audit_jarvis_step_runs() -> None:
    from eta_engine.scripts.nightly_audit import step_jarvis_health

    s = step_jarvis_health()
    assert s.name == "jarvis_health"
    assert s.status in ("pass", "warn", "fail")
    assert "specialists" in s.detail or "crash" in s.detail


def test_nightly_audit_jarvis_step_extras_present() -> None:
    from eta_engine.scripts.nightly_audit import step_jarvis_health

    s = step_jarvis_health()
    if s.status != "fail":
        assert s.extra.get("specialist_n") == 7
        assert "verdict_action" in s.extra


# ===========================================================================
# #76 EpisodicMemoryHealer
# ===========================================================================
def test_healer_no_changes_when_clean(tmp_path: Path) -> None:
    from eta_engine.jarvis.memory.healer import EpisodicMemoryHealer

    p = tmp_path / "mem.jsonl"
    p.write_text(
        json.dumps(
            {
                "decision_id": "d1",
                "ts_utc": "x",
                "symbol": "x",
                "regime": "x",
                "setup_name": "x",
                "pm_action": "skip",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    h = EpisodicMemoryHealer(p)
    report = h.heal_if_needed()
    assert report.healed is False
    assert report.n_quarantined == 0
    assert report.n_valid == 1


def test_healer_quarantines_corrupt_lines(tmp_path: Path) -> None:
    from eta_engine.jarvis.memory.healer import EpisodicMemoryHealer

    p = tmp_path / "mem.jsonl"
    p.write_text(
        json.dumps(
            {
                "decision_id": "good",
                "ts_utc": "x",
                "symbol": "x",
                "regime": "x",
                "setup_name": "x",
                "pm_action": "skip",
            }
        )
        + "\n"
        + "not-json\n"
        + json.dumps({"missing_required_keys": True})
        + "\n"
        + json.dumps(
            {
                "decision_id": "good2",
                "ts_utc": "x",
                "symbol": "x",
                "regime": "x",
                "setup_name": "x",
                "pm_action": "skip",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    h = EpisodicMemoryHealer(p)
    report = h.heal_if_needed()
    assert report.healed is True
    assert report.n_valid == 2
    assert report.n_quarantined == 2
    # Quarantine sidecar exists with the bad lines
    assert h.quarantine_path().exists()
    qp_content = h.quarantine_path().read_text(encoding="utf-8")
    assert "not-json" in qp_content
    # Original now contains only valid lines
    rows = p.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2


def test_healer_dry_run_makes_no_changes(tmp_path: Path) -> None:
    from eta_engine.jarvis.memory.healer import EpisodicMemoryHealer

    p = tmp_path / "mem.jsonl"
    p.write_text("not-json\n", encoding="utf-8")
    h = EpisodicMemoryHealer(p)
    h.heal_if_needed(dry_run=True)
    # Original unchanged
    assert p.read_text(encoding="utf-8") == "not-json\n"
    assert not h.quarantine_path().exists()


def test_healer_handles_missing_file(tmp_path: Path) -> None:
    from eta_engine.jarvis.memory.healer import EpisodicMemoryHealer

    h = EpisodicMemoryHealer(tmp_path / "nope.jsonl")
    report = h.heal_if_needed()
    assert report.healed is False
    assert report.n_total == 0


# ===========================================================================
# #77 runtime integration
# ===========================================================================
def test_on_decision_made_persists_with_embedding(tmp_path: Path) -> None:
    from eta_engine.jarvis import (
        DecisionContext,
        PMConsensus,
        build_default_panel,
    )
    from eta_engine.jarvis.memory import (
        DeterministicEmbedder,
        LocalMemoryStore,
    )
    from eta_engine.jarvis.runtime_integration import on_decision_made

    store = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    embedder = DeterministicEmbedder(dim=512)
    panel = build_default_panel()
    ctx = DecisionContext(
        decision_id="d1",
        bar_ts="2026-04-25T10:00:00",
        symbol="MNQ",
        regime="RISK-ON",
        setup_name="ORB",
        bar={"close": 21500.0, "atr": 18.0},
    )
    outs = [s.evaluate(ctx) for s in panel]
    verdict = PMConsensus().aggregate(outs, ctx=ctx)
    mem = on_decision_made(
        verdict=verdict,
        ctx=ctx,
        store=store,
        embedder=embedder,
        specialist_outputs=outs,
    )
    assert mem.decision_id == "d1"
    assert mem.embedding is not None
    assert len(mem.embedding) == 512
    assert store.count() == 1


def test_on_bar_close_resolves_outcomes(tmp_path: Path) -> None:
    from eta_engine.jarvis.memory import (
        EpisodicMemory,
        LocalMemoryStore,
        OutcomeTracker,
    )
    from eta_engine.jarvis.runtime_integration import on_bar_close

    store = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    t0 = datetime(2026, 4, 25, 10, 0, tzinfo=UTC)
    store.upsert(
        EpisodicMemory(
            decision_id="d1",
            ts_utc=t0.isoformat(),
            symbol="MNQ",
            regime="x",
            setup_name="ORB",
            pm_action="fire_long",
            weighted_score=0,
            confidence=0,
            votes={},
            falsifications=[],
            feature_vec={"entry": 100.0, "atr": 2.0},
        )
    )
    tracker = OutcomeTracker(store, bar_interval_seconds=300, offsets_bars=(1,))
    rec = on_bar_close(
        bar_ts_utc=(t0 + timedelta(minutes=5)).isoformat(),
        close=110.0,
        store=store,
        tracker=tracker,
    )
    assert any(r[0] == "d1" for r in rec)


# ===========================================================================
# #78 Voyage adapter seam
# ===========================================================================
def test_voyage_available_false_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VOYAGEAI_API_KEY", raising=False)
    from eta_engine.jarvis.memory.voyage_adapter import voyage_available

    assert voyage_available() is False


def test_voyage_adapter_construction_fails_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VOYAGEAI_API_KEY", raising=False)
    from eta_engine.jarvis.memory.voyage_adapter import VoyageEmbedderAdapter

    with pytest.raises(RuntimeError, match="VOYAGEAI_API_KEY"):
        VoyageEmbedderAdapter()


def test_make_embedder_falls_back_to_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VOYAGEAI_API_KEY", raising=False)
    from eta_engine.jarvis.memory.voyage_adapter import (
        DEFAULT_DIM,
        make_embedder,
    )

    e = make_embedder()
    assert e.dim == DEFAULT_DIM
    assert e.name == "deterministic"


# ===========================================================================
# #79 Transport factory
# ===========================================================================
def test_transport_factory_echo_when_forced(monkeypatch) -> None:
    from eta_engine.jarvis.transport_factory import make_transport

    monkeypatch.setenv("APEX_LLM_TRANSPORT", "echo")
    t = make_transport(role="specialist:quant")
    assert t.name.startswith("echo")


def test_transport_factory_echo_when_no_anthropic_key(monkeypatch) -> None:
    monkeypatch.delenv("APEX_LLM_TRANSPORT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from eta_engine.jarvis.transport_factory import make_transport

    t = make_transport(role="specialist:quant")
    assert t.name.startswith("echo")


def test_tier_for_role_maps_correctly() -> None:
    from eta_engine.jarvis.transport_factory import tier_for_role

    assert tier_for_role("specialist:quant") == "sonnet"
    assert tier_for_role("specialist:pm") == "opus"
    assert tier_for_role("pm") == "opus"
    assert tier_for_role("post_mortem") == "opus"
    assert tier_for_role("unknown_role") == "sonnet"  # default


def test_make_transport_with_audit_returns_pair(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APEX_LLM_TRANSPORT", "echo")
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    from eta_engine.jarvis.transport_factory import (
        make_transport_with_audit,
    )

    t, audit = make_transport_with_audit(role="pm")
    assert t is not None
    assert audit.path.parent == tmp_path


# ===========================================================================
# #80 ApprovalQueue
# ===========================================================================
def test_approval_queue_enqueue_then_pending(tmp_path: Path) -> None:
    from eta_engine.jarvis.approval_queue import ApprovalQueue

    q = ApprovalQueue(path=tmp_path / "aq.jsonl")
    req = q.enqueue(target="quant", kind="confidence_recalibration", delta=-0.05, rationale="test", auto_applyable=True)
    pending = q.pending()
    assert len(pending) == 1
    assert pending[0].request_id == req.request_id


def test_approval_queue_decide_approve(tmp_path: Path) -> None:
    from eta_engine.jarvis.approval_queue import ApprovalQueue

    q = ApprovalQueue(path=tmp_path / "aq.jsonl")
    req = q.enqueue(target="x", kind="freeze", delta=0, rationale="r", auto_applyable=False)
    assert q.decide(req.request_id, approved=True, operator="ed", note="ack")
    after = next(r for r in q.all() if r.request_id == req.request_id)
    assert after.status == "APPROVED"
    assert after.decided_by == "ed"


def test_approval_queue_decide_reject(tmp_path: Path) -> None:
    from eta_engine.jarvis.approval_queue import ApprovalQueue

    q = ApprovalQueue(path=tmp_path / "aq.jsonl")
    req = q.enqueue(target="x", kind="freeze", delta=0, rationale="r", auto_applyable=False)
    q.decide(req.request_id, approved=False, operator="ed")
    after = next(r for r in q.all() if r.request_id == req.request_id)
    assert after.status == "REJECTED"


def test_approval_queue_decide_unknown_returns_false(tmp_path: Path) -> None:
    from eta_engine.jarvis.approval_queue import ApprovalQueue

    q = ApprovalQueue(path=tmp_path / "aq.jsonl")
    assert q.decide("nope", approved=True, operator="x") is False


def test_approval_queue_auto_apply_eligible_blocked_by_forecast_gate(
    tmp_path: Path,
) -> None:
    """Forecast precision below 60% must block all auto-apply candidates."""
    from eta_engine.jarvis.approval_queue import ApprovalQueue
    from eta_engine.jarvis.postmortem import ForecastAccuracyTracker

    q = ApprovalQueue(path=tmp_path / "aq.jsonl")
    q.enqueue(target="x", kind="confidence_recalibration", delta=-0.05, rationale="r", auto_applyable=True)
    tracker = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl")
    # No forecasts -> precision 0 -> blocked
    eligible = q.auto_apply_eligible(tracker)
    assert eligible == []


def test_approval_queue_auto_apply_eligible_with_passing_gate(
    tmp_path: Path,
) -> None:
    from eta_engine.jarvis.approval_queue import ApprovalQueue
    from eta_engine.jarvis.postmortem import (
        ForecastAccuracyTracker,
        ForecastRecord,
    )

    q = ApprovalQueue(path=tmp_path / "aq.jsonl")
    q.enqueue(target="x", kind="confidence_recalibration", delta=-0.05, rationale="r", auto_applyable=True)
    q.enqueue(target="x", kind="freeze", delta=0, rationale="r", auto_applyable=False)
    tracker = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl", gate_precision=0.5)
    now = datetime(2026, 4, 25, tzinfo=UTC)
    for i in range(7):
        tracker.record(
            ForecastRecord(
                forecast_id=f"f{i}",
                made_at_utc=now.isoformat(timespec="seconds"),
                forecast_kind="x",
                target="x",
                horizon_days=1,
                resolved=True,
                correct=True,
            )
        )
    eligible = q.auto_apply_eligible(tracker)
    assert len(eligible) == 1
    assert eligible[0].kind == "confidence_recalibration"
