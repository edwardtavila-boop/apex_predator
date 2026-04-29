from __future__ import annotations

import pytest
from pydantic import ValidationError

from eta_engine.brain.jarvis_v3.training.curriculum import (
    EXERCISES,
    Exercise,
    count_per_persona,
    exercises_for,
)
from eta_engine.brain.model_policy import TaskCategory


def test_exercises_for_filters_case_insensitively_and_by_tier() -> None:
    all_batman = exercises_for("batman")
    advanced_batman = exercises_for("BATMAN", tier="advanced")

    assert all_batman
    assert all(e.persona == "BATMAN" for e in all_batman)
    assert advanced_batman
    assert all(e.tier == "advanced" for e in advanced_batman)


def test_count_per_persona_matches_curriculum_records() -> None:
    counts = count_per_persona()

    assert counts["BATMAN"] == sum(1 for e in EXERCISES if e.persona == "BATMAN")
    assert counts["ALFRED"] == sum(1 for e in EXERCISES if e.persona == "ALFRED")
    assert counts["ROBIN"] == sum(1 for e in EXERCISES if e.persona == "ROBIN")
    assert sum(counts.values()) == len(EXERCISES)


def test_exercise_contract_rejects_underbudget_and_unknown_tier() -> None:
    with pytest.raises(ValidationError):
        Exercise(
            id="BAD",
            persona="ROBIN",
            skill=TaskCategory.LOG_PARSING,
            prompt="too short",
            typical_tokens=10,
            tier="basic",
        )

    with pytest.raises(ValidationError):
        Exercise(
            id="BAD",
            persona="ROBIN",
            skill=TaskCategory.LOG_PARSING,
            prompt="Return a concise log summary.",
            typical_tokens=100,
            tier="expert",
        )
