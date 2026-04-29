"""Write a canonical operator-blocker snapshot for automation.

The dashboard can read live status through the API, but heartbeat automation
needs a cheap file artifact it can diff between wakeups without starting a
server. This command is broker-safe: it only calls the existing read-only
operator queue summary and writes the result under the canonical workspace
state directory by default.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from eta_engine.scripts import jarvis_status, workspace_roots  # noqa: E402


def load_snapshot(path: Path) -> dict[str, Any] | None:
    """Load a prior snapshot, returning None when absent or unreadable."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def compare_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact drift summary between two snapshot payloads."""
    if previous is None:
        return {
            "previous_present": False,
            "changed": True,
            "changed_fields": ["baseline_missing"],
            "blocked_count_delta": None,
            "status_changed": None,
            "first_blocker_changed": None,
            "first_next_action_changed": None,
            "summary": "no previous operator queue snapshot",
        }

    changed_fields: list[str] = []
    blocked_count_delta = int(current.get("blocked_count") or 0) - int(previous.get("blocked_count") or 0)
    status_changed = current.get("status") != previous.get("status")
    first_blocker_changed = current.get("first_blocker_op_id") != previous.get("first_blocker_op_id")
    first_next_action_changed = current.get("first_next_action") != previous.get("first_next_action")
    if blocked_count_delta:
        changed_fields.append("blocked_count")
    if status_changed:
        changed_fields.append("status")
    if first_blocker_changed:
        changed_fields.append("first_blocker_op_id")
    if first_next_action_changed:
        changed_fields.append("first_next_action")
    changed = bool(changed_fields)
    summary = (
        "operator queue drift detected: " + ", ".join(changed_fields)
        if changed
        else "operator queue unchanged"
    )
    return {
        "previous_present": True,
        "changed": changed,
        "changed_fields": changed_fields,
        "blocked_count_delta": blocked_count_delta,
        "status_changed": status_changed,
        "first_blocker_changed": first_blocker_changed,
        "first_next_action_changed": first_next_action_changed,
        "previous": {
            "status": previous.get("status"),
            "blocked_count": previous.get("blocked_count"),
            "first_blocker_op_id": previous.get("first_blocker_op_id"),
            "first_next_action": previous.get("first_next_action"),
            "generated_at": previous.get("generated_at"),
        },
        "summary": summary,
    }


def default_previous_path_for(path: Path) -> Path:
    """Return the previous-snapshot path paired with ``path``."""
    if path == workspace_roots.ETA_OPERATOR_QUEUE_SNAPSHOT_PATH:
        return workspace_roots.ETA_OPERATOR_QUEUE_PREVIOUS_SNAPSHOT_PATH
    return path.with_name(f"{path.stem}.previous{path.suffix}")


def build_snapshot(*, limit: int = 5) -> dict[str, Any]:
    """Return the canonical automation snapshot payload."""
    queue = jarvis_status.build_operator_queue_summary(limit=limit)
    summary = queue.get("summary") if isinstance(queue, dict) else {}
    top_blockers = queue.get("top_blockers") if isinstance(queue, dict) else []
    next_actions = queue.get("next_actions") if isinstance(queue, dict) else []
    blocked = int(summary.get("BLOCKED", 0)) if isinstance(summary, dict) else 0
    first_blocker = top_blockers[0] if isinstance(top_blockers, list) and top_blockers else {}
    first_op_id = first_blocker.get("op_id") if isinstance(first_blocker, dict) else None
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "jarvis_status.operator_queue",
        "status": "blocked" if blocked else "clear",
        "blocked_count": blocked,
        "first_blocker_op_id": first_op_id,
        "first_next_action": next_actions[0] if isinstance(next_actions, list) and next_actions else None,
        "operator_queue": queue,
    }


def write_snapshot(
    snapshot: dict[str, Any],
    path: Path = workspace_roots.ETA_OPERATOR_QUEUE_SNAPSHOT_PATH,
    *,
    previous_path: Path | None = workspace_roots.ETA_OPERATOR_QUEUE_PREVIOUS_SNAPSHOT_PATH,
) -> Path:
    """Atomically write ``snapshot`` to ``path`` and return the path."""
    workspace_roots.ensure_parent(path)
    if previous_path is not None and path.exists():
        workspace_roots.ensure_parent(previous_path)
        previous_tmp = previous_path.with_suffix(previous_path.suffix + ".tmp")
        previous_tmp.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        previous_tmp.replace(previous_path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _render_text(snapshot: dict[str, Any], path: Path | None) -> str:
    """Return a compact human line for logs and heartbeats."""
    target = f" -> {path}" if path is not None else ""
    first = snapshot.get("first_blocker_op_id") or "none"
    action = snapshot.get("first_next_action") or "none"
    drift = snapshot.get("drift") if isinstance(snapshot.get("drift"), dict) else {}
    drift_line = drift.get("summary") if isinstance(drift, dict) else None
    return (
        f"operator_queue_snapshot status={snapshot['status']} "
        f"blocked={snapshot['blocked_count']} first={first} next={action}"
        f"{f' drift={drift_line}' if drift_line else ''}{target}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="operator_queue_snapshot")
    parser.add_argument("--out", type=Path, default=workspace_roots.ETA_OPERATOR_QUEUE_SNAPSHOT_PATH)
    parser.add_argument("--previous", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="print JSON payload")
    parser.add_argument("--no-write", action="store_true", help="build and print without writing the artifact")
    parser.add_argument("--strict", action="store_true", help="exit 2 when blockers are present")
    args = parser.parse_args(argv)

    snapshot = build_snapshot(limit=max(1, args.limit))
    previous_path = args.previous or default_previous_path_for(args.out)
    previous = load_snapshot(args.out) or load_snapshot(previous_path)
    snapshot["drift"] = compare_snapshots(previous, snapshot)
    written_path = None if args.no_write else write_snapshot(snapshot, args.out, previous_path=previous_path)
    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))
    else:
        print(_render_text(snapshot, written_path))
    return 2 if args.strict and int(snapshot.get("blocked_count") or 0) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
