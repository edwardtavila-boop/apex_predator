"""Small in-process retrospective manager for live bot wiring.

The manager is deliberately pure and synchronous: bots can feed closed trades
and bar equity snapshots without risking network, disk, or async failures in
the hot trading loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eta_engine.strategies.adaptive_sizing import PriorSuccessMetrics, RegimeLabel
from eta_engine.strategies.retrospective import RetrospectiveReport, TradeOutcome

if TYPE_CHECKING:
    from collections.abc import Iterable

    from eta_engine.strategies.models import StrategyId


class RetrospectiveManager:
    """Track recent outcomes and emit stress reports under cooldown."""

    def __init__(
        self,
        *,
        starting_equity: float,
        losing_streak_trigger: int = 3,
        drawdown_trigger_r: float = 3.0,
        cooldown_bars: int = 20,
        risk_unit_pct: float = 1.0,
        max_trades: int = 500,
    ) -> None:
        self.starting_equity = float(starting_equity)
        self.current_equity = float(starting_equity)
        self.high_water_equity = float(starting_equity)
        self.losing_streak_trigger = max(1, int(losing_streak_trigger))
        self.drawdown_trigger_r = max(0.0, float(drawdown_trigger_r))
        self.cooldown_bars = max(0, int(cooldown_bars))
        self.risk_unit_pct = max(0.0, float(risk_unit_pct))
        self.max_trades = max(1, int(max_trades))
        self.trades: list[TradeOutcome] = []
        self.reports: list[RetrospectiveReport] = []
        self.consecutive_losses = 0
        self.bars_since_report = self.cooldown_bars

    @property
    def cumulative_pnl_r(self) -> float:
        """Total realized R across retained trades."""

        return sum(trade.pnl_r for trade in self.trades)

    @property
    def drawdown_r(self) -> float:
        """Current equity drawdown converted to the configured risk unit."""

        risk_unit_usd = self.starting_equity * (self.risk_unit_pct / 100.0)
        if risk_unit_usd <= 0.0:
            return 0.0
        return max(0.0, (self.high_water_equity - self.current_equity) / risk_unit_usd)

    def on_bar(self, *, regime: RegimeLabel, equity: float) -> RetrospectiveReport | None:
        """Update equity context and emit a drawdown report if needed."""

        self.current_equity = float(equity)
        self.high_water_equity = max(self.high_water_equity, self.current_equity)
        self.bars_since_report += 1
        if self.drawdown_trigger_r <= 0.0:
            return None
        if self.drawdown_r < self.drawdown_trigger_r or not self._cooldown_ready():
            return None
        return self._emit_report(
            trigger="equity_drawdown",
            summary=f"Equity drawdown reached {self.drawdown_r:.2f}R.",
            strategy=None,
            regime=regime,
        )

    def record_trade(self, outcome: TradeOutcome) -> RetrospectiveReport | None:
        """Record one closed trade and emit a stress report when thresholds trip."""

        self.trades.append(outcome)
        if len(self.trades) > self.max_trades:
            self.trades = self.trades[-self.max_trades :]
        self.current_equity = float(outcome.equity_after)
        self.high_water_equity = max(self.high_water_equity, self.current_equity)
        self.consecutive_losses = self.consecutive_losses + 1 if outcome.pnl_r < 0.0 else 0

        if not self._cooldown_ready():
            return None
        if self.consecutive_losses >= self.losing_streak_trigger:
            return self._emit_report(
                trigger="losing_streak",
                summary=f"{self.consecutive_losses} consecutive losing trades.",
                strategy=outcome.strategy,
                regime=outcome.regime,
            )
        if self.drawdown_trigger_r > 0.0 and self.drawdown_r >= self.drawdown_trigger_r:
            return self._emit_report(
                trigger="equity_drawdown",
                summary=f"Equity drawdown reached {self.drawdown_r:.2f}R.",
                strategy=outcome.strategy,
                regime=outcome.regime,
            )
        return None

    def recent_metrics(
        self,
        *,
        strategy: StrategyId,
        regime: RegimeLabel,
        limit: int = 50,
    ) -> PriorSuccessMetrics:
        """Return sizing-ready metrics for a strategy/regime bucket."""

        bucket = [
            trade
            for trade in self.trades[-max(1, int(limit)) :]
            if trade.strategy == strategy and trade.regime == regime
        ]
        if not bucket:
            return PriorSuccessMetrics()
        wins = [trade.pnl_r for trade in bucket if trade.pnl_r > 0.0]
        losses = [trade.pnl_r for trade in bucket if trade.pnl_r < 0.0]
        return PriorSuccessMetrics(
            n_trades=len(bucket),
            hit_rate=len(wins) / len(bucket),
            expectancy_r=sum(trade.pnl_r for trade in bucket) / len(bucket),
            avg_win_r=_average(wins),
            avg_loss_r=_average(losses),
            consecutive_losses=_tail_streak(bucket, losing=True),
            consecutive_wins=_tail_streak(bucket, losing=False),
        )

    def _cooldown_ready(self) -> bool:
        return self.cooldown_bars <= 0 or self.bars_since_report >= self.cooldown_bars

    def _emit_report(
        self,
        *,
        trigger: str,
        summary: str,
        strategy: StrategyId | None,
        regime: RegimeLabel | None,
    ) -> RetrospectiveReport:
        report = RetrospectiveReport(
            trigger=trigger,
            summary=summary,
            n_trades=len(self.trades),
            cumulative_pnl_r=self.cumulative_pnl_r,
            consecutive_losses=self.consecutive_losses,
            current_equity=self.current_equity,
            high_water_equity=self.high_water_equity,
            drawdown_r=self.drawdown_r,
            strategy=strategy,
            regime=regime,
        )
        self.reports.append(report)
        self.bars_since_report = 0
        return report


def _average(values: Iterable[float]) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


def _tail_streak(trades: list[TradeOutcome], *, losing: bool) -> int:
    streak = 0
    for trade in reversed(trades):
        if losing and trade.pnl_r < 0.0:
            streak += 1
            continue
        if not losing and trade.pnl_r > 0.0:
            streak += 1
            continue
        break
    return streak


__all__ = ["RetrospectiveManager"]
