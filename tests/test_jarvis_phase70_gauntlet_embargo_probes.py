"""Tests for #70: gauntlet, embargo, JARVIS firm_health probes, apex jarvis CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eta_engine.jarvis import embargo, gauntlet
from eta_engine.scripts import jarvis_brain_cli as jarvis_cli


# ===========================================================================
# 14-gate gauntlet
# ===========================================================================
def test_gauntlet_has_14_gates() -> None:
    assert len(gauntlet.GATES) == 14


def test_gauntlet_each_gate_has_unique_name() -> None:
    names = [g.name for g in gauntlet.GATES]
    assert len(names) == len(set(names))


def test_gauntlet_evaluate_returns_one_result_per_gate() -> None:
    results = gauntlet.evaluate()
    assert len(results) == len(gauntlet.GATES)


def test_gauntlet_manual_gates_default_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    results = gauntlet.evaluate()
    by_name = {r.name: r for r in results}
    for g in gauntlet.GATES:
        if g.kind in (gauntlet.GateKind.MANUAL, gauntlet.GateKind.EXTERNAL):
            assert by_name[g.name].status == gauntlet.GateStatus.PENDING


def test_gauntlet_mark_manual_gate_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    gauntlet.mark_manual_gate("manual_strategy_review", passed=True, operator="ed")
    results = gauntlet.evaluate()
    msr = next(r for r in results if r.name == "manual_strategy_review")
    assert msr.status == gauntlet.GateStatus.PASSED
    assert "ed" in msr.detail


def test_gauntlet_passed_for_live_false_in_dev(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    # In dev env, manual + external gates are PENDING -> not live-eligible
    assert gauntlet.passed_for_live() is False


def test_gauntlet_failing_gates_returns_subset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    failing = gauntlet.failing_gates()
    assert len(failing) >= 5  # at least the manual + external gates
    assert all(r.status != gauntlet.GateStatus.PASSED for r in failing)


def test_gauntlet_render_text_includes_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    out = gauntlet.render_text(gauntlet.evaluate())
    assert "14-gate gauntlet" in out
    assert "live-eligible" in out


def test_gauntlet_serializable_to_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    results = gauntlet.evaluate()
    json.dumps([r.as_dict() for r in results])


# ===========================================================================
# 60-day embargo
# ===========================================================================
def test_embargo_no_windows_means_no_embargo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    is_e, w = embargo.is_embargoed("2026-04-25")
    assert is_e is False and w is None


def test_embargo_add_window_makes_dates_inside_embargoed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    embargo.add_window(start_iso="2026-04-01", end_iso="2026-05-31", label="OOS-q2", set_by="ed")
    is_e, w = embargo.is_embargoed("2026-04-25")
    assert is_e is True
    assert w is not None and w.label == "OOS-q2"


def test_embargo_outside_window_not_embargoed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    embargo.add_window(start_iso="2026-04-01", end_iso="2026-05-31", label="x", set_by="ed")
    is_e, _ = embargo.is_embargoed("2026-06-15")
    assert is_e is False


def test_embargo_raise_inside_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    embargo.add_window(start_iso="2026-04-01", end_iso="2026-05-31", label="x", set_by="ed")
    with pytest.raises(embargo.EmbargoViolation):
        embargo.raise_if_embargoed("2026-04-25")


def test_embargo_bypass_lifts_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    embargo.add_window(start_iso="2026-04-01", end_iso="2026-05-31", label="x", set_by="ed")
    embargo.grant_bypass(operator="ed", hours_valid=1.0)
    # Should NOT raise now
    embargo.raise_if_embargoed("2026-04-25")


def test_embargo_revoke_bypass_re_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    embargo.add_window(start_iso="2026-04-01", end_iso="2026-05-31", label="x", set_by="ed")
    embargo.grant_bypass(operator="ed", hours_valid=1.0)
    embargo.revoke_bypass()
    with pytest.raises(embargo.EmbargoViolation):
        embargo.raise_if_embargoed("2026-04-25")


def test_embargo_violation_message_includes_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    embargo.add_window(start_iso="2026-04-01", end_iso="2026-05-31", label="OOS-q2", set_by="ed")
    try:
        embargo.raise_if_embargoed("2026-04-25")
    except embargo.EmbargoViolation as e:
        assert "OOS-q2" in str(e)
        assert "2026-04-25" in str(e)


# ===========================================================================
# JARVIS firm_health probes
# ===========================================================================
def test_jarvis_probes_register_into_registry() -> None:
    """The probes module imports must populate the global registry."""
    import importlib

    from eta_engine.obs import probes as p

    p.clear_registry_for_test()
    # Re-import the jarvis probe module so its decorators fire
    import eta_engine.obs.probes.jarvis as jp

    importlib.reload(jp)
    reg = p.get_registry()
    expected = {
        "jarvis_specialists_panel",
        "jarvis_pm_consensus",
        "jarvis_episodic_memory_io",
        "jarvis_tool_registry",
        "jarvis_parameter_registry",
        "jarvis_gauntlet_status",
    }
    missing = expected - set(reg)
    assert not missing, f"missing JARVIS probes: {missing}"


def test_jarvis_specialists_panel_probe_passes() -> None:
    from eta_engine.obs.probes.jarvis import probe_specialists_panel

    r = probe_specialists_panel()
    assert r.status == "pass"


def test_jarvis_pm_consensus_probe_passes() -> None:
    from eta_engine.obs.probes.jarvis import probe_pm_consensus

    r = probe_pm_consensus()
    assert r.status == "pass"


def test_jarvis_tool_registry_probe_passes() -> None:
    from eta_engine.obs.probes.jarvis import probe_tool_registry

    r = probe_tool_registry()
    assert r.status == "pass"


def test_jarvis_parameter_registry_probe_passes() -> None:
    from eta_engine.obs.probes.jarvis import probe_parameter_registry

    r = probe_parameter_registry()
    assert r.status == "pass"


# ===========================================================================
# apex jarvis CLI
# ===========================================================================
def test_jarvis_cli_help_lists_subcommands(capsys: pytest.CaptureFixture) -> None:
    rc = jarvis_cli.main(["--help"])
    assert rc == 0
    out = capsys.readouterr().out
    for sc in ("status", "gauntlet", "embargo", "decide", "post-mortem"):
        assert sc in out


def test_jarvis_cli_unknown_subcommand_returns_2(
    capsys: pytest.CaptureFixture,
) -> None:
    rc = jarvis_cli.main(["nope"])
    assert rc == 2


def test_jarvis_cli_decide_runs(capsys: pytest.CaptureFixture) -> None:
    rc = jarvis_cli.main(["decide", "--symbol", "MNQ", "--regime", "RISK-ON", "--setup", "ORB"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "verdict" in out


def test_jarvis_cli_decide_json_emits_parseable(
    capsys: pytest.CaptureFixture,
) -> None:
    rc = jarvis_cli.main(["decide", "--symbol", "MNQ", "--regime", "RISK-ON", "--setup", "ORB", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "verdict" in payload
    assert "specialists" in payload
    assert len(payload["specialists"]) == 7


def test_jarvis_cli_post_mortem_writes_memo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    out = tmp_path / "memo.md"
    rc = jarvis_cli.main(["post-mortem", "--write", str(out)])
    assert rc == 0
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert body.startswith("# Weekly Post-Mortem")


def test_jarvis_cli_gauntlet_json(
    capsys: pytest.CaptureFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    rc = jarvis_cli.main(["gauntlet", "--json"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 14


def test_jarvis_cli_embargo_add_then_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    jarvis_cli.main(
        ["embargo", "add", "--start", "2026-04-01", "--end", "2026-05-31", "--label", "x", "--operator", "ed"]
    )
    rc = jarvis_cli.main(["embargo", "check", "--date", "2026-04-25"])
    assert rc == 1  # EMBARGOED -> exits 1


# ===========================================================================
# apex_cli registers jarvis subcommand
# ===========================================================================
def test_apex_cli_lists_jarvis_subcommand() -> None:
    from eta_engine.scripts import apex_cli

    names = {sc.name for sc in apex_cli.SUBCOMMANDS}
    assert "jarvis" in names


def test_apex_cli_jarvis_help_dispatches(
    capsys: pytest.CaptureFixture,
) -> None:
    from eta_engine.scripts import apex_cli

    rc = apex_cli.main(["jarvis", "--help"])
    assert rc == 0
