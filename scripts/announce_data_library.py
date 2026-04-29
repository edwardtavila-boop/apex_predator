"""
EVOLUTIONARY TRADING ALGO  //  scripts.announce_data_library
=============================================================
Emit the current ``data.library`` inventory as a single
``Actor.JARVIS`` event on the decision journal so JARVIS (and any
operator scanning the journal) knows what's testable without
walking the filesystem.

Designed to be re-run after data fetch jobs complete — the latest
JARVIS event with ``intent="data_inventory"`` is the canonical
"what's available right now" snapshot.

Usage::

    python -m eta_engine.scripts.announce_data_library
        [--journal var/eta_engine/state/decision_journal.jsonl]
        [--dry-run]

The dry-run flag prints the markdown summary but doesn't append the
event — useful for operator-side eyeballing before publishing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from eta_engine.scripts.workspace_roots import (  # noqa: E402
    ETA_DATA_INVENTORY_SNAPSHOT_PATH,
    ETA_RUNTIME_DECISION_JOURNAL_PATH,
    ensure_parent,
)

if TYPE_CHECKING:
    from eta_engine.data.audit import BotAudit
    from eta_engine.data.library import DataLibrary, DatasetMeta
    from eta_engine.data.requirements import DataRequirement

_DEFAULT_JOURNAL = ETA_RUNTIME_DECISION_JOURNAL_PATH
_DEFAULT_SNAPSHOT = ETA_DATA_INVENTORY_SNAPSHOT_PATH

_INTRADAY_TIMEFRAMES = frozenset({"1s", "5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "4h"})
_FRESHNESS_THRESHOLDS_DAYS = {
    "intraday": {"fresh": 2.0, "warm": 10.0},
    "daily_or_higher": {"fresh": 3.0, "warm": 14.0},
}


def _requirement_payload(req: DataRequirement) -> dict[str, Any]:
    return {
        "kind": req.kind,
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "critical": req.critical,
        "note": req.note,
    }


def _freshness_family(timeframe: str) -> str:
    return "intraday" if timeframe in _INTRADAY_TIMEFRAMES else "daily_or_higher"


def _dataset_freshness(dataset: DatasetMeta, generated_at: datetime) -> dict[str, Any]:
    now = generated_at if generated_at.tzinfo is not None else generated_at.replace(tzinfo=UTC)
    end_ts = dataset.end_ts if dataset.end_ts.tzinfo is not None else dataset.end_ts.replace(tzinfo=UTC)
    age_days = max(0.0, (now - end_ts).total_seconds() / 86_400.0)
    family = _freshness_family(dataset.timeframe)
    thresholds = _FRESHNESS_THRESHOLDS_DAYS[family]
    if age_days <= thresholds["fresh"]:
        status = "fresh"
    elif age_days <= thresholds["warm"]:
        status = "warm"
    else:
        status = "stale"
    return {
        "status": status,
        "age_days": round(age_days, 2),
        "family": family,
        "fresh_days": thresholds["fresh"],
        "warm_days": thresholds["warm"],
    }


def _dataset_payload(dataset: DatasetMeta, *, generated_at: datetime | None = None) -> dict[str, Any]:
    payload = {
        "key": dataset.key,
        "symbol": dataset.symbol,
        "timeframe": dataset.timeframe,
        "schema_kind": dataset.schema_kind,
        "rows": dataset.row_count,
        "start": dataset.start_ts.isoformat(),
        "end": dataset.end_ts.isoformat(),
        "days": round(dataset.days_span(), 2),
        "path": str(dataset.path),
    }
    if generated_at is not None:
        payload["freshness"] = _dataset_freshness(dataset, generated_at)
    return payload


def _audit_payload(audit: BotAudit, *, generated_at: datetime | None = None) -> dict[str, Any]:
    return {
        "bot_id": audit.bot_id,
        "runnable": audit.is_runnable,
        "deactivated": audit.deactivated,
        "critical_coverage_pct": round(audit.critical_coverage_pct, 2),
        "available": [
            {
                "requirement": _requirement_payload(req),
                "dataset": _dataset_payload(dataset, generated_at=generated_at),
            }
            for req, dataset in audit.available
        ],
        "missing_critical": [_requirement_payload(req) for req in audit.missing_critical],
        "missing_optional": [_requirement_payload(req) for req in audit.missing_optional],
        "sources_hint": list(audit.sources_hint),
    }


def _freshness_summary(datasets: list[DatasetMeta], generated_at: datetime) -> dict[str, Any]:
    items = [
        {
            **_dataset_payload(dataset),
            "freshness": _dataset_freshness(dataset, generated_at),
        }
        for dataset in datasets
    ]
    counts = {"fresh": 0, "warm": 0, "stale": 0}
    for item in items:
        counts[item["freshness"]["status"]] += 1
    return {
        "thresholds_days": _FRESHNESS_THRESHOLDS_DAYS,
        "counts": counts,
        "stale": [item for item in items if item["freshness"]["status"] == "stale"],
        "warm": [item for item in items if item["freshness"]["status"] == "warm"],
    }


def build_inventory_snapshot(
    lib: DataLibrary,
    audits: list[BotAudit],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the latest data inventory payload for dashboards and gates."""
    ts = generated_at or datetime.now(UTC)
    datasets = lib.list()
    dataset_payload = [_dataset_payload(dataset, generated_at=ts) for dataset in datasets]
    runnable = [a.bot_id for a in audits if a.is_runnable and not a.deactivated]
    blocked = [a for a in audits if not a.is_runnable]
    deactivated = [a.bot_id for a in audits if a.deactivated]
    return {
        "schema_version": 1,
        "generated_at": ts.isoformat(),
        "dataset_count": len(dataset_payload),
        "symbol_count": len(lib.symbols()),
        "timeframe_count": len(lib.timeframes()),
        "roots": [str(r) for r in lib.roots],
        "datasets": dataset_payload,
        "freshness": _freshness_summary(datasets, ts),
        "bot_coverage": {
            "total": len(audits),
            "runnable_count": len(runnable),
            "blocked_count": len(blocked),
            "deactivated_count": len(deactivated),
            "runnable": runnable,
            "blocked": {
                a.bot_id: {
                    "missing_critical": [_requirement_payload(r) for r in a.missing_critical],
                    "sources_hint": list(a.sources_hint),
                }
                for a in blocked
            },
            "deactivated": deactivated,
            "items": [_audit_payload(a, generated_at=ts) for a in audits],
        },
    }


