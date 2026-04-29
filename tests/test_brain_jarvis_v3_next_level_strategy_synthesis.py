from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from eta_engine.brain.jarvis_v3.next_level.strategy_synthesis import (
    export_specs,
    mine,
)


@dataclass(frozen=True)
class _Key:
    regime: str
    session_phase: str
    event_category: str = "none"
    binding_constraint: str = "none"


@dataclass(frozen=True)
class _Query:
    n: int
    mean_r: float | None
    win_rate: float | None


class _Graph:
    def __init__(self, buckets: dict[_Key, _Query]) -> None:
        self._buckets = buckets

    def keys(self) -> list[_Key]:
        return list(self._buckets)

    def query(self, key: _Key) -> _Query:
        return self._buckets[key]


def test_mine_emits_priority_specs_for_supported_alpha_buckets() -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    hot = _Key("TREND", "OPEN_DRIVE", event_category="CPI", binding_constraint="stand_aside")
    medium = _Key("RANGE", "AFTERNOON")
    graph = _Graph(
        {
            hot: _Query(n=40, mean_r=1.2, win_rate=0.65),
            medium: _Query(n=25, mean_r=0.75, win_rate=0.55),
            _Key("LOW_SUPPORT", "LUNCH"): _Query(n=5, mean_r=3.0, win_rate=0.9),
            _Key("LOW_EDGE", "CLOSE"): _Query(n=40, mean_r=0.1, win_rate=0.7),
        }
    )

    report = mine(graph, now=now)

    assert report.buckets_scanned == 4
    assert report.candidates_found == 2
    assert [spec.priority for spec in report.specs] == ["high", "medium"]
    assert report.specs[0].event_category == "CPI"
    assert "binding=stand_aside" in report.specs[0].hypothesis
    assert report.specs[0].id.startswith("S-TREND-OPEN_DRIVE-")


def test_mine_handles_none_metrics_as_non_candidates_and_exports_specs(tmp_path) -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    graph = _Graph({_Key("NEWS", "MORNING"): _Query(n=100, mean_r=None, win_rate=None)})
    report = mine(graph, now=now)
    out = tmp_path / "strategy_specs.json"

    export_specs(report, out)
    text = out.read_text(encoding="utf-8")

    assert report.candidates_found == 0
    assert "mined 1 buckets" in report.note
    assert '"specs": []' in text
    assert now.isoformat() in text
