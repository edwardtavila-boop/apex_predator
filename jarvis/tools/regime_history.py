"""
RegimeHistoryTool — query past memories filtered by regime.

Backed by the same MemoryStore the retrieval engine uses (Phase 2).
Returns aggregate stats: count by setup, avg outcome, win-rate proxy.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from eta_engine.jarvis.tools.registry import Tool, ToolResult


class RegimeHistoryTool(Tool):
    name = "regime_history_lookup"
    description = (
        "Aggregate outcomes from episodic memory filtered by regime. "
        "Returns count by setup, avg +5-bar outcome, win rate."
    )
    read_only = True
    cost_per_call_usd = 0.0

    def __init__(self, store=None, outcome_key: str = "+5_bars") -> None:
        self.store = store
        self.outcome_key = outcome_key

    def invoke(
        self,
        *,
        regime: str = "",
        setup: str = "",
        **_: Any,
    ) -> ToolResult:
        if self.store is None:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="memory store not wired",
            )
        rows = [
            m for m in self.store.all() if (not regime or m.regime == regime) and (not setup or m.setup_name == setup)
        ]
        if not rows:
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"n": 0, "regime": regime, "setup": setup, "by_setup": {}, "avg_outcome": 0.0, "win_rate": 0.0},
            )
        outcomes = [float(m.outcomes.get(self.outcome_key, 0.0)) for m in rows]
        wins = sum(1 for o in outcomes if o > 0)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "n": len(rows),
                "regime": regime,
                "setup": setup,
                "by_setup": dict(Counter(m.setup_name for m in rows)),
                "avg_outcome": round(sum(outcomes) / len(outcomes), 4),
                "win_rate": round(wins / len(rows), 4),
                "outcome_key": self.outcome_key,
            },
        )
