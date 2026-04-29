from __future__ import annotations

import json

from eta_engine.brain.jarvis_v3.calibration import (
    PlattSigmoid,
    VerdictFeatures,
    calibrate_verdict,
    fit_from_audit,
    predict_batch,
)


def test_calibrate_verdict_penalizes_event_adjacent_high_stress() -> None:
    calm = calibrate_verdict(
        VerdictFeatures(
            verdict="APPROVED",
            stress_composite=0.1,
            sizing_mult=1.0,
            session_phase="MORNING",
        )
    )
    event = calibrate_verdict(
        VerdictFeatures(
            verdict="APPROVED",
            stress_composite=0.8,
            sizing_mult=1.0,
            session_phase="OVERNIGHT",
            event_within_1h=True,
        )
    )

    assert calm.p_correct > event.p_correct
    assert calm.score > event.score


def test_fit_from_audit_skips_bad_lines_and_counts_small_samples(tmp_path) -> None:
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        "\n".join(
            [
                "{bad json",
                json.dumps({"verdict": "APPROVED", "stress_composite": 0.2, "outcome_correct": 1}),
                json.dumps({"verdict": "DENIED", "stress_composite": 0.7, "outcome_correct": 0}),
                json.dumps({"verdict": "", "stress_composite": 0.1, "outcome_correct": 1}),
                json.dumps({"verdict": "DEFERRED", "stress_composite": 0.3}),
            ]
        ),
        encoding="utf-8",
    )

    sigmoid = fit_from_audit(audit)

    assert sigmoid.fit_samples == 2
    assert fit_from_audit(tmp_path / "missing.jsonl").fit_samples == 0


def test_predict_batch_reuses_supplied_sigmoid() -> None:
    sigmoid = PlattSigmoid(a=2.0, b=0.0, fit_samples=7)
    results = predict_batch(
        [
            VerdictFeatures(verdict="APPROVED", stress_composite=0.0),
            VerdictFeatures(verdict="DENIED", stress_composite=1.0),
        ],
        sigmoid=sigmoid,
    )

    assert [r.fit_samples for r in results] == [7, 7]
    assert results[0].p_correct > results[1].p_correct
