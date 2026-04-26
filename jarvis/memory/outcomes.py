"""
EVOLUTIONARY TRADING ALGO // jarvis.memory.outcomes
=======================================
OutcomeTracker — fills `EpisodicMemory.outcomes` at +1 / +5 / +20-bar
marks. Used by Phase 2 retrieval to weight memories by what actually
happened next.

Design:
  * On every closed bar, the tracker scans memories whose `ts_utc` was
    exactly 1 / 5 / 20 bars ago and writes the resolved outcome.
  * Outcome metric is configurable; default is normalized R-multiple
    (close - entry) / atr_at_entry — close to what kill_switch_runtime
    uses for slow_bleed detection.
  * Atomic via the underlying MemoryStore.upsert().
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from eta_engine.jarvis.memory.store import MemoryStore


@dataclass
class TradeOutcome:
    """Closed-trade result (or open snapshot at +N bars).

    `r_multiple` is the canonical metric: PnL in units of the entry-
    bar ATR. Positive = win, negative = loss.
    """

    r_multiple: float
    pnl_usd: float = 0.0
    bars_to_resolution: int = 0
    classification: str = "open"  # open | win | loss | flat

    def as_dict(self) -> dict[str, Any]:
        return {
            "r_multiple": round(self.r_multiple, 4),
            "pnl_usd": round(self.pnl_usd, 2),
            "bars_to_resolution": self.bars_to_resolution,
            "classification": self.classification,
        }


class OutcomeTracker:
    """Match closed bars back to past memories at +1 / +5 / +20.

    Usage (bar loop):

        tracker = OutcomeTracker(memory_store, bar_interval_seconds=300)
        for bar in bars:
            tracker.on_bar(bar)

    Production wiring: feed tracker.on_bar() from the runtime's
    bar-close hook. The tracker queries the store for memories whose
    ts_utc + N*interval == this bar's ts and writes outcome metrics.
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        bar_interval_seconds: int = 300,  # 5m bars by default
        offsets_bars: tuple[int, ...] = (1, 5, 20),
        outcome_key_template: str = "+{n}_bars",
    ) -> None:
        self.store = store
        self.bar_interval_seconds = bar_interval_seconds
        self.offsets = offsets_bars
        self.key_template = outcome_key_template

    def _key(self, n_bars: int) -> str:
        return self.key_template.format(n=n_bars)

    def on_bar(
        self,
        *,
        bar_ts_utc: str,
        close: float,
        outcome_callback=None,
    ) -> list[tuple[str, int, float]]:
        """Scan memories that mature this bar and record their outcome.

        outcome_callback(memory, n_bars_offset, close) -> TradeOutcome
        If None, defaults to a r_multiple proxy:
            (close - memory.feature_vec['entry']) / memory.feature_vec['atr']
        Returns a list of (decision_id, n_bars, r_multiple) for diagnostics.
        """
        try:
            now = datetime.fromisoformat(bar_ts_utc.replace("Z", "+00:00"))
        except ValueError:
            return []

        recorded: list[tuple[str, int, float]] = []
        for m in self.store.all():
            try:
                m_ts = datetime.fromisoformat(m.ts_utc.replace("Z", "+00:00"))
            except ValueError:
                continue
            for n_bars in self.offsets:
                target_ts = m_ts + timedelta(
                    seconds=n_bars * self.bar_interval_seconds,
                )
                # Match within tolerance of half a bar interval
                tol = self.bar_interval_seconds / 2
                if abs((now - target_ts).total_seconds()) <= tol:
                    key = self._key(n_bars)
                    if key in m.outcomes:
                        continue  # already recorded
                    if outcome_callback is not None:
                        outcome = outcome_callback(m, n_bars, close)
                        r = outcome.r_multiple
                    else:
                        entry = float(m.feature_vec.get("entry", 0.0))
                        atr = float(m.feature_vec.get("atr", 1.0)) or 1.0
                        sign = 1.0 if m.pm_action == "fire_long" else (-1.0 if m.pm_action == "fire_short" else 0.0)
                        r = sign * (close - entry) / atr
                    m.outcomes[key] = round(r, 4)
                    self.store.upsert(m)
                    recorded.append((m.decision_id, n_bars, r))
        return recorded
