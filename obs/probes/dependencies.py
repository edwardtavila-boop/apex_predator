"""Probe: core runtime dependencies importable."""
from __future__ import annotations

import importlib

from apex_predator.obs.probes import ProbeResult, register_probe

_REQUIRED = ("pydantic", "numpy", "pandas", "yaml")


@register_probe(name="dependencies", category="env", severity="critical")
def dependencies() -> ProbeResult:
    missing: list[str] = []
    for mod in _REQUIRED:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return ProbeResult(
            name="dependencies",
            status="fail",
            message=f"missing required deps: {', '.join(missing)}",
        )
    return ProbeResult(
        name="dependencies",
        status="pass",
        message=f"all {len(_REQUIRED)} core deps importable",
    )
