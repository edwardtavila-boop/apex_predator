"""
EVOLUTIONARY TRADING ALGO // jarvis.gauntlet
================================
14-gate gauntlet enumeration (hard rule #2: "14-gate gauntlet remains
the only path to live deployment").

Each gate is one of:
    GateKind.AUTOMATED  — has a checker function; status is computable
    GateKind.MANUAL     — operator must explicitly mark passed
    GateKind.EXTERNAL   — depends on a 3rd-party (broker auth, etc.)

Public surface:
    Gauntlet.gates              -> list of all 14 gates
    Gauntlet.evaluate()         -> [GateResult] for every gate
    Gauntlet.passed_for_live()  -> True iff every gate is ``passed``
    Gauntlet.failing_gates()    -> list of gates blocking live boot

Wired into firm_health (#70) so `apex health` shows gate status, and
into `run_eta_live --require-firm-health=strict` (#20) so the boot
is refused unless every gate passes.
"""

from __future__ import annotations

import json
import os
import threading as _threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]


class GateKind(StrEnum):
    AUTOMATED = "automated"
    MANUAL = "manual"
    EXTERNAL = "external"


class GateStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Gate:
    name: str
    description: str
    kind: GateKind
    checker: Callable[[], "GateResult"] | None = None  # AUTOMATED only


@dataclass
class GateResult:
    name: str
    status: GateStatus
    detail: str
    checked_at_utc: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Manual-gate ledger
# ---------------------------------------------------------------------------
def _ledger_path() -> Path:
    base = Path(
        os.environ.get(
            "APEX_STATE_DIR",
            str(REPO_ROOT / "state"),
        )
    )
    return base / "gauntlet_ledger.json"


def _read_ledger() -> dict[str, dict]:
    p = _ledger_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_ledger(d: dict) -> None:
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")


def mark_manual_gate(name: str, *, passed: bool, operator: str, reason: str = "") -> None:
    """Operator-side: stamp a manual gate as passed/failed."""
    led = _read_ledger()
    led[name] = {
        "status": "passed" if passed else "failed",
        "operator": operator,
        "reason": reason,
        "stamped_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _write_ledger(led)


def _manual_status(name: str) -> tuple[GateStatus, str]:
    entry = _read_ledger().get(name)
    if not entry:
        return GateStatus.PENDING, "operator has not stamped this gate"
    status = GateStatus.PASSED if entry.get("status") == "passed" else GateStatus.FAILED
    return status, (
        f"stamped by {entry.get('operator', '?')} at {entry.get('stamped_at_utc', '?')}: {entry.get('reason', '')}"
    )


# ---------------------------------------------------------------------------
# Automated checkers
# ---------------------------------------------------------------------------
def _gate_unit_tests_passing() -> GateResult:
    """We don't run pytest from inside the gate (too slow). Instead we
    consult `state/last_test_run.json` if it exists; absent file =
    pending (operator must run pytest)."""
    p = Path(os.environ.get("APEX_STATE_DIR", str(REPO_ROOT / "state")))
    p = p / "last_test_run.json"
    if not p.exists():
        return GateResult("unit_tests_passing", GateStatus.PENDING, "no state/last_test_run.json; run `apex perf`")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        rc = int(d.get("pytest_rc", 1))
    except (json.JSONDecodeError, OSError, ValueError):
        return GateResult("unit_tests_passing", GateStatus.FAILED, "last_test_run.json unparseable")
    return (
        GateResult("unit_tests_passing", GateStatus.PASSED, f"last run rc=0; tests={d.get('test_count', '?')}")
        if rc == 0
        else GateResult("unit_tests_passing", GateStatus.FAILED, f"last run rc={rc}")
    )


def _gate_kill_switch_armed() -> GateResult:
    """KillSwitchLatch must be ARMED (not TRIPPED)."""
    p = Path(os.environ.get("APEX_STATE_DIR", str(REPO_ROOT / "state")))
    p = p / "kill_switch_latch.json"
    if not p.exists():
        return GateResult("kill_switch_armed", GateStatus.PASSED, "latch absent → ARMED")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return GateResult("kill_switch_armed", GateStatus.FAILED, "latch file unparseable")
    if d.get("state") == "TRIPPED":
        return GateResult("kill_switch_armed", GateStatus.FAILED, f"latch TRIPPED: {d.get('reason')}")
    return GateResult("kill_switch_armed", GateStatus.PASSED, "latch ARMED")


def _gate_real_bug_lint() -> GateResult:
    """Every F821/F811/B006/B008/B904 must be clean."""
    import subprocess
    import sys

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--select=F821,F811,B006,B008,B904", "--no-fix", "eta_engine/"],
            cwd=str(REPO_ROOT.parent),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return GateResult("real_bug_lint", GateStatus.PENDING, "ruff unavailable")
    if proc.returncode == 0:
        return GateResult("real_bug_lint", GateStatus.PASSED, "clean")
    return GateResult("real_bug_lint", GateStatus.FAILED, f"violations present: {proc.stdout.strip()[:120]}")


def _gate_v1_locked_frozen() -> GateResult:
    """Mirror the v1_locked frozen-tree pytest in summary form."""
    mnq = Path("C:/Users/edwar/projects/mnq_bot")
    venv = mnq / ".venv" / "Scripts" / "python.exe"
    if not venv.exists():
        venv = mnq / ".venv" / "bin" / "python"
    test_p = mnq / "tests" / "level_1_unit" / "test_v1_locked_frozen.py"
    if not venv.exists() or not test_p.exists():
        return GateResult("v1_locked_frozen", GateStatus.SKIPPED, "mnq_bot not reachable")
    import subprocess

    try:
        proc = subprocess.run(
            [str(venv), "-m", "pytest", str(test_p), "-q"],
            cwd=str(mnq),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return GateResult("v1_locked_frozen", GateStatus.PENDING, "timeout")
    if proc.returncode == 0:
        return GateResult("v1_locked_frozen", GateStatus.PASSED, "frozen tree intact")
    return GateResult(
        "v1_locked_frozen", GateStatus.FAILED, proc.stdout.strip().splitlines()[-1] if proc.stdout else "fail"
    )


def _gate_changelog_in_sync() -> GateResult:
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "eta_engine.scripts.changelog_from_state", "--check"],
        cwd=str(REPO_ROOT.parent),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if proc.returncode == 0:
        return GateResult("changelog_in_sync", GateStatus.PASSED, "in sync")
    return GateResult("changelog_in_sync", GateStatus.FAILED, "drift; regenerate via apex changelog")


def _gate_runbook_in_sync() -> GateResult:
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "eta_engine.scripts.generate_runbook", "--check"],
        cwd=str(REPO_ROOT.parent),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if proc.returncode == 0:
        return GateResult("runbook_in_sync", GateStatus.PASSED, "in sync")
    return GateResult("runbook_in_sync", GateStatus.FAILED, "drift; regenerate via apex runbook")


