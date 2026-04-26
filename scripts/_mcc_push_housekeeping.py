"""APEX PREDATOR  //  scripts._mcc_push_housekeeping

Daily housekeeping for the JARVIS Master Command Center push channel:
prune dead Web-Push subscriptions that the push service has revoked.

Run via cron (see ``deploy/cron/avengers.crontab``)::

    python -m apex_predator.scripts._mcc_push_housekeeping

Algorithm
---------
1. Read ``DEAD_SUBSCRIPTIONS`` (``mcc_push_dead.jsonl``). The alert path
   in :mod:`obs.mcc_push_sender` appends to this file every time a
   :class:`pywebpush.WebPushException` returns HTTP 410 GONE.
2. Read ``PUSH_SUBSCRIPTIONS`` (``mcc_push_subscriptions.jsonl``).
3. Filter the subscriptions, dropping any whose endpoint appears in the
   dead set. Atomic-write the filtered set to a ``.tmp`` file, then
   ``os.replace`` it over the live file.
4. Truncate ``DEAD_SUBSCRIPTIONS`` (the dead-list has been consumed).

Idempotent: re-running with no new dead endpoints is a no-op.
Safe under crash mid-write: the atomic rename means either the
old subs file or the new one is on disk, never a torn write.

Exit codes
----------
* ``0`` -- always (housekeeping that finds nothing to do is success).

CLI flags
---------
* ``--dry-run``     -- print what would be pruned, write nothing.
* ``--quiet``       -- emit JSON summary only (cron-friendly).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# sys.path trick -- mirror scripts/_bot_health_probe.py so this module
# can be invoked as `python -m apex_predator.scripts._mcc_push_housekeeping`
# from a checkout that uses the symlink-into-/tmp/_pkg_root layout.
_PKG_PARENT = Path(__file__).resolve().parents[2]
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from apex_predator.obs.mcc_push_sender import (  # noqa: E402  -- after sys.path fix
    DEAD_SUBSCRIPTIONS,
    PUSH_SUBSCRIPTIONS,
)


def _load_dead_endpoints(path: Path) -> set[str]:
    """Return the set of endpoints recorded in the dead-list file."""
    if not path.exists():
        return set()
    out: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            ep = rec.get("endpoint")
            if isinstance(ep, str) and ep:
                out.add(ep)
    return out


def _load_subscriptions(path: Path) -> list[dict[str, Any]]:
    """Return every well-formed subscription record (preserving order)."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _atomic_write_subscriptions(path: Path, subs: list[dict[str, Any]]) -> None:
    """Write subs to ``path`` atomically: write to .tmp, fsync, rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = "".join(json.dumps(s) + "\n" for s in subs)
    with tmp.open("w", encoding="utf-8") as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def prune(*, dry_run: bool = False) -> dict[str, Any]:
    """Run one housekeeping cycle. Returns a summary dict."""
    dead = _load_dead_endpoints(DEAD_SUBSCRIPTIONS)
    subs_before = _load_subscriptions(PUSH_SUBSCRIPTIONS)

    if not dead:
        return {
            "dry_run": dry_run,
            "dead_count": 0,
            "subs_before": len(subs_before),
            "subs_after": len(subs_before),
            "pruned_count": 0,
            "pruned": [],
        }

    keep: list[dict[str, Any]] = []
    pruned: list[str] = []
    for s in subs_before:
        ep = s.get("endpoint")
        if isinstance(ep, str) and ep in dead:
            pruned.append(ep)
        else:
            keep.append(s)

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "dead_count": len(dead),
        "subs_before": len(subs_before),
        "subs_after": len(keep),
        "pruned_count": len(pruned),
        "pruned": pruned,
    }

    if dry_run:
        return summary

    # Only write the subs file if something actually changed; preserves
    # mtime / inode for callers that watch the file.
    if pruned:
        _atomic_write_subscriptions(PUSH_SUBSCRIPTIONS, keep)

    # Always truncate the dead-list so we don't re-process the same
    # endpoints next cycle (even when no live subscription matched --
    # the dead record is still consumed).
    with contextlib.suppress(OSError):
        DEAD_SUBSCRIPTIONS.write_text("", encoding="utf-8")

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcc-push-housekeeping",
        description=("Prune dead Web-Push subscriptions captured by obs.mcc_push_sender."),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be pruned; write nothing.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Emit only the JSON summary (cron-friendly).",
    )
    args = parser.parse_args(argv)

    summary = prune(dry_run=args.dry_run)

    if args.quiet:
        print(json.dumps(summary, separators=(",", ":")))
    else:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
