"""Tests for ``eta_engine.backtest.metrics``.

Auto-scaffolded by scripts/_test_scaffold.py -- the import smoke and
the per-symbol smoke tests are boilerplate. Edit freely; the
operator-specific edge cases belong here.
"""

from __future__ import annotations

import importlib


def test_import_smoke() -> None:
    """Module imports without raising."""
    importlib.import_module("eta_engine.backtest.metrics")


def test_compute_sharpe_smoke() -> None:
    """``compute_sharpe`` is callable (signature requires manual fill-in)."""
    from eta_engine.backtest.metrics import compute_sharpe

    assert callable(compute_sharpe)


def test_compute_sharpe_handles_fp_noise_constant_returns() -> None:
    """Three identical -1pct returns must NOT blow up to -1.2e+16.

    Regression: 2026-04-27 ETH/SOL walk-forward windows produced this
    exact pattern and poisoned the aggregate OOS Sharpe by 15 orders
    of magnitude. The constant series has sd=1.3e-17 (FP rounding),
    not the mathematically-correct 0; the guard treats relative
    dispersion below 1e-12 of the mean as effectively constant.
    """
    from eta_engine.backtest.metrics import compute_sharpe

    # Exact returns from the reproducer.
    rets = [-0.01, -0.01, -0.010000000000000023]
    assert compute_sharpe(rets) == 0.0

    # True-zero stdev still returns 0 (existing behaviour preserved).
    assert compute_sharpe([-0.01, -0.01, -0.01]) == 0.0

    # Real signal still produces a non-zero Sharpe.
    assert compute_sharpe([0.01, -0.005, 0.02, 0.005]) != 0.0


def test_compute_sortino_smoke() -> None:
    """``compute_sortino`` is callable (signature requires manual fill-in)."""
    from eta_engine.backtest.metrics import compute_sortino

    assert callable(compute_sortino)
    # TODO: invoke with realistic inputs and assert on output


def test_compute_profit_factor_smoke() -> None:
    """``compute_profit_factor`` is callable (signature requires manual fill-in)."""
    from eta_engine.backtest.metrics import compute_profit_factor

    assert callable(compute_profit_factor)
    # TODO: invoke with realistic inputs and assert on output


def test_compute_max_dd_smoke() -> None:
    """``compute_max_dd`` is callable (signature requires manual fill-in)."""
    from eta_engine.backtest.metrics import compute_max_dd

    assert callable(compute_max_dd)
    # TODO: invoke with realistic inputs and assert on output


def test_compute_expectancy_smoke() -> None:
    """``compute_expectancy`` is callable (signature requires manual fill-in)."""
    from eta_engine.backtest.metrics import compute_expectancy

    assert callable(compute_expectancy)
    # TODO: invoke with realistic inputs and assert on output
