"""Tests for Phase 5: WeeklyPostMortem + ForecastAccuracyTracker."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eta_engine.jarvis.memory import EpisodicMemory, LocalMemoryStore
from eta_engine.jarvis.postmortem import (
    ForecastAccuracyTracker,
    ForecastRecord,
    PostMortemReport,
    WeeklyPostMortem,
)


# ===========================================================================
# WeeklyPostMortem
# ===========================================================================
def _seed_week(tmp_path: Path) -> LocalMemoryStore:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    base = datetime(2026, 4, 25, tzinfo=UTC) - timedelta(days=3)
    for i in range(20):
        ts = (base + timedelta(hours=i)).isoformat(timespec="seconds")
        # Mix of wins / losses; loser bias when quant + macro both said long
        outcome = -1.5 if (i % 4 == 0) else 0.7
        s.upsert(
            EpisodicMemory(
                decision_id=f"d{i}",
                ts_utc=ts,
                symbol="MNQ",
                regime="RISK-ON",
                setup_name="ORB",
                pm_action="fire_long" if i % 2 == 0 else "fire_short",
                weighted_score=0.5,
                confidence=0.6,
                votes={"quant": "long", "macro": "long", "red_team": "neutral", "risk_manager": "neutral"}
                if i % 4 == 0
                else {"quant": "short", "macro": "short", "red_team": "neutral", "risk_manager": "neutral"},
                falsifications=["X"],
                outcomes={"+5_bars": outcome},
            )
        )
    return s


def test_post_mortem_runs_on_seeded_week(tmp_path: Path) -> None:
    s = _seed_week(tmp_path)
    pm = WeeklyPostMortem(s)
    report = pm.run(as_of=datetime(2026, 4, 25, tzinfo=UTC))
    assert isinstance(report, PostMortemReport)
    assert report.n_decisions > 0
    assert "Worst trades" in report.memo_md


def test_post_mortem_picks_worst_n_losses(tmp_path: Path) -> None:
    s = _seed_week(tmp_path)
    pm = WeeklyPostMortem(s, worst_n=3)
    report = pm.run(as_of=datetime(2026, 4, 25, tzinfo=UTC))
    assert len(report.worst_trades) <= 3


def test_post_mortem_attributes_specialist_errors(tmp_path: Path) -> None:
    s = _seed_week(tmp_path)
    pm = WeeklyPostMortem(s)
    report = pm.run(as_of=datetime(2026, 4, 25, tzinfo=UTC))
    # In the seed, every loser trade has quant + macro voting "long" while
    # the action was fire_long → both should be flagged as having voted
    # with the losing side.
    if report.worst_trades:
        assert "quant" in report.specialist_error_counts
        assert "macro" in report.specialist_error_counts


def test_post_mortem_proposes_recalibration(tmp_path: Path) -> None:
    s = _seed_week(tmp_path)
    pm = WeeklyPostMortem(s)
    report = pm.run(as_of=datetime(2026, 4, 25, tzinfo=UTC))
    if report.worst_trades:
        recalibs = [r for r in report.recommendations if r.kind == "confidence_recalibration"]
        assert recalibs
        assert recalibs[0].auto_applyable is True


def test_post_mortem_freezes_when_loss_rate_high(tmp_path: Path) -> None:
    """If >60% of decisions were losses, the recommendation list must
    contain a freeze recommendation."""
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    base = datetime(2026, 4, 25, tzinfo=UTC) - timedelta(days=2)
    for i in range(10):
        s.upsert(
            EpisodicMemory(
                decision_id=f"d{i}",
                ts_utc=(base + timedelta(hours=i)).isoformat(timespec="seconds"),
                symbol="MNQ",
                regime="RISK-ON",
                setup_name="ORB",
                pm_action="fire_long",
                weighted_score=0.5,
                confidence=0.6,
                votes={"quant": "long"},
                falsifications=["X"],
                outcomes={"+5_bars": -1.0},
            )
        )
    pm = WeeklyPostMortem(s)
    report = pm.run(as_of=datetime(2026, 4, 25, tzinfo=UTC))
    freezes = [r for r in report.recommendations if r.kind == "freeze"]
    assert freezes
    assert freezes[0].auto_applyable is False


def test_post_mortem_handles_empty_window(tmp_path: Path) -> None:
    s = LocalMemoryStore(path=tmp_path / "mem.jsonl")
    pm = WeeklyPostMortem(s)
    report = pm.run(as_of=datetime(2026, 4, 25, tzinfo=UTC))
    assert report.n_decisions == 0
    assert report.recommendations == []


def test_post_mortem_memo_is_valid_markdown(tmp_path: Path) -> None:
    s = _seed_week(tmp_path)
    pm = WeeklyPostMortem(s)
    report = pm.run(as_of=datetime(2026, 4, 25, tzinfo=UTC))
    assert report.memo_md.startswith("# Weekly Post-Mortem")
    # Hard rule #1: must explicitly state no code was modified
    assert "No code was modified" in report.memo_md


def test_post_mortem_report_serializable(tmp_path: Path) -> None:
    s = _seed_week(tmp_path)
    pm = WeeklyPostMortem(s)
    report = pm.run(as_of=datetime(2026, 4, 25, tzinfo=UTC))
    json.dumps(report.as_dict())


# ===========================================================================
# ForecastAccuracyTracker
# ===========================================================================
def test_record_then_read_back(tmp_path: Path) -> None:
    t = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl")
    t.record(
        ForecastRecord(
            forecast_id="f1",
            made_at_utc="2026-04-20T00:00:00",
            forecast_kind="trade_will_fail",
            target="d100",
            horizon_days=7,
        )
    )
    rows = t.all()
    assert len(rows) == 1
    assert rows[0].forecast_id == "f1"


def test_resolve_marks_correct(tmp_path: Path) -> None:
    t = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl")
    t.record(
        ForecastRecord(
            forecast_id="f1",
            made_at_utc="2026-04-20T00:00:00",
            forecast_kind="x",
            target="x",
            horizon_days=7,
        )
    )
    assert t.resolve("f1", correct=True)
    rows = t.all()
    assert rows[0].resolved is True
    assert rows[0].correct is True


def test_resolve_unknown_returns_false(tmp_path: Path) -> None:
    t = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl")
    assert t.resolve("nope", correct=True) is False


def test_precision_zero_with_no_resolved(tmp_path: Path) -> None:
    t = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl")
    assert t.precision() == 0.0


def test_precision_computed_over_window(tmp_path: Path) -> None:
    t = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl", gate_precision=0.6)
    now = datetime(2026, 4, 25, tzinfo=UTC)
    # 4 correct, 1 wrong, all within 12-week window
    for i in range(4):
        ts = (now - timedelta(days=2 * (i + 1))).isoformat(timespec="seconds")
        t.record(
            ForecastRecord(
                forecast_id=f"f{i}",
                made_at_utc=ts,
                forecast_kind="x",
                target="x",
                horizon_days=1,
                resolved=True,
                correct=True,
                resolved_at_utc=ts,
            )
        )
    t.record(
        ForecastRecord(
            forecast_id="fwrong",
            made_at_utc=(now - timedelta(days=1)).isoformat(timespec="seconds"),
            forecast_kind="x",
            target="x",
            horizon_days=1,
            resolved=True,
            correct=False,
            resolved_at_utc=now.isoformat(timespec="seconds"),
        )
    )
    p = t.precision(now=now)
    assert p == 0.8  # 4 of 5


def test_auto_apply_gate_blocks_below_threshold(tmp_path: Path) -> None:
    t = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl", gate_precision=0.6)
    now = datetime(2026, 4, 25, tzinfo=UTC)
    # 1 correct, 4 wrong -> precision 0.2
    t.record(
        ForecastRecord(
            forecast_id="f1",
            made_at_utc=now.isoformat(),
            forecast_kind="x",
            target="x",
            horizon_days=1,
            resolved=True,
            correct=True,
        )
    )
    for i in range(4):
        t.record(
            ForecastRecord(
                forecast_id=f"fw{i}",
                made_at_utc=now.isoformat(),
                forecast_kind="x",
                target="x",
                horizon_days=1,
                resolved=True,
                correct=False,
            )
        )
    ok, reason = t.auto_apply_allowed(now=now)
    assert ok is False
    assert "BLOCKED" in reason


def test_auto_apply_gate_allows_at_threshold(tmp_path: Path) -> None:
    t = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl", gate_precision=0.6)
    now = datetime(2026, 4, 25, tzinfo=UTC)
    # 6 correct, 4 wrong -> precision 0.6
    for i in range(6):
        t.record(
            ForecastRecord(
                forecast_id=f"fc{i}",
                made_at_utc=now.isoformat(),
                forecast_kind="x",
                target="x",
                horizon_days=1,
                resolved=True,
                correct=True,
            )
        )
    for i in range(4):
        t.record(
            ForecastRecord(
                forecast_id=f"fw{i}",
                made_at_utc=now.isoformat(),
                forecast_kind="x",
                target="x",
                horizon_days=1,
                resolved=True,
                correct=False,
            )
        )
    ok, _ = t.auto_apply_allowed(now=now)
    assert ok is True


def test_unresolved_due_by_finds_overdue(tmp_path: Path) -> None:
    t = ForecastAccuracyTracker(path=tmp_path / "fa.jsonl")
    now = datetime(2026, 4, 25, tzinfo=UTC)
    # Made 30 days ago, horizon 7 -> due 23 days ago
    t.record(
        ForecastRecord(
            forecast_id="overdue",
            made_at_utc=(now - timedelta(days=30)).isoformat(),
            forecast_kind="x",
            target="x",
            horizon_days=7,
        )
    )
    t.record(
        ForecastRecord(
            forecast_id="future",
            made_at_utc=now.isoformat(),
            forecast_kind="x",
            target="x",
            horizon_days=7,
        )
    )
    overdue = t.unresolved_due_by(now=now)
    ids = {r.forecast_id for r in overdue}
    assert ids == {"overdue"}
