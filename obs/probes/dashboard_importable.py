"""Probe: jarvis_dashboard module importable without side effects."""
from __future__ import annotations

import importlib

from apex_predator.obs.probes import ProbeResult, register_probe

_CANDIDATES = (
    "apex_predator.scripts.jarvis_dashboard",
    "apex_predator.deploy.dashboard",
)


@register_probe(name="dashboard_importable", category="ops", severity="advisory")
def dashboard_importable() -> ProbeResult:
    for mod in _CANDIDATES:
        try:
            importlib.import_module(mod)
        except ImportError:
            continue
        return ProbeResult(
            name="dashboard_importable",
            status="pass",
            message=f"dashboard available via {mod}",
        )
    return ProbeResult(
        name="dashboard_importable",
        status="warn",
        message=f"no dashboard module found (tried {_CANDIDATES})",
    )
