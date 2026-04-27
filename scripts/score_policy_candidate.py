"""JARVIS policy promotion gate -- score a candidate (Tier-1 #4, 2026-04-27).

The kaizen loop produces +1 tickets every day. Some of those tickets will
propose changes to JARVIS's decision logic ("lower min-confluence from 8.0
to 7.5"). The promotion gate is the safety brake: a candidate policy
cannot go live until it scores >= the current champion on the last 30
days of journal events.

This script implements the SCORING half of that gate. The actual
candidate-policy authoring + promotion is a separate workflow.

How it works
------------
  1. Load the last N days of decision-journal events for both:
     - what JARVIS DID with current policy v_champ
     - what JARVIS WOULD HAVE DONE with candidate v_cand (simulated)
  2. Compute per-policy aggregate metrics:
     - approval rate (too high = lax; too low = paranoid)
     - avg size_cap_mult on CONDITIONAL
     - rejection of subsequently-profitable orders ("opportunity cost")
     - approval of subsequently-losing orders ("damage cost")
     - net P&L of approved orders
  3. Print a side-by-side comparison + WIN/LOSS verdict per metric

Status: SCAFFOLD -- the candidate-simulation harness needs the policy
to be a callable (def evaluate_candidate(req, ctx) -> ActionResponse).
Once that interface is stable, this script wires up the comparison.

Usage::

    python scripts/score_policy_candidate.py --window-days 30
    python scripts/score_policy_candidate.py --candidate v18.py --champion v17.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("score_policy_candidate")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))


def load_audit_records(audit_paths: list[Path], *, since: datetime) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for p in audit_paths:
        if not p.is_file():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = rec.get("ts")
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                if ts >= since:
                    records.append(rec)
        except OSError:
            continue
    return records


def champion_metrics(records: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate metrics from existing audit records (the champion)."""
    if not records:
        return {"total": 0, "approval_rate": 0.0, "avg_cap": 1.0}
    total = len(records)
    approved = sum(1 for r in records if (r.get("response", {}) or {}).get("verdict") == "APPROVED")
    cond_caps = [
        (r.get("response", {}) or {}).get("size_cap_mult")
        for r in records
        if (r.get("response", {}) or {}).get("verdict") == "CONDITIONAL"
    ]
    cond_caps = [c for c in cond_caps if isinstance(c, (int, float))]
    return {
        "total": total,
        "approved": approved,
        "approval_rate": round(approved / total, 4),
        "avg_cap": round(sum(cond_caps) / len(cond_caps), 4) if cond_caps else 1.0,
        "denied": sum(1 for r in records if (r.get("response", {}) or {}).get("verdict") == "DENIED"),
        "deferred": sum(1 for r in records if (r.get("response", {}) or {}).get("verdict") == "DEFERRED"),
        "conditional": len(cond_caps),
    }


def candidate_metrics(records: list[dict[str, Any]], *, candidate_module: str | None) -> dict[str, float]:
    """Replay records through a candidate policy and aggregate.

    SCAFFOLD: when candidate_module is None, we mirror champion metrics
    (no-op replay). When provided, we'd dynamically import the module's
    `evaluate_request_v2(req, ctx)` callable and re-evaluate every record.
    """
    if candidate_module is None:
        # No candidate -- just return champion metrics so the report
        # shows "current policy vs current policy = TIE" baseline.
        return champion_metrics(records)
    # TODO: wire in candidate evaluator. The challenge is reconstructing
    # JarvisContext from the audit record's stress_composite + session_phase
    # fields. Keep this a scaffold until a stable candidate-policy interface
    # lands.
    logger.warning("candidate replay not yet implemented; returning champion baseline")
    return champion_metrics(records)


def compare(champ: dict[str, float], cand: dict[str, float]) -> dict[str, str]:
    verdicts: dict[str, str] = {}
    # higher-is-better metrics: approval_rate (within reason), total
    # lower-is-better: denied count
    # cap should be HIGHER (more permissive) only if it IMPROVES outcomes
    if cand["total"] > champ["total"]:
        verdicts["total"] = "WIN"
    elif cand["total"] < champ["total"]:
        verdicts["total"] = "LOSS"
    else:
        verdicts["total"] = "TIE"

    if cand["approval_rate"] > champ["approval_rate"]:
        verdicts["approval_rate"] = "WIN_higher"
    elif cand["approval_rate"] < champ["approval_rate"]:
        verdicts["approval_rate"] = "LOSS_lower"
    else:
        verdicts["approval_rate"] = "TIE"

    return verdicts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--audit-dir", type=Path,
                   default=ROOT / "state" / "jarvis_audit",
                   help="Directory containing JARVIS audit *.jsonl files")
    p.add_argument("--window-days", type=int, default=30)
    p.add_argument("--candidate", type=str, default=None,
                   help="Module path to candidate policy (scaffold; not yet wired)")
    p.add_argument("--json", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    since = datetime.now(UTC) - timedelta(days=args.window_days)
    audit_paths = list(args.audit_dir.glob("*.jsonl")) if args.audit_dir.exists() else []
    records = load_audit_records(audit_paths, since=since)

    champ = champion_metrics(records)
    cand  = candidate_metrics(records, candidate_module=args.candidate)
    verdicts = compare(champ, cand)

    if args.json:
        print(json.dumps({
            "window_days": args.window_days,
            "champion":    champ,
            "candidate":   cand,
            "verdicts":    verdicts,
        }, indent=2))
    else:
        print(f"\n  window: last {args.window_days} days  ({len(records)} records)")
        print(f"  metric           champion       candidate      verdict")
        for k in sorted(verdicts.keys()):
            print(f"  {k:<16} {champ.get(k, '-'):>12}   {cand.get(k, '-'):>12}   {verdicts[k]}")
        print()
        print("  [STATUS] candidate replay path is a SCAFFOLD -- replays as champion")
        print("  Wire a callable evaluate_request_v2(req, ctx) -> ActionResponse")
        print("  in the candidate module to enable real replay scoring.")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
