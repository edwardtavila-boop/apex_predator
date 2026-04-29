"""Pure value objects for the ETA retrospective loop.

The live bots intentionally keep retrospective wiring optional. These
dataclasses give every bot a stable, importable contract without introducing
I/O, background tasks, or policy mutation at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eta_engine.strategies.adaptive_sizing import RegimeLabel
    from eta_engine.strategies.models import StrategyId


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    """One closed trade, normalized into R units for retrospective analysis."""

    strategy: StrategyId
    regime: RegimeLabel
    pnl_r: float
    equity_after: float
    closed_at_utc: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class RetrospectiveReport:
    """Actionable summary emitted when the retrospective loop sees stress."""

    trigger: str
    summary: str
    n_trades: int
    cumulative_pnl_r: float
    consecutive_losses: int
    current_equity: float
    high_water_equity: float
    drawdown_r: float
    strategy: StrategyId | None = None
    regime: RegimeLabel | None = None
    generated_at_utc: datetime = field(default_factory=_utc_now)


__all__ = [
    "RetrospectiveReport",
    "TradeOutcome",
]
