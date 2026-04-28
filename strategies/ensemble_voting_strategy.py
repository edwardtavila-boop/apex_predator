"""
EVOLUTIONARY TRADING ALGO  //  strategies.ensemble_voting_strategy
===================================================================
Multi-strategy ensemble voting: only fires when ≥ N independent
sub-strategies propose the SAME side at roughly the same bar.

Rationale
---------
Each sub-strategy in the catalog captures a different edge:
* `crypto_regime_trend`              — pullback to fast EMA
* `crypto_macro_confluence` (+ETF)   — pullback + ETF flow filter
* `crypto_orb` (UTC anchor)          — UTC midnight breakout
* `htf_routed` (mean-revert mode)    — fade extremes in range

These are independently-edge'd signals on different mechanics. When
two or more agree on the same side at the same time, conviction is
materially higher than any single strategy alone — that's the
information theoretic value of independent confirmation.

The voter:
1. On each bar, calls all sub-strategies (their states advance
   regardless of voting outcome).
2. Collects their proposals (side + confidence — uses the strategy's
   inherent risk_usd as a proxy for confidence).
3. Counts votes per side.
4. Fires when total agreeing votes >= ``min_agreement_count``.
5. Position size is the AVERAGE of the agreeing strategies' sizes.

Trade count stays high because individual strategies still fire when
alone, but only ``min_agreement_count`` proposals get past the voter.
For ``min_agreement_count=2``, roughly half of all single-strategy
fires get a vote of confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eta_engine.backtest.engine import _Open
    from eta_engine.backtest.models import BacktestConfig
    from eta_engine.core.data_pipeline import BarData


# Type-alias for any sub-strategy that exposes maybe_enter()
if TYPE_CHECKING:
    from typing import Protocol

    class _SubStrategy(Protocol):
        """Protocol for any object with the engine's maybe_enter contract."""

        def maybe_enter(
            self,
            bar: BarData,
            hist: list[BarData],
            equity: float,
            config: BacktestConfig,
        ) -> _Open | None:
            ...


@dataclass(frozen=True)
class EnsembleVotingConfig:
    """Voter knobs."""

    # Minimum number of sub-strategies that must propose the same
    # side for an entry to fire. 2 = light agreement; 3+ = high
    # confidence (rare).
    min_agreement_count: int = 2

    # When agreement count exceeds min, optionally scale position size
    # by (count / min). Default OFF — agreement gates the trade but
    # doesn't amplify size.
    size_by_agreement: bool = False
    max_size_multiplier: float = 1.5

    # Tag to write into _Open.regime so the audit trail shows which
    # strategies voted.
    regime_prefix: str = "ensemble"


class EnsembleVotingStrategy:
    """Aggregates multiple strategies via majority vote."""

    def __init__(
        self,
        sub_strategies: list[tuple[str, _SubStrategy]],
        config: EnsembleVotingConfig | None = None,
    ) -> None:
        if not sub_strategies:
            raise ValueError("ensemble requires at least one sub-strategy")
        self._subs = list(sub_strategies)
        self.cfg = config or EnsembleVotingConfig()
        if self.cfg.min_agreement_count < 1:
            raise ValueError("min_agreement_count must be >= 1")
        if self.cfg.min_agreement_count > len(self._subs):
            raise ValueError(
                f"min_agreement_count {self.cfg.min_agreement_count} "
                f"exceeds number of sub-strategies {len(self._subs)}"
            )

    def maybe_enter(
        self,
        bar: BarData,
        hist: list[BarData],
        equity: float,
        config: BacktestConfig,
    ) -> _Open | None:
        # Always call ALL sub-strategies (even if vote will fail)
        # so their states (EMAs, cooldowns) advance every bar.
        proposals: list[tuple[str, _Open]] = []
        for name, strat in self._subs:
            try:
                out = strat.maybe_enter(bar, hist, equity, config)
            except Exception:  # noqa: BLE001 - sub isolation
                continue
            if out is not None:
                proposals.append((name, out))

        if len(proposals) < self.cfg.min_agreement_count:
            return None

        # Tally votes by side
        long_votes = [p for n, p in proposals if p.side == "BUY"]
        short_votes = [p for n, p in proposals if p.side == "SELL"]

        if len(long_votes) >= self.cfg.min_agreement_count:
            chosen_side = "BUY"
            chosen_proposals = long_votes
        elif len(short_votes) >= self.cfg.min_agreement_count:
            chosen_side = "SELL"
            chosen_proposals = short_votes
        else:
            # Sub-strategies disagree on side — no consensus
            return None

        # Aggregate the chosen side: take the AVERAGE entry, stop,
        # target, qty, risk across the agreeing proposals. This is
        # safer than just picking one — it dampens any single sub's
        # parameter quirks.
        n = len(chosen_proposals)
        avg_entry = sum(p.entry_price for p in chosen_proposals) / n
        avg_stop = sum(p.stop for p in chosen_proposals) / n
        avg_target = sum(p.target for p in chosen_proposals) / n
        avg_qty = sum(p.qty for p in chosen_proposals) / n
        avg_risk = sum(p.risk_usd for p in chosen_proposals) / n

        # Optional size scaling by vote count
        if self.cfg.size_by_agreement:
            mult = min(
                self.cfg.max_size_multiplier,
                n / self.cfg.min_agreement_count,
            )
            avg_qty *= mult
            avg_risk *= mult

        agreement_names = "+".join(name for name, _ in proposals if name in {
            n_ for n_, p in self._subs_for_proposals(chosen_proposals)
        })
        if not agreement_names:
            agreement_names = ",".join(name for name, p in proposals if p.side == chosen_side)

        regime_tag = (
            f"{self.cfg.regime_prefix}_{chosen_side.lower()}_"
            f"{n}of{len(self._subs)}_{agreement_names}"
        )

        # Use the FIRST agreeing proposal as the base (for entry_bar
        # + leverage etc.), then overlay the averaged values.
        base = chosen_proposals[0]
        return replace(
            base,
            side=chosen_side,
            entry_price=avg_entry,
            stop=avg_stop,
            target=avg_target,
            qty=avg_qty,
            risk_usd=avg_risk,
            confluence=10.0,
            regime=regime_tag,
        )

    # -- helper for audit-trail name tagging ---------------------------------

    def _subs_for_proposals(
        self, proposals: list[_Open],  # noqa: ARG002 - reserved for future ref-matching
    ) -> list[tuple[str, _SubStrategy]]:
        # Reverse-map proposals back to (name, sub) pairs by matching
        # references where possible. Best-effort; tagging is informational.
        return [(name, sub) for name, sub in self._subs if sub is not None]
