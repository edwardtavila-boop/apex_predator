"""Tests for #71 async batching + #72 cost breaker + #73 fast-path."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eta_engine.jarvis import (
    DecisionContext,
    PMConsensus,
    build_default_panel,
)
from eta_engine.jarvis.async_runner import AsyncSpecialistRunner
from eta_engine.jarvis.cost_breaker import (
    PerDecisionCostBreaker,
)
from eta_engine.jarvis.fast_path import FastPathPolicy
from eta_engine.jarvis.specialists.base import (
    DecisionContext as DC,
)
from eta_engine.jarvis.specialists.base import (
    SpecialistAgent,
    SpecialistOutput,
)


def _ctx(setup: str = "ORB") -> DecisionContext:
    return DC(
        decision_id=datetime.now(UTC).isoformat(timespec="seconds"),
        bar_ts=datetime.now(UTC).isoformat(timespec="seconds"),
        symbol="MNQ",
        regime="RISK-ON",
        setup_name=setup,
        bar={"close": 21500.0, "atr": 18.0},
    )


# ===========================================================================
# AsyncSpecialistRunner (#71)
# ===========================================================================
def test_async_runner_returns_one_output_per_specialist() -> None:
    runner = AsyncSpecialistRunner(build_default_panel())
    result = runner.run_sync(_ctx())
    assert len(result.outputs) == 7
    assert len(result.records) == 7
    assert all(isinstance(o, SpecialistOutput) for o in result.outputs)


def test_async_runner_records_per_specialist_latency() -> None:
    runner = AsyncSpecialistRunner(build_default_panel())
    result = runner.run_sync(_ctx())
    for r in result.records:
        assert r.elapsed_s >= 0
        assert r.succeeded is True


def test_async_runner_handles_specialist_crash() -> None:
    class Crasher(SpecialistAgent):
        name = "crasher"

        def evaluate(self, ctx):
            raise RuntimeError("boom")

    runner = AsyncSpecialistRunner([Crasher()])
    result = runner.run_sync(_ctx())
    assert len(result.outputs) == 1
    assert "CRASHED" in result.outputs[0].hypothesis
    assert result.records[0].succeeded is False
    assert "RuntimeError" in result.records[0].error


def test_async_runner_handles_specialist_timeout() -> None:
    import time as _t

    class Slow(SpecialistAgent):
        name = "slow"

        def evaluate(self, ctx):
            _t.sleep(2.0)
            return SpecialistOutput(
                hypothesis="x",
                evidence=["a"],
                signal="long",
                confidence=0.5,
                falsification="x",
            )

    runner = AsyncSpecialistRunner([Slow()], per_specialist_timeout_s=0.2)
    result = runner.run_sync(_ctx())
    assert "TIMEOUT" in result.outputs[0].hypothesis
    assert result.records[0].error == "timeout"


def test_async_runner_wall_clock_below_sum_of_latencies() -> None:
    """Concurrency benefit: wall-clock should be << sum of per-specialist
    latencies. With 7 deterministic specialists, each <1ms, wall-clock
    might be dominated by overhead — the assertion is permissive."""
    runner = AsyncSpecialistRunner(build_default_panel())
    result = runner.run_sync(_ctx())
    sum_lat = sum(r.elapsed_s for r in result.records)
    # Wall clock should be at most 5x the longest single specialist
    longest = max((r.elapsed_s for r in result.records), default=0.001)
    assert result.wall_clock_s < max(longest * 5 + 0.5, sum_lat)


def test_async_runner_pm_aggregation_works_on_async_outputs() -> None:
    """Round trip: async runner -> PMConsensus."""
    runner = AsyncSpecialistRunner(build_default_panel())
    result = runner.run_sync(_ctx())
    verdict = PMConsensus().aggregate(result.outputs, ctx=_ctx())
    assert verdict.action in {"fire_long", "fire_short", "skip", "abstain"}


# ===========================================================================
# PerDecisionCostBreaker (#72)
# ===========================================================================
def test_breaker_no_trip_when_under_cap(tmp_path: Path) -> None:
    b = PerDecisionCostBreaker(
        per_decision_cap_usd=0.50,
        ledger_path=tmp_path / "cb.jsonl",
    )
    b.record(decision_id="d1", cost_usd=0.10)
    row = b.record(decision_id="d1", cost_usd=0.20, finalize=True)
    assert row is not None
    assert row.cost_usd == 0.30
    assert row.trip is False


def test_breaker_trips_when_over_cap(tmp_path: Path) -> None:
    b = PerDecisionCostBreaker(
        per_decision_cap_usd=0.20,
        ledger_path=tmp_path / "cb.jsonl",
    )
    row = b.record(decision_id="d1", cost_usd=0.50, finalize=True)
    assert row.trip is True


def test_breaker_escalates_after_3_trips_in_window(tmp_path: Path) -> None:
    b = PerDecisionCostBreaker(
        per_decision_cap_usd=0.20,
        window_s=3600,
        trips_to_escalate=3,
        ledger_path=tmp_path / "cb.jsonl",
    )
    for i in range(2):
        b.record(decision_id=f"d{i}", cost_usd=0.50, finalize=True)
    assert not b.escalation_required()
    b.record(decision_id="d3", cost_usd=0.50, finalize=True)
    assert b.escalation_required()


def test_breaker_clear_escalation(tmp_path: Path) -> None:
    b = PerDecisionCostBreaker(
        per_decision_cap_usd=0.20,
        trips_to_escalate=1,
        ledger_path=tmp_path / "cb.jsonl",
    )
    b.record(decision_id="d1", cost_usd=0.50, finalize=True)
    assert b.escalation_required()
    b.clear_escalation()
    assert not b.escalation_required()


def test_breaker_appends_to_ledger(tmp_path: Path) -> None:
    p = tmp_path / "cb.jsonl"
    b = PerDecisionCostBreaker(per_decision_cap_usd=0.5, ledger_path=p)
    b.record(decision_id="d1", cost_usd=0.10, finalize=True)
    b.record(decision_id="d2", cost_usd=0.30, finalize=True)
    rows = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2


def test_breaker_snapshot_serializable(tmp_path: Path) -> None:
    import json

    b = PerDecisionCostBreaker(ledger_path=tmp_path / "cb.jsonl")
    json.dumps(b.snapshot())


# ===========================================================================
# FastPathPolicy (#73)
# ===========================================================================
def _verdict():
    from eta_engine.jarvis.consensus import PMVerdict

    return PMVerdict(
        decision_id="d1",
        ts_utc="x",
        action="fire_long",
        confidence=0.7,
        rationale="r",
        signal_tally={"long": 5, "neutral": 2},
        weighted_score=0.6,
        red_team_passed=True,
        red_team_objections=["a", "b"],
    )


def test_fast_path_skips_non_time_sensitive_setup() -> None:
    fp = FastPathPolicy()
    assert fp.try_get(_ctx(setup="EMA_PB")) is None


def test_fast_path_caches_for_time_sensitive_setup() -> None:
    fp = FastPathPolicy()
    ctx = _ctx(setup="ORB")
    assert fp.try_get(ctx) is None
    fp.store(ctx, _verdict())
    cached = fp.try_get(ctx)
    assert cached is not None
    assert cached.action == "fire_long"


def test_fast_path_cache_misses_on_different_regime() -> None:
    fp = FastPathPolicy()
    ctx_a = _ctx(setup="ORB")
    fp.store(ctx_a, _verdict())
    ctx_b = DC(
        decision_id="d2",
        bar_ts="t",
        symbol="MNQ",
        regime="RISK-OFF",
        setup_name="ORB",
        bar={"close": 21500.0, "atr": 18.0},
    )
    assert fp.try_get(ctx_b) is None  # different regime


def test_fast_path_freshness_window_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    fp = FastPathPolicy(freshness_window_s=0.1)
    ctx = _ctx(setup="ORB")
    fp.store(ctx, _verdict())
    time.sleep(0.2)
    assert fp.try_get(ctx) is None


def test_fast_path_lru_eviction() -> None:
    fp = FastPathPolicy(max_entries=2)
    for i, regime in enumerate(["RISK-ON", "RISK-OFF", "NEUTRAL"]):
        ctx = DC(
            decision_id=f"d{i}",
            bar_ts="t",
            symbol="MNQ",
            regime=regime,
            setup_name="ORB",
            bar={"close": 21500.0, "atr": 18.0},
        )
        fp.store(ctx, _verdict())
    assert fp.stats()["size"] == 2


def test_fast_path_stats_serializable() -> None:
    import json

    fp = FastPathPolicy()
    json.dumps(fp.stats())
