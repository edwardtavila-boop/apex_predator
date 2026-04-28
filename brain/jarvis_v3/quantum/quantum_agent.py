"""Quantum optimizer agent (Wave-9, 2026-04-27).

Plugs into the firm-board as a 6th specialist role: it receives the
current portfolio state + active candidate signals, formulates the
allocation/sizing/selection sub-problem as a QUBO, dispatches to the
QuantumCloudAdapter, and returns a structured recommendation.

Three problem types it handles out of the box:

  * PORTFOLIO_ALLOCATION  -- Markowitz mean-variance weights
  * SIZING_BASKET         -- pick K-of-N signals this hour
  * EXECUTION_SEQUENCING  -- order N orders to minimize cumulative slippage

It is intentionally OFFLINE-FIRST. The audit list explicitly warns
against putting cloud-quantum in the trade-decision hot path -- so
this agent is designed to run on the daily-rebalance schedule, on
new-regime triggers, or on operator demand. Its output is cached and
consulted at trade-time by the firm-board Auditor role.

Use case (cron job + firm-board hook):

    from eta_engine.brain.jarvis_v3.quantum import QuantumOptimizerAgent
    from eta_engine.brain.jarvis_v3.quantum.cloud_adapter import (
        CloudConfig, QuantumCloudAdapter,
    )

    agent = QuantumOptimizerAgent(
        adapter=QuantumCloudAdapter(CloudConfig(enable_cloud=False)),
    )

    rec = agent.allocate_portfolio(
        symbols=["MNQ", "BTC", "ETH", "MBT"],
        expected_returns=[1.2, 0.9, 0.7, 0.5],
        covariance=cov_matrix,
        target_n_positions=2,
    )
    print(rec.selected_symbols, rec.objective)

Output is consumed by the firm-board:
  - Researcher reads ``rec.contribution_summary`` for narrative
  - Risk Committee checks ``rec.cardinality`` against fleet caps
  - Executor uses ``rec.execution_order`` if present
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from eta_engine.brain.jarvis_v3.quantum.cloud_adapter import (
    QuantumCloudAdapter,
)
from eta_engine.brain.jarvis_v3.quantum.qubo_solver import (
    portfolio_allocation_qubo,
    sizing_basket_qubo,
)
from eta_engine.brain.jarvis_v3.quantum.tensor_network import (
    SignalScore,
    select_top_signal_combination,
    signal_correlation_matrix,
)

logger = logging.getLogger(__name__)


class ProblemKind(StrEnum):
    PORTFOLIO_ALLOCATION = "PORTFOLIO_ALLOCATION"
    SIZING_BASKET = "SIZING_BASKET"
    EXECUTION_SEQUENCING = "EXECUTION_SEQUENCING"


@dataclass
class Recommendation:
    """Structured output of one quantum-optimizer call."""

    ts: str
    kind: ProblemKind
    selected_labels: list[str]
    objective: float
    backend_used: str
    n_vars: int
    runtime_ms: float
    cost_estimate_usd: float
    used_cache: bool
    fell_back_to_classical: bool
    contribution_summary: str          # operator-readable narrative
    raw_solution: list[int] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# ─── Agent ─────────────────────────────────────────────────────────


class QuantumOptimizerAgent:
    """Firm-board pluggable agent.

    Stateless except for the underlying QuantumCloudAdapter, which
    does its own caching + audit logging. Methods are intentionally
    coarse-grained (one method per problem kind) so the agent stays
    grokkable; underlying QUBO encoders are exposed in qubo_solver.py
    if a caller wants finer control.
    """

    def __init__(
        self,
        *,
        adapter: QuantumCloudAdapter | None = None,
        n_iterations: int = 5_000,
    ) -> None:
        self.adapter = adapter or QuantumCloudAdapter()
        self.n_iterations = n_iterations

    # ── Portfolio allocation ────────────────────────────────

    def allocate_portfolio(
        self,
        *,
        symbols: list[str],
        expected_returns: list[float],
        covariance: list[list[float]],
        risk_aversion: float = 1.0,
        target_n_positions: int | None = None,
    ) -> Recommendation:
        """Run mean-variance allocation as a QUBO."""
        problem = portfolio_allocation_qubo(
            expected_returns=expected_returns,
            covariance=covariance,
            risk_aversion=risk_aversion,
            cardinality_min=target_n_positions,
            cardinality_max=target_n_positions,
            asset_labels=symbols,
        )
        result, record = self.adapter.solve(
            problem, n_iterations=self.n_iterations,
        )
        selected = result.selected_labels()
        contrib = (
            f"Quantum-optimizer (backend={record.backend}) selected "
            f"{len(selected)}/{len(symbols)} symbols "
            f"({', '.join(selected) if selected else 'none'}) "
            f"with portfolio objective {result.energy:+.4f}; "
            f"target cardinality "
            f"{target_n_positions if target_n_positions else 'unconstrained'}."
        )
        return Recommendation(
            ts=datetime.now(UTC).isoformat(),
            kind=ProblemKind.PORTFOLIO_ALLOCATION,
            selected_labels=selected,
            objective=result.energy,
            backend_used=record.backend,
            n_vars=record.n_vars,
            runtime_ms=record.runtime_ms,
            cost_estimate_usd=record.cost_estimate_usd,
            used_cache=record.used_cache,
            fell_back_to_classical=record.fell_back_to_classical,
            contribution_summary=contrib,
            raw_solution=list(result.x),
        )

    # ── K-of-N signal basket ────────────────────────────────

    def select_signal_basket(
        self,
        *,
        candidates: list[SignalScore],
        max_picks: int,
        correlation_penalty: float = 0.5,
        use_qubo: bool = True,
    ) -> Recommendation:
        """Pick ``max_picks`` signals out of ``candidates``.

        ``use_qubo=True`` uses the QUBO + simulated-annealing global
        optimizer; ``use_qubo=False`` uses the lighter tensor-network
        diversity-aware greedy. The greedy is faster but not provably
        optimal; the QUBO is what you want for nightly rebalancing.
        """
        if use_qubo:
            corr = signal_correlation_matrix(candidates)
            problem = sizing_basket_qubo(
                expected_r=[c.score for c in candidates],
                pairwise_correlation=corr,
                correlation_penalty=correlation_penalty,
                max_picks=max_picks,
                signal_labels=[c.name for c in candidates],
            )
            result, record = self.adapter.solve(
                problem, n_iterations=self.n_iterations,
            )
            selected = result.selected_labels()
            contrib = (
                f"Quantum-optimizer picked "
                f"{len(selected)} signals out of {len(candidates)} "
                f"using QUBO + {record.backend}: "
                f"{', '.join(selected) if selected else 'none'}. "
                f"Objective {result.energy:+.4f}."
            )
            return Recommendation(
                ts=datetime.now(UTC).isoformat(),
                kind=ProblemKind.SIZING_BASKET,
                selected_labels=selected,
                objective=result.energy,
                backend_used=record.backend,
                n_vars=record.n_vars,
                runtime_ms=record.runtime_ms,
                cost_estimate_usd=record.cost_estimate_usd,
                used_cache=record.used_cache,
                fell_back_to_classical=record.fell_back_to_classical,
                contribution_summary=contrib,
                raw_solution=list(result.x),
                extra={"correlation_penalty": correlation_penalty},
            )
        # Greedy diversity-aware path
        combo = select_top_signal_combination(candidates, k=max_picks)
        contrib = (
            f"Tensor-network selector picked {len(combo.selected)} "
            f"signals: {', '.join(s.name for s in combo.selected)}; "
            f"raw_score={combo.total_raw_score:.3f}, "
            f"diversity={combo.total_diversity_score:.3f}."
        )
        return Recommendation(
            ts=datetime.now(UTC).isoformat(),
            kind=ProblemKind.SIZING_BASKET,
            selected_labels=[s.name for s in combo.selected],
            objective=combo.objective,
            backend_used="tensor_network_greedy",
            n_vars=len(candidates),
            runtime_ms=0.0,
            cost_estimate_usd=0.0,
            used_cache=False,
            fell_back_to_classical=False,
            contribution_summary=contrib,
        )

    # ── Order execution sequencing ──────────────────────────

    def sequence_orders(
        self,
        *,
        order_labels: list[str],
        impact_estimates_bps: list[float],
        adjacency_penalty_bps: float = 1.0,
    ) -> Recommendation:
        """Choose which orders (subset) to send THIS slice to minimize
        cumulative slippage, leaving high-impact orders to TWAP across
        later slices.

        Modeled as: minimize sum_i impact[i] * x_i + penalty for picking
        too many at once.
        """
        n = len(order_labels)
        # Encode as QUBO: diagonal = impact[i]; off-diagonal = adjacency penalty
        Q: dict[int, dict[int, float]] = {}  # noqa: N806 -- QUBO matrix
        for i in range(n):
            Q.setdefault(i, {})[i] = impact_estimates_bps[i]
            for j in range(n):
                if i == j:
                    continue
                Q[i][j] = adjacency_penalty_bps
        from eta_engine.brain.jarvis_v3.quantum.qubo_solver import QuboProblem
        problem = QuboProblem(n_vars=n, Q=Q, labels=order_labels)
        result, record = self.adapter.solve(
            problem, n_iterations=self.n_iterations,
        )
        selected = result.selected_labels()
        contrib = (
            f"Execution sequencer picked {len(selected)}/{n} orders "
            f"to send this slice ({', '.join(selected)}); "
            f"estimated cumulative impact {result.energy:.2f} bps."
        )
        return Recommendation(
            ts=datetime.now(UTC).isoformat(),
            kind=ProblemKind.EXECUTION_SEQUENCING,
            selected_labels=selected,
            objective=result.energy,
            backend_used=record.backend,
            n_vars=record.n_vars,
            runtime_ms=record.runtime_ms,
            cost_estimate_usd=record.cost_estimate_usd,
            used_cache=record.used_cache,
            fell_back_to_classical=record.fell_back_to_classical,
            contribution_summary=contrib,
            raw_solution=list(result.x),
        )
