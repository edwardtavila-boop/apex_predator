"""Tests for ``eta_engine/scripts/_layer3_promotion_gate.py``.

Mirrors the contract pinned for mnq_bot's H4 9-gate set
(``mnq_bot/tests/level_1_unit/test_promotion_gate.py``):

  * The 8 layer-3 gates are registered with stable names
  * Each gate returns a GateResult with valid verdict
  * --gate <name> exit codes (0 PASS, 1 FAIL, 2 NO_DATA)
  * --all aggregate exit code (0 only when all PASS)
  * NO_DATA is HOLD (counts in the aggregate)
  * No --override / --force / --skip flag exists
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = (
    REPO_ROOT / "eta_engine" / "scripts" / "_layer3_promotion_gate.py"
)


@pytest.fixture(scope="module")
def gate_mod():
    spec = importlib.util.spec_from_file_location(
        "layer3_promotion_gate_for_test", GATE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["layer3_promotion_gate_for_test"] = module
    spec.loader.exec_module(module)
    return module


def test_eight_gates_registered(gate_mod) -> None:
    """Pin the gate count + names. Adding/dropping a gate must be a
    deliberate operator action reflected in this test."""
    expected = {
        "cme_micro_crypto_adapter",
        "ibkr_adapter_active",
        "backup_venue_configured",
        "layer3_cap_floor",
        "perp_l3_risk_caps_sane",
        "depeg_floor_set",
        "capital_sweep_layer3_ok",
        "paper_soak_min_weeks",
    }
    assert set(gate_mod._GATE_NAMES) == expected
    assert len(gate_mod._GATE_NAMES) == 8


def test_each_gate_has_callable_evaluator(gate_mod) -> None:
    for name, fn in gate_mod._GATES:
        assert callable(fn), f"{name} evaluator is not callable"


def test_aggregate_verdict_ordering(gate_mod) -> None:
    PASS, FAIL, NO_DATA = gate_mod.PASS, gate_mod.FAIL, gate_mod.NO_DATA
    G = gate_mod.GateResult

    all_pass = [G("a", PASS, "", {}), G("b", PASS, "", {})]
    assert gate_mod.aggregate_verdict(all_pass) == 0

    with_fail = [
        G("a", PASS, "", {}),
        G("b", FAIL, "", {}),
        G("c", NO_DATA, "", {}),
    ]
    assert gate_mod.aggregate_verdict(with_fail) == 1

    with_no_data = [G("a", PASS, "", {}), G("b", NO_DATA, "", {})]
    assert gate_mod.aggregate_verdict(with_no_data) == 2

    # Empty -> 0 (vacuously all pass; not expected in practice).
    assert gate_mod.aggregate_verdict([]) == 0


def test_main_all_returns_aggregate(
    gate_mod, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    PASS, FAIL = gate_mod.PASS, gate_mod.FAIL
    G = gate_mod.GateResult
    monkeypatch.setattr(
        gate_mod, "_GATES",
        [
            ("g1", lambda: G("g1", PASS, "ok", {})),
            ("g2", lambda: G("g2", FAIL, "broken", {})),
        ],
    )
    monkeypatch.setattr(gate_mod, "_GATE_NAMES", ["g1", "g2"])
    rc = gate_mod.main(["--all"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "PASS" in captured.out
    assert "FAIL" in captured.out


def test_main_single_gate_returns_individual_verdict(
    gate_mod, monkeypatch: pytest.MonkeyPatch,
) -> None:
    PASS = gate_mod.PASS
    G = gate_mod.GateResult
    monkeypatch.setattr(
        gate_mod, "_GATES",
        [("g1", lambda: G("g1", PASS, "ok", {}))],
    )
    monkeypatch.setattr(gate_mod, "_GATE_NAMES", ["g1"])
    rc = gate_mod.main(["--gate", "g1"])
    assert rc == 0


def test_main_unknown_gate_rejected(gate_mod) -> None:
    with pytest.raises(SystemExit) as exc:
        gate_mod.main(["--gate", "totally_made_up"])
    assert exc.value.code == 2  # argparse error


def test_main_requires_gate_or_all(gate_mod) -> None:
    with pytest.raises(SystemExit) as exc:
        gate_mod.main([])
    assert exc.value.code == 2


def test_main_json_output_shape(
    gate_mod, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    PASS = gate_mod.PASS
    G = gate_mod.GateResult
    monkeypatch.setattr(
        gate_mod, "_GATES",
        [("g1", lambda: G("g1", PASS, "ok", {"foo": 1}))],
    )
    monkeypatch.setattr(gate_mod, "_GATE_NAMES", ["g1"])

    gate_mod.main(["--all", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["rc"] == 0
    assert payload["n_pass"] == 1
    assert payload["gates"][0]["name"] == "g1"
    assert payload["gates"][0]["verdict"] == "PASS"


def test_no_override_flag_exists(gate_mod) -> None:
    """Architectural pin: NO --override / --force / --skip / --no-fail
    / --advisory flag is allowed. Failure is structural -- the operator
    fixes the failing gate's source, not the gate."""
    forbidden = {"--override", "--force", "--skip", "--no-fail", "--advisory"}
    import contextlib as ctx
    import io
    buf = io.StringIO()
    with ctx.redirect_stdout(buf), pytest.raises(SystemExit) as exc:
        gate_mod.main(["--help"])
    assert exc.value.code == 0
    help_text = buf.getvalue()
    for flag in forbidden:
        assert flag not in help_text, (
            f"forbidden override flag {flag!r} appears in layer-3 "
            f"promotion-gate --help. The operator contract requires no "
            f"override -- failure is structural."
        )


