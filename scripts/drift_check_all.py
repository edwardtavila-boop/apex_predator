"""
EVOLUTIONARY TRADING ALGO  //  scripts.drift_check_all
======================================================
Portfolio drift check — reads ``docs/strategy_baselines.json``,
runs ``obs.drift_watchdog.run_all`` over every strategy listed,
prints a summary table, writes one ``GRADER`` event per strategy
to the decision journal.

Designed for a Windows scheduled task / cron schedule. One process
per cycle (default 1 hour). If any strategy is amber, exit 1; if
any is red, exit 2; otherwise 0. That makes the wrapper command in
the scheduled task a single line:

    schtasks /Create /SC HOURLY /TN ETA-DriftCheck /TR \
        "python -m eta_engine.scripts.drift_check_all"

Or under PowerShell with notification on non-zero exit. See
``docs/operations/drift_check_setup.md`` for the wiring.

The baselines file is ``docs/strategy_baselines.json`` by default;
override with ``--baselines path.json``. Schema:

    {
      "strategies": [
        {
          "strategy_id": "mnq_v3",
          "n_trades": 200,
          "win_rate": 0.6,
          "avg_r": 0.4,
          "r_stddev": 1.0
        },
        ...
      ]
    }

When the file is missing or empty, the script no-ops with a clear
message and exits 0 — that's the right behaviour for the very first
run (operator hasn't baselined anything yet).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


_DEFAULT_BASELINES = ROOT / "docs" / "strategy_baselines.json"
_DEFAULT_JOURNAL = ROOT / "docs" / "decision_journal.jsonl"


def main() -> int:
    from eta_engine.obs.decision_journal import DecisionJournal
    from eta_engine.obs.drift_monitor import BaselineSnapshot
    from eta_engine.obs.drift_watchdog import run_all

    p = argparse.ArgumentParser(prog="drift_check_all")
    p.add_argument("--baselines", type=Path, default=_DEFAULT_BASELINES)
    p.add_argument("--journal", type=Path, default=_DEFAULT_JOURNAL)
    p.add_argument("--last-n", type=int, default=50)
    p.add_argument("--min-trades", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.baselines.exists():
        print(f"[drift_check_all] no baselines file at {args.baselines} — skipping")
        return 0

    raw = json.loads(args.baselines.read_text(encoding="utf-8"))
    entries = raw.get("strategies") or []
    if not entries:
        print(f"[drift_check_all] {args.baselines} has zero strategies — skipping")
        return 0

    pairs: list[tuple[str, BaselineSnapshot]] = []
    for entry in entries:
        try:
            bl = BaselineSnapshot(
                strategy_id=entry["strategy_id"],
                n_trades=int(entry["n_trades"]),
                win_rate=float(entry["win_rate"]),
                avg_r=float(entry["avg_r"]),
                r_stddev=float(entry["r_stddev"]),
            )
            pairs.append((bl.strategy_id, bl))
        except (KeyError, TypeError, ValueError) as exc:
            print(f"[drift_check_all] WARN: skipping malformed baseline {entry!r}: {exc}")

    journal = DecisionJournal(args.journal)
    out = run_all(
        journal=journal,
        strategy_baselines=pairs,
        last_n=args.last_n,
        min_trades=args.min_trades,
        write_event=not args.dry_run,
    )

    rank = {"green": 0, "amber": 1, "red": 2}
    worst = 0
    print(f"{'strategy':<28} {'severity':<8} {'n':>4} {'wr':>7} {'avg_r':>8} {'reason':<40}")
    print("-" * 100)
    for sid, a in out.items():
        worst = max(worst, rank[a.severity])
        reason_first = a.reasons[0][:38] if a.reasons else ""
        print(
            f"{sid:<28} {a.severity.upper():<8} {a.n_recent:>4} "
            f"{a.recent_win_rate * 100:>6.1f}% {a.recent_avg_r:>+8.3f} {reason_first}"
        )
    if args.dry_run:
        print("\n(dry-run: no GRADER events written)")
    return worst


if __name__ == "__main__":
    sys.exit(main())
