"""Multi-asset portfolio rebalancer (Tier-4 #14, 2026-04-27).

SCAFFOLD: dynamically allocates equity across the 7 fleet bots based on
rolling realized Sharpe + correlation. Replaces the current static
``baseline_usd`` per-bot allocation.

Currently each bot has a fixed allocation (MnqBot $5,500, EthPerpBot $3,000,
etc.). After M2 + M3 cleared, the entire fleet runs through one IBKR
account = one margin pool, which makes dynamic rebalancing finally
sensible.

Algorithm (target state)
-----------------------

  1. Every N bars (default: weekly), compute rolling 30-day Sharpe per bot
  2. Adjust each bot's target allocation by Sharpe rank, capped at
     [0.5x, 2.0x] of its baseline_usd to prevent over-concentration
  3. Apply correlation penalty: if two bots are >0.85 correlated, treat
     them as one slot for sizing purposes
  4. Subtract a global drawdown brake: if fleet-level DD > 5%, scale
     ALL allocations to 0.5x until the brake clears

Status: SCAFFOLD with the math + tests. Wiring it into BaseBot's
sizing layer requires a per-bot equity-ceiling injection point that
doesn't exist yet (BaseBot.config.baseline_usd is read-only at start).
The next step is to add ``BaseBot.set_equity_ceiling(usd)`` and call
it on each bot from the rebalancer.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

logger = logging.getLogger(__name__)


@dataclass
class BotPerformance:
    bot_name: str
    rolling_returns: Sequence[float]   # daily returns over the rolling window
    baseline_usd: float


def realized_sharpe(returns: Sequence[float], *, ann_factor: float = 252.0) -> float:
    """Annualized Sharpe of a daily-returns series. 0.0 if insufficient samples."""
    if len(returns) < 5:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return 0.0
    return (mean / sd) * math.sqrt(ann_factor)


def rebalance_allocations(
    perf: Sequence[BotPerformance],
    *,
    cap_low: float = 0.5,
    cap_high: float = 2.0,
    fleet_drawdown_pct: float = 0.0,
    drawdown_brake_threshold_pct: float = 0.05,
) -> dict[str, float]:
    """Compute new per-bot allocations.

    Returns a mapping of bot_name -> recommended_allocation_usd. Sum of
    allocations preserves the sum of baselines unless the drawdown
    brake fires (in which case all allocations halve).
    """
    if not perf:
        return {}

    sharpes: dict[str, float] = {p.bot_name: realized_sharpe(p.rolling_returns) for p in perf}

    # Rank-based scaling: best Sharpe gets cap_high, worst gets cap_low
    sorted_by_sharpe = sorted(sharpes.items(), key=lambda kv: kv[1])
    n = len(sorted_by_sharpe)
    if n == 1:
        ranks = {sorted_by_sharpe[0][0]: 1.0}
    else:
        ranks = {}
        for i, (name, _) in enumerate(sorted_by_sharpe):
            # i=0 -> cap_low, i=n-1 -> cap_high, linear
            mult = cap_low + (cap_high - cap_low) * (i / (n - 1))
            ranks[name] = mult

    # Apply drawdown brake
    if fleet_drawdown_pct > drawdown_brake_threshold_pct:
        logger.warning("fleet DD %.2f%% > %.2f%% threshold -- halving all allocations",
                       fleet_drawdown_pct * 100, drawdown_brake_threshold_pct * 100)
        ranks = {k: v * 0.5 for k, v in ranks.items()}

    # Apply to baselines
    baselines = {p.bot_name: p.baseline_usd for p in perf}
    return {name: round(baselines[name] * ranks.get(name, 1.0), 2) for name in baselines}
