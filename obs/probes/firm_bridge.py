"""Probe: brain.firm_bridge importable -- the link to The Firm board."""
from __future__ import annotations

import importlib

from apex_predator.obs.probes import ProbeResult, register_probe


@register_probe(name="firm_bridge", category="firm", severity="important")
def firm_bridge() -> ProbeResult:
    try:
        importlib.import_module("apex_predator.brain.firm_bridge")
    except ImportError as exc:
        return ProbeResult(
            name="firm_bridge",
            status="fail",
            message=f"firm_bridge import error: {exc!s}",
        )
    return ProbeResult(
        name="firm_bridge",
        status="pass",
        message="brain.firm_bridge importable",
    )
