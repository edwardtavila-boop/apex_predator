"""Probe: kill-switch latch is ARMED (or not yet written -- equivalent)."""
from __future__ import annotations

import os
from pathlib import Path

from apex_predator.core.kill_switch_latch import KillSwitchLatch, LatchState
from apex_predator.obs.probes import ProbeResult, register_probe

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _REPO_ROOT / "state" / "kill_switch_latch.json"


def _latch_path() -> Path:
    override = os.environ.get("APEX_KILL_SWITCH_LATCH_PATH")
    return Path(override) if override else _DEFAULT_PATH


@register_probe(name="kill_switch_state", category="risk", severity="critical")
def kill_switch_state() -> ProbeResult:
    latch = KillSwitchLatch(_latch_path())
    rec = latch.read()
    if rec.state == LatchState.ARMED:
        return ProbeResult(
            name="kill_switch_state",
            status="pass",
            message="kill switch ARMED",
        )
    return ProbeResult(
        name="kill_switch_state",
        status="fail",
        message=(
            f"kill switch TRIPPED: {rec.reason!r} "
            f"(action={rec.action}, scope={rec.scope})"
        ),
    )
