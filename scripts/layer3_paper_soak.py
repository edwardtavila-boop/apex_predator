"""Layer-3 paper-soak harness.

Produces ``eta_engine/reports/layer3_paper_soak.json`` -- the
artifact consumed by ``scripts/_layer3_promotion_gate.py`` gate 8
(``paper_soak_min_weeks``). The gate requires >= 2 weeks of clean
layer-3 paper soak before the layer-3 path is eligible for live
promotion.

How it works
------------
The harness reads a JSONL "soak journal" at
``docs/btc_live/broker_fleet/layer3_paper_soak.jsonl`` (operator
points the layer-3 paper runner at this path; one event per tick).
Each line is one of:

  {"ts_utc": "...", "kind": "tick",       "symbol": "MBT", ...}
  {"ts_utc": "...", "kind": "fill",       "symbol": "MBT", ...}
  {"ts_utc": "...", "kind": "kill_switch","reason": "..."}
  {"ts_utc": "...", "kind": "broker_error", "venue": "...",
                                            "reason": "..."}
  {"ts_utc": "...", "kind": "rejection",  "reason": "..."}

A "clean week" is one continuous 7-day window with NO entries of kind
``kill_switch`` or ``broker_error``. ``rejection`` events are
informational (gate-chain blocks are routine and don't reset the
soak); only kill-switch trips and broker errors invalidate the
window.

The harness counts how many trailing clean weeks the soak has
accumulated and writes the result to
``eta_engine/reports/layer3_paper_soak.json``:

    {
      "weeks_clean": 2.4,
      "start_date_utc": "2026-04-01T00:00:00Z",
      "end_date_utc":   "2026-04-26T15:00:00Z",
      "n_ticks":        14400,
      "n_fills":        37,
      "kill_switch_trips": 0,
      "broker_errors":     0,
      "rejections":        12,
      "last_invalidating_event": null
    }

Empty / missing journal -> ``weeks_clean: 0`` (gate stays NO_DATA or
FAIL until the soak runs).

Usage
-----
    python -m eta_engine.scripts.layer3_paper_soak
    python -m eta_engine.scripts.layer3_paper_soak \\
        --journal /alt/path/soak.jsonl \\
        --output  /alt/path/soak.json

Re-running with the same journal is idempotent. The gate
re-evaluates the artifact on every run.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APEX_ROOT = REPO_ROOT / "eta_engine"

DEFAULT_JOURNAL_PATH = (
    APEX_ROOT / "docs" / "btc_live" / "broker_fleet" / "layer3_paper_soak.jsonl"
)
DEFAULT_OUTPUT_PATH = APEX_ROOT / "reports" / "layer3_paper_soak.json"

# A "week" for soak-counting purposes.
WEEK_SECONDS = 7 * 24 * 3600

# Events that invalidate the soak (reset weeks_clean to 0). Other
# event kinds (tick, fill, rejection, etc.) are non-invalidating.
INVALIDATING_KINDS = frozenset({"kill_switch", "broker_error"})


@dataclass(frozen=True)
class SoakSummary:
    weeks_clean: float
    start_date_utc: str | None
    end_date_utc: str | None
    n_ticks: int
    n_fills: int
    kill_switch_trips: int
    broker_errors: int
    rejections: int
    last_invalidating_event: dict | None

    def to_dict(self) -> dict:
        return {
            "weeks_clean": self.weeks_clean,
            "start_date_utc": self.start_date_utc,
            "end_date_utc": self.end_date_utc,
            "n_ticks": self.n_ticks,
            "n_fills": self.n_fills,
            "kill_switch_trips": self.kill_switch_trips,
            "broker_errors": self.broker_errors,
            "rejections": self.rejections,
            "last_invalidating_event": self.last_invalidating_event,
        }


def _parse_ts(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp. Return None on bad input."""
    if not ts:
        return None
    try:
        # Accept both "2026-01-01T00:00:00+00:00" and "2026-01-01T00:00:00Z"
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_journal(journal_path: Path) -> list[dict]:
    """Read JSONL journal -> list of event dicts. Skips malformed lines."""
    if not journal_path.exists():
        return []
    events: list[dict] = []
    with journal_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def compute_summary(events: list[dict], *, now: datetime | None = None) -> SoakSummary:
    """From raw events compute a SoakSummary.

    ``weeks_clean`` semantics: continuous trailing duration since the
    most recent invalidating event (kill_switch / broker_error), in
    units of 7-day weeks. If no invalidating event has ever occurred,
    weeks_clean = (last_event_ts - first_event_ts) / 7 days.

    ``now`` defaults to UTC clock. Tests can pin it for determinism.
    """
    if now is None:
        now = datetime.now(UTC)

    n_ticks = sum(1 for e in events if e.get("kind") == "tick")
    n_fills = sum(1 for e in events if e.get("kind") == "fill")
    kill_switch_trips = sum(
        1 for e in events if e.get("kind") == "kill_switch"
    )
    broker_errors = sum(1 for e in events if e.get("kind") == "broker_error")
    rejections = sum(1 for e in events if e.get("kind") == "rejection")

    # First and last timestamp across all events (parsed).
    timestamps = [
        _parse_ts(e.get("ts_utc", ""))
        for e in events
    ]
    timestamps = [t for t in timestamps if t is not None]
    first_ts = min(timestamps) if timestamps else None
    last_ts = max(timestamps) if timestamps else None

    # Find the most recent invalidating event.
    invalidating = [
        e for e in events
        if e.get("kind") in INVALIDATING_KINDS
        and _parse_ts(e.get("ts_utc", "")) is not None
    ]
    invalidating.sort(key=lambda e: _parse_ts(e["ts_utc"]))
    last_inv = invalidating[-1] if invalidating else None
    last_inv_ts = _parse_ts(last_inv["ts_utc"]) if last_inv else None

    # weeks_clean: continuous duration since last invalidating event,
    # OR since the journal start if no invalidating event occurred.
    if not events or last_ts is None:
        weeks_clean = 0.0
    elif last_inv_ts is not None:
        clean_seconds = (last_ts - last_inv_ts).total_seconds()
        weeks_clean = max(0.0, clean_seconds / WEEK_SECONDS)
    elif first_ts is not None:
        clean_seconds = (last_ts - first_ts).total_seconds()
        weeks_clean = max(0.0, clean_seconds / WEEK_SECONDS)
    else:
        weeks_clean = 0.0

    return SoakSummary(
        weeks_clean=round(weeks_clean, 3),
        start_date_utc=first_ts.isoformat() if first_ts else None,
        end_date_utc=last_ts.isoformat() if last_ts else None,
        n_ticks=n_ticks,
        n_fills=n_fills,
        kill_switch_trips=kill_switch_trips,
        broker_errors=broker_errors,
        rejections=rejections,
        last_invalidating_event=last_inv,
    )


