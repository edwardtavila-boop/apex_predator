"""
EVOLUTIONARY TRADING ALGO // jarvis.tools.budget
====================================
Per-decision tool-call budget. Roadmap caps:
    max 4 tool calls per decision
    8s wall-clock cap

Plus a per-decision USD cost cap (operator-set; default $0.50/decision)
to prevent the cost-drift failure mode the user flagged.

When any cap is exceeded, the enforcer raises BudgetExceededError
which the PM treats as "stop investigating; decide with what you have."
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from eta_engine.jarvis.tools.registry import (
    ToolCallRecord,
    ToolRegistry,
    ToolResult,
)


@dataclass
class ToolBudget:
    max_calls: int = 4
    wall_clock_s: float = 8.0
    cost_usd: float = 0.50


class BudgetExceededError(RuntimeError):
    """Raised when any cap is exceeded mid-investigation."""

    def __init__(self, kind: str, used: float, cap: float) -> None:
        self.kind = kind
        self.used = used
        self.cap = cap
        super().__init__(f"tool budget exceeded: {kind} {used} > cap {cap}")


@dataclass
class BudgetState:
    n_calls: int = 0
    elapsed_s: float = 0.0
    cost_usd: float = 0.0
    started_monotonic: float = field(default_factory=time.monotonic)

    def check(self, budget: ToolBudget) -> None:
        if self.n_calls >= budget.max_calls:
            raise BudgetExceededError("calls", self.n_calls, budget.max_calls)
        if self.elapsed_s >= budget.wall_clock_s:
            raise BudgetExceededError("wall_clock_s", self.elapsed_s, budget.wall_clock_s)
        if self.cost_usd >= budget.cost_usd:
            raise BudgetExceededError("cost_usd", self.cost_usd, budget.cost_usd)


class ToolBudgetEnforcer:
    """Wraps a ToolRegistry with per-decision budget tracking.

    Usage:

        enforcer = ToolBudgetEnforcer(registry, budget=ToolBudget())
        with enforcer.session(decision_id="d1") as session:
            r = session.invoke("databento_query", symbol="MNQ")
            # raises BudgetExceededError after 4 calls or 8s wall clock
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        budget: ToolBudget | None = None,
    ) -> None:
        self.registry = registry
        self.budget = budget or ToolBudget()

    def session(self, *, decision_id: str) -> "ToolSession":
        return ToolSession(
            registry=self.registry,
            budget=self.budget,
            decision_id=decision_id,
        )


class ToolSession:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        budget: ToolBudget,
        decision_id: str,
    ) -> None:
        self.registry = registry
        self.budget = budget
        self.decision_id = decision_id
        self.state = BudgetState()
        self.records: list[ToolCallRecord] = []

    def __enter__(self) -> "ToolSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def invoke(self, name: str, **kwargs: Any) -> ToolResult:
        # Refresh elapsed before the gate check
        self.state.elapsed_s = time.monotonic() - self.state.started_monotonic
        self.state.check(self.budget)
        result = self.registry.invoke(name, **kwargs)
        self.state.n_calls += 1
        self.state.elapsed_s = time.monotonic() - self.state.started_monotonic
        self.state.cost_usd += result.cost_usd
        from datetime import UTC, datetime

        self.records.append(
            ToolCallRecord(
                decision_id=self.decision_id,
                ts_utc=datetime.now(UTC).isoformat(timespec="seconds"),
                tool_name=name,
                args=dict(kwargs),
                success=result.success,
                error=result.error,
                elapsed_s=result.elapsed_s,
                cost_usd=result.cost_usd,
            )
        )
        # Re-check after the call so the next .invoke() in this session
        # sees the post-call accumulator.
        try:
            self.state.check(self.budget)
        except BudgetExceededError:
            # Don't raise — the call already happened. Next call will refuse.
            pass
        return result
