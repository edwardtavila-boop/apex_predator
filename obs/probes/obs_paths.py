"""Probe: expected docs/ subdirectories exist for runtime artifacts."""
from __future__ import annotations

from pathlib import Path

from apex_predator.obs.probes import ProbeResult, register_probe

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED = (
    "docs",
    "docs/btc_live",
    "docs/btc_paper",
    "docs/broker_connections",
)


@register_probe(name="obs_paths", category="ops", severity="advisory")
def obs_paths() -> ProbeResult:
    missing = [p for p in _REQUIRED if not (_REPO_ROOT / p).is_dir()]
    if missing:
        return ProbeResult(
            name="obs_paths",
            status="warn",
            message=f"missing observability dirs: {missing}",
        )
    return ProbeResult(
        name="obs_paths",
        status="pass",
        message=f"all {len(_REQUIRED)} observability dirs present",
    )
