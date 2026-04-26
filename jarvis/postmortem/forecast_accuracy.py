"""
EVOLUTIONARY TRADING ALGO // jarvis.postmortem.forecast_accuracy
====================================================
Phase 5 gate: 60% precision on which-trades-fail forecast over the
last 12 weeks before any auto-apply.

Track:
    - For each post-mortem, the forecasts it produced ("trade X is
      likely to fail because spec Y is miscalibrated").
    - At the next post-mortem cycle, score whether those forecasts
      came true.
    - Maintain a rolling 12-week precision number.
    - Auto-apply path is GATED on precision >= 0.60.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class ForecastRecord:
    """One forecast: 'this scenario will happen / fail' + outcome."""

    forecast_id: str
    made_at_utc: str
    forecast_kind: str  # "trade_will_fail" | "specialist_will_be_wrong"
    target: str  # decision_id or specialist name
    horizon_days: int
    resolved: bool = False
    correct: bool | None = None
    resolved_at_utc: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ForecastAccuracyTracker:
    """JSONL-backed tracker. Each forecast is a row.

    Public API:
        tracker.record(forecast)                    # append
        tracker.resolve(forecast_id, correct=True)  # mark outcome
        tracker.precision(window_weeks=12)          # gate metric
        tracker.unresolved_due_by(now)              # what needs resolving
    """

    def __init__(self, path: Path | None = None, *, gate_precision: float = 0.60) -> None:
        self.path = path or self._default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.gate_precision = gate_precision

    @staticmethod
    def _default_path() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            base = base / "eta_engine" / "state"
        else:
            base = Path.home() / ".local" / "state" / "eta_engine"
        base = Path(os.environ.get("APEX_STATE_DIR", str(base)))
        return base / "forecast_accuracy.jsonl"

    def record(self, forecast: ForecastRecord) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(forecast.as_dict()) + "\n")

    def all(self) -> list[ForecastRecord]:
        if not self.path.exists():
            return []
        out: list[ForecastRecord] = []
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
                    ForecastRecord(
                        forecast_id=d["forecast_id"],
                        made_at_utc=d["made_at_utc"],
                        forecast_kind=d.get("forecast_kind", ""),
                        target=d.get("target", ""),
                        horizon_days=int(d.get("horizon_days", 7)),
                        resolved=bool(d.get("resolved", False)),
                        correct=d.get("correct"),
                        resolved_at_utc=d.get("resolved_at_utc", ""),
                    )
                )
        return out

    def resolve(self, forecast_id: str, *, correct: bool, now: datetime | None = None) -> bool:
        """Mark a forecast resolved. Atomic rewrite."""
        now = now or datetime.now(UTC)
        rows = self.all()
        for r in rows:
            if r.forecast_id == forecast_id:
                r.resolved = True
                r.correct = correct
                r.resolved_at_utc = now.isoformat(timespec="seconds")
                self._rewrite(rows)
                return True
        return False

    def _rewrite(self, rows: list[ForecastRecord]) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=".forecast_accuracy.", dir=str(self.path.parent))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r.as_dict()) + "\n")
            os.replace(tmp, self.path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def precision(self, *, window_weeks: int = 12, now: datetime | None = None) -> float:
        """Resolved-correct / resolved-total over the last N weeks."""
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(weeks=window_weeks)
        rows = [r for r in self.all() if r.resolved and r.correct is not None and self._made_within(r, cutoff)]
        if not rows:
            return 0.0
        correct = sum(1 for r in rows if r.correct)
        return round(correct / len(rows), 4)

    def unresolved_due_by(self, now: datetime | None = None) -> list[ForecastRecord]:
        """Return rows whose horizon is reached but not yet resolved."""
        now = now or datetime.now(UTC)
        out: list[ForecastRecord] = []
        for r in self.all():
            if r.resolved:
                continue
            try:
                made = datetime.fromisoformat(
                    r.made_at_utc.replace("Z", "+00:00"),
                )
            except ValueError:
                continue
            if now >= made + timedelta(days=r.horizon_days):
                out.append(r)
        return out

    def auto_apply_allowed(self, *, window_weeks: int = 12, now: datetime | None = None) -> tuple[bool, str]:
        """Gate primitive: should auto-apply be permitted right now?"""
        p = self.precision(window_weeks=window_weeks, now=now)
        if p >= self.gate_precision:
            return True, f"precision {p:.2%} >= gate {self.gate_precision:.0%}"
        return False, (
            f"precision {p:.2%} < gate {self.gate_precision:.0%}; auto-apply BLOCKED until precision recovers"
        )

    @staticmethod
    def _made_within(r: ForecastRecord, cutoff: datetime) -> bool:
        try:
            made = datetime.fromisoformat(r.made_at_utc.replace("Z", "+00:00"))
        except ValueError:
            return False
        return made >= cutoff
