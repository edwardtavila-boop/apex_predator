"""
EVOLUTIONARY TRADING ALGO // jarvis.tools.registry
======================================
Tool protocol + registry. The PM picks tools by name and invokes them
through the ToolBudgetEnforcer (which counts calls, wall-clock, and cost).

Sandbox enforcement: each tool declares ``read_only=True/False`` and
``cost_per_call_usd``. The PM's tool-use loop refuses execution-tier
tools (read_only=False) unless the gauntlet pass flag is set on the
registry — production wiring binds this to the 14-gate gauntlet
runtime check (Phase 3 sandbox rule).
"""

from __future__ import annotations

import abc
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    elapsed_s: float = 0.0
    cost_usd: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCallRecord:
    """One row in the tool-call audit trail."""

    decision_id: str
    ts_utc: str
    tool_name: str
    args: dict[str, Any]
    success: bool
    error: str = ""
    elapsed_s: float = 0.0
    cost_usd: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Tool(abc.ABC):
    """Abstract tool. Subclass and register on a ToolRegistry."""

    name: str = "base"
    description: str = ""
    read_only: bool = True
    cost_per_call_usd: float = 0.0

    @abc.abstractmethod
    def invoke(self, **kwargs: Any) -> ToolResult: ...

    def schema(self) -> dict[str, Any]:
        """Self-describe for the PM prompt builder."""
        return {
            "name": self.name,
            "description": self.description,
            "read_only": self.read_only,
            "cost_per_call_usd": self.cost_per_call_usd,
        }


class ToolRegistry:
    """Registry + execution surface.

    By default ``allow_execution_tier=False`` — PM cannot invoke tools
    with ``read_only=False``. Wiring sets this to True only when the
    gauntlet flagged the strategy as live-eligible.
    """

    def __init__(self, *, allow_execution_tier: bool = False) -> None:
        self._tools: dict[str, Tool] = {}
        self.allow_execution_tier = allow_execution_tier

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def list(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def invoke(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"unknown tool {name!r}",
            )
        if not tool.read_only and not self.allow_execution_tier:
            return ToolResult(
                tool_name=name,
                success=False,
                error=(
                    "execution-tier tool blocked by sandbox; gauntlet pass required to set allow_execution_tier=True"
                ),
            )
        t0 = time.monotonic()
        try:
            result = tool.invoke(**kwargs)
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"{type(e).__name__}: {e}",
                elapsed_s=time.monotonic() - t0,
            )
        result.elapsed_s = time.monotonic() - t0
        result.cost_usd = tool.cost_per_call_usd
        return result
