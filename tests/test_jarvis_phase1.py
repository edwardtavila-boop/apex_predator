"""Tests for Phase 1: SpecialistOutput, SpecialistAgent base, 7 reference
specialists, PMConsensus aggregator, and ReasoningQualityEvaluator."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from eta_engine.jarvis import (
    DecisionContext,
    PMConsensus,
    SpecialistOutput,
    build_default_panel,
)
from eta_engine.jarvis.reasoning_eval import (
    EvalReport,
    ReasoningQualityEvaluator,
)
from eta_engine.jarvis.specialists.base import (
    red_team_gate_passes,
    red_team_objections,
)
from eta_engine.jarvis.specialists.reference import (
    MacroSpecialist,
    MicrostructureSpecialist,
    QuantSpecialist,
    RedTeamSpecialist,
    RiskManagerSpecialist,
)


# ===========================================================================
# SpecialistOutput Pydantic validation
# ===========================================================================
def test_specialist_output_valid() -> None:
    o = SpecialistOutput(
        hypothesis="x",
        evidence=["fact1"],
        signal="long",
        confidence=0.5,
        falsification="y",
    )
    assert o.signal == "long"
    assert o.confidence == 0.5


def test_specialist_output_rejects_bad_signal() -> None:
    with pytest.raises(ValidationError):
        SpecialistOutput(
            hypothesis="x",
            evidence=["a"],
            signal="maybe",
            confidence=0.5,
            falsification="y",
        )


def test_specialist_output_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        SpecialistOutput(
            hypothesis="x",
            evidence=["a"],
            signal="long",
            confidence=1.5,
            falsification="y",
        )
    with pytest.raises(ValidationError):
        SpecialistOutput(
            hypothesis="x",
            evidence=["a"],
            signal="long",
            confidence=-0.1,
            falsification="y",
        )


def test_specialist_output_rejects_empty_evidence() -> None:
    with pytest.raises(ValidationError):
        SpecialistOutput(
            hypothesis="x",
            evidence=[],
            signal="long",
            confidence=0.5,
            falsification="y",
        )


def test_specialist_output_strips_whitespace_only_evidence() -> None:
    with pytest.raises(ValidationError):
        SpecialistOutput(
            hypothesis="x",
            evidence=["   "],
            signal="long",
            confidence=0.5,
            falsification="y",
        )


def test_specialist_output_serializes_to_json() -> None:
    o = SpecialistOutput(
        hypothesis="h",
        evidence=["e1"],
        signal="long",
        confidence=0.5,
        falsification="f",
    )
    s = o.model_dump_json()
    parsed = json.loads(s)
    assert parsed["signal"] == "long"


# ===========================================================================
# Red Team gate
# ===========================================================================
def test_red_team_gate_fails_when_only_one_falsification() -> None:
    a = SpecialistOutput(hypothesis="h", evidence=["a"], signal="long", confidence=0.5, falsification="X happens")
    b = SpecialistOutput(hypothesis="h", evidence=["b"], signal="long", confidence=0.5, falsification="X happens")
    passes, _ = red_team_gate_passes([a, b])
    assert passes is False


def test_red_team_gate_passes_with_two_distinct() -> None:
    a = SpecialistOutput(hypothesis="h", evidence=["a"], signal="long", confidence=0.5, falsification="X happens")
    b = SpecialistOutput(hypothesis="h", evidence=["b"], signal="long", confidence=0.5, falsification="Y happens")
    passes, _ = red_team_gate_passes([a, b])
    assert passes is True


def test_red_team_objections_dedupes_case_insensitive() -> None:
    outs = [
        SpecialistOutput(hypothesis="h", evidence=["a"], signal="long", confidence=0.5, falsification="VIX > 30"),
        SpecialistOutput(hypothesis="h", evidence=["b"], signal="long", confidence=0.5, falsification="vix > 30"),
        SpecialistOutput(
            hypothesis="h", evidence=["c"], signal="long", confidence=0.5, falsification="Spread > 3 ticks"
        ),
    ]
    assert len(red_team_objections(outs)) == 2


# ===========================================================================
# Reference specialists
# ===========================================================================
def _ctx(
    *,
    regime: str = "RISK-ON",
    setup: str = "ORB",
    bot_overrides: dict | None = None,
    market_overrides: dict | None = None,
) -> DecisionContext:
    return DecisionContext(
        decision_id="d1",
        bar_ts="2026-04-25T10:00:00",
        symbol="MNQH6",
        regime=regime,
        setup_name=setup,
        bar={"close": 21500.0, "atr": 18.0},
        bot_snapshot=bot_overrides
        or {
            "equity_usd": 5000.0,
            "peak_equity_usd": 5000.0,
            "consecutive_losses": 0,
            "open_position_count": 0,
        },
        market_features=market_overrides
        or {
            "vix_z": 0.0,
            "spy_corr": 0.7,
            "dxy_z": 0.0,
            "spread_ticks": 1.0,
            "tick_z": 0.0,
        },
    )


def test_quant_specialist_skips_when_no_setup() -> None:
    out = QuantSpecialist().evaluate(_ctx(setup=""))
    assert out.signal == "skip"
    assert "no" in out.hypothesis.lower() or "setup" in out.hypothesis.lower()


def test_quant_specialist_skips_in_crisis() -> None:
    out = QuantSpecialist().evaluate(_ctx(regime="CRISIS"))
    assert out.signal == "skip"


def test_quant_specialist_long_in_risk_on() -> None:
    out = QuantSpecialist().evaluate(_ctx(regime="RISK-ON"))
    assert out.signal == "long"


def test_quant_specialist_short_in_risk_off() -> None:
    out = QuantSpecialist().evaluate(_ctx(regime="RISK-OFF"))
    assert out.signal == "short"


def test_red_team_specialist_skip_in_crisis() -> None:
    out = RedTeamSpecialist().evaluate(_ctx(regime="CRISIS"))
    assert out.signal == "skip"


def test_red_team_raises_distinct_falsification() -> None:
    """Red Team must surface a falsification distinct from Quant's."""
    ctx = _ctx()
    quant = QuantSpecialist().evaluate(ctx)
    rt = RedTeamSpecialist().evaluate(ctx)
    assert quant.falsification != rt.falsification


