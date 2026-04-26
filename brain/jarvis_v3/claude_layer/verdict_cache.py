"""
JARVIS v3 // claude_layer.verdict_cache
========================================
Layer 2 of the cascading inference pyramid.

After escalation says "yes, Claude is justified" and distillation says
"no, classifier isn't confident enough to skip", we have one more cheap
veto: have we already gotten an answer for an essentially-identical
decision in the recent past?

The verdict cache buckets the input features (floats rounded to coarse
grids, ints binned, strings as-is) and SHA-hashes the result into a
key. The value is the previously-computed ``final_vote`` plus metadata
about WHEN it was computed and which dispatch route produced it. TTL
is short (default 1 hour) because market conditions change; HIGH-stress
or CRISIS-regime entries get an even shorter TTL.

Why this matters for cost
-------------------------
Every cache hit avoids the full persona debate. A typical hot session
(active trading window) sees the same regime + similar stress score for
many minutes -- consecutive escalations within 5-10 minutes are very
likely to bucket-hash identically. Even with conservative bucketing
(stress @ 0.05 grid, sizing @ 0.10 grid), real-world hit rates of
30-60% during steady periods are realistic.

Cost saving per hit: roughly 1 BATMAN-orchestrated debate ($0.05 to
$0.20 depending on persona plan and cache state of the prefix). Even
at the low end, 50 cache hits per day saves ~$2.50 -- meaningful at
the $10/day quota cap.

Pure stdlib + pydantic. No I/O. The dispatcher is responsible for
deciding when to consult the cache and when to write back.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Bucketing -- coarse-grain a feature dict so similar contexts hash equally.
# ---------------------------------------------------------------------------

# Feature bucket grids. Tuned conservatively: too coarse and we cache wrong
# verdicts across genuinely different situations; too fine and hit rate
# collapses. These grids are the result of operator-experience tuning.
_FLOAT_GRIDS: dict[str, float] = {
    # Continuous 0..1 features rounded to 0.05 (20 buckets).
    "stress_composite":       0.05,
    "sizing_mult":            0.10,
    "doctrine_net_bias":      0.10,
    # Continuous unbounded features rounded to 0.5 (R-at-risk steps).
    "r_at_risk":              0.5,
    # hours_until_event handled separately (sparse bucketing).
}

_INT_BINS: dict[str, list[int]] = {
    # operator_overrides_24h binned to (0, 1-2, 3-4, 5+)
    "operator_overrides_24h": [0, 1, 3, 5],
    # precedent_n binned to (0, 1-10, 11-50, 51+)
    "precedent_n":            [0, 1, 11, 51],
}

# How long a cached verdict is valid by regime (more volatile = shorter).
_TTL_BY_REGIME: dict[str, int] = {
    "CRISIS":  300,    # 5 minutes -- conditions change fast
    "STRESS":  900,    # 15 minutes
    "NEUTRAL": 3600,   # 1 hour -- default
    "CALM":    7200,   # 2 hours
}
_DEFAULT_TTL = 3600  # 1 hour


def _bucket_float(name: str, value: float) -> str:
    """Snap a float to its bucket grid; format with the grid's precision."""
    grid = _FLOAT_GRIDS.get(name)
    if grid is None:
        # Unknown float feature -- coarse default of 0.1 to be safe.
        grid = 0.1
    snapped = round(value / grid) * grid
    # Format with enough precision to disambiguate adjacent buckets.
    decimals = max(0, len(str(grid).split(".")[-1])) if "." in str(grid) else 0
    return f"{snapped:.{decimals}f}"


def _bucket_int(name: str, value: int) -> str:
    """Bin an int to the largest threshold it meets."""
    bins = _INT_BINS.get(name)
    if bins is None:
        return str(value)  # use as-is
    chosen = 0
    for b in bins:
        if value >= b:
            chosen = b
    return f"{chosen}+"


def _bucket_hours_until_event(value: float | None) -> str:
    """Sparse bucketing for event proximity."""
    if value is None:
        return "none"
    if value <= 1.0:
        return "imminent"   # <= 1h
    if value <= 4.0:
        return "near"       # 1-4h
    if value <= 24.0:
        return "today"      # 4-24h
    return "later"


