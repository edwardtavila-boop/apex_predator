"""Probe: interpreter is at the project's minimum Python version."""
from __future__ import annotations

import sys

from apex_predator.obs.probes import ProbeResult, register_probe

_MIN = (3, 12)


@register_probe(name="python_version", category="env", severity="critical")
def python_version() -> ProbeResult:
    cur = sys.version_info[:2]
    if cur >= _MIN:
        return ProbeResult(
            name="python_version",
            status="pass",
            message=f"python {cur[0]}.{cur[1]} >= {_MIN[0]}.{_MIN[1]}",
        )
    return ProbeResult(
        name="python_version",
        status="fail",
        message=f"python {cur[0]}.{cur[1]} below required {_MIN[0]}.{_MIN[1]}",
    )
