from __future__ import annotations

from datetime import UTC, datetime

from eta_engine.brain.jarvis_v3.kaizen import KaizenTicket
from eta_engine.brain.jarvis_v3.next_level.autopr import (
    AutoPRResult,
    Scope,
    build_agent_prompt,
    build_plan,
    estimate_scope,
    submit_plan,
)
from eta_engine.brain.model_policy import ModelTier


def _ticket(title: str, *, impact: str = "medium") -> KaizenTicket:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    return KaizenTicket(
        id="KAI-001",
        parent_retrospective_ts=now,
        title=title,
        rationale="Ship one safe improvement with tests.",
        impact=impact,
        opened_at=now,
    )


def test_estimate_scope_uses_impact_before_title_heuristics() -> None:
    assert estimate_scope(_ticket("fix typo in docs", impact="critical")) is Scope.XL
    assert estimate_scope(_ticket("rename variable", impact="large")) is Scope.L
    assert estimate_scope(_ticket("fix typo in dashboard")) is Scope.S
    assert estimate_scope(_ticket("add parser coverage")) is Scope.M


def test_build_plan_creates_self_contained_prompt_and_model_tier() -> None:
    plan = build_plan(_ticket("fix typo in dashboard"))

    assert plan.branch_name == "kaizen/kai-001"
    assert plan.scope is Scope.S
    assert plan.tier is ModelTier.HAIKU
    assert "KAIZEN TICKET KAI-001" in plan.prompt
    assert "pytest must pass" in plan.prompt
    assert plan.acceptance == ["tests pass", "ruff clean", "single-purpose change only"]


def test_submit_plan_handles_dry_run_xl_and_executor_paths() -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    dry_run = submit_plan(build_plan(_ticket("add parser coverage")), executor=None, now=now)
    xl = submit_plan(build_plan(_ticket("architecture rewrite", impact="critical")), executor=None, now=now)

    assert dry_run.success is False
    assert dry_run.message == "dry-run: no executor wired"
    assert xl.success is False
    assert "operator" in xl.message

    def executor(plan):
        return AutoPRResult(
            plan=plan,
            success=True,
            pr_url="https://example.test/pr/1",
            branch=plan.branch_name,
            ts_started=now,
            ts_finished=now,
            message="created",
        )

    plan = build_plan(_ticket("rename local variable"))
    result = submit_plan(plan, executor=executor, now=now)
    assert result.success is True
    assert result.branch == "kaizen/kai-001"
    assert build_agent_prompt(_ticket("rename local variable")).startswith("[KAIZEN TICKET")
