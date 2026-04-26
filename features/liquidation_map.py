"""APEX PREDATOR  //  features.liquidation_map
==================================================
Liquidation heatmap surface used by the Crowd Pain Index and any
strategy that hunts forced-flow zones.

A heatmap is a tuple of clusters. Each cluster is a price band where a
material amount of leveraged notional sits at risk of liquidation. The
side tag tells you which way the unwind would push price (longs liq'ing
sells; shorts liq'ing buys).

This module is pure data shape -- the actual heatmap synthesis (from
exchange OI maps + leverage histograms) lives in the Bybit/Bitget feed
adapters; the rest of the codebase only depends on the dataclass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

LiqSide = Literal["long", "short"]


@dataclass(frozen=True)
class LiquidationCluster:
    price: float
    side: LiqSide
    notional_usd: float
    leverage_avg: float


@dataclass(frozen=True)
class LiquidationHeatmap:
    timestamp: datetime
    symbol: str
    clusters: tuple[LiquidationCluster, ...]


__all__ = [
    "LiqSide",
    "LiquidationCluster",
    "LiquidationHeatmap",
]
