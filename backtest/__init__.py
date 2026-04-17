"""
APEX PREDATOR  //  backtest
===========================
Bar-replay backtest harness, metrics, tearsheet rendering.
"""

from apex_predator.backtest.deflated_sharpe import (
    compute_dsr,
    compute_probabilistic_sharpe,
)
from apex_predator.backtest.engine import BacktestEngine
from apex_predator.backtest.metrics import (
    compute_expectancy,
    compute_max_dd,
    compute_profit_factor,
    compute_sharpe,
    compute_sortino,
)
from apex_predator.backtest.models import BacktestConfig, BacktestResult, Trade
from apex_predator.backtest.replay import BarReplay
from apex_predator.backtest.tearsheet import TearsheetBuilder
from apex_predator.backtest.walk_forward import (
    WalkForwardConfig,
    WalkForwardEngine,
    WalkForwardResult,
)

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "BarReplay",
    "TearsheetBuilder",
    "Trade",
    "WalkForwardConfig",
    "WalkForwardEngine",
    "WalkForwardResult",
    "compute_dsr",
    "compute_expectancy",
    "compute_max_dd",
    "compute_probabilistic_sharpe",
    "compute_profit_factor",
    "compute_sharpe",
    "compute_sortino",
]