# ---------------------------------------------------------------------------
# Real-state smoke tests: the gates run against the actual config + adapters
# ---------------------------------------------------------------------------


def test_real_ibkr_active_passes(gate_mod) -> None:
    """IBKR must be active in the current dormancy set. If this test
    fails, IBKR has been put dormant -- that's a deliberate operator
    action and the gate correctly catches it."""
    result = gate_mod._gate_ibkr_adapter_active()
    assert result.verdict == gate_mod.PASS, result.detail


def test_real_layer3_cap_floor_at_or_below_10_pct(gate_mod) -> None:
    """Operator-set ceiling: layer3_max_fraction_of_total_pct <= 10."""
    result = gate_mod._gate_layer3_cap_floor()
    assert result.verdict == gate_mod.PASS, result.detail


def test_real_perp_l3_caps_sane(gate_mod) -> None:
    """perp_l3 caps must never exceed casino-tier caps."""
    result = gate_mod._gate_perp_l3_risk_caps_sane()
    assert result.verdict == gate_mod.PASS, result.detail


def test_real_depeg_floor_at_or_above_threshold(gate_mod) -> None:
    """stablecoin_depeg_floor must be >= 0.98."""
    result = gate_mod._gate_depeg_floor_set()
    assert result.verdict == gate_mod.PASS, result.detail


def test_real_cme_micro_crypto_symbol_map_intact(gate_mod) -> None:
    """The BTC/USD->MBT and ETH/USD->MET mapping is the contract every
    layer-3 order routing path depends on."""
    result = gate_mod._gate_cme_micro_crypto_adapter()
    assert result.verdict == gate_mod.PASS, result.detail


def test_real_capital_sweep_layer3_api_intact(gate_mod) -> None:
    """capital_sweep_layer3 must export its public API."""
    result = gate_mod._gate_capital_sweep_layer3_ok()
    assert result.verdict == gate_mod.PASS, result.detail


def test_real_backup_venue_present(gate_mod) -> None:
    """At least one non-zero backup venue (kraken_margin / hyperliquid)
    must be configured."""
    result = gate_mod._gate_backup_venue_configured()
    assert result.verdict == gate_mod.PASS, result.detail
