"""
EVOLUTIONARY TRADING ALGO // jarvis.embargo
===============================
60-day embargo enforcer (hard rule #3: "60-day embargo data stays
untouched until final out-of-sample test").

The embargo is operator-set: a manifest at `state/embargo.json` lists
the date ranges that ANY data-loading code must refuse. The enforcer
exposes three helpers:

    is_embargoed(date)         -> bool
    raise_if_embargoed(...)    -> raises EmbargoViolation
    EmbargoEnforcer.allow_pass(operator) -> one-time bypass token

Backtest / replay code wraps its bar-loading loop with `raise_if_embargoed`.
The bypass token is used ONLY for the final OOS pass, requires an operator
confirmation via `apex confirm` typed-token.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class EmbargoWindow:
    start_iso: str  # YYYY-MM-DD
    end_iso: str  # YYYY-MM-DD
    label: str
    set_by: str
    set_at_utc: str

    def contains(self, d: date) -> bool:
        try:
            s = date.fromisoformat(self.start_iso)
            e = date.fromisoformat(self.end_iso)
        except ValueError:
            return False
        return s <= d <= e


class EmbargoViolation(RuntimeError):
    """Raised when code tries to load data inside an embargoed window."""

    def __init__(self, target_date: date, window: EmbargoWindow) -> None:
        self.target_date = target_date
        self.window = window
        super().__init__(
            f"date {target_date} is in EMBARGO window {window.start_iso}..{window.end_iso} ({window.label})"
        )


def _manifest_path() -> Path:
    base = Path(
        os.environ.get(
            "APEX_STATE_DIR",
            str(REPO_ROOT / "state"),
        )
    )
    return base / "embargo.json"


def _bypass_path() -> Path:
    return _manifest_path().with_name("embargo_bypass.json")


def load_windows() -> list[EmbargoWindow]:
    p = _manifest_path()
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out = []
    for r in rows:
        try:
            out.append(
                EmbargoWindow(
                    start_iso=r["start_iso"],
                    end_iso=r["end_iso"],
                    label=r.get("label", ""),
                    set_by=r.get("set_by", "?"),
                    set_at_utc=r.get("set_at_utc", ""),
                )
            )
        except KeyError:
            continue
    return out


def add_window(*, start_iso: str, end_iso: str, label: str, set_by: str) -> EmbargoWindow:
    """Append a new embargo window to the manifest."""
    p = _manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = load_windows()
    new = EmbargoWindow(
        start_iso=start_iso,
        end_iso=end_iso,
        label=label,
        set_by=set_by,
        set_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    rows = [asdict(w) for w in existing] + [asdict(new)]
    p.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return new


def is_embargoed(d: date | str) -> tuple[bool, EmbargoWindow | None]:
    """True iff the date is in any active embargo window. Bypass tokens
    do NOT affect this query — they're checked separately by
    raise_if_embargoed."""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return False, None
    for w in load_windows():
        if w.contains(d):
            return True, w
    return False, None


def _bypass_active(now: datetime | None = None) -> bool:
    p = _bypass_path()
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not d.get("active", False):
        return False
    expires = d.get("expires_at_utc")
    if not expires:
        return True
    try:
        exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (now or datetime.now(UTC)) < exp


def grant_bypass(*, operator: str, hours_valid: float = 4.0) -> dict:
    """Stamp a one-time embargo bypass. Operator MUST run this through
    `apex confirm` so the typed-token check applies."""
    from datetime import timedelta

    p = _bypass_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": True,
        "operator": operator,
        "stamped_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "expires_at_utc": (datetime.now(UTC) + timedelta(hours=hours_valid)).isoformat(timespec="seconds"),
    }
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def revoke_bypass() -> None:
    p = _bypass_path()
    if p.exists():
        p.unlink()


def raise_if_embargoed(d: date | str) -> None:
    """Wrap any data-loading line. Raises EmbargoViolation unless a
    valid bypass is active."""
    embargoed, window = is_embargoed(d)
    if not embargoed or window is None:
        return
    if _bypass_active():
        return
    if isinstance(d, str):
        d = date.fromisoformat(d)
    raise EmbargoViolation(d, window)
