"""
EVOLUTIONARY TRADING ALGO // jarvis.cost_breaker
====================================
Per-decision cost circuit breaker (closes the cost-drift risk the user
flagged).

The roadmap caps per-decision cost via:
  * 4 tool calls / 8s wall clock (ToolBudgetEnforcer in jarvis.tools.budget)
  * implicit per-decision LLM cost (this module)

Behavior:
  * On every call to ``record(decision_id, cost_usd)`` we sum the cost.
  * If decision exceeds ``per_decision_cap_usd``, that decision is
    flagged ``trip=True``.
  * If we accumulate ``trips_to_escalate`` trips inside ``window_s``,
    ``escalation_required`` becomes True until the operator clears it.

Wired via:
  * Specialist + PM LLM calls: each result.cost_usd → record(...)
  * Tool calls: same hook for the few tools that have non-zero cost
  * Dashboard: /api/jarvis/cost surfaces the breaker state
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class DecisionCost:
    decision_id: str
    cost_usd: float
    n_calls: int
    trip: bool
    ts_utc: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PerDecisionCostBreaker:
    """In-process accumulator + escalation gate."""

    def __init__(
        self,
        *,
        per_decision_cap_usd: float = 0.50,
        window_s: float = 3600.0,
        trips_to_escalate: int = 3,
        ledger_path: Path | None = None,
    ) -> None:
        self.cap = per_decision_cap_usd
        self.window_s = window_s
        self.trips_to_escalate = trips_to_escalate
        self._open: dict[str, dict[str, float | int]] = {}
        self._trips: deque[float] = deque()
        self._escalated_at: float | None = None
        self.ledger_path = ledger_path or self._default_ledger()

    @staticmethod
    def _default_ledger() -> Path:
        base = Path(
            os.environ.get(
                "APEX_STATE_DIR",
                str(Path(__file__).resolve().parents[1] / "state"),
            )
        )
        return base / "jarvis_cost_breaker.jsonl"

    def record(
        self,
        *,
        decision_id: str,
        cost_usd: float,
        finalize: bool = False,
    ) -> DecisionCost | None:
        """Add cost to the open ledger for this decision_id.
        When ``finalize=True``, close the row, evaluate trip, and append
        to the persistent ledger. Returns the closed DecisionCost (or
        None if still open)."""
        slot = self._open.setdefault(decision_id, {"cost": 0.0, "n": 0})
        slot["cost"] = float(slot["cost"]) + float(cost_usd)
        slot["n"] = int(slot["n"]) + 1

        if not finalize:
            return None

        cost = float(slot["cost"])
        n = int(slot["n"])
        del self._open[decision_id]
        trip = cost > self.cap
        if trip:
            now = datetime.now(UTC).timestamp()
            self._trips.append(now)
            self._purge_old_trips(now)
            if len(self._trips) >= self.trips_to_escalate and self._escalated_at is None:
                self._escalated_at = now

        row = DecisionCost(
            decision_id=decision_id,
            cost_usd=round(cost, 6),
            n_calls=n,
            trip=trip,
            ts_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._append_ledger(row)
        return row

    def _purge_old_trips(self, now: float) -> None:
        cutoff = now - self.window_s
        while self._trips and self._trips[0] < cutoff:
            self._trips.popleft()

    def _append_ledger(self, row: DecisionCost) -> None:
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row.as_dict()) + "\n")
        except OSError:
            pass

    def escalation_required(self) -> bool:
        return self._escalated_at is not None

    def clear_escalation(self) -> None:
        """Operator path: clear after acknowledging."""
        self._escalated_at = None
        self._trips.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "per_decision_cap_usd": self.cap,
            "window_s": self.window_s,
            "trips_to_escalate": self.trips_to_escalate,
            "trips_in_window": len(self._trips),
            "escalation_required": self.escalation_required(),
            "open_decisions": len(self._open),
        }
