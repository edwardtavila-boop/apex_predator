"""Probe: firm runtime shim importable.

The shim wraps the_firm_complete board so the bot runtime can call into
it without depending on the upstream package's internal structure.
"""
from __future__ import annotations

import importlib

from apex_predator.obs.probes import ProbeResult, register_probe

_CANDIDATES = (
    "apex_predator.brain.firm_runtime_shim",
    "apex_predator.brain.firm_bridge",  # current shim home
)


@register_probe(name="firm_runtime_shim", category="firm", severity="important")
def firm_runtime_shim() -> ProbeResult:
    for mod in _CANDIDATES:
        try:
            importlib.import_module(mod)
        except ImportError:
            continue
        return ProbeResult(
            name="firm_runtime_shim",
            status="pass",
            message=f"firm runtime shim available via {mod}",
        )
    return ProbeResult(
        name="firm_runtime_shim",
        status="fail",
        message=f"no firm runtime shim found (tried {_CANDIDATES})",
    )
