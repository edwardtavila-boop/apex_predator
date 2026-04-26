"""APEX PREDATOR  //  features.crowd_pain_index
====================================================
Composite signal for trades that profit when the crowd's leveraged
position is forced to unwind.

Five components, each scored to [0, 1]:

    1. ``funding_pressure_aligned`` -- recent funding extreme on the
       opposite side of our intended bias (we short into long crowd).
    2. ``oi_price_divergence``      -- OI spiking while price moves the
       opposite direction (signature of late add).
    3. ``liq_cluster_proximity``    -- a material liquidation cluster
       within a couple of ATR of current price.
    4. ``taker_pressure_zscore``    -- taker buy/sell ratio z-score
       against the recent window.
    5. ``taker_flow_size``          -- the most-recent taker flow USD
       crossed a notional threshold.

The CPI score is the simple mean of the five components, scaled to
[0, 100]. The :func:`cpi_signals_trade` gate adds a "minimum number of
components above 0.7" floor so a single freak signal doesn't trigger.

Trap-regime relaxation: in a TRAP regime the threshold drops by 10
points because the priors are skewed in our favour even before the CPI
fires.

Composite weight in the confluence scorer is 2.0 (double the typical
feature) since CPI fires rarely but with high information content.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from apex_predator.features.base import Feature

if TYPE_CHECKING:
    from collections.abc import Sequence

    from apex_predator.core.data_pipeline import BarData, FundingRate
    from apex_predator.features.liquidation_map import LiquidationHeatmap


_COMPONENT_NAMES: tuple[str, ...] = (
    "funding_pressure_aligned",
    "oi_price_divergence",
    "liq_cluster_proximity",
    "taker_pressure_zscore",
    "taker_flow_size",
)
_NORMAL_THRESHOLD: float = 70.0
_TRAP_RELAXATION: float = 10.0
_COMPONENTS_ABOVE_FLOOR: int = 3
_COMPONENT_PASS: float = 0.7


@dataclass
class CPIBreakdown:
    components: dict[str, float] = field(default_factory=dict)
    cpi_score: float = 0.0
    components_above_07: int = 0


def _funding_pressure(
    funding_history: Sequence[FundingRate] | None,
    bias: int,
) -> float:
    """Score 1.0 if the latest 8h cumulative funding is contrarian-aligned
    with our bias and at or above the 0.002 (20bp / 8h) extreme threshold.

    bias > 0 means we're long, so we want funding NEGATIVE (crowd short).
    bias < 0 means we're short, so we want funding POSITIVE (crowd long).
    """
    if not funding_history or bias == 0:
        return 0.0
    recent = list(funding_history)[-8:]
    cum = sum(f.rate for f in recent)
    if bias > 0 and cum >= 0:
        return 0.0
    if bias < 0 and cum <= 0:
        return 0.0
    magnitude = abs(cum)
    return min(1.0, magnitude / 0.002)


def _oi_price_divergence(
    oi_history: Sequence[float] | None,
    price_history: Sequence[float] | None,
) -> float:
    """High score when OI z-score is large AND price moved opposite."""
    if not oi_history or not price_history:
        return 0.0
    if len(oi_history) < 10 or len(price_history) < 10:
        return 0.0
    prior_oi = list(oi_history)[:-1]
    latest_oi = oi_history[-1]
    try:
        oi_mean = statistics.fmean(prior_oi)
        oi_std = statistics.stdev(prior_oi)
    except statistics.StatisticsError:
        return 0.0
    if oi_std <= 0.0:
        return 0.0
    oi_z = (latest_oi - oi_mean) / oi_std
    if oi_z <= 0.0:
        return 0.0

    # Last bar's price move sign vs the OI add direction.
    price_move = price_history[-1] - price_history[-2]
    if price_move >= 0.0:
        return 0.0  # not a divergence -- OI up + price up = trend chase, not trap

    z_strength = min(1.0, oi_z / 5.0)  # saturate at z=5
    return z_strength


def _liq_proximity(
    heatmap: LiquidationHeatmap | None,
    price: float,
    atr: float,
) -> float:
    """1.0 if a cluster sits within 1 ATR; falls off linearly to 0 at 3 ATR."""
    if heatmap is None or atr <= 0.0 or not heatmap.clusters:
        return 0.0
    nearest_dist = min(abs(c.price - price) for c in heatmap.clusters)
    ratio = nearest_dist / atr
    if ratio <= 1.0:
        return 1.0
    if ratio >= 3.0:
        return 0.0
    return 1.0 - (ratio - 1.0) / 2.0


def _taker_pressure_zscore(taker_ratios: Sequence[float] | None) -> float:
    """Z-score saturated at 4 sigma."""
    if not taker_ratios or len(taker_ratios) < 30:
        return 0.0
    prior = list(taker_ratios)[:-1]
    latest = taker_ratios[-1]
    try:
        mean = statistics.fmean(prior)
        stdev = statistics.stdev(prior)
    except statistics.StatisticsError:
        return 0.0
    if stdev <= 0.0:
        return 0.0
    z = abs(latest - mean) / stdev
    return min(1.0, z / 4.0)


def _taker_flow_size(last_flow_usd: float | None) -> float:
    """Linear ramp 0 -> 1 between $1M and $10M last-bar taker flow."""
    if last_flow_usd is None or last_flow_usd <= 0.0:
        return 0.0
    if last_flow_usd <= 1_000_000.0:
        return 0.0
    if last_flow_usd >= 10_000_000.0:
        return 1.0
    return (last_flow_usd - 1_000_000.0) / 9_000_000.0


def compute_cpi(bar: BarData, ctx: dict[str, Any]) -> CPIBreakdown:
    """Build a :class:`CPIBreakdown` from the available context inputs."""
    funding = _funding_pressure(
        ctx.get("funding_history"),
        int(ctx.get("bias", 0) or 0),
    )
    oi_div = _oi_price_divergence(
        ctx.get("oi_history"),
        ctx.get("price_history"),
    )
    liq_prox = _liq_proximity(
        ctx.get("liq_heatmap"),
        bar.close,
        float(ctx.get("atr", 0.0) or 0.0),
    )
    taker_z = _taker_pressure_zscore(ctx.get("taker_ratio_history"))
    taker_flow = _taker_flow_size(ctx.get("taker_last_flow_usd"))

    components = {
        "funding_pressure_aligned": funding,
        "oi_price_divergence":      oi_div,
        "liq_cluster_proximity":    liq_prox,
        "taker_pressure_zscore":    taker_z,
        "taker_flow_size":          taker_flow,
    }
    above = sum(1 for v in components.values() if v >= _COMPONENT_PASS)
    score = sum(components.values()) / len(_COMPONENT_NAMES) * 100.0
    return CPIBreakdown(
        components=components,
        cpi_score=score,
        components_above_07=above,
    )


def cpi_signals_trade(
    breakdown: CPIBreakdown,
    *,
    regime_is_trap: bool = False,
) -> bool:
    """Trade gate. Requires components_above_07 >= 3 AND cpi_score above
    the (regime-adjusted) threshold."""
    if breakdown.components_above_07 < _COMPONENTS_ABOVE_FLOOR:
        return False
    threshold = _NORMAL_THRESHOLD - (_TRAP_RELAXATION if regime_is_trap else 0.0)
    return breakdown.cpi_score >= threshold


class CrowdPainIndexFeature(Feature):
    """Confluence-pipeline wrapper. Stashes ``last_breakdown`` for telemetry."""

    name = "crowd_pain_index"
    weight = 2.0

    def __init__(self) -> None:
        self.last_breakdown: CPIBreakdown | None = None

    def compute(self, bar: BarData, ctx: dict[str, Any]) -> float:
        breakdown = compute_cpi(bar, ctx)
        self.last_breakdown = breakdown
        return breakdown.cpi_score / 100.0


__all__ = [
    "CPIBreakdown",
    "CrowdPainIndexFeature",
    "compute_cpi",
    "cpi_signals_trade",
]
