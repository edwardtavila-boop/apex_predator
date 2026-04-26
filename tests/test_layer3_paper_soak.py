"""Tests for ``eta_engine/scripts/layer3_paper_soak.py``.

Pin the contract gate 8 (``paper_soak_min_weeks``) of the layer-3
promotion gate consumes:

  * weeks_clean is continuous trailing duration since the most recent
    invalidating event (kill_switch or broker_error)
  * Empty journal -> weeks_clean = 0
  * Journal with no invalidating events -> weeks_clean = full span
  * Kill-switch event resets weeks_clean to "time since the trip"
  * rejection events are informational and DO NOT reset weeks_clean
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOAK_PATH = REPO_ROOT / "eta_engine" / "scripts" / "layer3_paper_soak.py"


@pytest.fixture(scope="module")
def soak_mod():
    spec = importlib.util.spec_from_file_location(
        "layer3_paper_soak_for_test", SOAK_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["layer3_paper_soak_for_test"] = module
    spec.loader.exec_module(module)
    return module


def _ev(kind: str, days_ago: int, *, now: datetime | None = None, **extra) -> dict:
    """Build a synthetic journal event N days before ``now``."""
    if now is None:
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    ts = now - timedelta(days=days_ago)
    e = {"ts_utc": ts.isoformat(), "kind": kind}
    e.update(extra)
    return e


# ---------------------------------------------------------------------------
# Empty / missing
# ---------------------------------------------------------------------------


def test_empty_events_yields_zero_weeks_clean(soak_mod) -> None:
    summary = soak_mod.compute_summary([])
    assert summary.weeks_clean == 0.0
    assert summary.n_ticks == 0
    assert summary.start_date_utc is None
    assert summary.end_date_utc is None


def test_missing_journal_returns_zero_summary(soak_mod, tmp_path: Path) -> None:
    """If the journal file doesn't exist, the harness writes a
    zero-weeks summary (so the gate sees NO_DATA -> can decide HOLD)."""
    journal = tmp_path / "missing.jsonl"
    output = tmp_path / "soak.json"
    rc = soak_mod.main([
        "--journal", str(journal),
        "--output", str(output),
        "--quiet",
    ])
    assert rc == 0
    assert output.exists()
    data = json.loads(output.read_text())
    assert data["weeks_clean"] == 0.0


# ---------------------------------------------------------------------------
# Clean weeks counting
# ---------------------------------------------------------------------------


def test_two_clean_weeks_no_invalidating_events(soak_mod) -> None:
    """14 days of ticks with NO kill_switch / broker_error -> weeks_clean ~= 2."""
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    events = [
        _ev("tick", 14, now=now),
        _ev("tick", 7, now=now),
        _ev("fill", 5, now=now, symbol="MBT"),
        _ev("tick", 0, now=now),
    ]
    summary = soak_mod.compute_summary(events, now=now)
    assert summary.weeks_clean == pytest.approx(2.0, abs=0.01)
    assert summary.n_ticks == 3
    assert summary.n_fills == 1
    assert summary.kill_switch_trips == 0


def test_kill_switch_event_resets_weeks_clean(soak_mod) -> None:
    """Kill switch trip 3 days ago -> weeks_clean = ~3/7 = ~0.43."""
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    events = [
        _ev("tick", 14, now=now),
        _ev("kill_switch", 3, now=now, reason="test trip"),
        _ev("tick", 0, now=now),
    ]
    summary = soak_mod.compute_summary(events, now=now)
    expected = 3.0 / 7.0
    assert summary.weeks_clean == pytest.approx(expected, abs=0.01)
    assert summary.kill_switch_trips == 1
    assert summary.last_invalidating_event is not None
    assert summary.last_invalidating_event["kind"] == "kill_switch"


def test_broker_error_also_resets(soak_mod) -> None:
    """Broker error 5 days ago -> weeks_clean = ~5/7 = ~0.71."""
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    events = [
        _ev("tick", 30, now=now),
        _ev("broker_error", 5, now=now, venue="ibkr", reason="connection drop"),
        _ev("tick", 0, now=now),
    ]
    summary = soak_mod.compute_summary(events, now=now)
    expected = 5.0 / 7.0
    assert summary.weeks_clean == pytest.approx(expected, abs=0.01)
    assert summary.broker_errors == 1


def test_rejection_does_not_reset_weeks(soak_mod) -> None:
    """Gate-chain rejections are routine -- they don't invalidate the soak."""
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    events = [
        _ev("tick", 14, now=now),
        _ev("rejection", 7, now=now, reason="heat_budget"),
        _ev("rejection", 5, now=now, reason="correlation_cap"),
        _ev("tick", 0, now=now),
    ]
    summary = soak_mod.compute_summary(events, now=now)
    # Rejections don't reset; weeks_clean should be ~2 weeks.
    assert summary.weeks_clean == pytest.approx(2.0, abs=0.01)
    assert summary.rejections == 2
    assert summary.last_invalidating_event is None


