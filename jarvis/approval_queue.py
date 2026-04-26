"""
EVOLUTIONARY TRADING ALGO // jarvis.approval_queue
======================================
Phase 5 human gate. Recommendations from the WeeklyPostMortem land
here as PENDING; the operator approves or rejects via `apex confirm`
typed-token gate before they take effect.

Hard rule reinforced: only `confidence_recalibration` may auto-apply,
and only when ForecastAccuracyTracker.precision >= 60% over 12 weeks.
Any other kind requires explicit operator approval.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ApprovalRequest:
    request_id: str
    target: str
    kind: str
    delta: float
    rationale: str
    auto_applyable: bool
    proposed_at_utc: str
    status: str = "PENDING"  # PENDING | APPROVED | REJECTED | AUTO_APPLIED
    decided_by: str = ""
    decided_at_utc: str = ""
    decision_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ApprovalQueue:
    DEFAULT_FILENAME = "jarvis_approval_queue.jsonl"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_path() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            base = base / "eta_engine" / "state"
        else:
            base = Path.home() / ".local" / "state" / "eta_engine"
        base = Path(os.environ.get("APEX_STATE_DIR", str(base)))
        return base / ApprovalQueue.DEFAULT_FILENAME

    def all(self) -> list[ApprovalRequest]:
        if not self.path.exists():
            return []
        out: list[ApprovalRequest] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                out.append(
                    ApprovalRequest(
                        **{
                            k: d[k]
                            for k in (
                                "request_id",
                                "target",
                                "kind",
                                "delta",
                                "rationale",
                                "auto_applyable",
                                "proposed_at_utc",
                            )
                            if k in d
                        },
                        status=d.get("status", "PENDING"),
                        decided_by=d.get("decided_by", ""),
                        decided_at_utc=d.get("decided_at_utc", ""),
                        decision_note=d.get("decision_note", ""),
                    )
                )
        return out

    def pending(self) -> list[ApprovalRequest]:
        return [r for r in self.all() if r.status == "PENDING"]

    def enqueue(self, *, target: str, kind: str, delta: float, rationale: str, auto_applyable: bool) -> ApprovalRequest:
        import hashlib

        rid = hashlib.sha1(f"{target}|{kind}|{delta}|{datetime.now(UTC).isoformat()}".encode()).hexdigest()[:12]
        req = ApprovalRequest(
            request_id=rid,
            target=target,
            kind=kind,
            delta=delta,
            rationale=rationale,
            auto_applyable=auto_applyable,
            proposed_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(req.as_dict()) + "\n")
        return req

    def decide(
        self, request_id: str, *, approved: bool, operator: str, note: str = "", as_auto_apply: bool = False
    ) -> bool:
        rows = self.all()
        for r in rows:
            if r.request_id == request_id:
                r.status = "AUTO_APPLIED" if (approved and as_auto_apply) else "APPROVED" if approved else "REJECTED"
                r.decided_by = operator
                r.decided_at_utc = datetime.now(UTC).isoformat(timespec="seconds")
                r.decision_note = note
                self._rewrite(rows)
                return True
        return False

    def _rewrite(self, rows: list[ApprovalRequest]) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=".approval_queue.", dir=str(self.path.parent))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r.as_dict()) + "\n")
            os.replace(tmp, self.path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def auto_apply_eligible(
        self,
        forecast_tracker: Any,
    ) -> list[ApprovalRequest]:
        """Returns PENDING requests where:
          1. auto_applyable=True
          2. ForecastAccuracyTracker.auto_apply_allowed() == True

        The operator (via `apex confirm`) still types a token to fire.
        """
        ok, _reason = forecast_tracker.auto_apply_allowed()
        if not ok:
            return []
        return [r for r in self.pending() if r.auto_applyable]
