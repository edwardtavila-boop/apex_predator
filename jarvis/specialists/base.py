"""
EVOLUTIONARY TRADING ALGO // jarvis.specialists.base
========================================
Phase 1 foundation. Replaces numeric scoring with structured reasoning.

Every specialist outputs a ``SpecialistOutput`` with five fields:
    hypothesis    — one-sentence WHY this setup is interesting
    evidence      — list of concrete facts the specialist relied on
    signal        — one of {"long", "short", "skip", "neutral"}
    confidence    — float in [0.0, 1.0]
    falsification — what condition would PROVE this hypothesis wrong

The PM aggregates these into a structured consensus, NOT just a number.
The Red Team gate (per Phase 1) requires ≥2 specialists to provide a
falsification condition that another specialist's evidence does not
satisfy — otherwise the decision is rejected as "no real disagreement."
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Signal = Literal["long", "short", "skip", "neutral"]


class SpecialistOutput(BaseModel):
    """Structured reasoning output from one specialist.

    The Pydantic validator enforces:
      * confidence ∈ [0, 1]
      * signal ∈ {long, short, skip, neutral}
      * evidence is a list of strings (≥1 required)
      * falsification is non-empty
    """

    hypothesis: str = Field(
        min_length=1,
        description="One-sentence WHY this setup is interesting.",
    )
    evidence: list[str] = Field(
        min_length=1,
        description="Concrete facts the specialist relied on.",
    )
    signal: Signal = Field(
        description="The recommended directional verdict.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Strength of conviction in [0.0, 1.0].",
    )
    falsification: str = Field(
        min_length=1,
        description="The condition that would prove the hypothesis wrong.",
    )

    # Optional fields the PM uses but specialists may omit.
    cited_memories: list[str] = Field(
        default_factory=list,
        description="decision_id values the specialist consulted (Phase 2).",
    )
    tool_calls: list[str] = Field(
        default_factory=list,
        description="Tool names invoked while forming this opinion (Phase 3).",
    )

    @field_validator("hypothesis", "falsification")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("evidence")
    @classmethod
    def _strip_evidence(cls, v: list[str]) -> list[str]:
        out = [e.strip() for e in v if e and e.strip()]
        if not out:
            raise ValueError("evidence must contain at least one non-empty string")
        return out


@dataclass(frozen=True)
class DecisionContext:
    """Inputs every specialist sees.

    Aggregated upstream from market state, regime detector, and bot
    snapshots. Specialists must NOT mutate this — it's frozen.
    """

    decision_id: str
    bar_ts: str  # ISO-8601 of the bar in question
    symbol: str
    regime: str  # "RISK-ON" | "RISK-OFF" | "NEUTRAL" | "CRISIS"
    setup_name: str  # "ORB" | "EMA_PB" | "SWEEP" | ... | "" if no setup
    bar: dict[str, Any]  # OHLCV + indicators
    bot_snapshot: dict[str, Any] = field(default_factory=dict)
    market_features: dict[str, Any] = field(default_factory=dict)
    retrieved_memories: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class SpecialistAgent(abc.ABC):
    """Abstract base class for every specialist.

    Subclass contract:
      * ``name`` class attribute (snake_case, used in audit log role)
      * implement ``evaluate(ctx: DecisionContext) -> SpecialistOutput``
      * MAY use ``self.transport`` to call an LLM (always logged via
        the optional ``self.audit`` LLMAuditLog)
      * MUST NOT have side effects beyond optional LLM calls
    """

    name: str = "base"

    def __init__(
        self,
        *,
        transport: Any | None = None,  # LLMTransport (avoid cyclic import)
        audit: Any | None = None,  # LLMAuditLog
        model_hint: str | None = None,
    ) -> None:
        self.transport = transport
        self.audit = audit
        self.model_hint = model_hint

    @abc.abstractmethod
    def evaluate(self, ctx: DecisionContext) -> SpecialistOutput: ...

    def _llm_complete(
        self,
        *,
        prompt: str,
        system: str = "",
        decision_id: str = "",
    ) -> str:
        """Helper: invoke the wired transport, log the call, return text.

        Specialists that don't need an LLM (the deterministic reference
        implementations in #63) ignore this helper entirely.
        """
        if self.transport is None:
            raise RuntimeError(f"{self.name}: tried to call LLM but no transport wired")
        result = self.transport.complete(
            prompt=prompt,
            system=system,
            model_hint=self.model_hint,
        )
        if self.audit is not None:
            self.audit.record(
                result,
                prompt=prompt,
                system=system,
                decision_id=decision_id,
                role=f"specialist:{self.name}",
            )
        return result.text


# ---------------------------------------------------------------------------
# Red Team gate primitive
# ---------------------------------------------------------------------------
def red_team_objections(
    outputs: list[SpecialistOutput],
    *,
    min_required: int = 2,
) -> list[str]:
    """Return the unique falsification conditions raised across specialists.

    The Phase 1 Red Team gate requires ``len(red_team_objections(...)) >= 2``
    BEFORE the PM is allowed to fire. The intent: at least two specialists
    must surface a meaningfully distinct way the hypothesis could fail.

    "Meaningfully distinct" is approximated by string-normalized identity
    here; a future Phase 1 hardening can swap in semantic similarity.
    """
    seen: set[str] = set()
    out: list[str] = []
    for o in outputs:
        key = " ".join(o.falsification.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(o.falsification.strip())
    return out


def red_team_gate_passes(
    outputs: list[SpecialistOutput],
    *,
    min_required: int = 2,
) -> tuple[bool, str]:
    """Phase 1 gate. Returns (passes, reason)."""
    objections = red_team_objections(outputs, min_required=min_required)
    if len(objections) < min_required:
        return False, (
            f"red team gate FAILED: only {len(objections)} distinct falsification conditions; need {min_required}"
        )
    return True, f"{len(objections)} distinct falsifications"
