"""Probe: preflight runtime entrypoint is importable.

Doesn't run preflight (that's expensive + has side effects). Just confirms
the module loads so a syntax error in scripts.preflight is caught early.
"""
from __future__ import annotations

import importlib

from apex_predator.obs.probes import ProbeResult, register_probe


@register_probe(name="preflight", category="ops", severity="important")
def preflight() -> ProbeResult:
    try:
        importlib.import_module("apex_predator.scripts.preflight")
    except ImportError as exc:
        return ProbeResult(
            name="preflight",
            status="fail",
            message=f"preflight import error: {exc!s}",
        )
    return ProbeResult(
        name="preflight",
        status="pass",
        message="scripts.preflight importable",
    )
