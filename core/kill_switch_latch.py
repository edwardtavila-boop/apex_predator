"""APEX PREDATOR  //  core.kill_switch_latch
=================================================
Persistent boot-gate latch for the kill switch.

The runtime kill switch (core.kill_switch_runtime) emits KillVerdicts on
every tick. Most are non-latching (HALVE_SIZE, FLATTEN_BOT) and clear on
the next session. But two are catastrophic enough that the operator must
manually acknowledge before the system trades again:

    * FLATTEN_ALL                 -- portfolio-wide circuit blew
    * FLATTEN_TIER_A_PREEMPTIVE   -- Apex eval account in danger of bust

This module persists those trips to disk so that:

    * a process restart cannot un-trip the latch
    * boot-up checks the latch BEFORE any venue connection
    * first-trip-wins -- the earliest catastrophic verdict is preserved
      across subsequent trips for the post-mortem record
    * a corrupt latch file is treated as TRIPPED (fail-closed)

The on-disk JSON is the source of truth. All writes are atomic
(write to .tmp, fsync, rename) so a crash mid-write cannot leave a
partial file the next boot would mis-read.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apex_predator.core.kill_switch_runtime import KillVerdict


class LatchState(StrEnum):
    ARMED = "ARMED"
    TRIPPED = "TRIPPED"


_LATCHING_ACTIONS: frozenset[str] = frozenset(
    {"FLATTEN_ALL", "FLATTEN_TIER_A_PREEMPTIVE"}
)


@dataclass
class LatchRecord:
    state: LatchState = LatchState.ARMED
    action: str | None = None
    severity: str | None = None
    reason: str | None = None
    scope: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    tripped_at_utc: str | None = None
    cleared_at_utc: str | None = None
    cleared_by: str | None = None

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> LatchRecord:
        state_raw = raw.get("state", LatchState.ARMED.value)
        return cls(
            state=LatchState(state_raw),
            action=raw.get("action"),
            severity=raw.get("severity"),
            reason=raw.get("reason"),
            scope=raw.get("scope"),
            evidence=dict(raw.get("evidence") or {}),
            tripped_at_utc=raw.get("tripped_at_utc"),
            cleared_at_utc=raw.get("cleared_at_utc"),
            cleared_by=raw.get("cleared_by"),
        )


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class KillSwitchLatch:
    """Persistent, fail-closed boot gate for catastrophic kill verdicts."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> LatchRecord:
        """Return the current latch record. Corrupt file => TRIPPED."""
        if not self.path.exists():
            return LatchRecord()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return LatchRecord(
                state=LatchState.TRIPPED,
                reason="latch file corrupt -- fail-closed",
                action="CORRUPT",
            )
        return LatchRecord.from_json(raw)

    def boot_allowed(self) -> tuple[bool, str]:
        """Return (allowed, reason). Reason is operator-readable."""
        rec = self.read()
        if rec.state == LatchState.ARMED:
            return True, "armed"
        if rec.action == "CORRUPT":
            return False, (
                "kill switch latch corrupt -- treated as TRIPPED. "
                "Run scripts.clear_kill_switch to reset after manual review."
            )
        return False, (
            f"kill switch TRIPPED: {rec.reason!r} "
            f"(action={rec.action}, scope={rec.scope}, at={rec.tripped_at_utc}). "
            f"Run scripts.clear_kill_switch to reset."
        )

    def record_verdict(self, verdict: KillVerdict) -> bool:
        """Record a verdict. Returns True iff the latch state changed.

        First-trip-wins: a second catastrophic verdict does NOT overwrite
        the original. Non-latching verdicts (HALVE_SIZE, FLATTEN_BOT,
        CONTINUE, etc.) are ignored entirely.
        """
        action_str = verdict.action.value
        if action_str not in _LATCHING_ACTIONS:
            return False

        current = self.read()
        if current.state == LatchState.TRIPPED:
            return False

        new = LatchRecord(
            state=LatchState.TRIPPED,
            action=action_str,
            severity=verdict.severity.value,
            reason=verdict.reason,
            scope=verdict.scope,
            evidence=dict(verdict.evidence or {}),
            tripped_at_utc=_utcnow(),
        )
        self._atomic_write(new)
        return True

    def clear(self, *, cleared_by: str) -> LatchRecord:
        """Reset the latch to ARMED. Preserves trip metadata for audit."""
        if not cleared_by or not cleared_by.strip():
            raise ValueError("cleared_by must be a non-empty operator name")

        current = self.read()
        # Preserve trip metadata even on corrupt read so post-mortem is
        # possible. Corrupt files have action="CORRUPT" which we drop on
        # clear since there's no real trip context to preserve.
        if current.action == "CORRUPT":
            current = LatchRecord()

        cleared = LatchRecord(
            state=LatchState.ARMED,
            action=current.action,
            severity=current.severity,
            reason=current.reason,
            scope=current.scope,
            evidence=current.evidence,
            tripped_at_utc=current.tripped_at_utc,
            cleared_at_utc=_utcnow(),
            cleared_by=cleared_by.strip(),
        )
        self._atomic_write(cleared)
        return cleared

    def _atomic_write(self, rec: LatchRecord) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(rec.to_json(), indent=2, sort_keys=True)
        with tmp.open("w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.path)