def write_inventory_snapshot(path: Path, payload: dict[str, Any]) -> Path:
    """Write the latest inventory snapshot as pretty JSON."""
    ensure_parent(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    from eta_engine.data.library import default_library
    from eta_engine.obs.decision_journal import (
        Actor,
        DecisionJournal,
        JournalEvent,
        Outcome,
    )

    p = argparse.ArgumentParser(prog="announce_data_library")
    p.add_argument(
        "--journal",
        type=Path,
        default=_DEFAULT_JOURNAL,
        help="Decision journal JSONL (default: var/eta_engine/state/decision_journal.jsonl)",
    )
    p.add_argument(
        "--snapshot",
        type=Path,
        default=_DEFAULT_SNAPSHOT,
        help="Latest inventory JSON snapshot (default: var/eta_engine/state/data_inventory_latest.json)",
    )
    p.add_argument("--no-snapshot", action="store_true", help="do not write the latest JSON snapshot")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    lib = default_library()
    print(lib.summary_markdown())
    print()

    # Bot-coverage audit. Surfaces which bots can run vs which are
    # blocked on missing data feeds (especially crypto).
    from eta_engine.data.audit import audit_all
    from eta_engine.data.audit import summary_markdown as audit_summary
    audits = audit_all(library=lib)
    print(audit_summary(audits))
    print()

    if args.dry_run:
        print("(dry-run: no JARVIS event or snapshot written)")
        return 0

    inventory_snapshot = build_inventory_snapshot(lib, audits)
    payload = inventory_snapshot["datasets"]
    runnable = [a.bot_id for a in audits if a.is_runnable and not a.deactivated]
    deactivated = [a.bot_id for a in audits if a.deactivated]
    blocked = {
        a.bot_id: {
            "missing_critical": [
                {"kind": r.kind, "symbol": r.symbol, "timeframe": r.timeframe}
                for r in a.missing_critical
            ],
            "sources_hint": list(a.sources_hint),
        }
        for a in audits if not a.is_runnable
    }

    journal = DecisionJournal(args.journal)
    journal.append(
        JournalEvent(
            actor=Actor.JARVIS,
            intent="data_inventory",
            rationale=(
                f"library refreshed: {len(payload)} datasets, "
                f"{len(lib.symbols())} symbols, {len(lib.timeframes())} timeframes; "
                f"{len(runnable)}/{len(audits)} active bots runnable, "
                f"{len(blocked)} blocked on missing critical feeds, "
                f"{len(deactivated)} deactivated"
            ),
            gate_checks=[
                f"+datasets:{len(payload)}",
                f"+runnable_bots:{len(runnable)}",
                f"-blocked_bots:{len(blocked)}",
            ],
            outcome=Outcome.NOTED if not blocked else Outcome.BLOCKED,
            metadata={
                "datasets": payload,
                "roots": [str(r) for r in lib.roots],
                "runnable_bots": runnable,
                "deactivated_bots": deactivated,
                "blocked_bots": blocked,
                "freshness": inventory_snapshot["freshness"],
            },
        )
    )
    if not args.no_snapshot:
        write_inventory_snapshot(args.snapshot, inventory_snapshot)
        print(f"[announce_data_library] latest inventory snapshot written to {args.snapshot}")
    print(f"[announce_data_library] JARVIS event appended to {args.journal}")
    return 0 if not blocked else 1


if __name__ == "__main__":
    sys.exit(main())
