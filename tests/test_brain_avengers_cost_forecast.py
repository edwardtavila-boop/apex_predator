from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from eta_engine.brain.avengers.cost_forecast import CostForecast


def _record(ts: datetime, *, caller: str, category: str, persona: str, cost: float) -> dict[str, object]:
    return {
        "ts": ts.isoformat(),
        "envelope": {
            "ts": ts.isoformat(),
            "caller": caller,
            "category": category,
            "goal": "unit test",
        },
        "result": {
            "persona_id": persona,
            "success": True,
            "cost_multiplier": cost,
        },
    }


def test_cost_forecast_rolls_windows_and_severity(tmp_path) -> None:
    now = datetime(2026, 4, 29, 16, 0, tzinfo=UTC)
    journal = tmp_path / "avengers.jsonl"
    journal.write_text(
        "\n".join(
            [
                json.dumps(
                    _record(
                        now - timedelta(minutes=10),
                        caller="operator.edward",
                        category="debug",
                        persona="alfred",
                        cost=1.0,
                    )
                ),
                json.dumps(
                    _record(
                        now - timedelta(hours=2),
                        caller="bot.mnq",
                        category="red_team",
                        persona="batman",
                        cost=5.0,
                    )
                ),
                json.dumps({"kind": "heartbeat"}),
                "{bad json",
            ]
        ),
        encoding="utf-8",
    )
    forecast = CostForecast(
        journal_path=journal,
        monthly_cap_usd=5.0,
        sonnet_usd_per_call=1.0,
        clock=lambda: now,
    )

    report = forecast.snapshot()

    assert report.last_hour.dispatches == 1
    assert report.last_day.dispatches == 2
    assert report.last_day.total_cost_mult == 6.0
    assert report.severity == "RED"
    assert report.top_callers[0] == ("bot.mnq", 5.0)


def test_cost_forecast_missing_journal_is_green_and_renderable(tmp_path) -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    forecast = CostForecast(journal_path=tmp_path / "missing.jsonl", clock=lambda: now)

    report = forecast.snapshot()
    rendered = forecast.render_plaintext(report)

    assert report.severity == "GREEN"
    assert report.last_day.dispatches == 0
    assert "[GREEN]" in rendered
    assert "24h: 0d" in rendered
