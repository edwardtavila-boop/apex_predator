"""
TradovateL2Tool — read-only L2 snapshot lookup.

Per CLAUDE.md (2026-04-24, broker dormancy mandate), Tradovate is
DORMANT. This tool refuses to call the live Tradovate API and instead
returns the cached snapshot from state/tradovate_l2_cache/<symbol>.json
(operator-populated when the broker comes back online).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from eta_engine.jarvis.tools.registry import Tool, ToolResult


class TradovateL2Tool(Tool):
    name = "tradovate_l2_snapshot"
    description = (
        "Read-only L2 snapshot for futures symbols. Reads cached "
        "snapshots only (Tradovate broker is DORMANT until funding "
        "clears, per operator mandate 2026-04-24)."
    )
    read_only = True
    cost_per_call_usd = 0.0

    def __init__(self, cache_dir: Path | None = None) -> None:
        if cache_dir is None:
            base = Path(os.environ.get("APEX_STATE_DIR", str(Path.home() / ".eta_engine")))
            cache_dir = base / "tradovate_l2_cache"
        self.cache_dir = cache_dir

    def invoke(self, *, symbol: str = "", **_: Any) -> ToolResult:
        if not symbol:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="symbol required",
            )
        # Honor the dormancy mandate: refuse even attempting a live call
        # check the env var that gates the brokers.
        try:
            from eta_engine.venues.router import DORMANT_BROKERS

            if "tradovate" in DORMANT_BROKERS:
                target = self.cache_dir / f"{symbol}.json"
                if not target.exists():
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error=(f"tradovate is DORMANT and no cached snapshot exists at {target}"),
                    )
                try:
                    data = json.loads(target.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error=f"parse: {e}",
                    )
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={**data, "source": "cache_dormancy"},
                )
        except ImportError:
            pass
        # If the dormancy mandate is lifted, this is where a real
        # tradovate adapter call would go. Default safe fallthrough.
        return ToolResult(
            tool_name=self.name,
            success=False,
            error="live Tradovate adapter not wired in this build",
        )