def test_risk_manager_skips_on_consec_losses() -> None:
    out = RiskManagerSpecialist().evaluate(
        _ctx(
            bot_overrides={
                "consecutive_losses": 5,
                "equity_usd": 5000,
                "peak_equity_usd": 5000,
                "open_position_count": 0,
            },
        )
    )
    assert out.signal == "skip"
    assert out.confidence > 0.9


def test_risk_manager_skips_on_drawdown() -> None:
    out = RiskManagerSpecialist().evaluate(
        _ctx(
            bot_overrides={
                "consecutive_losses": 0,
                "equity_usd": 4500,
                "peak_equity_usd": 5000,
                "open_position_count": 0,
            },
        )
    )
    assert out.signal == "skip"


def test_macro_specialist_short_on_high_vix() -> None:
    out = MacroSpecialist().evaluate(
        _ctx(
            market_overrides={"vix_z": 2.0, "spy_corr": 0.5, "dxy_z": 0.0, "spread_ticks": 1.0, "tick_z": 0.0},
        )
    )
    assert out.signal == "short"


def test_microstructure_skips_on_wide_spread() -> None:
    out = MicrostructureSpecialist().evaluate(
        _ctx(
            market_overrides={"vix_z": 0.0, "spy_corr": 0.7, "dxy_z": 0.0, "spread_ticks": 5.0, "tick_z": 0.0},
        )
    )
    assert out.signal == "skip"


# ===========================================================================
# PMConsensus
# ===========================================================================
def test_pm_consensus_abstains_with_no_voters() -> None:
    pm = PMConsensus()
    v = pm.aggregate([], ctx=_ctx())
    assert v.action == "abstain"
    assert v.blocked_reason == "no_voters"


def test_pm_consensus_abstains_below_quorum() -> None:
    pm = PMConsensus(min_voters=4)
    o = SpecialistOutput(hypothesis="h", evidence=["a"], signal="long", confidence=0.9, falsification="x")
    v = pm.aggregate([o], ctx=_ctx())
    assert v.action == "abstain"
    assert v.blocked_reason == "quorum_failed"


def test_pm_consensus_skips_when_red_team_gate_fails() -> None:
    pm = PMConsensus(min_voters=2, red_team_min_objections=2)
    o1 = SpecialistOutput(
        hypothesis="h", evidence=["a"], signal="long", confidence=0.9, falsification="same falsification"
    )
    o2 = SpecialistOutput(
        hypothesis="h", evidence=["b"], signal="long", confidence=0.9, falsification="same falsification"
    )
    v = pm.aggregate([o1, o2], ctx=_ctx())
    assert v.action == "skip"
    assert v.blocked_reason == "red_team_gate"


def test_pm_consensus_fires_long_with_strong_agreement() -> None:
    pm = PMConsensus(min_voters=4, fire_threshold=0.40, red_team_min_objections=2)
    voters = [
        SpecialistOutput(hypothesis="h", evidence=["a"], signal="long", confidence=0.9, falsification="X breaks"),
        SpecialistOutput(hypothesis="h", evidence=["b"], signal="long", confidence=0.8, falsification="Y breaks"),
        SpecialistOutput(hypothesis="h", evidence=["c"], signal="long", confidence=0.7, falsification="Z breaks"),
        SpecialistOutput(hypothesis="h", evidence=["d"], signal="neutral", confidence=0.3, falsification="W breaks"),
    ]
    v = pm.aggregate(voters, ctx=_ctx())
    assert v.action == "fire_long"
    assert v.weighted_score > 0.40
    assert v.red_team_passed is True


