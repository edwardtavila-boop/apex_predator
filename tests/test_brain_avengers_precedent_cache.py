from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from eta_engine.brain.avengers.base import make_envelope
from eta_engine.brain.avengers.precedent_cache import PrecedentCache
from eta_engine.brain.model_policy import TaskCategory


def _journal_record(ts: datetime, goal: str, *, success: bool = True) -> dict[str, object]:
    return {
        "ts": ts.isoformat(),
        "envelope": {
            "ts": ts.isoformat(),
            "category": TaskCategory.DEBUG.value,
            "caller": "operator.edward",
            "goal": goal,
        },
        "result": {
            "success": success,
            "artifact": f"artifact for {goal}",
        },
    }


def test_precedent_cache_reuses_successful_similar_artifact(tmp_path) -> None:
    now = datetime.now(UTC)
    journal = tmp_path / "avengers.jsonl"
    journal.write_text(
        "\n".join(
            json.dumps(_journal_record(now - timedelta(hours=idx), "fix failing pytest import error"))
            for idx in range(3)
        ),
        encoding="utf-8",
    )
    cache = PrecedentCache(journal, min_similarity=0.5, min_precedents=3)
    envelope = make_envelope(category=TaskCategory.DEBUG, goal="fix failing pytest import error")

    verdict = cache.should_skip(envelope)

    assert verdict is not None
    assert verdict.confidence >= 0.5
    assert "3 successful matches" in verdict.reason
    assert "artifact for" in verdict.reused_artifact


def test_precedent_cache_requires_enough_successful_precedents(tmp_path) -> None:
    now = datetime.now(UTC)
    journal = tmp_path / "avengers.jsonl"
    journal.write_text(
        "\n".join(
            [
                json.dumps(_journal_record(now, "fix failing pytest import error", success=True)),
                json.dumps(_journal_record(now, "fix failing pytest import error", success=False)),
                "{bad json",
                json.dumps({"kind": "heartbeat"}),
            ]
        ),
        encoding="utf-8",
    )
    cache = PrecedentCache(journal, min_similarity=0.5, min_precedents=2)
    envelope = make_envelope(category=TaskCategory.DEBUG, goal="fix failing pytest import error")

    assert cache.should_skip(envelope) is None
    assert len(cache.lookup(envelope)) == 2


def test_precedent_cache_missing_journal_has_no_hits(tmp_path) -> None:
    cache = PrecedentCache(tmp_path / "missing.jsonl")
    envelope = make_envelope(category=TaskCategory.DEBUG, goal="fix failing pytest")

    assert cache.lookup(envelope) == []
    assert cache.should_skip(envelope) is None
