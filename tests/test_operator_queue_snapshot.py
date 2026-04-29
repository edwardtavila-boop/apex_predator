from __future__ import annotations

import json

from eta_engine.scripts import jarvis_status, operator_queue_snapshot


def test_build_snapshot_summarizes_top_blocker(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        jarvis_status,
        "build_operator_queue_summary",
        lambda **_kwargs: {
            "summary": {"BLOCKED": 2, "OBSERVED": 1, "UNKNOWN": 0, "DONE": 0},
            "top_blockers": [{"op_id": "OP-18", "title": "Resolve DR blockers"}],
            "next_actions": ["cp .env.example .env && chmod 600 .env"],
            "error": None,
        },
    )

    snapshot = operator_queue_snapshot.build_snapshot(limit=3)

    assert snapshot["schema_version"] == 1
    assert snapshot["source"] == "jarvis_status.operator_queue"
    assert snapshot["status"] == "blocked"
    assert snapshot["blocked_count"] == 2
    assert snapshot["first_blocker_op_id"] == "OP-18"
    assert snapshot["first_next_action"] == "cp .env.example .env && chmod 600 .env"


def test_write_snapshot_uses_atomic_temp_then_target(tmp_path) -> None:
    target = tmp_path / "state" / "operator_queue_snapshot.json"
    snapshot = {
        "schema_version": 1,
        "generated_at": "2026-04-29T00:00:00+00:00",
        "source": "test",
        "status": "clear",
        "blocked_count": 0,
        "operator_queue": {"summary": {"BLOCKED": 0}},
    }

    written = operator_queue_snapshot.write_snapshot(snapshot, target, previous_path=tmp_path / "previous.json")

    assert written == target
    assert not target.with_suffix(".json.tmp").exists()
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "clear"


def test_write_snapshot_preserves_previous_target(tmp_path) -> None:
    target = tmp_path / "state" / "operator_queue_snapshot.json"
    previous = tmp_path / "state" / "operator_queue_snapshot.previous.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "blocked",
                "blocked_count": 3,
                "first_blocker_op_id": "OP-18",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    operator_queue_snapshot.write_snapshot(
        {
            "schema_version": 1,
            "generated_at": "2026-04-29T00:01:00+00:00",
            "source": "test",
            "status": "clear",
            "blocked_count": 0,
        },
        target,
        previous_path=previous,
    )

    assert json.loads(previous.read_text(encoding="utf-8"))["blocked_count"] == 3
    assert json.loads(target.read_text(encoding="utf-8"))["blocked_count"] == 0


def test_compare_snapshots_reports_changed_fields() -> None:
    previous = {
        "status": "blocked",
        "blocked_count": 2,
        "first_blocker_op_id": "OP-18",
        "first_next_action": "old",
    }
    current = {
        "status": "blocked",
        "blocked_count": 3,
        "first_blocker_op_id": "OP-18",
        "first_next_action": "new",
    }

    drift = operator_queue_snapshot.compare_snapshots(previous, current)

    assert drift["previous_present"] is True
    assert drift["changed"] is True
    assert drift["blocked_count_delta"] == 1
    assert drift["changed_fields"] == ["blocked_count", "first_next_action"]


def test_compare_snapshots_reports_unchanged() -> None:
    previous = {
        "status": "blocked",
        "blocked_count": 2,
        "first_blocker_op_id": "OP-18",
        "first_next_action": "same",
    }
    current = dict(previous)

    drift = operator_queue_snapshot.compare_snapshots(previous, current)

    assert drift["changed"] is False
    assert drift["changed_fields"] == []
    assert drift["summary"] == "operator queue unchanged"


def test_custom_out_uses_sibling_previous_path(tmp_path) -> None:
    target = tmp_path / "custom_snapshot.json"

    previous = operator_queue_snapshot.default_previous_path_for(target)

    assert previous == tmp_path / "custom_snapshot.previous.json"


def test_main_no_write_json_does_not_create_default(monkeypatch, capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "operator_queue_snapshot.json"
    monkeypatch.setattr(
        jarvis_status,
        "build_operator_queue_summary",
        lambda **_kwargs: {
            "summary": {"BLOCKED": 0},
            "top_blockers": [],
            "next_actions": [],
            "error": None,
        },
    )

    rc = operator_queue_snapshot.main(["--out", str(target), "--json", "--no-write"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "clear"
    assert payload["drift"]["previous_present"] is False
    assert not target.exists()


def test_main_strict_returns_two_when_blocked(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        jarvis_status,
        "build_operator_queue_summary",
        lambda **_kwargs: {
            "summary": {"BLOCKED": 1},
            "top_blockers": [{"op_id": "OP-18"}],
            "next_actions": ["fix it"],
            "error": None,
        },
    )

    rc = operator_queue_snapshot.main(["--out", str(tmp_path / "snapshot.json"), "--strict"])

    assert rc == 2
