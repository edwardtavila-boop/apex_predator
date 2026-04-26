"""
EVOLUTIONARY TRADING ALGO // jarvis.memory.healer
=====================================
Self-healing guard for the LocalMemoryStore JSONL.

Mirror of the existing ``mnq._shim_guard`` pattern: episodic memory
lives in a single JSONL that OneDrive / fsync hiccups can truncate.
The healer:

  * Validates that every line parses as JSON with the required keys.
  * Salvages all valid lines into a temp file.
  * Quarantines corrupt lines into a `.quarantine` sidecar so the
    operator can review.
  * Rewrites the original atomically with the salvaged rows.

Returns a `HealReport` describing what was done.

Wire via `EpisodicMemoryHealer.heal_if_needed()` in any startup path
that imports the memory store.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_KEYS = {"decision_id", "ts_utc", "symbol", "regime", "setup_name", "pm_action"}


@dataclass
class HealReport:
    path: str
    n_total: int = 0
    n_valid: int = 0
    n_quarantined: int = 0
    quarantine_path: str | None = None
    healed: bool = False
    detail: str = ""
    generated_at_utc: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EpisodicMemoryHealer:
    def __init__(self, store_path: Path) -> None:
        self.store_path = Path(store_path)

    def quarantine_path(self) -> Path:
        return self.store_path.with_suffix(self.store_path.suffix + ".quarantine")

    def check(self) -> HealReport:
        """Read-only inspection. Returns counts + flags."""
        report = HealReport(
            path=str(self.store_path),
            generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        if not self.store_path.exists():
            report.detail = "store does not exist; nothing to heal"
            return report
        with self.store_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                report.n_total += 1
                try:
                    d = json.loads(line)
                    if not isinstance(d, dict):
                        report.n_quarantined += 1
                        continue
                    missing = REQUIRED_KEYS - set(d)
                    if missing:
                        report.n_quarantined += 1
                        continue
                    report.n_valid += 1
                except json.JSONDecodeError:
                    report.n_quarantined += 1
        report.detail = f"{report.n_valid} valid / {report.n_quarantined} quarantine candidates"
        return report

    def heal_if_needed(self, *, dry_run: bool = False) -> HealReport:
        """Run check; if any quarantine candidates exist, atomically
        rewrite the store with only valid rows + write the bad rows to
        the quarantine sidecar."""
        report = self.check()
        if report.n_quarantined == 0:
            return report
        if dry_run:
            report.detail += " (DRY-RUN; no changes)"
            return report

        valid_lines: list[str] = []
        quarantine_lines: list[str] = []
        with self.store_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.rstrip("\n")
                if not stripped.strip():
                    continue
                try:
                    d = json.loads(stripped)
                    if isinstance(d, dict) and not (REQUIRED_KEYS - set(d)):
                        valid_lines.append(line if line.endswith("\n") else line + "\n")
                        continue
                except json.JSONDecodeError:
                    pass
                quarantine_lines.append(line if line.endswith("\n") else line + "\n")

        # Write quarantine sidecar
        qp = self.quarantine_path()
        with qp.open("a", encoding="utf-8") as f:
            f.write(f"# === healed at {report.generated_at_utc} ===\n")
            for ln in quarantine_lines:
                f.write(ln)

        # Atomic rewrite
        fd, tmp_name = tempfile.mkstemp(prefix=".memory_heal.", dir=str(self.store_path.parent))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(valid_lines)
            os.replace(tmp, self.store_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        report.healed = True
        report.quarantine_path = str(qp)
        report.detail += f" (quarantined to {qp.name})"
        return report
