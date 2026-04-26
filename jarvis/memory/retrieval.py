"""
EVOLUTIONARY TRADING ALGO // jarvis.memory.retrieval
========================================
Hybrid retrieval (cosine + regime filter + recency × outcome weighting).

`RetrievalEngine.retrieve(query_text, ...)` returns the k most similar
past decisions. `RetrievalImpactEvaluator` is the Phase 2 gate harness:
runs decisions WITH and WITHOUT retrieval and reports the delta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from eta_engine.jarvis.memory.embeddings import EmbeddingPipeline, cosine
from eta_engine.jarvis.memory.store import EpisodicMemory, MemoryStore


@dataclass
class RetrievalResult:
    memory: EpisodicMemory
    cosine_sim: float
    weighted_score: float
    age_days: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.memory.decision_id,
            "ts_utc": self.memory.ts_utc,
            "regime": self.memory.regime,
            "setup_name": self.memory.setup_name,
            "pm_action": self.memory.pm_action,
            "outcomes": self.memory.outcomes,
            "cosine_sim": round(self.cosine_sim, 4),
            "weighted_score": round(self.weighted_score, 4),
            "age_days": round(self.age_days, 2),
        }


class RetrievalEngine:
    """Hybrid retrieval over a MemoryStore.

    Final score = cosine_sim × recency_weight × outcome_weight.
      * cosine_sim       — query ⋅ memory.embedding
      * recency_weight   — exp(-age_days / half_life_days)
      * outcome_weight   — 1.0 + abs(outcome.+5) (memories with strong
                           outcomes carry more signal)

    Filter: regime must match the query's regime when ``regime_filter=True``.
    """

    def __init__(
        self,
        store: MemoryStore,
        embedder: EmbeddingPipeline,
        *,
        recency_half_life_days: float = 30.0,
        outcome_key: str = "+5_bars",
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.recency_half_life = recency_half_life_days
        self.outcome_key = outcome_key

    def retrieve(
        self,
        query_text: str,
        *,
        k: int = 10,
        regime: str | None = None,
        regime_filter: bool = True,
        min_cosine: float = 0.05,
    ) -> list[RetrievalResult]:
        candidates = self.store.all()
        if not candidates:
            return []
        if regime_filter and regime is not None:
            candidates = [m for m in candidates if m.regime == regime]
        if not candidates:
            return []

        query_vec = self.embedder.embed([query_text])[0]
        now = datetime.now(UTC)

        results: list[RetrievalResult] = []
        import math

        for m in candidates:
            if m.embedding is None:
                continue
            sim = cosine(query_vec, m.embedding)
            if sim < min_cosine:
                continue
            try:
                ts = datetime.fromisoformat(m.ts_utc.replace("Z", "+00:00"))
                age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
            except ValueError:
                age_days = 999.0
            recency_w = math.exp(-age_days / max(0.1, self.recency_half_life))
            outcome_val = float(m.outcomes.get(self.outcome_key, 0.0))
            outcome_w = 1.0 + abs(outcome_val)
            score = sim * recency_w * outcome_w
            results.append(
                RetrievalResult(
                    memory=m,
                    cosine_sim=sim,
                    weighted_score=score,
                    age_days=age_days,
                )
            )
        results.sort(key=lambda r: r.weighted_score, reverse=True)
        return results[:k]


# ---------------------------------------------------------------------------
# Phase 2 gate harness
# ---------------------------------------------------------------------------
@dataclass
class ImpactReport:
    n_setups: int
    sharpe_with_retrieval: float
    sharpe_without_retrieval: float
    sharpe_lift: float
    avg_outcome_with: float
    avg_outcome_without: float
    verdict: str  # "PASS" | "MARGINAL" | "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_setups": self.n_setups,
            "sharpe_with_retrieval": round(self.sharpe_with_retrieval, 4),
            "sharpe_without_retrieval": round(self.sharpe_without_retrieval, 4),
            "sharpe_lift": round(self.sharpe_lift, 4),
            "avg_outcome_with": round(self.avg_outcome_with, 4),
            "avg_outcome_without": round(self.avg_outcome_without, 4),
            "verdict": self.verdict,
        }


class RetrievalImpactEvaluator:
    """Phase 2 gate. Replays a list of (query_text, regime, true_outcome)
    setups twice — once where the retrieval result biases the decision,
    once without — and reports the Sharpe lift.

    The 0.3 Sharpe lift gate from the roadmap is operator-set via
    `min_sharpe_lift`.

    For testing, the harness uses a deterministic decision policy:
        with retrieval:    decision = sign(avg_retrieved_outcome)
        without retrieval: decision = +1 (always long, the "naive baseline")
    Real production wiring would replace these with the actual PM
    aggregator behavior; the harness shape stays the same.
    """

    def __init__(
        self,
        engine: RetrievalEngine,
        *,
        min_sharpe_lift: float = 0.3,
        outcome_key: str = "+5_bars",
    ) -> None:
        self.engine = engine
        self.min_sharpe_lift = min_sharpe_lift
        self.outcome_key = outcome_key

    @staticmethod
    def _sharpe(returns: list[float]) -> float:
        if not returns:
            return 0.0
        n = len(returns)
        mu = sum(returns) / n
        if n < 2:
            return 0.0
        var = sum((r - mu) ** 2 for r in returns) / (n - 1)
        sd = var**0.5
        if sd == 0:
            return 0.0
        return mu / sd * (n**0.5)  # ad-hoc per-window Sharpe

    def evaluate(
        self,
        setups: list[tuple[str, str, float]],
    ) -> ImpactReport:
        """setups = [(query_text, regime, true_outcome), ...]"""
        ret_outcomes: list[float] = []
        baseline_outcomes: list[float] = []
        for query_text, regime, true_outcome in setups:
            results = self.engine.retrieve(query_text, regime=regime, k=5)
            if results:
                avg = sum(float(r.memory.outcomes.get(self.outcome_key, 0.0)) for r in results) / len(results)
                decision_sign = 1.0 if avg >= 0 else -1.0
            else:
                decision_sign = 1.0  # fall back to baseline when no memories
            ret_outcomes.append(decision_sign * true_outcome)
            baseline_outcomes.append(1.0 * true_outcome)

        sw = self._sharpe(ret_outcomes)
        sb = self._sharpe(baseline_outcomes)
        lift = sw - sb
        verdict = "PASS" if lift >= self.min_sharpe_lift else ("MARGINAL" if lift >= 0 else "FAIL")
        return ImpactReport(
            n_setups=len(setups),
            sharpe_with_retrieval=sw,
            sharpe_without_retrieval=sb,
            sharpe_lift=lift,
            avg_outcome_with=(sum(ret_outcomes) / len(ret_outcomes) if ret_outcomes else 0.0),
            avg_outcome_without=(sum(baseline_outcomes) / len(baseline_outcomes) if baseline_outcomes else 0.0),
            verdict=verdict,
        )
