"""
EVOLUTIONARY TRADING ALGO // jarvis.consensus
=================================
PM consensus aggregator. Takes a list of SpecialistOutputs and produces
a structured PMVerdict that includes the WHY, not just a number.

Phase 1 contract:
  1. Validate at least N specialists weighed in (default 4 of 7)
  2. Run the Red Team gate (≥2 distinct falsification conditions)
  3. Aggregate signals weighted by confidence
  4. Derive a final verdict with a written rationale

The aggregation is deterministic + transparent so the unit tests can
pin behavior. When a real LLM PM is wired in, the same PMVerdict shape
is returned and the deterministic version becomes a fallback.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from eta_engine.jarvis.specialists.base import (
    DecisionContext,
    SpecialistOutput,
    red_team_gate_passes,
    red_team_objections,
)

PMAction = Literal["fire_long", "fire_short", "skip", "abstain"]


@dataclass
class PMVerdict:
    decision_id: str
    ts_utc: str
    action: PMAction
    confidence: float
    rationale: str  # WHY in plain English
    signal_tally: dict[str, int]  # per-signal vote count
    weighted_score: float  # signed: positive = long bias
    red_team_passed: bool
    red_team_objections: list[str]
    contributors: list[dict[str, Any]] = field(default_factory=list)
    blocked_reason: str = ""  # populated when action == "skip" / "abstain"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PMConsensus:
    """Aggregates SpecialistOutputs into one PMVerdict.

    Default policy:
      * min_voters: 4 (of 7 specialists must respond)
      * fire_threshold: |weighted_score| >= 0.40 to fire
      * red_team gate: must surface >= 2 distinct falsifications
      * tie / low-confidence -> "skip" (not "abstain")
      * crash / no voters    -> "abstain"
    """

    def __init__(
        self,
        *,
        min_voters: int = 4,
        fire_threshold: float = 0.40,
        red_team_min_objections: int = 2,
    ) -> None:
        self.min_voters = min_voters
        self.fire_threshold = fire_threshold
        self.red_team_min_objections = red_team_min_objections

    def aggregate(
        self,
        outputs: list[SpecialistOutput],
        *,
        ctx: DecisionContext,
    ) -> PMVerdict:
        ts = datetime.now(UTC).isoformat(timespec="seconds")

        if not outputs:
            return PMVerdict(
                decision_id=ctx.decision_id,
                ts_utc=ts,
                action="abstain",
                confidence=0.0,
                rationale="no specialist responded",
                signal_tally={},
                weighted_score=0.0,
                red_team_passed=False,
                red_team_objections=[],
                blocked_reason="no_voters",
            )

        if len(outputs) < self.min_voters:
            return PMVerdict(
                decision_id=ctx.decision_id,
                ts_utc=ts,
                action="abstain",
                confidence=0.0,
                rationale=(f"only {len(outputs)}/{self.min_voters} specialists responded; quorum not reached"),
                signal_tally=dict(Counter(o.signal for o in outputs)),
                weighted_score=0.0,
                red_team_passed=False,
                red_team_objections=[],
                contributors=[self._contributor(o) for o in outputs],
                blocked_reason="quorum_failed",
            )

        # Red Team gate
        rt_pass, rt_reason = red_team_gate_passes(
            outputs,
            min_required=self.red_team_min_objections,
        )
        objections = red_team_objections(outputs)
        if not rt_pass:
            return PMVerdict(
                decision_id=ctx.decision_id,
                ts_utc=ts,
                action="skip",
                confidence=0.0,
                rationale=(f"Red Team gate failed ({rt_reason}); skipping until at least 2 distinct objections exist"),
                signal_tally=dict(Counter(o.signal for o in outputs)),
                weighted_score=0.0,
                red_team_passed=False,
                red_team_objections=objections,
                contributors=[self._contributor(o) for o in outputs],
                blocked_reason="red_team_gate",
            )

        # Weighted score: long=+1, short=-1, skip/neutral=0, weighted by confidence
        signal_to_sign = {"long": 1.0, "short": -1.0, "skip": 0.0, "neutral": 0.0}
        weighted = sum(signal_to_sign.get(o.signal, 0.0) * o.confidence for o in outputs) / max(1, len(outputs))

        tally = dict(Counter(o.signal for o in outputs))

        if abs(weighted) < self.fire_threshold:
            return PMVerdict(
                decision_id=ctx.decision_id,
                ts_utc=ts,
                action="skip",
                confidence=round(abs(weighted), 4),
                rationale=(f"weighted score {weighted:+.3f} below fire threshold {self.fire_threshold}; tally={tally}"),
                signal_tally=tally,
                weighted_score=round(weighted, 4),
                red_team_passed=True,
                red_team_objections=objections,
                contributors=[self._contributor(o) for o in outputs],
                blocked_reason="below_fire_threshold",
            )

        action: PMAction = "fire_long" if weighted > 0 else "fire_short"
        # Rationale: longest evidence list from a specialist whose signal
        # matches the verdict gives the operator a "why" trail.
        agreers = [o for o in outputs if signal_to_sign.get(o.signal, 0.0) * weighted > 0]
        why = ""
        if agreers:
            best = max(agreers, key=lambda o: o.confidence)
            why = f"{best.hypothesis} | top evidence: {best.evidence[0]}"
        return PMVerdict(
            decision_id=ctx.decision_id,
            ts_utc=ts,
            action=action,
            confidence=round(abs(weighted), 4),
            rationale=(why + f" | weighted={weighted:+.3f}, tally={tally}, objections={len(objections)}"),
            signal_tally=tally,
            weighted_score=round(weighted, 4),
            red_team_passed=True,
            red_team_objections=objections,
            contributors=[self._contributor(o) for o in outputs],
        )

    @staticmethod
    def _contributor(o: SpecialistOutput) -> dict[str, Any]:
        return {
            "hypothesis": o.hypothesis,
            "signal": o.signal,
            "confidence": o.confidence,
            "evidence_count": len(o.evidence),
            "falsification": o.falsification,
            "tool_calls": list(o.tool_calls),
            "cited_memories": list(o.cited_memories),
        }
