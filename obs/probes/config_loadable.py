"""Probe: config.json parses and contains required top-level keys."""
from __future__ import annotations

import json
from pathlib import Path

from apex_predator.obs.probes import ProbeResult, register_probe

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _REPO_ROOT / "config.json"


@register_probe(name="config_loadable", category="env", severity="critical")
def config_loadable() -> ProbeResult:
    if not _CONFIG.exists():
        return ProbeResult(
            name="config_loadable",
            status="fail",
            message=f"{_CONFIG} not found",
        )
    try:
        json.loads(_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ProbeResult(
            name="config_loadable",
            status="fail",
            message=f"config.json parse error: {exc!s}",
        )
    return ProbeResult(
        name="config_loadable",
        status="pass",
        message="config.json parses",
    )
