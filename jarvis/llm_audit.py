"""
EVOLUTIONARY TRADING ALGO // jarvis.llm_audit
=================================
Append-only JSONL log of every LLM call. Closes hard rule #4
("every LLM call is logged with prompt + response + cost for replay
and audit").

Schema per row:
    ts                  ISO-8601 UTC
    transport           "echo" | "batman" | future
    model               provider's model id
    decision_id         optional caller-provided correlation id
    role                "specialist:<name>" | "pm" | "post_mortem" | ...
    prompt              full prompt (may be truncated; see truncate_at)
    system              full system prompt (or "")
    response            full text
    prompt_tokens       int
    completion_tokens   int
    cost_usd            float (0.0 if transport doesn't surface cost)
    latency_s           float
    request_id          provider's request id (or our hash)

Bounded by `max_rows` rotation (default 5000). Combined with state
retention (#27), file stays under ~50MB on a multi-month deployment.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eta_engine.jarvis.llm_transport import LLMResult


@dataclass(frozen=True)
class LLMAuditRow:
    ts: str
    transport: str
    model: str
    decision_id: str
    role: str
    prompt: str
    system: str
    response: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_s: float
    request_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class LLMAuditLog:
    """Per-process audit-log writer.

    Construct ONCE per process (or per JarvisRuntime); call
    ``record(...)`` after every LLM call. Cheap to call — single
    appended line, fsync skipped (state retention sweeper handles
    durability via daily archiving).
    """

    DEFAULT_FILENAME = "llm_audit.jsonl"
    DEFAULT_MAX_ROWS = 5000

    def __init__(
        self,
        path: Path | None = None,
        *,
        max_rows: int = DEFAULT_MAX_ROWS,
        truncate_at: int = 4000,
    ) -> None:
        self.path = path or self._default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_rows = max_rows
        self.truncate_at = truncate_at

    @staticmethod
    def _default_path() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            base = base / "eta_engine" / "state"
        else:
            base = Path.home() / ".local" / "state" / "eta_engine"
        base = Path(os.environ.get("APEX_STATE_DIR", str(base)))
        return base / LLMAuditLog.DEFAULT_FILENAME

    @staticmethod
    def _truncate(s: str, limit: int) -> str:
        if len(s) <= limit:
            return s
        return s[:limit] + f" ... [truncated {len(s) - limit} chars]"

    def record(
        self,
        result: LLMResult,
        *,
        prompt: str,
        system: str = "",
        decision_id: str = "",
        role: str = "unknown",
    ) -> LLMAuditRow:
        row = LLMAuditRow(
            ts=datetime.now(UTC).isoformat(timespec="seconds"),
            transport=str(result.raw.get("transport", "?")) if isinstance(result.raw, dict) else "?",
            model=result.model,
            decision_id=decision_id,
            role=role,
            prompt=self._truncate(prompt, self.truncate_at),
            system=self._truncate(system, self.truncate_at),
            response=self._truncate(result.text, self.truncate_at),
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cost_usd=result.cost_usd,
            latency_s=result.latency_s,
            request_id=result.request_id,
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row.as_dict()) + "\n")
        self._maybe_trim()
        return row

    def _maybe_trim(self) -> None:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return
        if len(lines) <= self.max_rows:
            return
        keep = lines[-self.max_rows :]
        fd, tmp = tempfile.mkstemp(prefix=".llm_audit.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(keep)
            os.replace(tmp, self.path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise

    def read_recent(self, n: int = 50) -> list[LLMAuditRow]:
        if not self.path.exists():
            return []
        out: list[LLMAuditRow] = []
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
                    LLMAuditRow(
                        ts=d.get("ts", ""),
                        transport=d.get("transport", "?"),
                        model=d.get("model", "?"),
                        decision_id=d.get("decision_id", ""),
                        role=d.get("role", ""),
                        prompt=d.get("prompt", ""),
                        system=d.get("system", ""),
                        response=d.get("response", ""),
                        prompt_tokens=int(d.get("prompt_tokens", 0)),
                        completion_tokens=int(d.get("completion_tokens", 0)),
                        cost_usd=float(d.get("cost_usd", 0.0)),
                        latency_s=float(d.get("latency_s", 0.0)),
                        request_id=d.get("request_id", ""),
                    )
                )
        out.reverse()
        return out[:n]

    def cost_summary(self, *, last_n: int = 1000) -> dict:
        rows = self.read_recent(n=last_n)
        if not rows:
            return {"n": 0, "total_cost_usd": 0.0, "by_role": {}, "by_model": {}}
        by_role: dict[str, dict] = {}
        by_model: dict[str, dict] = {}
        for r in rows:
            for bucket, key in ((by_role, r.role), (by_model, r.model)):
                b = bucket.setdefault(key, {"n": 0, "cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0})
                b["n"] += 1
                b["cost_usd"] = round(b["cost_usd"] + r.cost_usd, 6)
                b["prompt_tokens"] += r.prompt_tokens
                b["completion_tokens"] += r.completion_tokens
        return {
            "n": len(rows),
            "total_cost_usd": round(sum(r.cost_usd for r in rows), 6),
            "by_role": by_role,
            "by_model": by_model,
        }