def test_pm_consensus_skips_below_fire_threshold() -> None:
    pm = PMConsensus(min_voters=4, fire_threshold=0.40, red_team_min_objections=2)
    voters = [
        SpecialistOutput(hypothesis="h", evidence=["a"], signal="long", confidence=0.4, falsification="X"),
        SpecialistOutput(hypothesis="h", evidence=["b"], signal="short", confidence=0.4, falsification="Y"),
        SpecialistOutput(hypothesis="h", evidence=["c"], signal="neutral", confidence=0.3, falsification="Z"),
        SpecialistOutput(hypothesis="h", evidence=["d"], signal="neutral", confidence=0.3, falsification="W"),
    ]
    v = pm.aggregate(voters, ctx=_ctx())
    assert v.action == "skip"
    assert v.blocked_reason == "below_fire_threshold"


def test_pm_consensus_verdict_is_serializable() -> None:
    pm = PMConsensus()
    v = pm.aggregate([], ctx=_ctx())
    payload = json.dumps(v.as_dict())
    assert "action" in payload


# ===========================================================================
# ReasoningQualityEvaluator
# ===========================================================================
def _seed_contexts(n: int) -> list[DecisionContext]:
    """Mix of regimes / setups to exercise every specialist branch."""
    out = []
    regimes = ["RISK-ON", "RISK-OFF", "NEUTRAL", "CRISIS"]
    setups = ["ORB", "EMA_PB", "SWEEP", ""]
    for i in range(n):
        out.append(
            DecisionContext(
                decision_id=f"d{i}",
                bar_ts=f"2026-04-25T10:{i:02d}:00",
                symbol="MNQH6",
                regime=regimes[i % len(regimes)],
                setup_name=setups[i % len(setups)],
                bar={"close": 21500.0 + i, "atr": 18.0},
                bot_snapshot={
                    "equity_usd": 5000.0,
                    "peak_equity_usd": 5000.0,
                    "consecutive_losses": 0,
                    "open_position_count": 0,
                },
                market_features={
                    "vix_z": (i % 5 - 2) * 0.5,
                    "spy_corr": 0.7,
                    "dxy_z": 0.0,
                    "spread_ticks": 1.0 + (i % 3) * 1.0,
                    "tick_z": (i % 7 - 3) * 0.4,
                },
            )
        )
    return out


def test_evaluator_full_panel_50_setups_meets_coverage() -> None:
    evaluator = ReasoningQualityEvaluator(build_default_panel())
    report = evaluator.evaluate(_seed_contexts(50))
    assert isinstance(report, EvalReport)
    assert report.n_setups == 50
    # The 7-specialist panel always emits 7 outputs -> coverage_pct = 100%
    assert report.coverage_pct == 1.0


def test_evaluator_red_team_gate_holds_on_50_setups() -> None:
    evaluator = ReasoningQualityEvaluator(build_default_panel())
    report = evaluator.evaluate(_seed_contexts(50))
    # The reference panel produces meaningfully distinct falsifications;
    # red_team_pct should be very high.
    assert report.red_team_pct >= 0.95


def test_evaluator_returns_FAIL_on_empty_input() -> None:
    evaluator = ReasoningQualityEvaluator(build_default_panel())
    report = evaluator.evaluate([])
    assert report.verdict == "FAIL"


def test_evaluator_handles_specialist_crashes_gracefully() -> None:
    """A crashing specialist must not break the eval; it's recorded as
    a "neutral / falsification: crashed" output."""

    class CrashingSpecialist(QuantSpecialist):
        name = "crasher"

        def evaluate(self, ctx):
            raise RuntimeError("simulated crash")

    panel = build_default_panel() + [CrashingSpecialist()]
    evaluator = ReasoningQualityEvaluator(panel)
    report = evaluator.evaluate(_seed_contexts(5))
    # Coverage holds because we count *responses*, including the crash-stub
    assert report.n_setups == 5


def test_evaluator_verdict_PASS_when_all_thresholds_clear() -> None:
    evaluator = ReasoningQualityEvaluator(
        build_default_panel(),
        min_coverage_pct=0.5,
        min_red_team_pct=0.5,
        min_avg_evidence=1.0,
    )
    report = evaluator.evaluate(_seed_contexts(10))
    assert report.verdict == "PASS"
