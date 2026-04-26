"""
EVOLUTIONARY TRADING ALGO // jarvis.runtime_integration
===========================================
Glue helpers for wiring JARVIS into the existing eta_engine runtime
loop without touching `scripts/run_eta_live.py` directly.

Two helpers:

    on_decision_made(verdict, ctx, store, embedder)
        Called after PM emits a verdict. Persists the EpisodicMemory
        row with the embedding pre-computed.

    on_bar_close(bar_ts, close, store, tracker)
        Called from the runtime's bar-close hook. Resolves outcomes
        for any memories that mature this bar (+1/+5/+20 offsets).

These give the runtime everything it needs to populate Phase 2 memory
without the runtime having to know about embedding pipelines or
MemoryStore internals.
"""

from __future__ import annotations

from eta_engine.jarvis.consensus import PMVerdict
from eta_engine.jarvis.memory.embeddings import EmbeddingPipeline
from eta_engine.jarvis.memory.outcomes import OutcomeTracker
from eta_engine.jarvis.memory.store import EpisodicMemory, MemoryStore
from eta_engine.jarvis.specialists.base import (
    DecisionContext,
    SpecialistOutput,
)


def _format_narrative(ctx: DecisionContext, verdict: PMVerdict) -> str:
    """Compact text representation of the decision used for embedding.

    Keeping the narrative deterministic is what makes the embedding
    similarity cluster: regime / setup / signal_tally / objections.
    """
    bits = [
        f"setup {ctx.setup_name}",
        f"regime {ctx.regime}",
        f"symbol {ctx.symbol}",
        f"action {verdict.action}",
        f"weighted {verdict.weighted_score:+.2f}",
    ]
    for sig, n in (verdict.signal_tally or {}).items():
        bits.append(f"vote_{sig}_{n}")
    return " ".join(bits)


def on_decision_made(
    *,
    verdict: PMVerdict,
    ctx: DecisionContext,
    store: MemoryStore,
    embedder: EmbeddingPipeline,
    specialist_outputs: list[SpecialistOutput] | None = None,
) -> EpisodicMemory:
    """Persist the decision into episodic memory. Returns the row."""
    votes: dict[str, str] = {}
    falsifications: list[str] = []
    if specialist_outputs:
        for i, o in enumerate(specialist_outputs):
            # SpecialistAgent.name isn't on the output object, so the
            # caller is expected to pass them in panel order if they
            # want named votes. Fallback: index-based key.
            votes[f"s{i}"] = o.signal
            if o.falsification:
                falsifications.append(o.falsification)
    narrative = _format_narrative(ctx, verdict)
    embedding = embedder.embed([narrative])[0]
    feature_vec = {
        "entry": float(ctx.bar.get("close", 0.0)),
        "atr": float(ctx.bar.get("atr", ctx.bar.get("atr_14", 1.0))),
        "weighted_score": verdict.weighted_score,
        "confidence": verdict.confidence,
    }
    mem = EpisodicMemory(
        decision_id=ctx.decision_id,
        ts_utc=ctx.bar_ts,
        symbol=ctx.symbol,
        regime=ctx.regime,
        setup_name=ctx.setup_name,
        pm_action=verdict.action,
        weighted_score=verdict.weighted_score,
        confidence=verdict.confidence,
        votes=votes,
        falsifications=falsifications,
        feature_vec=feature_vec,
        outcomes={},
        embedding=embedding,
    )
    store.upsert(mem)
    return mem


def on_bar_close(
    *,
    bar_ts_utc: str,
    close: float,
    store: MemoryStore,
    tracker: OutcomeTracker,
) -> list[tuple[str, int, float]]:
    """Resolve outcomes for memories that mature this bar.

    Returns list of (decision_id, n_bars_offset, r_multiple) for
    diagnostic surfacing on the dashboard.
    """
    return tracker.on_bar(bar_ts_utc=bar_ts_utc, close=close)
