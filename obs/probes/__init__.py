"""APEX PREDATOR  //  obs.probes
=====================================
Health-probe registry. Each probe is a zero-arg callable that returns a
:class:`ProbeResult` describing one slice of system health.

Probes are registered at module-import time via the :func:`register_probe`
decorator. :func:`discover_probes` walks ``obs/probes/*.py`` and triggers
every probe module's import-time registration so the operator dashboard
can call them on demand without each subsystem wiring up its own
endpoint.

Severities (operator escalation hint, not enforcement):

    * ``advisory``   -- nice to know
    * ``important``  -- operator should look (default)
    * ``critical``   -- block boot / page operator

Categories are free-form string labels for grouping (env, runtime,
broker, firm, etc.).
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

Severity = Literal["advisory", "important", "critical"]
Status = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class ProbeResult:
    name: str
    status: Status
    message: str


@dataclass(frozen=True)
class RegisteredProbe:
    name: str
    category: str
    severity: Severity
    fn: Callable[[], ProbeResult]


_REGISTRY: dict[str, RegisteredProbe] = {}


def register_probe(
    *,
    name: str,
    category: str = "default",
    severity: Severity = "important",
) -> Callable[[Callable[[], ProbeResult]], Callable[[], ProbeResult]]:
    """Decorator -- registers the probe at import time.

    Raises ``ValueError`` on duplicate name so two modules can't quietly
    shadow each other.
    """

    def _wrap(fn: Callable[[], ProbeResult]) -> Callable[[], ProbeResult]:
        if name in _REGISTRY:
            raise ValueError(f"probe {name!r} already registered")
        _REGISTRY[name] = RegisteredProbe(
            name=name, category=category, severity=severity, fn=fn,
        )
        return fn

    return _wrap


def get_registry() -> dict[str, RegisteredProbe]:
    """Return a copy of the current registry."""
    return dict(_REGISTRY)


def clear_registry_for_test() -> None:
    """Wipe the registry. Tests only -- production must never call this."""
    _REGISTRY.clear()


def discover_probes() -> dict[str, RegisteredProbe]:
    """Import every ``obs/probes/*.py`` so registration side-effects fire.

    Returns the registry after discovery. Idempotent: a second call is a
    no-op since modules are cached in ``sys.modules``.
    """
    pkg = importlib.import_module(__name__)
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        if mod_info.name.startswith("_"):
            continue
        full = f"{__name__}.{mod_info.name}"
        importlib.import_module(full)
    return get_registry()


__all__ = [
    "ProbeResult",
    "RegisteredProbe",
    "Severity",
    "Status",
    "clear_registry_for_test",
    "discover_probes",
    "get_registry",
    "register_probe",
]
