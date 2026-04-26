"""Tests for jarvis.llm_transport + jarvis.llm_audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eta_engine.jarvis import LLMAuditLog
from eta_engine.jarvis.llm_transport import (
    EchoLLMTransport,
    LLMResult,
)


# ===========================================================================
# EchoLLMTransport
# ===========================================================================
def test_echo_returns_LLMResult() -> None:
    t = EchoLLMTransport()
    r = t.complete(prompt="hello world")
    assert isinstance(r, LLMResult)
    assert "hello" in r.text or "echo" in r.text
    assert r.prompt_tokens > 0
    assert r.completion_tokens > 0


def test_echo_response_is_deterministic_for_same_prompt() -> None:
    t = EchoLLMTransport()
    r1 = t.complete(prompt="ABC", system="sys")
    r2 = t.complete(prompt="ABC", system="sys")
    # Text shape is deterministic; latency varies but token counts don't
    assert r1.text.startswith("[echo:")
    assert r2.text.startswith("[echo:")
    assert r1.prompt_tokens == r2.prompt_tokens
    assert r1.completion_tokens == r2.completion_tokens


def test_echo_request_for_json_emits_json_payload() -> None:
    t = EchoLLMTransport()
    r = t.complete(prompt="give me one. RESPOND_AS_JSON")
    parsed = json.loads(r.text)
    assert "hypothesis" in parsed
    assert "evidence" in parsed
    assert "signal" in parsed
    assert "confidence" in parsed
    assert "falsification" in parsed


def test_echo_cost_is_proportional_to_prompt_length() -> None:
    t = EchoLLMTransport()
    short = t.complete(prompt="a" * 100)
    long = t.complete(prompt="a" * 10_000)
    assert long.cost_usd > short.cost_usd
    assert long.prompt_tokens > short.prompt_tokens


def test_echo_max_tokens_caps_completion() -> None:
    t = EchoLLMTransport()
    r = t.complete(prompt="x" * 10_000, max_tokens=10)
    assert r.completion_tokens <= 10


def test_echo_request_id_is_unique_per_call() -> None:
    t = EchoLLMTransport()
    ids = {t.complete(prompt=f"p{i}").request_id for i in range(5)}
    assert len(ids) == 5


# ===========================================================================
# LLMAuditLog
# ===========================================================================
def test_audit_log_writes_one_row_per_record(tmp_path: Path) -> None:
    log = LLMAuditLog(path=tmp_path / "audit.jsonl")
    t = EchoLLMTransport()
    for i in range(3):
        r = t.complete(prompt=f"prompt {i}")
        log.record(r, prompt=f"prompt {i}", role="test")
    rows = log.read_recent(n=10)
    assert len(rows) == 3


def test_audit_log_records_role_and_decision_id(tmp_path: Path) -> None:
    log = LLMAuditLog(path=tmp_path / "audit.jsonl")
    r = EchoLLMTransport().complete(prompt="x")
    log.record(r, prompt="x", role="specialist:quant", decision_id="dec-42")
    rows = log.read_recent(n=1)
    assert rows[0].role == "specialist:quant"
    assert rows[0].decision_id == "dec-42"


def test_audit_log_truncates_long_prompts(tmp_path: Path) -> None:
    log = LLMAuditLog(path=tmp_path / "audit.jsonl", truncate_at=100)
    huge_prompt = "X" * 10_000
    r = EchoLLMTransport().complete(prompt=huge_prompt)
    log.record(r, prompt=huge_prompt, role="test")
    rows = log.read_recent(n=1)
    assert len(rows[0].prompt) <= 200  # 100 chars + truncation marker
    assert "truncated" in rows[0].prompt


def test_audit_log_caps_at_max_rows(tmp_path: Path) -> None:
    log = LLMAuditLog(path=tmp_path / "audit.jsonl", max_rows=10)
    t = EchoLLMTransport()
    for i in range(25):
        r = t.complete(prompt=f"p{i}")
        log.record(r, prompt=f"p{i}", role="r")
    rows = log.read_recent(n=100)
    assert len(rows) == 10


def test_audit_log_cost_summary_aggregates(tmp_path: Path) -> None:
    log = LLMAuditLog(path=tmp_path / "audit.jsonl")
    t = EchoLLMTransport()
    for role in ("specialist:quant", "specialist:macro", "pm"):
        for _ in range(3):
            r = t.complete(prompt="x" * 200)
            log.record(r, prompt="x" * 200, role=role)
    summary = log.cost_summary()
    assert summary["n"] == 9
    assert summary["total_cost_usd"] > 0
    assert "specialist:quant" in summary["by_role"]
    assert summary["by_role"]["pm"]["n"] == 3


def test_audit_log_corrupt_lines_skipped(tmp_path: Path) -> None:
    log = LLMAuditLog(path=tmp_path / "audit.jsonl")
    # Manually inject a bad line
    log.path.parent.mkdir(parents=True, exist_ok=True)
    log.path.write_text(
        '{"ts":"2026-04-25T00:00:00","transport":"echo","model":"x",'
        '"decision_id":"","role":"r","prompt":"","system":"","response":"",'
        '"prompt_tokens":1,"completion_tokens":1,"cost_usd":0,"latency_s":0,'
        '"request_id":"r1"}\n'
        "not-json\n"
        '{"ts":"2026-04-25T00:00:01","transport":"echo","model":"x",'
        '"decision_id":"","role":"r","prompt":"","system":"","response":"",'
        '"prompt_tokens":1,"completion_tokens":1,"cost_usd":0,"latency_s":0,'
        '"request_id":"r2"}\n',
        encoding="utf-8",
    )
    rows = log.read_recent(n=10)
    assert len(rows) == 2


def test_audit_log_default_path_uses_state_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path))
    log = LLMAuditLog()
    assert log.path.parent == tmp_path
    assert log.path.name == "llm_audit.jsonl"
