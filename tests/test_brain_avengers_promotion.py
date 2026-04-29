from __future__ import annotations

import json
from datetime import UTC, datetime

from eta_engine.brain.avengers.promotion import (
    PromotionAction,
    PromotionDecision,
    PromotionGate,
    PromotionSpec,
    PromotionStage,
    StageMetrics,
    default_red_team_gate,
)


def test_default_red_team_gate_vetoes_fragile_promotion_margin() -> None:
    metrics = StageMetrics(
        trades=52,
        days_active=15,
        sharpe=1.02,
        max_dd_pct=4.8,
        win_rate=0.46,
        mean_slippage_bps=1.0,
    )
    spec = PromotionSpec(
        strategy_id="orb-v1",
        current_stage=PromotionStage.SHADOW,
        entered_stage_at=datetime(2026, 4, 29, tzinfo=UTC),
        metrics=metrics,
    )
    decision = PromotionDecision(
        strategy_id="orb-v1",
        from_stage=PromotionStage.SHADOW,
        to_stage=PromotionStage.PAPER,
        action=PromotionAction.PROMOTE,
        reasons=["all thresholds cleared"],
        metrics=metrics,
    )

    verdict = default_red_team_gate(spec, decision)

    assert verdict.approve is False
    assert verdict.risk_score > 0
    assert any("sharpe" in reason for reason in verdict.reasons)
    assert any("trades" in reason for reason in verdict.reasons)


def test_promotion_gate_promotes_and_journals_stage_change(tmp_path) -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    gate = PromotionGate(
        state_path=tmp_path / "promotion.json",
        journal_path=tmp_path / "promotion.jsonl",
        red_team_gate=None,
        clock=lambda: now,
    )
    gate.register("orb-v2")
    gate.update_metrics(
        "orb-v2",
        StageMetrics(
            trades=80,
            days_active=20,
            sharpe=1.8,
            max_dd_pct=2.0,
            win_rate=0.58,
            mean_slippage_bps=1.0,
        ),
    )

    decision = gate.evaluate("orb-v2")
    applied = gate.apply(decision)

    assert decision.action is PromotionAction.PROMOTE
    assert applied.current_stage is PromotionStage.PAPER
    assert applied.metrics == StageMetrics()
    journal_lines = (tmp_path / "promotion.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(journal_lines[-1])["action"] == "PROMOTE"


def test_promotion_gate_retires_shadow_strategy_on_hard_break(tmp_path) -> None:
    gate = PromotionGate(
        state_path=tmp_path / "promotion.json",
        journal_path=tmp_path / "promotion.jsonl",
        red_team_gate=None,
    )
    gate.register("broken-shadow")
    gate.update_metrics(
        "broken-shadow",
        StageMetrics(trades=20, days_active=4, sharpe=-1.0, max_dd_pct=11.0, win_rate=0.1),
    )

    decision = gate.evaluate("broken-shadow")

    assert decision.action is PromotionAction.RETIRE
    assert decision.to_stage is PromotionStage.RETIRED
    assert "hard break at SHADOW" in decision.reasons
