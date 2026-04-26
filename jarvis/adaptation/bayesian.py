"""
EVOLUTIONARY TRADING ALGO // jarvis.adaptation.bayesian
===========================================
Bayesian online updating with Thompson sampling.

For each parameter, we maintain a Beta(alpha, beta) belief over the
"goodness" of the parameter. After every closed trade we update:
    success (R > 0) -> alpha += 1
    failure (R <= 0) -> beta  += 1

To propose a new value, we Thompson-sample N candidate values inside
the parameter's hard bound and pick the one whose Beta sample is
highest — biasing toward exploration when uncertain, exploitation
when the posterior has tightened.

Auto-revert: if the rolling 3-day Sharpe over realized R-multiples
goes negative, the adapter reverts every parameter to its
``auto_revert_value`` and freezes adaptation for the configured
cool-down window.

200-trade rolling window per the roadmap. The adapter keeps a deque of
the last N trades; older ones drop out.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from eta_engine.jarvis.adaptation.parameters import (
    ParameterRegistry,
)


@dataclass
class _BetaBelief:
    alpha: float = 1.0
    beta: float = 1.0

    def update(self, success: bool) -> None:
        if success:
            self.alpha += 1.0
        else:
            self.beta += 1.0

    def mean(self) -> float:
        return self.alpha / max(1.0, self.alpha + self.beta)


@dataclass
class _Trade:
    ts: datetime
    r_multiple: float


@dataclass
class AdaptationProposal:
    """One proposed parameter change."""

    parameter: str
    old_value: float
    new_value: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class BayesianParameterAdapter:
    """Bounded Bayesian adapter.

    Public flow:
        adapter = BayesianParameterAdapter(registry)
        adapter.record_trade(r_multiple=0.8)            # online update
        adapter.record_trade(r_multiple=-0.4)
        ...
        proposals = adapter.propose()                    # may revert if Sharpe<0
        # Operator (or downstream gauntlet) applies proposals via
        # registry.set_current(...) — adapter does NOT mutate the
        # registry directly. This keeps the auto-revert path explicit.
    """

    def __init__(
        self,
        registry: ParameterRegistry,
        *,
        rolling_window_n: int = 200,
        sharpe_window_days: int = 3,
        sharpe_revert_threshold: float = 0.0,
        thompson_samples: int = 64,
        rng_seed: int = 0xA1EC,
        revert_cooldown_days: float = 1.0,
    ) -> None:
        self.registry = registry
        self.rolling_window_n = rolling_window_n
        self.sharpe_window_days = sharpe_window_days
        self.sharpe_revert_threshold = sharpe_revert_threshold
        self.thompson_samples = thompson_samples
        self.revert_cooldown_days = revert_cooldown_days

        self._trades: deque[_Trade] = deque(maxlen=rolling_window_n)
        self._beliefs: dict[str, _BetaBelief] = {spec.name: _BetaBelief() for spec in registry.list()}
        self._rng = random.Random(rng_seed)
        self._frozen_until: datetime | None = None

    # ------------------------------------------------------------------ #
    # Online updates
    # ------------------------------------------------------------------ #
    def record_trade(
        self,
        *,
        r_multiple: float,
        ts: datetime | None = None,
    ) -> None:
        ts = ts or datetime.now(UTC)
        self._trades.append(_Trade(ts=ts, r_multiple=float(r_multiple)))
        success = r_multiple > 0
        for b in self._beliefs.values():
            b.update(success)

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #
    def n_trades(self) -> int:
        return len(self._trades)

    def rolling_sharpe(
        self,
        *,
        now: datetime | None = None,
    ) -> float:
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(days=self.sharpe_window_days)
        window = [t.r_multiple for t in self._trades if t.ts >= cutoff]
        if len(window) < 2:
            return 0.0
        mu = sum(window) / len(window)
        var = sum((r - mu) ** 2 for r in window) / (len(window) - 1)
        sd = math.sqrt(var)
        if sd == 0:
            return 0.0
        return mu / sd * math.sqrt(len(window))

    def is_frozen(self, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return self._frozen_until is not None and now < self._frozen_until

    # ------------------------------------------------------------------ #
    # Proposal logic
    # ------------------------------------------------------------------ #
    def propose(
        self,
        *,
        now: datetime | None = None,
    ) -> list[AdaptationProposal]:
        """Return a list of proposed parameter updates.

        Behavior:
          * Auto-revert path: if rolling Sharpe < threshold, propose
            reverts for every parameter and set the freeze window.
          * Frozen path: while frozen, propose nothing.
          * Normal path: Thompson-sample a new candidate value per
            parameter from the Beta posterior, mapped onto the
            parameter's hard bound.
        """
        now = now or datetime.now(UTC)

        if self.is_frozen(now=now):
            return []

        sharpe = self.rolling_sharpe(now=now)
        if len(self._trades) >= 5 and sharpe < self.sharpe_revert_threshold:
            self._frozen_until = now + timedelta(days=self.revert_cooldown_days)
            return [
                AdaptationProposal(
                    parameter=s.name,
                    old_value=s.current,
                    new_value=s.auto_revert_value,
                    reason=(f"auto-revert: rolling sharpe {sharpe:.3f} < threshold {self.sharpe_revert_threshold}"),
                )
                for s in self.registry.list()
                if abs(s.current - s.auto_revert_value) > 1e-9
            ]

        # Normal path — propose Thompson-sampled candidates
        out: list[AdaptationProposal] = []
        for spec in self.registry.list():
            belief = self._beliefs.get(spec.name) or _BetaBelief()
            best_score = -1.0
            best_value = spec.current
            for _ in range(max(8, self.thompson_samples)):
                # Sample from Beta(alpha, beta) using random.betavariate
                p = self._rng.betavariate(belief.alpha, belief.beta)
                # Map p ∈ [0,1] onto the parameter's hard bound
                candidate = spec.bound.lo + p * (spec.bound.hi - spec.bound.lo)
                if p > best_score:
                    best_score = p
                    best_value = candidate
            if abs(best_value - spec.current) >= 1e-6:
                out.append(
                    AdaptationProposal(
                        parameter=spec.name,
                        old_value=spec.current,
                        new_value=round(best_value, 4),
                        reason=(
                            f"thompson sample best={best_score:.3f} from "
                            f"Beta(α={belief.alpha:.1f}, β={belief.beta:.1f})"
                        ),
                    )
                )
        return out

    # ------------------------------------------------------------------ #
    # Diagnostic snapshot
    # ------------------------------------------------------------------ #
    def snapshot(self, *, now: datetime | None = None) -> dict[str, Any]:
        return {
            "n_trades": self.n_trades(),
            "rolling_sharpe": round(self.rolling_sharpe(now=now), 4),
            "frozen": self.is_frozen(now=now),
            "frozen_until": (self._frozen_until.isoformat() if self._frozen_until else None),
            "beliefs": {
                name: {"alpha": b.alpha, "beta": b.beta, "mean": round(b.mean(), 4)}
                for name, b in self._beliefs.items()
            },
            "registry": self.registry.snapshot(),
        }
