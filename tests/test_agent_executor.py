"""
Tests for agent-CLI executors (P3 + P5):
  * ``ClaudeCodeAgentExecutor`` -- shells ``claude --print``
  * ``CodexAgentExecutor`` -- shells ``codex exec``
  * ``FallbackChainExecutor`` -- chain executors, return first success

All subprocess calls are mocked. No real CLI invocation -- we verify
command shape, output passthrough, error/timeout handling, and fallback
chain behavior.
"""
from __future__ import annotations

import subprocess

import pytest

from apex_predator.brain.avengers.agent_executor import (
    ClaudeCodeAgentExecutor,
    CodexAgentExecutor,
    FallbackChainExecutor,
)
from apex_predator.brain.avengers.base import (
    SubsystemId,
    TaskCategory,
    TaskEnvelope,
)
from apex_predator.brain.model_policy import ModelTier


def _envelope() -> TaskEnvelope:
    return TaskEnvelope(
        category=TaskCategory.REFACTOR,
        goal="rename foo->bar in module x",
        caller=SubsystemId.OPERATOR,
    )


# ---------------------------------------------------------------------------
# Helper: fake subprocess.CompletedProcess
# ---------------------------------------------------------------------------


def _make_completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["fake"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# ClaudeCodeAgentExecutor
# ---------------------------------------------------------------------------


def test_claude_code_executor_returns_stdout_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _make_completed(stdout="agent did the thing\n")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    exe = ClaudeCodeAgentExecutor()
    out = exe(
        tier=ModelTier.SONNET,
        system_prompt="You are ROBIN. Be terse.",
        user_prompt="Refactor foo() to bar()",
        envelope=_envelope(),
    )
    assert out == "agent did the thing\n"
    # The command should include `--print` and the combined instruction.
    assert "--print" in captured["cmd"]
    instruction = captured["cmd"][-1]
    assert "<persona-role>" in instruction
    assert "<task>" in instruction
    assert "Refactor foo()" in instruction


def test_claude_code_executor_returns_diagnostic_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _make_completed(returncode=2, stderr="bad config"),
    )
    exe = ClaudeCodeAgentExecutor()
    out = exe(
        tier=ModelTier.HAIKU,
        system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert out.startswith("[ClaudeCodeAgentExecutor] exit 2")
    assert "bad config" in out


def test_claude_code_executor_returns_diagnostic_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=10)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    exe = ClaudeCodeAgentExecutor(timeout_s=10)
    out = exe(
        tier=ModelTier.HAIKU,
        system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert out.startswith("[ClaudeCodeAgentExecutor] timed out after 10s")


def test_claude_code_executor_returns_diagnostic_on_missing_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_fnf(*args, **kwargs):
        raise FileNotFoundError("no such binary")

    monkeypatch.setattr(subprocess, "run", _raise_fnf)
    exe = ClaudeCodeAgentExecutor(binary_path="nonexistent_binary_xyz")
    out = exe(
        tier=ModelTier.HAIKU,
        system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert out.startswith("[ClaudeCodeAgentExecutor] binary not found")


def test_claude_code_executor_passes_extra_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _make_completed(stdout="ok")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    exe = ClaudeCodeAgentExecutor(extra_args=["--allowedTools", "Read,Bash"])
    exe(tier=ModelTier.SONNET, system_prompt="x", user_prompt="y",
        envelope=_envelope())
    assert "--allowedTools" in captured["cmd"]
    assert "Read,Bash" in captured["cmd"]


# ---------------------------------------------------------------------------
# CodexAgentExecutor
# ---------------------------------------------------------------------------


def test_codex_executor_uses_exec_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _make_completed(stdout="codex did it")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    exe = CodexAgentExecutor()
    out = exe(
        tier=ModelTier.HAIKU,
        system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert out == "codex did it"
    assert "exec" in captured["cmd"]


def test_codex_executor_returns_diagnostic_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _make_completed(returncode=1, stderr="api key missing"),
    )
    exe = CodexAgentExecutor()
    out = exe(
        tier=ModelTier.HAIKU,
        system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert out.startswith("[CodexAgentExecutor] exit 1")
    assert "api key missing" in out


def test_codex_executor_returns_diagnostic_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd="x", timeout=5),
        ),
    )
    exe = CodexAgentExecutor(timeout_s=5)
    out = exe(
        tier=ModelTier.HAIKU,
        system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert "timed out after 5s" in out


# ---------------------------------------------------------------------------
# FallbackChainExecutor
# ---------------------------------------------------------------------------


def test_fallback_chain_requires_at_least_one_executor() -> None:
    with pytest.raises(ValueError):
        FallbackChainExecutor([])


def test_fallback_chain_returns_first_success() -> None:
    class _GoodExecutor:
        def __call__(self, **_kwargs):
            return "primary success"

    class _SkippedExecutor:
        def __call__(self, **_kwargs):
            raise AssertionError("should not be called")

    chain = FallbackChainExecutor([_GoodExecutor(), _SkippedExecutor()])
    out = chain(
        tier=ModelTier.HAIKU, system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert out == "primary success"


def test_fallback_chain_falls_through_on_diagnostic_string() -> None:
    """An executor returning '[ClassName] error...' triggers fallback."""
    class _DiagExecutor:
        def __call__(self, **_kwargs):
            return "[ClaudeCodeAgentExecutor] exit 2\nfoo"

    class _GoodExecutor:
        def __call__(self, **_kwargs):
            return "secondary success"

    chain = FallbackChainExecutor([_DiagExecutor(), _GoodExecutor()])
    out = chain(
        tier=ModelTier.HAIKU, system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert out == "secondary success"


def test_fallback_chain_falls_through_on_exception() -> None:
    class _BoomExecutor:
        def __call__(self, **_kwargs):
            raise RuntimeError("boom")

    class _GoodExecutor:
        def __call__(self, **_kwargs):
            return "secondary success"

    chain = FallbackChainExecutor([_BoomExecutor(), _GoodExecutor()])
    out = chain(
        tier=ModelTier.HAIKU, system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    assert out == "secondary success"


def test_fallback_chain_returns_last_diag_when_all_fail() -> None:
    class _DiagExecutor:
        def __call__(self, **_kwargs):
            return "[ClaudeCodeAgentExecutor] exit 1"

    class _AnotherDiagExecutor:
        def __call__(self, **_kwargs):
            return "[CodexAgentExecutor] exit 1"

    chain = FallbackChainExecutor([_DiagExecutor(), _AnotherDiagExecutor()])
    out = chain(
        tier=ModelTier.HAIKU, system_prompt="x", user_prompt="y",
        envelope=_envelope(),
    )
    # Last diagnostic wins.
    assert "CodexAgentExecutor" in out
