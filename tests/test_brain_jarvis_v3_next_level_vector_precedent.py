from __future__ import annotations

from datetime import UTC, datetime

from eta_engine.brain.jarvis_v3.next_level.vector_precedent import (
    EMBEDDING_DIM,
    VectorPrecedentStore,
)


def test_vector_precedent_records_searches_and_synthesizes_positive_neighbors() -> None:
    store = VectorPrecedentStore()
    ts = datetime(2026, 4, 29, tzinfo=UTC)
    entry = store.record(
        entry_id="fomc-risk-on",
        ts=ts,
        regime="RISK_ON",
        session_phase="OPEN",
        event_category="FOMC",
        binding_constraint="low_stress",
        tags=["orb", "momentum"],
        action="TRADE",
        outcome_correct=1,
        realized_r=0.8,
        numeric_features={"stress": -1.0},
    )

    neighbors = store.search(
        regime="RISK_ON",
        session_phase="OPEN",
        event_category="FOMC",
        binding_constraint="low_stress",
        tags=["orb", "momentum"],
        numeric_features={"stress": -1.0},
        k=3,
    )
    synthesis = store.synthesize(neighbors)

    assert len(entry.vector) == EMBEDDING_DIM
    assert neighbors[0].entry.id == "fomc-risk-on"
    assert neighbors[0].similarity == 1.0
    assert synthesis.hit_rate == 1.0
    assert synthesis.mean_r == 0.8
    assert "favors TRADE" in synthesis.suggestion


def test_vector_precedent_save_load_round_trip(tmp_path) -> None:
    path = tmp_path / "vector_precedents.json"
    ts = datetime(2026, 4, 29, tzinfo=UTC)
    store = VectorPrecedentStore()
    store.record(
        entry_id="cpi-risk-off",
        ts=ts,
        regime="RISK_OFF",
        session_phase="CLOSE",
        event_category="CPI",
        binding_constraint="macro",
        tags=["defensive"],
        action="STAND_ASIDE",
        outcome_correct=1,
        realized_r=-0.5,
    )

    store.save(path)
    loaded = VectorPrecedentStore.load(path)

    assert loaded.size() == 1
    assert loaded.search(regime="RISK_OFF", session_phase="CLOSE", event_category="CPI")[0].entry.id == "cpi-risk-off"


def test_vector_precedent_empty_store_returns_baseline_synthesis() -> None:
    store = VectorPrecedentStore()

    assert store.search(regime="NEUTRAL", session_phase="LUNCH") == []
    synthesis = store.synthesize([])
    assert synthesis.n_neighbors == 0
    assert synthesis.suggestion == "no neighbors -- proceed with baseline"
