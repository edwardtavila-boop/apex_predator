"""
EVOLUTIONARY TRADING ALGO // jarvis.fast_path
=================================
Fast-path skip for time-sensitive setups.

The user flagged that for ORB / liquidity-sweep setups, 2-6s of LLM
consensus is too slow. The fast-path:

  * Time-sensitive setups (ORB, SWEEP) bypass async LLM specialist
    calls and use a CACHED PMVerdict from the last N seconds.
  * Cache key: (regime, setup_name, bar_close_rounded). If a hit
    within the freshness window, return the cached verdict.
  * Cache MISS or non-time-sensitive setup: fall through to the
    normal AsyncSpecialistRunner path.

Cache is bounded (default 256 entries) with LRU eviction. Operator
sets `time_sensitive_setups` based on their strategy; the default
covers the obvious cases.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from eta_engine.jarvis.consensus import PMVerdict
from eta_engine.jarvis.specialists.base import DecisionContext


@dataclass(frozen=True)
class _CacheKey:
    regime: str
    setup_name: str
    bar_close_bin: int  # close rounded to nearest 0.25


@dataclass
class _CacheEntry:
    verdict: PMVerdict
    cached_at_monotonic: float


class FastPathPolicy:
    """Policy + cache for time-sensitive setup fast-path.

    Usage:

        fp = FastPathPolicy()
        cached = fp.try_get(ctx)
        if cached is not None:
            verdict = cached
        else:
            verdict = pm_consensus.aggregate(...)
            fp.store(ctx, verdict)
    """

    DEFAULT_TIME_SENSITIVE = frozenset(
        {
            "ORB",
            "ORB_LONG",
            "ORB_SHORT",
            "SWEEP",
            "LIQUIDITY_SWEEP",
            "BREAKOUT",
        }
    )

    def __init__(
        self,
        *,
        time_sensitive_setups: frozenset[str] | None = None,
        freshness_window_s: float = 60.0,
        max_entries: int = 256,
        bar_close_bin_size: float = 0.25,
    ) -> None:
        self.time_sensitive = (
            time_sensitive_setups if time_sensitive_setups is not None else self.DEFAULT_TIME_SENSITIVE
        )
        self.freshness_window_s = freshness_window_s
        self.max_entries = max_entries
        self.bin_size = bar_close_bin_size
        self._cache: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()

    def is_time_sensitive(self, ctx: DecisionContext) -> bool:
        return ctx.setup_name.upper() in self.time_sensitive

    def _key(self, ctx: DecisionContext) -> _CacheKey:
        close = float(ctx.bar.get("close", 0.0))
        bin_idx = int(round(close / max(self.bin_size, 1e-9)))
        return _CacheKey(
            regime=ctx.regime,
            setup_name=ctx.setup_name.upper(),
            bar_close_bin=bin_idx,
        )

    def try_get(self, ctx: DecisionContext) -> PMVerdict | None:
        if not self.is_time_sensitive(ctx):
            return None
        key = self._key(ctx)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.cached_at_monotonic > self.freshness_window_s:
            self._cache.pop(key, None)
            return None
        # LRU: bump on access
        self._cache.move_to_end(key)
        return entry.verdict

    def store(self, ctx: DecisionContext, verdict: PMVerdict) -> None:
        if not self.is_time_sensitive(ctx):
            return
        key = self._key(ctx)
        self._cache[key] = _CacheEntry(
            verdict=verdict,
            cached_at_monotonic=time.monotonic(),
        )
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)

    def stats(self) -> dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_entries": self.max_entries,
            "freshness_window_s": self.freshness_window_s,
            "time_sensitive_setups": sorted(self.time_sensitive),
        }