def test_multiple_kill_switches_uses_most_recent(soak_mod) -> None:
    """If the soak has multiple invalidating events, only the LAST one
    determines weeks_clean."""
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    events = [
        _ev("kill_switch", 30, now=now, reason="old trip"),
        _ev("kill_switch", 10, now=now, reason="recent trip"),
        _ev("tick", 0, now=now),
    ]
    summary = soak_mod.compute_summary(events, now=now)
    expected = 10.0 / 7.0
    assert summary.weeks_clean == pytest.approx(expected, abs=0.01)
    assert summary.kill_switch_trips == 2
    assert (
        summary.last_invalidating_event["reason"] == "recent trip"
    )


def test_journal_io_round_trip(soak_mod, tmp_path: Path) -> None:
    """Write a JSONL journal, run the harness, verify summary matches
    in-memory computation."""
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    events = [
        _ev("tick", 14, now=now),
        _ev("fill", 7, now=now, symbol="MET"),
        _ev("tick", 0, now=now),
    ]
    journal = tmp_path / "soak.jsonl"
    journal.write_text(
        "\n".join(json.dumps(e) for e in events),
        encoding="utf-8",
    )
    output = tmp_path / "soak.json"
    rc = soak_mod.main([
        "--journal", str(journal),
        "--output", str(output),
        "--quiet",
    ])
    assert rc == 0
    on_disk = json.loads(output.read_text())
    in_mem = soak_mod.compute_summary(events, now=now).to_dict()
    # Compare common fields (now-relative may differ by sub-second; just
    # compare the structure + counts)
    for key in ("n_ticks", "n_fills", "kill_switch_trips", "broker_errors"):
        assert on_disk[key] == in_mem[key]


def test_malformed_journal_lines_skipped(soak_mod, tmp_path: Path) -> None:
    """Malformed JSON lines are skipped (don't crash the harness)."""
    journal = tmp_path / "bad.jsonl"
    journal.write_text(
        '{"ts_utc": "2026-04-01T00:00:00Z", "kind": "tick"}\n'
        "this is not json\n"
        "{not valid either\n"
        '{"ts_utc": "2026-04-15T00:00:00Z", "kind": "tick"}\n',
        encoding="utf-8",
    )
    summary = soak_mod.compute_summary(soak_mod._read_journal(journal))
    assert summary.n_ticks == 2  # only the 2 valid lines


def test_summary_to_dict_has_all_required_fields(soak_mod) -> None:
    """Gate 8 reads the artifact and pulls weeks_clean. Pin the schema."""
    events = []
    summary = soak_mod.compute_summary(events)
    d = summary.to_dict()
    expected = {
        "weeks_clean", "start_date_utc", "end_date_utc",
        "n_ticks", "n_fills", "kill_switch_trips",
        "broker_errors", "rejections", "last_invalidating_event",
    }
    assert set(d.keys()) == expected
