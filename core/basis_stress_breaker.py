"""APEX PREDATOR  //  core.basis_stress_breaker
====================================================
L3 funding-arbitrage emergency-exit gate.

The basis trade (long perp / short spot, or vice versa) is delta-neutral
in normal regimes. But it has six tail-risk failure modes where holding
the trade is strictly worse than flattening:

    1. Either venue unreachable -- can't manage the leg we still have.
    2. Stablecoin depeg          -- USD denomination is wrong; "neutral"
                                    is a lie until peg restores.
    3. Perp margin critical      -- liquidation incoming on the perp leg.
    4. Spot margin critical      -- liquidation incoming on the spot leg.
    5. Basis magnitude > N%      -- the cross-venue spread is so wide
                                    that holding loses to a forced re-hedge.
    6. Basis z-score > N         -- regime shift detected; historical
                                    correlation no longer applies.

Priority is fixed (top to bottom): unreachability beats depeg beats
margin beats basis. The first reason found wins; later checks are not
evaluated. This is intentional -- if we can't reach perp venue, the
margin readings on it are stale anyway.

This module is pure policy. It returns a StressDecision; the runtime
acts on it.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import StrEnum


class StressAction(StrEnum):
    HOLD = "HOLD"
    ALERT_ONLY = "ALERT_ONLY"
    FLATTEN_PERP_ONLY = "FLATTEN_PERP_ONLY"
    FLATTEN_SPOT_ONLY = "FLATTEN_SPOT_ONLY"
    FLATTEN_BOTH = "FLATTEN_BOTH"


class StressReason(StrEnum):
    NONE = "NONE"
    EXCHANGE_UNREACHABLE = "EXCHANGE_UNREACHABLE"
    STABLECOIN_DEPEG = "STABLECOIN_DEPEG"
    PERP_MARGIN_CRITICAL = "PERP_MARGIN_CRITICAL"
    SPOT_MARGIN_CRITICAL = "SPOT_MARGIN_CRITICAL"
    BASIS_MAGNITUDE = "BASIS_MAGNITUDE"
    BASIS_ZSCORE = "BASIS_ZSCORE"


@dataclass(frozen=True)
class BasisSnapshot:
    """Per-tick state of the funding-arb pair."""
    perp_mid: float
    spot_mid: float
    perp_margin_distance_usd: float    # USD until liquidation on perp leg
    spot_margin_distance_usd: float    # USD until liquidation on spot leg
    perp_notional_usd: float
    spot_notional_usd: float
    basis_history_bps: tuple[float, ...]   # rolling history of (perp-spot)/spot in bps
    stablecoin_peg: float = 1.0            # observed USD per 1 unit of quote stable
    perp_venue_reachable: bool = True
    spot_venue_reachable: bool = True


@dataclass(frozen=True)
class BasisStressPolicy:
    """Configurable thresholds. Defaults match the funding-arb runbook."""
    margin_floor_ratio: float = 0.15           # margin_distance / notional
    stablecoin_peg_floor: float = 0.985        # below this -> depeg
    basis_stress_threshold_pct: float = 0.03   # |perp-spot|/spot above this -> trip
    basis_zscore_threshold: float = 4.0
    basis_zscore_min_samples: int = 30


@dataclass(frozen=True)
class StressDecision:
    action: StressAction
    reason: StressReason
    evidence: dict[str, float] = field(default_factory=dict)


_DEFAULT_POLICY = BasisStressPolicy()


def evaluate_basis_stress(
    snap: BasisSnapshot,
    *,
    policy: BasisStressPolicy = _DEFAULT_POLICY,
) -> StressDecision:
    """Evaluate the snapshot against policy. First-trip-wins priority."""
    # Priority 1: venue reachability.
    if not snap.perp_venue_reachable and not snap.spot_venue_reachable:
        return StressDecision(
            action=StressAction.ALERT_ONLY,
            reason=StressReason.EXCHANGE_UNREACHABLE,
            evidence={"perp_reachable": 0.0, "spot_reachable": 0.0},
        )
    if not snap.perp_venue_reachable:
        return StressDecision(
            action=StressAction.FLATTEN_SPOT_ONLY,
            reason=StressReason.EXCHANGE_UNREACHABLE,
            evidence={"perp_reachable": 0.0, "spot_reachable": 1.0},
        )
    if not snap.spot_venue_reachable:
        return StressDecision(
            action=StressAction.FLATTEN_PERP_ONLY,
            reason=StressReason.EXCHANGE_UNREACHABLE,
            evidence={"perp_reachable": 1.0, "spot_reachable": 0.0},
        )

    # Priority 2: stablecoin peg. USD denomination broken.
    if snap.stablecoin_peg < policy.stablecoin_peg_floor:
        return StressDecision(
            action=StressAction.FLATTEN_BOTH,
            reason=StressReason.STABLECOIN_DEPEG,
            evidence={
                "stablecoin_peg": snap.stablecoin_peg,
                "floor": policy.stablecoin_peg_floor,
            },
        )

    # Priority 3: margin distance on each leg.
    perp_ratio = (
        snap.perp_margin_distance_usd / snap.perp_notional_usd
        if snap.perp_notional_usd > 0 else 1.0
    )
    if perp_ratio < policy.margin_floor_ratio:
        return StressDecision(
            action=StressAction.FLATTEN_BOTH,
            reason=StressReason.PERP_MARGIN_CRITICAL,
            evidence={
                "perp_margin_ratio": perp_ratio,
                "floor": policy.margin_floor_ratio,
            },
        )
    spot_ratio = (
        snap.spot_margin_distance_usd / snap.spot_notional_usd
        if snap.spot_notional_usd > 0 else 1.0
    )
    if spot_ratio < policy.margin_floor_ratio:
        return StressDecision(
            action=StressAction.FLATTEN_BOTH,
            reason=StressReason.SPOT_MARGIN_CRITICAL,
            evidence={
                "spot_margin_ratio": spot_ratio,
                "floor": policy.margin_floor_ratio,
            },
        )

    # Priority 4: basis magnitude.
    if snap.spot_mid > 0:
        basis_pct = abs(snap.perp_mid - snap.spot_mid) / snap.spot_mid
        if basis_pct > policy.basis_stress_threshold_pct:
            return StressDecision(
                action=StressAction.FLATTEN_BOTH,
                reason=StressReason.BASIS_MAGNITUDE,
                evidence={
                    "basis_pct": basis_pct,
                    "threshold_pct": policy.basis_stress_threshold_pct,
                },
            )

    # Priority 5: basis z-score against rolling history.
    history = snap.basis_history_bps
    if len(history) >= policy.basis_zscore_min_samples:
        prior = history[:-1]
        latest = history[-1]
        try:
            mean = statistics.fmean(prior)
            stdev = statistics.stdev(prior)
        except statistics.StatisticsError:
            stdev = 0.0
            mean = 0.0
        if stdev > 0.0:
            z = abs(latest - mean) / stdev
            if z > policy.basis_zscore_threshold:
                return StressDecision(
                    action=StressAction.FLATTEN_BOTH,
                    reason=StressReason.BASIS_ZSCORE,
                    evidence={
                        "z_score": z,
                        "threshold": policy.basis_zscore_threshold,
                    },
                )

    return StressDecision(
        action=StressAction.HOLD,
        reason=StressReason.NONE,
    )
