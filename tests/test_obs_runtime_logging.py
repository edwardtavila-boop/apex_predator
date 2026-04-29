"""Direct observability coverage for runtime logging helpers."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

import eta_engine.obs.latency_tracker as latency_tracker
import eta_engine.obs.supabase_sink as supabase_sink
from eta_engine.obs.log_aggregator import get_eta_logger
from eta_engine.obs.logger import StructuredLogger


def test_latency_timer_writes_jsonl_and_daily_summary(monkeypatch, tmp_path) -> None:
    path = tmp_path / "latency" / "events.jsonl"
    monkeypatch.setattr(latency_tracker, "EVENTS_PATH", path)
    times = iter([1.0, 1.1, 1.35, 1.4])
    monkeypatch.setattr(latency_tracker.time, "time", lambda: next(times))

    timer = latency_tracker.LatencyTimer(signal_id="sig-1")
    timer.mark("signal_emitted")
    timer.mark("jarvis_verdict")
    timer.mark("venue_ack")

    assert timer.finalize() == path

    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["signal_id"] == "sig-1"
    assert row["deltas_ms"]["signal_emitted_to_jarvis_verdict"] == 100.0
    assert row["deltas_ms"]["jarvis_verdict_to_venue_ack"] == 250.0
    assert row["total_ms"] == 350.0

    summary = latency_tracker.daily_summary(since_hours=1_000_000)
    assert summary["n"] == 1
    assert summary["mean_total_ms"] == 350.0


def test_structured_logger_writes_contextual_json_and_audit(tmp_path) -> None:
    sink = tmp_path / "structured.jsonl"
    logger = StructuredLogger(
        name=f"eta_test_structured_{uuid4().hex}",
        file_sink=sink,
        level=logging.ERROR,
    ).with_context(bot="mnq")

    logger.info("filtered", ignored=True)
    logger.audit("operator override", ticket="OP-1")

    rows = [json.loads(line) for line in sink.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["level"] == "AUDIT"
    assert rows[0]["message"] == "operator override"
    assert rows[0]["bot"] == "mnq"
    assert rows[0]["ticket"] == "OP-1"


def test_eta_log_aggregator_writes_local_and_shared_json(tmp_path) -> None:
    bot_name = f"bot_{uuid4().hex}"
    aggregate_path = tmp_path / "state" / "logs" / "eta.jsonl"
    local_path = tmp_path / "logs" / "bot.log"

    logger = get_eta_logger(
        bot_name,
        local_log_path=local_path,
        aggregate_path=aggregate_path,
    )
    logger.info("opened long", extra={"price": 21450.0, "qty": 2})
    for handler in logger.handlers:
        handler.flush()

    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8").strip())
    assert aggregate["bot"] == bot_name
    assert aggregate["msg"] == "opened long"
    assert aggregate["extra"]["price"] == 21450.0
    assert "opened long" in local_path.read_text(encoding="utf-8")


def test_supabase_sink_reports_unconfigured_without_network(monkeypatch) -> None:
    monkeypatch.delenv("ETA_SUPABASE_URL", raising=False)
    monkeypatch.delenv("ETA_SUPABASE_ANON_KEY", raising=False)

    assert supabase_sink.is_configured() is False
