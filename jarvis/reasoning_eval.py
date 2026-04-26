"""
EVOLUTIONARY TRADING ALGO // jarvis.reasoning_eval
======================================
Phase 1 reasoning-quality evaluator.

Runs the 7-specialist panel + PM consensus over a list of historical
DecisionContexts (the "50 historical setups" gate from the roadmap)
and scores the output along three dimensions:

  coverage    — % of setups where ≥4 specialists responded (quorum)
  red_team    — % of setups where ≥2 distinct falsifications raised
  evidence    — average evidence-rows-per-specialist

Output: an EvalReport dict suitable for the dashboard, plus a verdict
("PASS" | "MARGINAL" | "FAIL") against operator-set thresholds.

Default thresholds are conservative; loosen via constructor args.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from eta_engine.jarvis.consensus import PMConsensus, PMVerdict
from eta_engine.jarvis.specialists.base import (
    DecisionContext,
    SpecialistAgent,
    SpecialistOutput,
    red_team_objections,
)


@dataclass
class EvalReport:
    n_setups: int
    coverage_pct: float  # quorum rate
    red_team_pct: float  # ≥2 distinct falsifications rate
    avg_evidence_per_specialist: float
    verdict_breakdown: dict[str, int] = field(default_factory=dict)
    verdict: str = "FAIL"
    reasons: list[str] = field(default_factory=list)
    generated_at_utc: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReasoningQualityEvaluator:
    """Run the panel over N setups and score the output."""

    def __init__(
        self,
        specialists: list[SpecialistAgent],
        *,
        consensus: PMConsensus | None = None,
        min_coverage_pct: float = 0.95,
        min_red_team_pct: float = 0.80,
        min_avg_evidence: float = 1.5,
    ) -> None:
        self.specialists = list(specialists)
        self.consensus = consensus or PMConsensus()
        self.min_coverage_pct = min_coverage_pct
        self.min_red_team_pct = min_red_team_pct
        self.min_avg_evidence = min_avg_evidence

    def evaluate_one(
        self,
        ctx: DecisionContext,
    ) -> tuple[list[SpecialistOutput], PMVerdict]:
        outputs: list[SpecialistOutput] = []
        for s in self.specialists:
            try:
                outputs.append(s.evaluate(ctx))
            except Exception as e:  # noqa: BLE001
                # A specialist crash is a real risk; we record it as an
                # explicit "neutral / falsification: crashed" output so
                # the eval surfaces it rather than masking it.
                outputs.append(
                    SpecialistOutput(
                        hypothesis=f"{s.name} crashed during evaluation",
                        evidence=[f"exception: {type(e).__name__}: {e}"],
                        signal="neutral",
                        confidence=0.0,
                        falsification=f"{s.name} runs without exception on this context",
                    )
                )
        verdict = self.consensus.aggregate(outputs, ctx=ctx)
        return outputs, verdict

    def evaluate(self, contexts: list[DecisionContext]) -> EvalReport:
        if not contexts:
            return EvalReport(
                n_setups=0,
                coverage_pct=0.0,
                red_team_pct=0.0,
                avg_evidence_per_specialist=0.0,
                verdict="FAIL",
                reasons=["no contexts provided"],
                generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            )

        n = len(contexts)
        quorum_min = self.consensus.min_voters
        red_team_min = self.consensus.red_team_min_objections
        coverage_hits = 0
        red_team_hits = 0
        evidence_total = 0
        evidence_count = 0
        verdict_breakdown: dict[str, int] = {
            "fire_long": 0,
            "fire_short": 0,
            "skip": 0,
            "abstain": 0,
        }

        for ctx in contexts:
            outputs, verdict = self.evaluate_one(ctx)
            verdict_breakdown[verdict.action] = (
                verdict_breakdown.get(
                    verdict.action,
                    0,
                )
                + 1
            )
            if len(outputs) >= quorum_min:
                coverage_hits += 1
            if len(red_team_objections(outputs)) >= red_team_min:
                red_team_hits += 1
            for o in outputs:
                evidence_total += len(o.evidence)
                evidence_count += 1

        report = EvalReport(
            n_setups=n,
            coverage_pct=round(coverage_hits / n, 4),
            red_team_pct=round(red_team_hits / n, 4),
            avg_evidence_per_specialist=round(
                evidence_total / max(1, evidence_count),
                2,
            ),
            verdict_breakdown=verdict_breakdown,
            generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        )

        reasons: list[str] = []
        if report.coverage_pct < self.min_coverage_pct:
            reasons.append(f"coverage {report.coverage_pct:.2%} < {self.min_coverage_pct:.2%}")
        if report.red_team_pct < self.min_red_team_pct:
            reasons.append(f"red_team {report.red_team_pct:.2%} < {self.min_red_team_pct:.2%}")
        if report.avg_evidence_per_specialist < self.min_avg_evidence:
            reasons.append(f"avg evidence {report.avg_evidence_per_specialist:.2f} < {self.min_avg_evidence:.2f}")
        if not reasons:
            report.verdict = "PASS"
        elif len(reasons) == 1:
            report.verdict = "MARGINAL"
        else:
            report.verdict = "FAIL"
        report.reasons = reasons
        return report
