"""APEX PREDATOR  //  scripts._mcc_push_test

End-to-end self-test for the JARVIS Master Command Center push channel.
Fires a single Web-Push notification to every stored subscription and
prints a structured :class:`obs.mcc_push_sender.PushResult`.

Run::

    python -m apex_predator.scripts._mcc_push_test
    python -m apex_predator.scripts._mcc_push_test --severity critical \\
        --title "Self-test" --body "If you see this, push works."

Exit codes
----------
* ``0`` -- at least one subscription delivered successfully.
* ``1`` -- attempted but every send failed (deps + env + subs all
  present, but the push services rejected every payload).
* ``2`` -- nothing attempted: missing pywebpush, missing VAPID env,
  or no stored subscriptions. The ``skipped`` field of the result
  explains which.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parents[2]
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from apex_predator.obs.mcc_push_sender import send_to_all  # noqa: E402  -- after sys.path fix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcc-push-test",
        description=("Fire a single Web-Push self-test through obs.mcc_push_sender."),
    )
    parser.add_argument(
        "--severity",
        choices=("info", "warn", "critical"),
        default="info",
        help="Severity preset (drives Urgency header + TTL).",
    )
    parser.add_argument(
        "--title",
        default="MCC self-test",
        help="Notification title.",
    )
    parser.add_argument(
        "--body",
        default="If you see this, the JARVIS MCC push channel works.",
        help="Notification body.",
    )
    args = parser.parse_args(argv)

    result = send_to_all(
        severity=args.severity,
        title=args.title,
        body=args.body,
        extra={"event": "mcc_self_test"},
    )

    summary = {
        "attempted": result.attempted,
        "delivered": result.delivered,
        "failed": result.failed,
        "skipped": result.skipped,
        "dead_endpoints": result.dead_endpoints,
        "ok": result.ok,
    }
    print(json.dumps(summary, indent=2))

    if result.attempted == 0:
        return 2
    if result.delivered == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
