from __future__ import annotations

from eta_engine.brain.jarvis_v3.training.eval_harness import (
    aggregate_report,
    grade_exercise,
    persona_has_skill_for,
)
from eta_engine.brain.model_policy import TaskCategory


def test_grade_exercise_rewards_alfred_signature_and_budget() -> None:
    response = "## Plan\n- isolate\n## Deliverable\npatch\n## Check\npytest"
    result = grade_exercise("ALFRED", "ALF-001", TaskCategory.TEST_RUN.value, response, typical_tokens=50)

    assert result.format_ok is True
    assert result.within_budget is True
    assert result.score == 1.0
    assert result.notes == "ok"


def test_grade_exercise_flags_batman_missing_sections_and_budget_overrun() -> None:
    response = "## Thesis\n" + ("padding " * 100)
    result = grade_exercise(
        "BATMAN",
        "BAT-001",
        TaskCategory.ADVERSARIAL_REVIEW.value,
        response,
        typical_tokens=10,
    )

    assert result.format_ok is False
    assert result.within_budget is False
    assert result.score < 0.5
    assert any("missing '## Verdict'" in hit for hit in result.anti_pattern_hits)


def test_aggregate_report_and_skill_lookup_surface_calibration_targets() -> None:
    weak = grade_exercise("ROBIN", "ROB-001", TaskCategory.COMMIT_MESSAGE.value, "Sure! here is a message", 80)
    strong = grade_exercise("ALFRED", "ALF-001", TaskCategory.TEST_RUN.value, "## Plan\n## Deliverable\n## Check", 80)
    report = aggregate_report("MIXED", [weak, strong])

    assert report.n_exercises == 2
    assert report.n_passed == 1
    assert report.anti_pattern_hits >= 1
    assert "focus on" in report.recommendation
    assert persona_has_skill_for("ALFRED", TaskCategory.TEST_RUN.value) is True
    assert persona_has_skill_for("ROBIN", TaskCategory.TEST_RUN.value) is False
    assert aggregate_report("EMPTY", []).recommendation == "no exercises run"
