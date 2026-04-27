"""Multi-policy dispatcher (wave-6, 2026-04-27).

Runs every registered candidate policy against a single
(ActionRequest, JarvisContext) and returns a diff matrix showing what
each candidate would do.

Use cases:
  1. Operator inspection: "what does each candidate think about THIS
     order, RIGHT NOW?" -- without flipping ETA_BANDIT_ENABLED on.
  2. Audit log enrichment: write the multi-policy diff alongside the
     champion's verdict so the burn-in journal carries v17/v18/v19/v20/
     v21/v22 outputs side-by-side. Future replay scoring can compare
     champions against ANY arm without re-running.
  3. Live operator override: when the operator wants a heavier veto
     than v17 in a specific moment, they can flip the dispatcher into
     "consensus" mode and use the most-pessimistic verdict across all
     arms.

Read-only by default -- doesn't change live JARVIS behavior unless
the operator explicitly chooses a non-champion verdict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PolicyVerdict:
    """One candidate's response to (req, ctx)."""

    arm_id: str
    parent_version: int
    verdict: str
    reason_code: str
    reason: str
    size_cap_mult: float | None
    error: str | None = None


@dataclass
class DispatchResult:
    """Aggregate of every registered candidate's verdict on a single request."""

    request_id: str
    champion_arm: str
    verdicts: list[PolicyVerdict]
    consensus_verdict: str            # most pessimistic across arms
    consensus_size_cap_mult: float    # min cap across arms
    disagreement_count: int           # non-champion arms whose verdict != champion's


def _verdict_pessimism_rank(verdict: str) -> int:
    """Lower = more conservative. DENIED < DEFERRED < CONDITIONAL < APPROVED."""
    return {
        "DENIED": 0,
        "DEFERRED": 1,
        "CONDITIONAL": 2,
        "APPROVED": 3,
    }.get(verdict, 999)


def dispatch_all(req: Any, ctx: Any, *, champion_arm: str = "v17") -> DispatchResult:
    """Run every registered candidate against (req, ctx) and aggregate.

    Returns ``DispatchResult`` with per-arm verdict + consensus metrics.
    Errors per arm are captured (one bad candidate doesn't break the rest).
    """
    # Auto-register candidates if the package hasn't been touched yet.
    try:
        from eta_engine.brain.jarvis_v3 import policies  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        logger.warning("policies package import failed: %s", exc)

    from eta_engine.brain.jarvis_v3.candidate_policy import (
        get_candidate, list_candidates,
    )

    verdicts: list[PolicyVerdict] = []
    most_pessimistic_rank = 999
    consensus_verdict = "APPROVED"
    consensus_cap = 1.0
    champion_verdict_str = ""
    disagreement = 0

    for c in list_candidates():
        arm_id = c["name"]
        try:
            policy = get_candidate(arm_id)
            resp = policy(req, ctx)
            v_str = resp.verdict.value if hasattr(resp.verdict, "value") else str(resp.verdict)
            cap = resp.size_cap_mult if resp.size_cap_mult is not None else 1.0
            verdicts.append(PolicyVerdict(
                arm_id=arm_id,
                parent_version=int(c.get("parent_version", 0)),
                verdict=v_str,
                reason_code=resp.reason_code,
                reason=resp.reason[:200],
                size_cap_mult=cap,
            ))
            rank = _verdict_pessimism_rank(v_str)
            if rank < most_pessimistic_rank:
                most_pessimistic_rank = rank
                consensus_verdict = v_str
            if cap < consensus_cap:
                consensus_cap = cap
            if arm_id == champion_arm:
                champion_verdict_str = v_str
        except Exception as exc:  # noqa: BLE001
            logger.warning("candidate %s raised: %s", arm_id, exc)
            verdicts.append(PolicyVerdict(
                arm_id=arm_id,
                parent_version=int(c.get("parent_version", 0)),
                verdict="ERROR",
                reason_code="exception",
                reason=str(exc)[:200],
                size_cap_mult=None,
                error=str(exc),
            ))

    # Disagreement count: non-champion arms whose verdict differs
    if champion_verdict_str:
        for v in verdicts:
            if v.arm_id == champion_arm:
                continue
            if v.verdict != champion_verdict_str:
                disagreement += 1

    return DispatchResult(
        request_id=getattr(req, "request_id", ""),
        champion_arm=champion_arm,
        verdicts=verdicts,
        consensus_verdict=consensus_verdict,
        consensus_size_cap_mult=round(consensus_cap, 4),
        disagreement_count=disagreement,
    )


def diff_matrix(result: DispatchResult) -> dict[str, Any]:
    """Render the dispatch result as a flat dict for JSON / dashboard."""
    return {
        "request_id": result.request_id,
        "champion": result.champion_arm,
        "consensus_verdict": result.consensus_verdict,
        "consensus_size_cap_mult": result.consensus_size_cap_mult,
        "disagreement_count": result.disagreement_count,
        "per_arm": [
            {
                "arm_id": v.arm_id,
                "parent_version": v.parent_version,
                "verdict": v.verdict,
                "reason_code": v.reason_code,
                "size_cap_mult": v.size_cap_mult,
                "error": v.error,
            }
            for v in result.verdicts
        ],
    }
