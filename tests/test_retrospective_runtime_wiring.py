"""Regression coverage for optional retrospective bot wiring."""

from __future__ import annotations

import pytest

from eta_engine.bots.base_bot import Fill
from eta_engine.bots.crypto_seed.bot import CryptoSeedBot
from eta_engine.bots.eth_perp.bot import EthPerpBot
from eta_engine.bots.mnq.bot import MnqBot
from eta_engine.bots.retrospective_adapter import build_trade_outcome
from eta_engine.strategies.adaptive_sizing import RegimeLabel
from eta_engine.strategies.models import StrategyId
from eta_engine.strategies.retrospective_wiring import RetrospectiveManager


def test_retrospective_manager_reports_losing_streak() -> None:
    manager = RetrospectiveManager(
        starting_equity=1_000.0,
        losing_streak_trigger=2,
        cooldown_bars=0,
    )
    first = build_trade_outcome(
        strategy=StrategyId.OB_BREAKER_RETEST,
        regime=RegimeLabel.TRANSITION,
        pnl_r=-1.0,
        equity_after=990.0,
    )
    second = build_trade_outcome(
        strategy=StrategyId.OB_BREAKER_RETEST,
        regime=RegimeLabel.TRANSITION,
        pnl_r=-0.5,
        equity_after=985.0,
    )

    assert manager.record_trade(first) is None
    report = manager.record_trade(second)

    assert report is not None
    assert report.trigger == "losing_streak"
    assert report.consecutive_losses == 2
    assert report.cumulative_pnl_r == -1.5


@pytest.mark.asyncio
async def test_mnq_auto_wires_retrospective_manager() -> None:
    bot = MnqBot(auto_wire_retrospective=True)

    await bot.start()

    assert isinstance(bot.retrospective_manager, RetrospectiveManager)


@pytest.mark.asyncio
async def test_eth_auto_wires_retrospective_manager() -> None:
    bot = EthPerpBot(auto_wire_retrospective=True)

    await bot.start()

    assert isinstance(bot.retrospective_manager, RetrospectiveManager)


@pytest.mark.asyncio
async def test_crypto_seed_auto_wires_retrospective_manager() -> None:
    bot = CryptoSeedBot(auto_wire_retrospective=True)

    await bot.start()

    assert isinstance(bot.retrospective_manager, RetrospectiveManager)


def test_crypto_seed_record_fill_feeds_retrospective_manager() -> None:
    manager = RetrospectiveManager(
        starting_equity=2_000.0,
        losing_streak_trigger=1,
        cooldown_bars=0,
    )
    bot = CryptoSeedBot(retrospective_manager=manager)
    fill = Fill(
        symbol="BTCUSDT",
        side="SELL",
        price=60_000.0,
        size=0.01,
        realized_pnl=-10.0,
        risk_at_entry=10.0,
    )

    assert bot.record_fill(fill) is False

    assert len(manager.trades) == 1
    assert manager.consecutive_losses == 1
    assert manager.reports[-1].trigger == "losing_streak"
