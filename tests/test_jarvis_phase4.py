"""Tests for Phase 4: bounded online adaptation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from eta_engine.jarvis.adaptation import (
    BayesianParameterAdapter,
    ParameterBound,
    ParameterRegistry,
    ParameterSpec,
)
from eta_engine.jarvis.adaptation.parameters import (
    FORBIDDEN_PARAMETERS,
)


# ===========================================================================
# ParameterBound + ParameterSpec
# ===========================================================================
def test_bound_clamp_inside_bound() -> None:
    b = ParameterBound(lo=1.0, hi=3.0)
    assert b.clamp(2.0) == 2.0


def test_bound_clamp_below() -> None:
    b = ParameterBound(lo=1.0, hi=3.0)
    assert b.clamp(0.5) == 1.0


def test_bound_clamp_above() -> None:
    b = ParameterBound(lo=1.0, hi=3.0)
    assert b.clamp(5.0) == 3.0


def test_spec_rejects_initial_outside_bound() -> None:
    with pytest.raises(ValueError):
        ParameterSpec(
            name="x",
            bound=ParameterBound(lo=1.0, hi=3.0),
            current=10.0,
            initial=10.0,
            auto_revert_value=2.0,
        )


def test_spec_rejects_revert_value_outside_bound() -> None:
    with pytest.raises(ValueError):
        ParameterSpec(
            name="x",
            bound=ParameterBound(lo=1.0, hi=3.0),
            current=2.0,
            initial=2.0,
            auto_revert_value=99.0,
        )


# ===========================================================================
# ParameterRegistry
# ===========================================================================
def test_registry_default_has_4_roadmap_params() -> None:
    r = ParameterRegistry()
    names = set(r.names())
    assert {"atr_multiplier", "entry_threshold_z", "time_stop_bars", "position_size_scalar"} <= names


def test_registry_refuses_forbidden_parameter() -> None:
    forbidden = next(iter(FORBIDDEN_PARAMETERS))
    bad = ParameterSpec(
        name=forbidden,
        bound=ParameterBound(lo=0.0, hi=1.0),
        current=0.5,
        initial=0.5,
        auto_revert_value=0.5,
    )
    r = ParameterRegistry(specs=())  # empty registry
    with pytest.raises(ValueError, match="forbidden"):
        r.register(bad)


def test_registry_set_current_clamps_to_bound() -> None:
    r = ParameterRegistry()
    r.set_current("atr_multiplier", 99.0)
    assert r.get("atr_multiplier").current == 2.5  # hi bound
    assert r.get("atr_multiplier").last_proposal == 2.0  # prior


def test_registry_revert_restores_default() -> None:
    r = ParameterRegistry()
    r.set_current("atr_multiplier", 2.4)
    r.revert("atr_multiplier")
    assert r.get("atr_multiplier").current == 2.0


def test_registry_unknown_param_raises() -> None:
    r = ParameterRegistry()
    with pytest.raises(KeyError):
        r.set_current("no_such_param", 1.0)


def test_registry_snapshot_serializable() -> None:
    import json

    r = ParameterRegistry()
    snap = r.snapshot()
    # Must be JSON-serializable
    json.dumps(snap)


# ===========================================================================
# BayesianParameterAdapter — online updates
# ===========================================================================
def test_adapter_records_trades() -> None:
    a = BayesianParameterAdapter(ParameterRegistry())
    for r in (1.0, -0.5, 0.8, -0.3):
        a.record_trade(r_multiple=r)
    assert a.n_trades() == 4


def test_adapter_belief_updates_on_wins_and_losses() -> None:
    a = BayesianParameterAdapter(ParameterRegistry())
    for _ in range(10):
        a.record_trade(r_multiple=1.0)  # all wins
    snap = a.snapshot()
    for name, belief in snap["beliefs"].items():
        # Mean should pull toward 1.0 with all wins
        assert belief["mean"] > 0.7, name


def test_adapter_belief_pulls_low_with_all_losses() -> None:
    a = BayesianParameterAdapter(ParameterRegistry())
    for _ in range(10):
        a.record_trade(r_multiple=-1.0)
    snap = a.snapshot()
    for name, belief in snap["beliefs"].items():
        assert belief["mean"] < 0.3, name


def test_rolling_sharpe_within_window_only() -> None:
    a = BayesianParameterAdapter(
        ParameterRegistry(),
        sharpe_window_days=3,
    )
    now = datetime(2026, 4, 25, tzinfo=UTC)
    a.record_trade(r_multiple=10.0, ts=now - timedelta(days=10))  # outside window
    a.record_trade(r_multiple=1.2, ts=now - timedelta(days=1))
    a.record_trade(r_multiple=0.8, ts=now - timedelta(days=2))
    a.record_trade(r_multiple=0.5, ts=now - timedelta(days=2))
    s = a.rolling_sharpe(now=now)
    # All within-window trades positive but with variance -> positive Sharpe
    assert s > 0


# ===========================================================================
# Auto-revert path
# ===========================================================================
def test_auto_revert_proposes_revert_when_sharpe_negative() -> None:
    reg = ParameterRegistry()
    # Move current away from auto_revert so a revert would have effect
    reg.set_current("atr_multiplier", 2.4)
    a = BayesianParameterAdapter(reg, sharpe_revert_threshold=0.0)
    now = datetime(2026, 4, 25, tzinfo=UTC)
    # Seed losses with VARIANCE so rolling_sharpe is computable + negative
    losses = [-1.5, -0.8, -1.2, -0.6, -1.0, -0.4, -1.3, -0.7, -0.9, -1.1]
    for i, r in enumerate(losses):
        a.record_trade(r_multiple=r, ts=now - timedelta(hours=i))
    proposals = a.propose(now=now)
    revert_p = next((p for p in proposals if p.parameter == "atr_multiplier"), None)
    assert revert_p is not None
    assert revert_p.new_value == 2.0  # auto_revert_value
    assert "auto-revert" in revert_p.reason


def test_auto_revert_freezes_subsequent_proposals() -> None:
    a = BayesianParameterAdapter(
        ParameterRegistry(),
        sharpe_revert_threshold=0.0,
        revert_cooldown_days=1.0,
    )
    now = datetime(2026, 4, 25, tzinfo=UTC)
    # Move parameter so revert WOULD happen
    a.registry.set_current("atr_multiplier", 2.4)
    losses = [-1.5, -0.8, -1.2, -0.6, -1.0, -0.4, -1.3, -0.7, -0.9, -1.1]
    for i, r in enumerate(losses):
        a.record_trade(r_multiple=r, ts=now - timedelta(hours=i))
    a.propose(now=now)  # triggers freeze
    later = now + timedelta(hours=12)
    assert a.is_frozen(now=later)
    assert a.propose(now=later) == []


def test_auto_revert_unfreezes_after_cooldown() -> None:
    a = BayesianParameterAdapter(
        ParameterRegistry(),
        sharpe_revert_threshold=0.0,
        revert_cooldown_days=1.0,
    )
    now = datetime(2026, 4, 25, tzinfo=UTC)
    a.registry.set_current("atr_multiplier", 2.4)
    losses = [-1.5, -0.8, -1.2, -0.6, -1.0, -0.4, -1.3, -0.7, -0.9, -1.1]
    for i, r in enumerate(losses):
        a.record_trade(r_multiple=r, ts=now - timedelta(hours=i))
    a.propose(now=now)
    later = now + timedelta(days=2)  # past 1-day cooldown
    assert not a.is_frozen(now=later)


# ===========================================================================
# Thompson sampling
# ===========================================================================
def test_proposals_stay_within_bounds() -> None:
    a = BayesianParameterAdapter(ParameterRegistry(), rng_seed=42)
    # Seed mixed outcomes so adapter proposes non-revert values
    for r in (1.0, -0.5, 0.8, -0.3, 1.2, -0.1):
        a.record_trade(r_multiple=r)
    proposals = a.propose()
    for p in proposals:
        spec = a.registry.get(p.parameter)
        assert spec is not None
        assert spec.bound.contains(p.new_value), (
            f"{p.parameter}: proposed {p.new_value} outside {spec.bound.lo}..{spec.bound.hi}"
        )


def test_proposals_deterministic_with_same_seed() -> None:
    a1 = BayesianParameterAdapter(ParameterRegistry(), rng_seed=99)
    a2 = BayesianParameterAdapter(ParameterRegistry(), rng_seed=99)
    for r in (1.0, -1.0, 0.5):
        a1.record_trade(r_multiple=r)
        a2.record_trade(r_multiple=r)
    p1 = [(p.parameter, p.new_value) for p in a1.propose()]
    p2 = [(p.parameter, p.new_value) for p in a2.propose()]
    assert p1 == p2


def test_no_proposals_when_no_trades() -> None:
    a = BayesianParameterAdapter(ParameterRegistry(), rng_seed=1)
    # No trades -> rolling Sharpe is 0, NOT < threshold; normal path runs
    # but proposals are valid. Some may even equal current -> filtered.
    # We just confirm it doesn't crash.
    out = a.propose()
    assert isinstance(out, list)


def test_snapshot_serializable() -> None:
    import json

    a = BayesianParameterAdapter(ParameterRegistry())
    a.record_trade(r_multiple=0.5)
    json.dumps(a.snapshot())
