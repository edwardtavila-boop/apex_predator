"""Probe: roadmap_state.json was updated within the last N days."""
from __future__ import annotations

import time
from pathlib import Path

from apex_predator.obs.probes import ProbeResult, register_probe

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATE = _REPO_ROOT / "roadmap_state.json"
_STALE_DAYS = 14


@register_probe(name="roadmap_state_fresh", category="ops", severity="advisory")
def roadmap_state_fresh() -> ProbeResult:
    if not _STATE.exists():
        return ProbeResult(
            name="roadmap_state_fresh",
            status="fail",
            message=f"{_STATE.name} not found",
        )
    age_days = (time.time() - _STATE.stat().st_mtime) / 86_400.0
    if age_days > _STALE_DAYS:
        return ProbeResult(
            name="roadmap_state_fresh",
            status="warn",
            message=f"roadmap_state.json {age_days:.1f}d old (>{_STALE_DAYS}d)",
        )
    return ProbeResult(
        name="roadmap_state_fresh",
        status="pass",
        message=f"roadmap_state.json {age_days:.1f}d old",
    )
