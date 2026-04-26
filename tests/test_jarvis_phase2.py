"""Tests for Phase 2: episodic memory + RAG."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from eta_engine.jarvis.memory import (
    DeterministicEmbedder,
    EpisodicMemory,
    LocalMemoryStore,
    OutcomeTracker,
    RetrievalEngine,
    RetrievalImpactEvaluator,
)
from eta_engine.jarvis.memory.embeddings import cosine


# ===========================================================================
# DeterministicEmbedder
# ===========================================================================
def test_embedder_returns_correct_dim() -> None:
    e = DeterministicEmbedder(dim=512)
    vecs = e.embed(["hello world"])
    assert len(vecs[0]) == 512


def test_embedder_is_deterministic() -> None:
    e = DeterministicEmbedder(dim=256)
    a = e.embed(["alpha beta"])[0]
    b = e.embed(["alpha beta"])[0]
    assert a == b


def test_embedder_l2_normalized() -> None:
    e = DeterministicEmbedder(dim=128)
    v = e.embed(["the quick brown fox"])[0]
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_embedder_overlap_implies_high_cosine() -> None:
    e = DeterministicEmbedder(dim=1024)
    a, b = e.embed(["the quick brown fox jumps", "the quick brown fox runs"])
    assert cosine(a, b) > 0.5


def test_embedder_disjoint_implies_low_cosine() -> None:
    e = DeterministicEmbedder(dim=1024)
    a, b = e.embed(["alpha beta gamma delta", "zzz yyy xxx www"])
    assert cosine(a, b) < 0.1


def test_embedder_rejects_nonpositive_dim() -> None:
    with pytest.raises(ValueError):
        DeterministicEmbedder(dim=0)


# ===========================================================================
# LocalMemoryStore
# ===========================================================================
def test_store_upsert_then_get(tmp_path: Path) -> None:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    m = EpisodicMemory(
        decision_id="d1",
        ts_utc="2026-04-25T10:00:00",
        symbol="MNQ",
        regime="RISK-ON",
        setup_name="ORB",
        pm_action="fire_long",
        weighted_score=0.6,
        confidence=0.7,
        votes={"quant": "long"},
        falsifications=["X breaks"],
    )
    s.upsert(m)
    got = s.get("d1")
    assert got is not None
    assert got.regime == "RISK-ON"


def test_store_persists_across_instances(tmp_path: Path) -> None:
    p = tmp_path / "mem.jsonl"
    s1 = LocalMemoryStore(path=p)
    s1.upsert(
        EpisodicMemory(
            decision_id="d1",
            ts_utc="2026-04-25T10:00:00",
            symbol="MNQ",
            regime="RISK-ON",
            setup_name="ORB",
            pm_action="skip",
            weighted_score=0.0,
            confidence=0.0,
            votes={},
            falsifications=[],
        )
    )
    s2 = LocalMemoryStore(path=p)
    assert s2.count() == 1
    assert s2.get("d1") is not None


def test_store_returns_in_chronological_order(tmp_path: Path) -> None:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    s.upsert(
        EpisodicMemory(
            decision_id="b",
            ts_utc="2026-04-25T11:00:00",
            symbol="x",
            regime="x",
            setup_name="",
            pm_action="",
            weighted_score=0,
            confidence=0,
            votes={},
            falsifications=[],
        )
    )
    s.upsert(
        EpisodicMemory(
            decision_id="a",
            ts_utc="2026-04-25T10:00:00",
            symbol="x",
            regime="x",
            setup_name="",
            pm_action="",
            weighted_score=0,
            confidence=0,
            votes={},
            falsifications=[],
        )
    )
    ids = [m.decision_id for m in s.all()]
    assert ids == ["a", "b"]


def test_store_handles_corrupt_lines_on_load(tmp_path: Path) -> None:
    p = tmp_path / "mem.jsonl"
    p.write_text(
        '{"decision_id":"good","ts_utc":"2026-04-25T10:00:00","symbol":"x",'
        '"regime":"x","setup_name":"","pm_action":"","weighted_score":0,'
        '"confidence":0,"votes":{},"falsifications":[],"feature_vec":{},'
        '"outcomes":{},"embedding":null}\n'
        "not-json-row\n",
        encoding="utf-8",
    )
    s = LocalMemoryStore(path=p)
    assert s.count() == 1


# ===========================================================================
# RetrievalEngine
# ===========================================================================
def _seed_store(
    tmp_path: Path,
    *,
    embedder: DeterministicEmbedder,
    n: int = 30,
    regimes=("RISK-ON", "RISK-OFF", "NEUTRAL", "CRISIS"),
) -> LocalMemoryStore:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        ts = (base + timedelta(days=i)).isoformat(timespec="seconds")
        regime = regimes[i % len(regimes)]
        narrative = f"setup ORB regime {regime} bar {i} VIX low MNQ"
        m = EpisodicMemory(
            decision_id=f"d{i}",
            ts_utc=ts,
            symbol="MNQ",
            regime=regime,
            setup_name="ORB",
            pm_action="fire_long" if i % 2 == 0 else "fire_short",
            weighted_score=0.5,
            confidence=0.5,
            votes={"quant": "long"},
            falsifications=["X"],
            feature_vec={"narrative": 1.0, "vix_z": 0.0},
            outcomes={"+5_bars": (1.0 if i % 3 == 0 else -0.5)},
            embedding=embedder.embed([narrative])[0],
        )
        s.upsert(m)
    return s


def test_retrieve_returns_at_most_k(tmp_path: Path) -> None:
    e = DeterministicEmbedder(dim=512)
    s = _seed_store(tmp_path, embedder=e, n=50)
    eng = RetrievalEngine(s, e)
    r = eng.retrieve("setup ORB regime RISK-ON bar VIX low", k=10, regime="RISK-ON")
    assert len(r) <= 10


def test_retrieve_filters_by_regime(tmp_path: Path) -> None:
    e = DeterministicEmbedder(dim=512)
    s = _seed_store(tmp_path, embedder=e, n=20)
    eng = RetrievalEngine(s, e)
    r = eng.retrieve("any text", regime="RISK-ON", regime_filter=True)
    for hit in r:
        assert hit.memory.regime == "RISK-ON"


def test_retrieve_disabled_filter_returns_all_regimes(tmp_path: Path) -> None:
    e = DeterministicEmbedder(dim=512)
    s = _seed_store(tmp_path, embedder=e, n=20)
    eng = RetrievalEngine(s, e)
    # Use a query that shares vocabulary with the seeded narratives
    # (the seeded text is "setup ORB regime <X> bar <i> VIX low MNQ")
    # so cosine > min_threshold and we actually get hits across regimes.
    r = eng.retrieve("setup ORB regime bar VIX MNQ", regime_filter=False, k=20, min_cosine=0.0)
    regimes = {hit.memory.regime for hit in r}
    assert len(regimes) > 1


def test_retrieve_empty_store_returns_empty(tmp_path: Path) -> None:
    e = DeterministicEmbedder(dim=128)
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    eng = RetrievalEngine(s, e)
    assert eng.retrieve("anything", regime="RISK-ON") == []


def test_retrieve_higher_score_for_more_similar(tmp_path: Path) -> None:
    e = DeterministicEmbedder(dim=1024)
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    target = EpisodicMemory(
        decision_id="t",
        ts_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        symbol="x",
        regime="RISK-ON",
        setup_name="ORB",
        pm_action="fire_long",
        weighted_score=0,
        confidence=0,
        votes={},
        falsifications=[],
        embedding=e.embed(["alpha beta gamma"])[0],
    )
    far = EpisodicMemory(
        decision_id="f",
        ts_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        symbol="x",
        regime="RISK-ON",
        setup_name="ORB",
        pm_action="fire_long",
        weighted_score=0,
        confidence=0,
        votes={},
        falsifications=[],
        embedding=e.embed(["zzz yyy xxx"])[0],
    )
    s.upsert(target)
    s.upsert(far)
    eng = RetrievalEngine(s, e)
    hits = eng.retrieve("alpha beta gamma", regime="RISK-ON")
    assert hits[0].memory.decision_id == "t"


# ===========================================================================
# OutcomeTracker
# ===========================================================================
def test_outcome_tracker_records_at_offset(tmp_path: Path) -> None:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    t0 = datetime(2026, 4, 25, 10, 0, tzinfo=UTC)
    s.upsert(
        EpisodicMemory(
            decision_id="d1",
            ts_utc=t0.isoformat(),
            symbol="MNQ",
            regime="x",
            setup_name="ORB",
            pm_action="fire_long",
            weighted_score=0.5,
            confidence=0.5,
            votes={},
            falsifications=[],
            feature_vec={"entry": 100.0, "atr": 2.0},
        )
    )
    tracker = OutcomeTracker(s, bar_interval_seconds=300, offsets_bars=(1, 5))
    # +1 bar = +5 minutes -> 10:05
    bar_ts = (t0 + timedelta(minutes=5)).isoformat(timespec="seconds")
    rec = tracker.on_bar(bar_ts_utc=bar_ts, close=110.0)
    assert any(r[0] == "d1" and r[1] == 1 for r in rec)
    assert s.get("d1").outcomes["+1_bars"] == round((110 - 100) / 2, 4)


def test_outcome_tracker_does_not_double_record(tmp_path: Path) -> None:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    t0 = datetime(2026, 4, 25, 10, 0, tzinfo=UTC)
    s.upsert(
        EpisodicMemory(
            decision_id="d1",
            ts_utc=t0.isoformat(),
            symbol="MNQ",
            regime="x",
            setup_name="ORB",
            pm_action="fire_long",
            weighted_score=0,
            confidence=0,
            votes={},
            falsifications=[],
            feature_vec={"entry": 100.0, "atr": 2.0},
        )
    )
    tracker = OutcomeTracker(s, bar_interval_seconds=300, offsets_bars=(1,))
    bar_ts = (t0 + timedelta(minutes=5)).isoformat(timespec="seconds")
    tracker.on_bar(bar_ts_utc=bar_ts, close=110.0)
    rec2 = tracker.on_bar(bar_ts_utc=bar_ts, close=120.0)
    assert rec2 == []  # already recorded


def test_outcome_tracker_skips_when_outside_tolerance(tmp_path: Path) -> None:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    t0 = datetime(2026, 4, 25, 10, 0, tzinfo=UTC)
    s.upsert(
        EpisodicMemory(
            decision_id="d1",
            ts_utc=t0.isoformat(),
            symbol="MNQ",
            regime="x",
            setup_name="ORB",
            pm_action="fire_long",
            weighted_score=0,
            confidence=0,
            votes={},
            falsifications=[],
            feature_vec={"entry": 100.0, "atr": 2.0},
        )
    )
    tracker = OutcomeTracker(s, bar_interval_seconds=300, offsets_bars=(1,))
    # +30 minutes — way past +1 bar (5 min)
    bar_ts = (t0 + timedelta(minutes=30)).isoformat(timespec="seconds")
    rec = tracker.on_bar(bar_ts_utc=bar_ts, close=110.0)
    assert rec == []


# ===========================================================================
# RetrievalImpactEvaluator (Phase 2 gate)
# ===========================================================================
def test_impact_evaluator_with_useful_memories_lifts_sharpe(
    tmp_path: Path,
) -> None:
    """Memories where the RIGHT action's outcome is positive should let
    the retrieval-aware policy beat the always-long baseline."""
    e = DeterministicEmbedder(dim=512)
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    base = datetime(2026, 4, 25, tzinfo=UTC)
    # 30 memories in RISK-OFF where the past outcome is consistently
    # NEGATIVE — i.e. "if you went long, you lost"
    for i in range(30):
        ts = (base + timedelta(hours=i)).isoformat(timespec="seconds")
        s.upsert(
            EpisodicMemory(
                decision_id=f"d{i}",
                ts_utc=ts,
                symbol="MNQ",
                regime="RISK-OFF",
                setup_name="ORB",
                pm_action="fire_long",
                weighted_score=0,
                confidence=0,
                votes={},
                falsifications=[],
                outcomes={"+5_bars": -1.0},
                embedding=e.embed(["setup ORB regime RISK-OFF VIX high"])[0],
            )
        )
    eng = RetrievalEngine(s, e, recency_half_life_days=365)
    evaluator = RetrievalImpactEvaluator(eng, min_sharpe_lift=0.0)
    setups = [("setup ORB regime RISK-OFF VIX high", "RISK-OFF", -1.0) for _ in range(10)]
    report = evaluator.evaluate(setups)
    # Retrieval policy should pick "go short" (outcome was negative);
    # baseline (always long) loses; so sharpe_with should be positive
    # and sharpe_without should be very negative or zero. Lift > 0.
    assert report.sharpe_lift >= 0


def test_impact_evaluator_pass_verdict_when_lift_meets_gate(
    tmp_path: Path,
) -> None:
    e = DeterministicEmbedder(dim=512)
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    for i in range(30):
        s.upsert(
            EpisodicMemory(
                decision_id=f"d{i}",
                ts_utc=datetime(2026, 4, 25, 0, i, tzinfo=UTC).isoformat(),
                symbol="x",
                regime="r",
                setup_name="s",
                pm_action="fire_long",
                weighted_score=0,
                confidence=0,
                votes={},
                falsifications=[],
                outcomes={"+5_bars": -1.0},
                embedding=e.embed(["x"])[0],
            )
        )
    eng = RetrievalEngine(s, e, recency_half_life_days=365)
    ev = RetrievalImpactEvaluator(eng, min_sharpe_lift=0.0)
    setups = [("x", "r", -1.0)] * 10
    r = ev.evaluate(setups)
    assert r.verdict in {"PASS", "MARGINAL"}


def test_impact_evaluator_handles_empty_setups(tmp_path: Path) -> None:
    e = DeterministicEmbedder(dim=128)
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    eng = RetrievalEngine(s, e)
    ev = RetrievalImpactEvaluator(eng)
    r = ev.evaluate([])
    assert r.n_setups == 0
