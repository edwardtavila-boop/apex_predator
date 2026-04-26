"""
DatabentoQueryTool — read-only L2 / OHLCV lookup against the parquet cache.

Per CLAUDE.md operator mandate (2026-04-24, third re-lock), this tool
NEVER triggers an actual Databento API pull. It only reads the
existing parquet cache that operator pulls populate. The cache miss
case returns a `success=False` ToolResult; the PM treats that as
"investigation incomplete; decide with what you have."
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from eta_engine.jarvis.tools.registry import Tool, ToolResult


class DatabentoQueryTool(Tool):
    name = "databento_query"
    description = (
        "Read-only lookup against the local parquet cache (.cache/parquet/). No live API pulls per operator mandate."
    )
    read_only = True
    cost_per_call_usd = 0.0

    def __init__(self, cache_root: Path | None = None) -> None:
        self.cache_root = cache_root or self._default_cache_root()

    @staticmethod
    def _default_cache_root() -> Path:
        env = os.environ.get("APEX_PARQUET_CACHE")
        if env:
            return Path(env)
        # Per CLAUDE.md: .cache/parquet/ is canonical
        return Path(__file__).resolve().parents[3] / ".cache" / "parquet"

    def invoke(
        self,
        *,
        symbol: str = "",
        date: str = "",
        kind: str = "ohlcv_1m",
        **_: Any,
    ) -> ToolResult:
        if not symbol or not date:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="symbol and date are required",
            )
        target = self.cache_root / kind / symbol / f"{date}.parquet"
        if not target.exists():
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"cache miss at {target}",
                data={"path": str(target)},
            )
        # Don't actually load the file — that's a heavy dep. Just confirm
        # presence + return metadata. Real PM wiring would parse with pyarrow.
        try:
            size = target.stat().st_size
        except OSError as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"stat failed: {e}",
            )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"path": str(target), "size_bytes": size, "kind": kind, "symbol": symbol, "date": date},
        )
