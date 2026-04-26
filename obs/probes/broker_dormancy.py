"""Probe: DORMANT_BROKERS in venues.router matches the operator mandate.

The 2026-04-24 mandate requires Tradovate to remain DORMANT until funding
clears. This probe surfaces drift if someone re-enables Tradovate without
also flipping the mandate flag.
"""
from __future__ import annotations

from apex_predator.obs.probes import ProbeResult, register_probe

_EXPECTED_DORMANT = frozenset({"tradovate"})


@register_probe(name="broker_dormancy", category="broker", severity="critical")
def broker_dormancy() -> ProbeResult:
    try:
        from apex_predator.venues import router  # type: ignore[attr-defined]
    except ImportError:
        return ProbeResult(
            name="broker_dormancy",
            status="warn",
            message="venues.router not importable yet",
        )
    actual = frozenset(getattr(router, "DORMANT_BROKERS", set()) or set())
    missing = _EXPECTED_DORMANT - actual
    if missing:
        return ProbeResult(
            name="broker_dormancy",
            status="fail",
            message=(
                f"missing dormant brokers: {sorted(missing)}; "
                "router would route to a funding-blocked venue"
            ),
        )
    return ProbeResult(
        name="broker_dormancy",
        status="pass",
        message=f"dormant set OK: {sorted(actual)}",
    )
