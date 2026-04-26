"""
MonteCarloTool — pure-Python deterministic Monte Carlo over a trade
return distribution. 5,000 paths default per the roadmap.
"""

from __future__ import annotations

import random
from typing import Any

from eta_engine.jarvis.tools.registry import Tool, ToolResult


class MonteCarloTool(Tool):
    name = "monte_carlo_run"
    description = (
        "Run a Monte Carlo over a trade-return distribution. Returns "
        "p5/p25/p50/p75/p95 of equity at horizon, plus drawdown stats."
    )
    read_only = True
    cost_per_call_usd = 0.0

    def invoke(
        self,
        *,
        trade_returns: list[float] | None = None,
        n_paths: int = 5000,
        horizon_n_trades: int = 100,
        seed: int = 0xA1EC,
        **_: Any,
    ) -> ToolResult:
        if not trade_returns:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="trade_returns required (a list of historical R-multiples)",
            )
        if any(not isinstance(r, (int, float)) for r in trade_returns):
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="trade_returns must be numeric",
            )

        rng = random.Random(seed)
        n_paths = max(100, min(int(n_paths), 50_000))
        horizon = max(1, min(int(horizon_n_trades), 1000))

        final_equities: list[float] = []
        max_dds: list[float] = []
        for _p in range(n_paths):
            cum = 0.0
            peak = 0.0
            dd = 0.0
            for _ in range(horizon):
                r = rng.choice(trade_returns)
                cum += r
                peak = max(peak, cum)
                dd = min(dd, cum - peak)
            final_equities.append(cum)
            max_dds.append(dd)

        final_equities.sort()
        max_dds.sort()

        def _q(arr: list[float], q: float) -> float:
            if not arr:
                return 0.0
            i = int(q * (len(arr) - 1))
            return round(arr[i], 4)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "n_paths": n_paths,
                "horizon_n_trades": horizon,
                "final_equity_p5": _q(final_equities, 0.05),
                "final_equity_p25": _q(final_equities, 0.25),
                "final_equity_p50": _q(final_equities, 0.50),
                "final_equity_p75": _q(final_equities, 0.75),
                "final_equity_p95": _q(final_equities, 0.95),
                "max_dd_p5": _q(max_dds, 0.05),
                "max_dd_p50": _q(max_dds, 0.50),
                "max_dd_p95": _q(max_dds, 0.95),
                "sample_size_in": len(trade_returns),
            },
        )