def bucket_features(features: dict[str, Any]) -> dict[str, str]:
    """Reduce a feature dict to coarse string buckets -- ready to hash.

    The output is JSON-stable: same input dict produces identical buckets
    regardless of key order. Unknown fields are passed through as-is so
    new features don't silently get ignored.
    """
    out: dict[str, str] = {}
    for k, v in features.items():
        if k == "hours_until_event":
            out[k] = _bucket_hours_until_event(v)
        elif isinstance(v, bool):
            out[k] = "1" if v else "0"
        elif isinstance(v, (int,)) and not isinstance(v, bool):
            out[k] = _bucket_int(k, v)
        elif isinstance(v, float):
            out[k] = _bucket_float(k, v)
        elif v is None:
            out[k] = "none"
        else:
            out[k] = str(v)
    return out


def hash_features(features: dict[str, Any]) -> str:
    """SHA-256 hex digest of bucketed features (12-char prefix is enough)."""
    bucketed = bucket_features(features)
    # Sort keys so the hash is order-independent.
    canonical = "|".join(f"{k}={bucketed[k]}" for k in sorted(bucketed))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Cache entry + cache itself
# ---------------------------------------------------------------------------


class CachedVerdict(BaseModel):
    """One cached entry."""
    model_config = ConfigDict(frozen=True)

    feature_hash: str = Field(min_length=8)
    final_vote:   str = Field(min_length=1)
    route:        str = ""
    stakes:       str = ""
    note:         str = ""
    cached_at:    datetime
    expires_at:   datetime


class VerdictCache:
    """In-memory verdict cache with regime-aware TTL.

    Not threadsafe -- the dispatcher is single-threaded by design. If
    that ever changes, wrap reads/writes in a lock.

    Persistence is left to the caller: ``snapshot()`` / ``restore()``
    let the daemon save state across restarts.
    """

    def __init__(self) -> None:
        self._store: dict[str, CachedVerdict] = {}
        # Stats for the dashboard.
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # --- core API ----------------------------------------------------------

    def get(
        self, features: dict[str, Any], *, now: datetime | None = None,
    ) -> CachedVerdict | None:
        """Return a cached verdict if one is fresh; else ``None``.

        Also evicts stale entries opportunistically when they're hit.
        """
        now = now or datetime.now(UTC)
        key = hash_features(features)
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at <= now:
            # Stale -- evict and report a miss.
            del self._store[key]
            self.evictions += 1
            self.misses += 1
            return None
        self.hits += 1
        return entry

    def put(
        self,
        features: dict[str, Any],
        *,
        final_vote: str,
        route: str = "",
        stakes: str = "",
        note: str = "",
        now: datetime | None = None,
        ttl_seconds: int | None = None,
    ) -> CachedVerdict:
        """Insert or replace a verdict for the bucketed feature shape.

        TTL is regime-aware: CRISIS = 5m, NEUTRAL = 1h, etc. Caller can
        override with ``ttl_seconds``.
        """
        now = now or datetime.now(UTC)
        if ttl_seconds is None:
            regime = str(features.get("regime", "NEUTRAL")).upper()
            ttl_seconds = _TTL_BY_REGIME.get(regime, _DEFAULT_TTL)
        key = hash_features(features)
        entry = CachedVerdict(
            feature_hash=key,
            final_vote=final_vote,
            route=route,
            stakes=stakes,
            note=note,
            cached_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self._store[key] = entry
        return entry

    # --- maintenance -------------------------------------------------------

    def prune(self, *, now: datetime | None = None) -> int:
        """Drop expired entries. Returns the count evicted."""
        now = now or datetime.now(UTC)
        stale = [k for k, e in self._store.items() if e.expires_at <= now]
        for k in stale:
            del self._store[k]
        self.evictions += len(stale)
        return len(stale)

    # --- observability -----------------------------------------------------

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return round(self.hits / total, 4)

    def stats(self) -> dict[str, int | float]:
        return {
            "size":      len(self._store),
            "hits":      self.hits,
            "misses":    self.misses,
            "evictions": self.evictions,
            "hit_rate":  self.hit_rate(),
        }

    # --- persistence -------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        return {
            "entries": [e.model_dump(mode="json") for e in self._store.values()],
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Replace state from a previous snapshot."""
        self._store.clear()
        for raw in data.get("entries", []):
            entry = CachedVerdict.model_validate(raw)
            self._store[entry.feature_hash] = entry
        self.hits = int(data.get("hits", 0))
        self.misses = int(data.get("misses", 0))
        self.evictions = int(data.get("evictions", 0))


__all__ = [
    "CachedVerdict",
    "VerdictCache",
    "bucket_features",
    "hash_features",
]
