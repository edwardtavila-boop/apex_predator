from __future__ import annotations

import json

from eta_engine.scripts import jarvis_status, operator_queue_heartbeat


def _queue(blocked: int, *, op_id: str | None = "OP-18", action: str | None = "fix it") -> dict[str, object]:
    blockers = [{"op_id": op_id}] if op_id else []
    actions = [action] if action else []
    return {
        "summary": {"BLOCKED": blocked},
        "top_blockers": blockers,
        "next_actions": actions,
        "error": None,
    }


def test_build_heartbeat_marks_notify_from_drift() -> None:
    heartbeat = operator_queue_heartbeat.build_heartbeat(
        {
            "generated_at": "2026-04-29T00:00:00+00:00",
            "status": "blocked",
            "blocked_count": 2,
            "first_blocker_op_id": "OP-18",
            "first_next_action": "fix it",
            "drift": {
                "changed": True,
                "summary": "operator queue drift detected: blocked_count",
                "changed_fields": ["blocked_count"],
                "blocked_count_delta": 1,
            },
        },
        None,
    )

    assert heartbeat["notify"] is True
    assert heartbeat["drift_changed"] is True
    assert heartbeat["changed_fields"] == ["blocked_count"]
    assert heartbeat["blocked_count_delta"] == 1


def test_main_changed_only_suppresses_unchanged_output(monkeypatch, capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "operator_queue_snapshot.json"
    target.write_text(
        json.dumps(
            {
                "status": "blocked",
                "blocked_count": 1,
                "first_blocker_op_id": "OP-18",
                "first_next_action": "fix it",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(jarvis_status, "build_operator_queue_summary", lambda **_kwargs: _queue(1))

    rc = operator_queue_heartbeat.main(["--out", str(target), "--changed-only"])

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_main_changed_only_emits_json_when_drift_changes(monkeypatch, capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "operator_queue_snapshot.json"
    target.write_text(
        json.dumps(
            {
                "status": "blocked",
                "blocked_count": 1,
                "first_blocker_op_id": "OP-18",
                "first_next_action": "fix it",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(jarvis_status, "build_operator_queue_summary", lambda **_kwargs: _queue(2))

    rc = operator_queue_heartbeat.main(["--out", str(target), "--changed-only", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["notify"] is True
    assert payload["changed_fields"] == ["blocked_count"]
    assert payload["blocked_count_delta"] == 1


def test_main_strict_drift_returns_three(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "operator_queue_snapshot.json"
    target.write_text(
        json.dumps(
            {
                "status": "clear",
                "blocked_count": 0,
                "first_blocker_op_id": None,
                "first_next_action": None,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(jarvis_status, "build_operator_queue_summary", lambda **_kwargs: _queue(1))

    rc = operator_queue_heartbeat.main(["--out", str(target), "--strict-drift"])

    assert rc == 3


def test_main_strict_blockers_returns_two(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(jarvis_status, "build_operator_queue_summary", lambda **_kwargs: _queue(1))

    rc = operator_queue_heartbeat.main(["--out", str(tmp_path / "snapshot.json"), "--strict-blockers"])

    assert rc == 2
