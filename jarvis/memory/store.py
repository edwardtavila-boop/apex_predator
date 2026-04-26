"""
EVOLUTIONARY TRADING ALGO // jarvis.memory.store
====================================
EpisodicMemory record + storage backends.

The Phase 2 schema (per the roadmap):
    decision_id, ts, regime, feature_vec, votes, objection,
    outcomes, embedding(1024)

The reference LocalMemoryStore persists rows to a single JSONL file
+ holds the rows in memory for fast iteration. Production swaps in
PgVectorMemoryStore (same Protocol surface) when pgvector is wired.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class EpisodicMemory:
    """One row in the episodic memory store.

    `embedding` is None on insert; the embedding pipeline fills it
    asynchronously (or synchronously in the local backend). `outcomes`
    is filled by OutcomeTracker at the +1/+5/+20-bar marks.
    """

    decision_id: str
    ts_utc: str
    symbol: str
    regime: str
    setup_name: str
    pm_action: str  # fire_long | fire_short | skip | abstain
    weighted_score: float
    confidence: float
    votes: dict[str, str]  # specialist name -> signal
    falsifications: list[str]
    feature_vec: dict[str, float] = field(default_factory=dict)
    outcomes: dict[str, float] = field(default_factory=dict)
    embedding: list[float] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class MemoryStore(Protocol):
    name: str

    def upsert(self, mem: EpisodicMemory) -> None: ...
    def get(self, decision_id: str) -> EpisodicMemory | None: ...
    def all(self) -> list[EpisodicMemory]: ...
    def count(self) -> int: ...


class LocalMemoryStore:
    """JSONL-backed memory store. One file under APEX_STATE_DIR/episodic_memory.jsonl.

    Inserts are append-only; updates are append-then-rewrite (cheap
    enough at <100k rows). Loaded into memory on first access for
    O(1) lookups + retrieval scans.
    """

    name = "local"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, EpisodicMemory] | None = None

    @staticmethod
    def _default_path() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            base = base / "eta_engine" / "state"
        else:
            base = Path.home() / ".local" / "state" / "eta_engine"
        base = Path(os.environ.get("APEX_STATE_DIR", str(base)))
        return base / "episodic_memory.jsonl"

    def _ensure_cache(self) -> None:
        if self._cache is not None:
            return
        cache: dict[str, EpisodicMemory] = {}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cache[d["decision_id"]] = EpisodicMemory(
                        decision_id=d["decision_id"],
                        ts_utc=d["ts_utc"],
                        symbol=d.get("symbol", ""),
                        regime=d.get("regime", ""),
                        setup_name=d.get("setup_name", ""),
                        pm_action=d.get("pm_action", ""),
                        weighted_score=float(d.get("weighted_score", 0.0)),
                        confidence=float(d.get("confidence", 0.0)),
                        votes=dict(d.get("votes", {})),
                        falsifications=list(d.get("falsifications", [])),
                        feature_vec=dict(d.get("feature_vec", {})),
                        outcomes=dict(d.get("outcomes", {})),
                        embedding=list(d["embedding"]) if d.get("embedding") is not None else None,
                    )
        self._cache = cache

    def upsert(self, mem: EpisodicMemory) -> None:
        self._ensure_cache()
        assert self._cache is not None
        self._cache[mem.decision_id] = mem
        self._rewrite()

    def get(self, decision_id: str) -> EpisodicMemory | None:
        self._ensure_cache()
        assert self._cache is not None
        return self._cache.get(decision_id)

    def all(self) -> list[EpisodicMemory]:
        self._ensure_cache()
        assert self._cache is not None
        # Sort by ts so retrieval scans see chronological order
        return sorted(self._cache.values(), key=lambda m: m.ts_utc)

    def count(self) -> int:
        self._ensure_cache()
        assert self._cache is not None
        return len(self._cache)

    def _rewrite(self) -> None:
        """Atomic rewrite of the entire file. O(N) per insert; acceptable
        until N > 100k where we'd swap in pgvector."""
        assert self._cache is not None
        rows = sorted(self._cache.values(), key=lambda m: m.ts_utc)
        fd, tmp_name = tempfile.mkstemp(prefix=".episodic_memory.", dir=str(self.path.parent))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r.as_dict()) + "\n")
            os.replace(tmp, self.path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
