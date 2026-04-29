from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eta_engine.brain.jarvis_v3.anomaly import DriftDetector, MultiFieldDetector
from eta_engine.brain.jarvis_v3.preferences import (
    OperatorPreferenceLearner,
    OverrideEvent,
)


def test_anomaly_detector_flags_deterministic_z_score_spike() -> None:
    detector = DriftDetector("vix", window=24, z_red=3.0, ks_red=1.1)
    for value in [15.0, 15.1] * 6:
        report = detector.observe(value)

    assert report.severity == "GREEN"

    spike = detector.observe(45.0)

    assert spike.severity == "RED"
    assert spike.field == "vix"
    assert spike.z_score is not None
    assert spike.z_score > 3.0
    assert "distribution shift" in spike.reason


def test_anomaly_detector_flags_constant_feed_after_warmup() -> None:
    detector = DriftDetector("regime_conf")

    for _ in range(8):
        report = detector.observe(0.77)

    assert report.severity == "YELLOW"
    assert "stuck" in report.reason
    assert report.samples == 8


def test_multifield_detector_reports_invalid_numbers_and_ignores_unknown_fields() -> None:
    detector = MultiFieldDetector(["vix", "daily_drawdown"])

    reports = detector.observe(
        {
            "vix": float("nan"),
            "daily_drawdown": "not-a-number",
            "unknown": float("inf"),
        }
    )

    assert len(reports) == 1
    assert reports[0].field == "vix"
    assert reports[0].severity == "RED"
    assert "NaN/Inf" in reports[0].reason


def test_operator_preference_learner_scores_veto_as_stronger_tighten() -> None:
    learner = OperatorPreferenceLearner(half_life_days=30)
    now = datetime(2026, 4, 29, 16, tzinfo=UTC)
    key = {
        "subsystem": "bot.mnq",
        "action": "ORDER_PLACE",
        "reason_code": "trade_ok",
    }

    learner.observe(OverrideEvent(ts=now, direction="loosen", **key))
    learner.observe(OverrideEvent(ts=now + timedelta(minutes=1), direction="veto", **key))

    nudge = learner.nudge_for(**key, now=now + timedelta(minutes=2))

    assert nudge is not None
    assert nudge.score < 0
    assert nudge.sample_count == 2
    assert nudge.confidence == 0.2
    assert "tighten" in nudge.suggestion


def test_operator_preference_learner_persists_tally_and_sample_counts(tmp_path) -> None:
    learner = OperatorPreferenceLearner(half_life_days=7)
    now = datetime(2026, 4, 29, 16, tzinfo=UTC)
    event = OverrideEvent(
        ts=now,
        subsystem="bot.btc",
        action="SIZE_CAP",
        reason_code="drawdown_guard",
        direction="tighten",
        rationale="operator kept beta smaller during news",
    )
    learner.observe(event)
    path = tmp_path / "preferences.json"

    learner.save(path)
    loaded = OperatorPreferenceLearner.load(path)
    nudge = loaded.nudge_for("bot.btc", "SIZE_CAP", "drawdown_guard", now=now)

    assert loaded.half_life_days == 7
    assert nudge is not None
    assert nudge.score == -1.0
    assert nudge.sample_count == 1
