"""
APEX PREDATOR  //  brain.avengers.agent_executor
================================================
Agent-CLI executors -- delegate to a full Claude Code or Codex agent
loop instead of a single inference call.

Why this exists
---------------
The ``AnthropicExecutor`` runs ONE ``messages.create()`` per dispatch.
That's correct for verdict-shaped tasks (BULL/BEAR/SKEPTIC/HISTORIAN
votes, refactor verdicts, sweep-policy diffs). It is the wrong tool
for tasks that require **multi-step tool use** -- reading a fixture
file, running a test, parsing the output, editing the file again,
re-running. Those tasks need a tool-loop runtime.

Both ``claude`` (Claude Code CLI, already installed on the VPS) and
``codex`` (OpenAI Codex CLI, also installed) provide exactly that
runtime. This module wraps each as an Avengers ``Executor`` so a
Persona can dispatch to them when the task category warrants it.

Cost model
----------
Agent CLI calls are NOT tracked by ``UsageTracker`` (which only knows
per-call ``messages.create`` cost). Wall-clock time is tracked as a
proxy. For accurate cost accounting, surface the CLI's own usage
report (Claude Code writes a session summary; Codex emits structured
events) -- left as a follow-up.

Drop-in conformance
-------------------
Both classes satisfy the existing ``brain.avengers.base.Executor``
protocol so they can be passed directly to ``Fleet(executor=...)``
or ``Persona(executor=...)`` without any other code changes.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apex_predator.brain.avengers.base import TaskEnvelope
    from apex_predator.brain.model_policy import ModelTier


# ---------------------------------------------------------------------------
# Claude Code agent executor
# ---------------------------------------------------------------------------


class ClaudeCodeAgentExecutor:
    """Spawn ``claude --print`` to run an Avengers task as a full agent loop.

    Conforms to the ``Executor`` protocol. The ``tier`` parameter is
    accepted for protocol compatibility but ignored -- Claude Code uses
    whatever model the user configured via ``claude config``.

    Parameters
    ----------
    binary_path
        Resolved on construction via ``shutil.which``. Defaults to "claude".
        On this VPS, Claude Code is on PATH for the Administrator user.
    timeout_s
        Hard wall-clock limit for the subprocess. Default 300s (5 min).
        If the agent doesn't finish in time, the call returns an error
        string instead of raising -- consistent with how Persona.dispatch
        treats executor failures (recorded as ``executor_error`` in the
        JSONL journal, not propagated).
    extra_args
        Additional CLI flags (e.g. ``["--allowedTools", "Read,Bash"]``)
        passed before the instruction string.

    Output
    ------
    Returns the subprocess stdout. On non-zero exit, returns a short
    diagnostic string starting with ``[ClaudeCodeAgentExecutor]`` so
    downstream parsers can recognize CLI failure vs Claude's own output.
    """

    def __init__(
        self,
        *,
        binary_path: str = "claude",
        timeout_s: int = 300,
        extra_args: list[str] | None = None,
    ) -> None:
        # which() returns the absolute path or None; fall back to the
        # name (subprocess.run will then use PATH at call time).
        self.binary_path = shutil.which(binary_path) or binary_path
        self.timeout_s = timeout_s
        self.extra_args = list(extra_args or [])

    def __call__(
        self,
        *,
        tier: ModelTier,
        system_prompt: str,
        user_prompt: str,
        envelope: TaskEnvelope,
    ) -> str:
        # tier is ignored on purpose -- Claude Code controls its own model.
        del tier
        instruction = self._build_instruction(system_prompt, user_prompt)
        cmd = [self.binary_path, "--print", *self.extra_args, instruction]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return (
                f"[ClaudeCodeAgentExecutor] timed out after "
                f"{self.timeout_s}s for task {envelope.task_id}"
            )
        except FileNotFoundError as exc:
            return (
                f"[ClaudeCodeAgentExecutor] binary not found "
                f"({self.binary_path}): {exc}"
            )
        except Exception as exc:  # noqa: BLE001 -- surface as a logged failure
            return f"[ClaudeCodeAgentExecutor] subprocess error: {exc!r}"

        if result.returncode != 0:
            stderr_snip = (result.stderr or "")[-300:]
            return (
                f"[ClaudeCodeAgentExecutor] exit {result.returncode} for "
                f"task {envelope.task_id}\n{stderr_snip}"
            )
        return result.stdout

    @staticmethod
    def _build_instruction(system_prompt: str, user_prompt: str) -> str:
        """Combine system + user into one prompt the agent CLI accepts.

        Claude Code's ``--print`` takes a single instruction string;
        there's no separate system field. We embed the persona role +
        task in tagged sections so the agent can distinguish them.
        """
        return (
            "<persona-role>\n"
            f"{system_prompt.strip()}\n"
            "</persona-role>\n\n"
            "<task>\n"
            f"{user_prompt.strip()}\n"
            "</task>"
        )


# ---------------------------------------------------------------------------
# Codex agent executor (P5)
# ---------------------------------------------------------------------------


class CodexAgentExecutor:
    """Spawn ``codex exec`` to run an Avengers task as an OpenAI Codex agent.

    Mirrors ``ClaudeCodeAgentExecutor`` but for the Codex CLI. Useful
    for the Robin lane when the task is mechanical coding work and the
    operator wants to spread cost across providers (Claude vs OpenAI).

    Conforms to the ``Executor`` protocol. ``tier`` is ignored; Codex
    uses its own model config (set via ``codex config``).

    On the apex_predator VPS, Codex is wired via the shared wrapper at
    ``C:\\TheFirm\\bin\\codex.cmd`` (auto-resolved via shutil.which).
    """

    def __init__(
        self,
        *,
        binary_path: str = "codex",
        timeout_s: int = 300,
        extra_args: list[str] | None = None,
    ) -> None:
        self.binary_path = shutil.which(binary_path) or binary_path
        self.timeout_s = timeout_s
        # Codex defaults to non-interactive when invoked with `exec`.
        # extra_args land between the subcommand and the instruction.
        self.extra_args = list(extra_args or [])

    def __call__(
        self,
        *,
        tier: ModelTier,
        system_prompt: str,
        user_prompt: str,
        envelope: TaskEnvelope,
    ) -> str:
        del tier
        instruction = ClaudeCodeAgentExecutor._build_instruction(
            system_prompt, user_prompt,
        )
        cmd = [self.binary_path, "exec", *self.extra_args, instruction]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return (
                f"[CodexAgentExecutor] timed out after "
                f"{self.timeout_s}s for task {envelope.task_id}"
            )
        except FileNotFoundError as exc:
            return (
                f"[CodexAgentExecutor] binary not found "
                f"({self.binary_path}): {exc}"
            )
        except Exception as exc:  # noqa: BLE001
            return f"[CodexAgentExecutor] subprocess error: {exc!r}"

        if result.returncode != 0:
            stderr_snip = (result.stderr or "")[-300:]
            return (
                f"[CodexAgentExecutor] exit {result.returncode} for "
                f"task {envelope.task_id}\n{stderr_snip}"
            )
        return result.stdout


# ---------------------------------------------------------------------------
# Fallback-chain executor (P5) -- try each in order, return first success
# ---------------------------------------------------------------------------


class FallbackChainExecutor:
    """Try a sequence of executors; return the first non-error output.

    Used to chain provider-specific executors so a transient outage on
    one provider doesn't block JARVIS. Example wiring:

        primary = AnthropicExecutor(...)
        secondary = ClaudeCodeAgentExecutor()
        last_resort = DryRunExecutor()
        chain = FallbackChainExecutor([primary, secondary, last_resort])
        Fleet(executor=chain)

    An "error" is detected by the leading ``[<ClassName>]`` diagnostic
    string convention used by the agent executors above. The Anthropic
    inference executor never returns that prefix; its errors are caught
    INSIDE the executor and re-raised, which the Persona handles.

    To force a hop to the next executor for the inference path too, the
    chain catches exceptions itself and treats them as a failure signal.
    """

    def __init__(self, executors: list[object]) -> None:
        if not executors:
            raise ValueError("FallbackChainExecutor needs at least one executor")
        self.executors = list(executors)

    def __call__(
        self,
        *,
        tier: ModelTier,
        system_prompt: str,
        user_prompt: str,
        envelope: TaskEnvelope,
    ) -> str:
        last_diag = ""
        for ex in self.executors:
            try:
                out = ex(
                    tier=tier,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    envelope=envelope,
                )
            except Exception as exc:  # noqa: BLE001 -- chain swallows + retries
                last_diag = (
                    f"[FallbackChainExecutor] {type(ex).__name__} raised: "
                    f"{exc!r}"
                )
                continue
            if isinstance(out, str) and out.startswith("[") and "]" in out[:80]:
                # Looks like an agent-CLI diagnostic (error-shaped output).
                last_diag = out
                continue
            return out
        return last_diag or "[FallbackChainExecutor] all executors failed"


__all__ = [
    "ClaudeCodeAgentExecutor",
    "CodexAgentExecutor",
    "FallbackChainExecutor",
]