def write_summary(summary: SoakSummary, output_path: Path) -> None:
    """Write the summary JSON. Atomic via tmpfile + replace."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(summary.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    tmp.replace(output_path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument(
        "--journal", type=Path, default=DEFAULT_JOURNAL_PATH,
        help="JSONL soak journal path",
    )
    p.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_PATH,
        help="output JSON artifact path",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="suppress progress output",
    )
    args = p.parse_args(argv)

    events = _read_journal(args.journal)
    summary = compute_summary(events)
    write_summary(summary, args.output)

    if not args.quiet:
        print(f"layer-3 paper soak summary -> {args.output}")
        print(f"  weeks_clean        : {summary.weeks_clean}")
        print(f"  n_ticks            : {summary.n_ticks}")
        print(f"  n_fills            : {summary.n_fills}")
        print(f"  kill_switch_trips  : {summary.kill_switch_trips}")
        print(f"  broker_errors      : {summary.broker_errors}")
        print(f"  rejections         : {summary.rejections}")
        if summary.start_date_utc:
            print(
                f"  range              : {summary.start_date_utc} "
                f"-> {summary.end_date_utc}",
            )

    # Exit 0 always: the gate consumes the artifact, this script's job
    # is just to write it. The gate's PASS/FAIL is the operator's
    # decision tool, not this script's exit code.
    return 0


if __name__ == "__main__":
    sys.exit(main())
