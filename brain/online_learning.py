"""Online learning hook for bots (Tier-4 #13, 2026-04-27).

SCAFFOLD: defines the contract for a bot to update its internal belief
mid-session as fills come back. Each bot already has a
``_refresh_runtime_throttle`` style hook; this module provides the
shared interface so the per-bot update logic is consistent.

Pattern::

    from eta_engine.brain.online_learning import OnlineUpdater

    class MyBot(BaseBot):
        def __init__(self, ..., online_updater: OnlineUpdater | None = None):
            ...
            self._online = online_updater or OnlineUpdater(bot_name=self.config.name)

        def on_fill(self, fill: Fill, *, intent: ActionType, confluence: float) -> None:
            super().on_fill(fill)
            # Feed the realized P&L of the trade back to the updater.
            r_multiple = self._compute_r_multiple(fill)
            self._online.observe(
                feature_bucket=f"confluence_{int(confluence)}",
                r_multiple=r_multiple,
            )
            # Subsequent _refresh_runtime_throttle() reads the updated
            # priors via online_updater.expected_r(feature_bucket).

This is intentionally a thin EWMA tracker, not a full RL pipeline. The
goal is to capture "are setups in confluence-bucket-7 still working
as well as they did in walk-forward?" -- a slow regime-shift detector
keyed off realized R-multiples.

Status: SCAFFOLD with tests; per-bot wiring pending.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Mapping

logger = logging.getLogger(__name__)


@dataclass
class _BucketStats:
    n: int = 0
    ewma_r: float = 0.0
    ewma_alpha: float = 0.10  # how fast to forget old samples (~10 trades half-life)


class OnlineUpdater:
    """Per-bot online tracker for realized R-multiples by feature bucket.

    Backward-compatible: when not used, the bot behaves exactly as before.
    Forward-compatible: when wired, the bot's sizing/throttle logic can
    multiply size by ``expected_r(bucket)`` to lean into hot buckets and
    fade cold ones.
    """

    def __init__(self, *, bot_name: str = "unknown", alpha: float = 0.10) -> None:
        self.bot_name = bot_name
        self._buckets: dict[str, _BucketStats] = {}
        self.alpha = alpha

    def observe(self, *, feature_bucket: str, r_multiple: float) -> None:
        """Record a realized R-multiple for a (bucket) and update the EWMA.

        ``r_multiple`` should be expressed as a multiple of risk:
        ``+1.0`` = winner of size = the configured stop distance,
        ``-1.0`` = loser stopped at the stop, ``0.0`` = scratch.
        """
        b = self._buckets.setdefault(feature_bucket, _BucketStats(ewma_alpha=self.alpha))
        b.n += 1
        if b.n == 1:
            b.ewma_r = r_multiple
        else:
            b.ewma_r = (b.ewma_alpha * r_multiple) + ((1.0 - b.ewma_alpha) * b.ewma_r)

    def expected_r(self, feature_bucket: str) -> float:
        """Return the current EWMA R-multiple for a bucket, or 0.0 if unseen."""
        b = self._buckets.get(feature_bucket)
        return b.ewma_r if b else 0.0

    def confidence(self, feature_bucket: str) -> int:
        """Sample count for the bucket (proxy for confidence)."""
        b = self._buckets.get(feature_bucket)
        return b.n if b else 0

    def snapshot(self) -> Mapping[str, dict[str, float]]:
        return {
            bucket: {"n": float(s.n), "ewma_r": round(s.ewma_r, 4), "alpha": s.ewma_alpha}
            for bucket, s in self._buckets.items()
        }
