"""
FredMacroTool — read-only FRED macro lookup against a local snapshot.

Production wiring sets `cache_dir` to a real FRED snapshot dir; the
reference impl reads from `state/fred_cache/<series>.json` (operator
populates via a separate cache-warmer script).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from eta_engine.jarvis.tools.registry import Tool, ToolResult


class FredMacroTool(Tool):
    name = "fred_macro"
    description = (
        "Read VIX / DXY / DGS10 / DFF series from local FRED cache. "
        "Returns latest value + age in days. No live API call."
    )
    read_only = True
    cost_per_call_usd = 0.0

    KNOWN_SERIES = ("VIXCLS", "DXY", "DGS10", "DFF", "T10Y2Y", "UNRATE")

    def __init__(self, cache_dir: Path | None = None) -> None:
        if cache_dir is None:
            base = Path(os.environ.get("APEX_STATE_DIR", str(Path.home() / ".eta_engine")))
            cache_dir = base / "fred_cache"
        self.cache_dir = cache_dir

    def invoke(self, *, series: str = "", **_: Any) -> ToolResult:
        if not series:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=("series is required; known: " + ", ".join(self.KNOWN_SERIES)),
            )
        target = self.cache_dir / f"{series}.json"
        if not target.exists():
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"cache miss at {target}",
                data={"path": str(target), "hint": "populate via fred cache-warmer script"},
            )
        try:
            d = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"parse: {e}",
            )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "series": series,
                "latest_value": d.get("latest_value"),
                "as_of": d.get("as_of"),
                "age_days": d.get("age_days"),
            },
        )