def _gate_broker_dormancy_mandate() -> GateResult:
    try:
        from eta_engine.venues.router import DORMANT_BROKERS
    except ImportError as e:
        return GateResult("broker_dormancy_mandate", GateStatus.FAILED, f"import: {e}")
    if "tradovate" in DORMANT_BROKERS:
        return GateResult("broker_dormancy_mandate", GateStatus.PASSED, f"dormant={sorted(DORMANT_BROKERS)}")
    return GateResult(
        "broker_dormancy_mandate",
        GateStatus.FAILED,
        "tradovate missing from DORMANT_BROKERS (operator mandate 2026-04-24)",
    )


def _gate_firm_health_ready() -> GateResult:
    """firm_health verdict must be READY."""
    try:
        import contextlib
        import io

        from eta_engine.scripts import firm_health as fh

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            results = fh.run_all(skip_bridge=None)
            verdict = fh.verdict_from(results, strict=False)
    except Exception as e:  # noqa: BLE001
        return GateResult("firm_health_ready", GateStatus.FAILED, f"crashed: {type(e).__name__}: {e}")
    if verdict == "READY":
        return GateResult("firm_health_ready", GateStatus.PASSED, "READY")
    return GateResult("firm_health_ready", GateStatus.FAILED, f"verdict={verdict}")


def _gate_kill_rehearsal_recovery() -> GateResult:
    try:
        from eta_engine.scripts import kill_rehearsal as kr

        r = kr.run_drill("recovery")
    except Exception as e:  # noqa: BLE001
        return GateResult("kill_rehearsal_recovery", GateStatus.FAILED, f"crashed: {type(e).__name__}: {e}")
    return (
        GateResult("kill_rehearsal_recovery", GateStatus.PASSED, "trip→clear→boot OK")
        if r.passed
        else GateResult("kill_rehearsal_recovery", GateStatus.FAILED, r.detail)
    )


