"""Phase 3: tool use + investigative autonomy."""

from __future__ import annotations

from eta_engine.jarvis.tools.budget import (
    BudgetExceededError,
    ToolBudget,
    ToolBudgetEnforcer,
)

# Reference tool implementations
from eta_engine.jarvis.tools.databento import DatabentoQueryTool
from eta_engine.jarvis.tools.fred import FredMacroTool
from eta_engine.jarvis.tools.monte_carlo import MonteCarloTool
from eta_engine.jarvis.tools.regime_history import RegimeHistoryTool
from eta_engine.jarvis.tools.registry import (
    Tool,
    ToolCallRecord,
    ToolRegistry,
    ToolResult,
)
from eta_engine.jarvis.tools.tradovate_l2 import TradovateL2Tool


def build_default_tool_registry(
    *,
    memory_store=None,
) -> ToolRegistry:
    """Returns a registry pre-populated with the 5 roadmap tools."""
    reg = ToolRegistry()
    reg.register(DatabentoQueryTool())
    reg.register(FredMacroTool())
    reg.register(TradovateL2Tool())
    reg.register(MonteCarloTool())
    reg.register(RegimeHistoryTool(store=memory_store))
    return reg


__all__ = [
    "BudgetExceededError",
    "DatabentoQueryTool",
    "FredMacroTool",
    "MonteCarloTool",
    "RegimeHistoryTool",
    "Tool",
    "ToolBudget",
    "ToolBudgetEnforcer",
    "ToolCallRecord",
    "ToolRegistry",
    "ToolResult",
    "TradovateL2Tool",
    "build_default_tool_registry",
]
