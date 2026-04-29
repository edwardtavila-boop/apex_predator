from __future__ import annotations

from eta_engine.brain.jarvis_v3.claude_layer.distillation import (
    FEATURE_KEYS,
    Distiller,
    DistillerModel,
    DistillSample,
)


def _sample(stress: float, deterministic: str, claude: str) -> DistillSample:
    return DistillSample(
        features={
            "stress_composite": stress,
            "sizing_mult": 1.0,
            "precedent_n": 4,
        },
        deterministic_verdict=deterministic,
        claude_verdict=claude,
    )


def test_distill_sample_agreement_label_is_case_insensitive() -> None:
    assert _sample(0.1, "approved", "APPROVED").agreement_label == 1
    assert _sample(0.8, "APPROVED", "DENIED").agreement_label == 0


def test_distiller_fit_updates_version_and_normalizes_all_feature_keys() -> None:
    distiller = Distiller()
    model = distiller.fit(
        [
            _sample(0.1, "APPROVED", "APPROVED"),
            _sample(0.2, "APPROVED", "APPROVED"),
            _sample(0.8, "APPROVED", "DENIED"),
            _sample(0.9, "DENIED", "APPROVED"),
        ],
        iters=20,
    )

    assert model.version == 1
    assert model.train_n == 4
    assert set(model.weights) == set(FEATURE_KEYS)
    assert 0.0 <= model.accuracy <= 1.0


def test_distiller_skip_decision_and_persistence_round_trip(tmp_path) -> None:
    path = tmp_path / "distiller.json"
    model = DistillerModel(weights={"stress_composite": 0.0}, bias=5.0, train_n=10, accuracy=1.0, version=3)
    distiller = Distiller(model)
    decision = distiller.should_skip({"stress_composite": 0.5}, skip_threshold=0.9)
    distiller.save(path)
    loaded = Distiller.load(path)

    assert decision.skip_claude is True
    assert decision.model_version == 3
    assert loaded.model.version == 3
    assert Distiller.load(tmp_path / "missing.json").model.version == 0