# ---------------------------------------------------------------------------
# 14-gate gauntlet
# ---------------------------------------------------------------------------
GATES: tuple[Gate, ...] = (
    # 1-3: code quality
    Gate("unit_tests_passing", "Latest pytest sweep returned rc=0", GateKind.AUTOMATED, _gate_unit_tests_passing),
    Gate(
        "real_bug_lint", "Real-bug ruff rules clean (F821/F811/B006/B008/B904)", GateKind.AUTOMATED, _gate_real_bug_lint
    ),
    Gate("v1_locked_frozen", "v1_locked manifest matches on-disk hashes", GateKind.AUTOMATED, _gate_v1_locked_frozen),
    # 4-5: discipline artifacts
    Gate("changelog_in_sync", "CHANGELOG.md matches roadmap_state.json", GateKind.AUTOMATED, _gate_changelog_in_sync),
    Gate("runbook_in_sync", "RUNBOOK.md matches live registries", GateKind.AUTOMATED, _gate_runbook_in_sync),
    # 6-8: safety
    Gate("kill_switch_armed", "Kill-switch latch is ARMED", GateKind.AUTOMATED, _gate_kill_switch_armed),
    Gate(
        "kill_rehearsal_recovery",
        "Recovery drill round-trips cleanly",
        GateKind.AUTOMATED,
        _gate_kill_rehearsal_recovery,
    ),
    Gate(
        "broker_dormancy_mandate",
        "DORMANT_BROKERS includes tradovate",
        GateKind.AUTOMATED,
        _gate_broker_dormancy_mandate,
    ),
    # 9: integration health
    Gate("firm_health_ready", "firm_health verdict == READY", GateKind.AUTOMATED, _gate_firm_health_ready),
    # 10-14: operator-stamped manual gates (the human review points
    # the roadmap insists must NEVER be auto-bypassed)
    Gate("manual_strategy_review", "Operator confirms strategy logic is reviewed + approved", GateKind.MANUAL),
    Gate("manual_red_team_review", "Red Team review surfaced ≥2 valid objections", GateKind.MANUAL),
    Gate("manual_capacity_signoff", "Operator confirms portfolio sizing within Apex caps", GateKind.MANUAL),
    Gate("external_broker_auth", "Active broker (IBKR or Tastytrade) authenticated end-to-end", GateKind.EXTERNAL),
    Gate("external_data_feed", "TV / Yahoo data feed delivering bars within freshness SLO", GateKind.EXTERNAL),
)


_eval_guard = _threading.local()


def evaluate(gates: tuple[Gate, ...] = GATES) -> list[GateResult]:
    """Evaluate every gate. Manual + external gates consult the ledger.

    Re-entrancy guard: ``firm_health.run_all`` runs the
    ``jarvis_gauntlet_status`` probe which calls back into ``evaluate``;
    without the guard this loops until the v1_locked_frozen subprocess
    timeout fires (~60s × N gates). On re-entry every gate returns
    SKIPPED with a recursion-guard note so the caller still sees a
    well-formed result list of the right length.
    """
    if getattr(_eval_guard, "active", False):
        now_iso = datetime.now(UTC).isoformat(timespec="seconds")
        out = []
        for g in gates:
            r = GateResult(g.name, GateStatus.SKIPPED, "recursion guard: nested evaluate() call")
            r.checked_at_utc = now_iso
            out.append(r)
        return out
    _eval_guard.active = True
    try:
        out: list[GateResult] = []
        now_iso = datetime.now(UTC).isoformat(timespec="seconds")
        for g in gates:
            if g.kind == GateKind.AUTOMATED and g.checker is not None:
                try:
                    r = g.checker()
                except Exception as e:  # noqa: BLE001
                    r = GateResult(g.name, GateStatus.FAILED, f"checker crashed: {type(e).__name__}: {e}")
            else:
                status, detail = _manual_status(g.name)
                r = GateResult(g.name, status, detail)
            r.checked_at_utc = now_iso
            out.append(r)
        return out
    finally:
        _eval_guard.active = False


def passed_for_live(results: list[GateResult] | None = None) -> bool:
    results = results if results is not None else evaluate()
    return all(r.status == GateStatus.PASSED for r in results)


def failing_gates(results: list[GateResult] | None = None) -> list[GateResult]:
    results = results if results is not None else evaluate()
    return [r for r in results if r.status != GateStatus.PASSED]


def render_text(results: list[GateResult]) -> str:
    bar = "-" * 80
    icon = {
        GateStatus.PASSED: "[+]",
        GateStatus.FAILED: "[x]",
        GateStatus.PENDING: "[?]",
        GateStatus.SKIPPED: "[~]",
    }
    lines = [bar, "  EVOLUTIONARY TRADING ALGO  //  14-gate gauntlet", bar]
    for r in results:
        lines.append(f"  {icon[r.status]} {r.name:<30s}  {r.status.upper():<8s}  {r.detail}")
    lines.append(bar)
    n_pass = sum(1 for r in results if r.status == GateStatus.PASSED)
    lines.append(f"  passed: {n_pass}/{len(results)}  live-eligible: {passed_for_live(results)}")
    lines.append(bar)
    return "\n".join(lines)
