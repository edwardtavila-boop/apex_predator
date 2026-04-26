"""
EVOLUTIONARY TRADING ALGO // jarvis.adaptation.parameters
=============================================
Whitelisted parameter registry with hard bounds.

The Phase 4 contract is "logic stays frozen, parameters breathe." This
registry is the SINGLE source of truth for which parameters are
adaptable + their hard bounds. The BayesianParameterAdapter NEVER
proposes a value outside these bounds, regardless of what the meta-
learner suggests.

Roadmap explicitly allows:
    ATR multiplier      (1.5–2.5×)
    entry threshold z   (z-score; bounds vary by strategy)
    time stop           (bars; bounds vary)
    position size       scalar (0.5–1.0×)

Roadmap explicitly forbids:
    Strategy logic, entry/exit conditions, gauntlet gates, risk caps,
    daily loss kill switch.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ParameterBound:
    """Hard bound on an adaptable parameter."""

    lo: float
    hi: float
    description: str = ""

    def clamp(self, x: float) -> float:
        return max(self.lo, min(self.hi, x))

    def contains(self, x: float) -> bool:
        return self.lo <= x <= self.hi


@dataclass
class ParameterSpec:
    """One adaptable parameter."""

    name: str
    bound: ParameterBound
    current: float
    initial: float
    auto_revert_value: float
    last_proposal: float | None = None

    def __post_init__(self) -> None:
        if not self.bound.contains(self.current):
            raise ValueError(f"{self.name}: current={self.current} outside bound {self.bound.lo}..{self.bound.hi}")
        if not self.bound.contains(self.auto_revert_value):
            raise ValueError(f"{self.name}: auto_revert_value={self.auto_revert_value} outside bound")

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bound"] = {"lo": self.bound.lo, "hi": self.bound.hi, "description": self.bound.description}
        return d


# Roadmap-canonical parameters. Operators add more by calling
# ``ParameterRegistry.register(...)``.
DEFAULT_PARAMETERS: tuple[ParameterSpec, ...] = (
    ParameterSpec(
        name="atr_multiplier",
        bound=ParameterBound(lo=1.5, hi=2.5, description="Stop = entry ± atr × multiplier"),
        current=2.0,
        initial=2.0,
        auto_revert_value=2.0,
    ),
    ParameterSpec(
        name="entry_threshold_z",
        bound=ParameterBound(lo=0.5, hi=2.5, description="Z-score threshold for VWAP MR / sweep"),
        current=1.5,
        initial=1.5,
        auto_revert_value=1.5,
    ),
    ParameterSpec(
        name="time_stop_bars",
        bound=ParameterBound(lo=5, hi=60, description="Bars before time-stop fires"),
        current=20,
        initial=20,
        auto_revert_value=20,
    ),
    ParameterSpec(
        name="position_size_scalar",
        bound=ParameterBound(lo=0.5, hi=1.0, description="Multiplier on configured size"),
        current=1.0,
        initial=1.0,
        auto_revert_value=1.0,
    ),
)


# Things that MUST NOT be on this registry (defense-in-depth).
FORBIDDEN_PARAMETERS: frozenset[str] = frozenset(
    {
        "kill_switch_enabled",
        "daily_loss_cap_pct",
        "max_drawdown_kill_pct",
        "broker_primary",
        "strategy_logic_version",
        "gauntlet_passes",
    }
)


class ParameterRegistry:
    """In-memory registry of adaptable parameters."""

    def __init__(
        self,
        specs: Iterable[ParameterSpec] = DEFAULT_PARAMETERS,
    ) -> None:
        self._params: dict[str, ParameterSpec] = {}
        for s in specs:
            self.register(s)

    def register(self, spec: ParameterSpec) -> None:
        if spec.name in FORBIDDEN_PARAMETERS:
            raise ValueError(f"refuse to register forbidden parameter {spec.name!r} — this is in FORBIDDEN_PARAMETERS")
        if spec.name in self._params:
            raise ValueError(f"parameter {spec.name!r} already registered")
        self._params[spec.name] = spec

    def get(self, name: str) -> ParameterSpec | None:
        return self._params.get(name)

    def list(self) -> list[ParameterSpec]:
        return sorted(self._params.values(), key=lambda s: s.name)

    def names(self) -> list[str]:
        return sorted(self._params)

    def set_current(self, name: str, value: float) -> ParameterSpec:
        """Apply a new value, clamped to bounds. Records prior in
        last_proposal so the auto-revert path can roll back."""
        spec = self._params.get(name)
        if spec is None:
            raise KeyError(f"unknown parameter {name!r}")
        clamped = spec.bound.clamp(value)
        spec.last_proposal = spec.current
        spec.current = clamped
        return spec

    def revert(self, name: str) -> ParameterSpec:
        """Revert to ``auto_revert_value``."""
        spec = self._params.get(name)
        if spec is None:
            raise KeyError(f"unknown parameter {name!r}")
        spec.last_proposal = spec.current
        spec.current = spec.auto_revert_value
        return spec

    def revert_all(self) -> None:
        for name in list(self._params):
            self.revert(name)

    def snapshot(self) -> dict[str, Any]:
        return {name: s.as_dict() for name, s in self._params.items()}
