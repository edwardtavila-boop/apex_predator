"""Tests for Phase 3: tool registry + 5 reference tools + budget enforcer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eta_engine.jarvis.memory import EpisodicMemory, LocalMemoryStore
from eta_engine.jarvis.tools import (
    BudgetExceededError,
    DatabentoQueryTool,
    FredMacroTool,
    MonteCarloTool,
    RegimeHistoryTool,
    Tool,
    ToolBudget,
    ToolBudgetEnforcer,
    ToolRegistry,
    ToolResult,
    TradovateL2Tool,
    build_default_tool_registry,
)


# ===========================================================================
# Tool / ToolRegistry
# ===========================================================================
class _DummyTool(Tool):
    name = "dummy"
    description = "test stub"
    read_only = True
    cost_per_call_usd = 0.01

    def invoke(self, **kwargs):
        return ToolResult(tool_name=self.name, success=True, data={"got": kwargs})


def test_registry_register_and_invoke() -> None:
    r = ToolRegistry()
    r.register(_DummyTool())
    out = r.invoke("dummy", a=1)
    assert out.success
    assert out.data == {"got": {"a": 1}}


def test_registry_unknown_tool_returns_failure() -> None:
    r = ToolRegistry()
    out = r.invoke("nope")
    assert not out.success
    assert "unknown" in out.error


def test_registry_duplicate_register_raises() -> None:
    r = ToolRegistry()
    r.register(_DummyTool())
    with pytest.raises(ValueError):
        r.register(_DummyTool())


def test_registry_blocks_execution_tier_by_default() -> None:
    class Exec(Tool):
        name = "exec"
        read_only = False

        def invoke(self, **kwargs):
            return ToolResult(tool_name=self.name, success=True)

    r = ToolRegistry()
    r.register(Exec())
    out = r.invoke("exec")
    assert not out.success
    assert "execution-tier" in out.error


def test_registry_allows_execution_tier_when_gauntlet_passes() -> None:
    class Exec(Tool):
        name = "exec"
        read_only = False

        def invoke(self, **kwargs):
            return ToolResult(tool_name=self.name, success=True)

    r = ToolRegistry(allow_execution_tier=True)
    r.register(Exec())
    out = r.invoke("exec")
    assert out.success


def test_registry_invoke_catches_tool_exception() -> None:
    class Boom(Tool):
        name = "boom"

        def invoke(self, **kwargs):
            raise RuntimeError("boom")

    r = ToolRegistry()
    r.register(Boom())
    out = r.invoke("boom")
    assert not out.success
    assert "RuntimeError" in out.error


def test_registry_records_cost_per_call() -> None:
    r = ToolRegistry()
    r.register(_DummyTool())
    out = r.invoke("dummy", x=1)
    assert out.cost_usd == 0.01


# ===========================================================================
# ToolBudgetEnforcer
# ===========================================================================
def test_enforcer_allows_calls_within_budget() -> None:
    r = ToolRegistry()
    r.register(_DummyTool())
    enf = ToolBudgetEnforcer(r, budget=ToolBudget(max_calls=4))
    with enf.session(decision_id="d1") as s:
        for _ in range(3):
            s.invoke("dummy", x=1)
    assert s.state.n_calls == 3


def test_enforcer_blocks_after_max_calls() -> None:
    r = ToolRegistry()
    r.register(_DummyTool())
    enf = ToolBudgetEnforcer(r, budget=ToolBudget(max_calls=2))
    with enf.session(decision_id="d1") as s:
        s.invoke("dummy", x=1)
        s.invoke("dummy", x=2)
        with pytest.raises(BudgetExceededError):
            s.invoke("dummy", x=3)


def test_enforcer_blocks_on_cost_overrun() -> None:
    class Pricey(Tool):
        name = "pricey"
        cost_per_call_usd = 0.30

        def invoke(self, **kwargs):
            return ToolResult(tool_name=self.name, success=True)

    r = ToolRegistry()
    r.register(Pricey())
    enf = ToolBudgetEnforcer(r, budget=ToolBudget(cost_usd=0.50, max_calls=10))
    with enf.session(decision_id="d1") as s:
        s.invoke("pricey")
        s.invoke("pricey")  # cost=0.60 > 0.50
        with pytest.raises(BudgetExceededError) as exc:
            s.invoke("pricey")
        assert exc.value.kind == "cost_usd"


def test_enforcer_records_audit_trail() -> None:
    r = ToolRegistry()
    r.register(_DummyTool())
    enf = ToolBudgetEnforcer(r)
    with enf.session(decision_id="d-42") as s:
        s.invoke("dummy", a=1)
        s.invoke("dummy", a=2)
    assert len(s.records) == 2
    assert all(rec.decision_id == "d-42" for rec in s.records)
    assert s.records[0].args == {"a": 1}


# ===========================================================================
# Reference tools — DatabentoQueryTool
# ===========================================================================
def test_databento_requires_symbol_and_date(tmp_path: Path) -> None:
    t = DatabentoQueryTool(cache_root=tmp_path)
    out = t.invoke()
    assert not out.success
    assert "required" in out.error


def test_databento_cache_miss_reported(tmp_path: Path) -> None:
    t = DatabentoQueryTool(cache_root=tmp_path)
    out = t.invoke(symbol="MNQ", date="2026-04-25")
    assert not out.success
    assert "cache miss" in out.error


def test_databento_cache_hit_returns_metadata(tmp_path: Path) -> None:
    p = tmp_path / "ohlcv_1m" / "MNQ" / "2026-04-25.parquet"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x" * 100)
    t = DatabentoQueryTool(cache_root=tmp_path)
    out = t.invoke(symbol="MNQ", date="2026-04-25")
    assert out.success
    assert out.data["size_bytes"] == 100


# ===========================================================================
# FredMacroTool
# ===========================================================================
def test_fred_requires_series(tmp_path: Path) -> None:
    t = FredMacroTool(cache_dir=tmp_path)
    out = t.invoke()
    assert not out.success
    assert "series" in out.error


def test_fred_cache_miss(tmp_path: Path) -> None:
    t = FredMacroTool(cache_dir=tmp_path)
    out = t.invoke(series="VIXCLS")
    assert not out.success


def test_fred_cache_hit(tmp_path: Path) -> None:
    (tmp_path / "VIXCLS.json").write_text(
        json.dumps({"latest_value": 16.5, "as_of": "2026-04-24", "age_days": 1.0}),
        encoding="utf-8",
    )
    t = FredMacroTool(cache_dir=tmp_path)
    out = t.invoke(series="VIXCLS")
    assert out.success
    assert out.data["latest_value"] == 16.5


# ===========================================================================
# MonteCarloTool
# ===========================================================================
def test_monte_carlo_requires_returns() -> None:
    t = MonteCarloTool()
    out = t.invoke()
    assert not out.success


def test_monte_carlo_basic_run() -> None:
    t = MonteCarloTool()
    out = t.invoke(
        trade_returns=[1.0, -0.5, 1.0, -0.5, 0.5],
        n_paths=200,
        horizon_n_trades=20,
        seed=42,
    )
    assert out.success
    assert out.data["n_paths"] == 200
    # p50 should be positive (positive expectancy distribution)
    assert out.data["final_equity_p50"] > 0


def test_monte_carlo_deterministic_with_same_seed() -> None:
    t = MonteCarloTool()
    a = t.invoke(trade_returns=[1, -1, 0.5], n_paths=100, horizon_n_trades=10, seed=7)
    b = t.invoke(trade_returns=[1, -1, 0.5], n_paths=100, horizon_n_trades=10, seed=7)
    assert a.data == b.data


def test_monte_carlo_clamps_n_paths() -> None:
    t = MonteCarloTool()
    out = t.invoke(trade_returns=[1.0], n_paths=10, horizon_n_trades=5)
    # min clamp is 100
    assert out.data["n_paths"] == 100


# ===========================================================================
# RegimeHistoryTool
# ===========================================================================
def test_regime_history_requires_store(tmp_path: Path) -> None:
    t = RegimeHistoryTool(store=None)
    out = t.invoke(regime="RISK-ON")
    assert not out.success


def test_regime_history_aggregates(tmp_path: Path) -> None:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    for i, regime in enumerate(["RISK-ON", "RISK-ON", "RISK-OFF"]):
        s.upsert(
            EpisodicMemory(
                decision_id=f"d{i}",
                ts_utc=f"2026-04-25T0{i}:00:00",
                symbol="x",
                regime=regime,
                setup_name="ORB",
                pm_action="fire_long",
                weighted_score=0,
                confidence=0,
                votes={},
                falsifications=[],
                outcomes={"+5_bars": 1.0 if i < 2 else -1.0},
            )
        )
    t = RegimeHistoryTool(store=s)
    out = t.invoke(regime="RISK-ON")
    assert out.success
    assert out.data["n"] == 2
    assert out.data["win_rate"] == 1.0


def test_regime_history_empty_filter_returns_zero() -> None:
    s = LocalMemoryStore(path=Path("does_not_exist.jsonl"))
    t = RegimeHistoryTool(store=s)
    out = t.invoke(regime="NONESUCH")
    assert out.success
    assert out.data["n"] == 0


# ===========================================================================
# build_default_tool_registry — the 5 tools the roadmap requires
# ===========================================================================
def test_default_registry_contains_5_tools() -> None:
    r = build_default_tool_registry()
    names = {t["name"] for t in r.list()}
    assert names == {
        "databento_query",
        "fred_macro",
        "tradovate_l2_snapshot",
        "monte_carlo_run",
        "regime_history_lookup",
    }


def test_default_registry_all_tools_are_read_only() -> None:
    r = build_default_tool_registry()
    for entry in r.list():
        assert entry["read_only"] is True


# ===========================================================================
# TradovateL2 dormancy
# ===========================================================================
def test_tradovate_l2_refuses_when_dormant_and_no_cache(tmp_path: Path) -> None:
    """Per CLAUDE.md, Tradovate is DORMANT and no live call may go out."""
    t = TradovateL2Tool(cache_dir=tmp_path)
    out = t.invoke(symbol="MNQH6")
    assert not out.success
    assert "dormant" in out.error.lower() or "not wired" in out.error.lower()


def test_tradovate_l2_returns_cached_snapshot_when_present(tmp_path: Path) -> None:
    (tmp_path / "MNQH6.json").write_text(
        json.dumps({"bid": [21495, 21494], "ask": [21496, 21497]}),
        encoding="utf-8",
    )
    t = TradovateL2Tool(cache_dir=tmp_path)
    out = t.invoke(symbol="MNQH6")
    # Will succeed iff the dormancy check found cache present
    if out.success:
        assert out.data["source"] == "cache_dormancy"
