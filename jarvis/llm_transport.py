"""
EVOLUTIONARY TRADING ALGO // jarvis.llm_transport
=====================================
LLM call abstraction. Every LLM-backed reasoning operation goes through
a `LLMTransport` so tests are deterministic and the audit log captures
prompt/response/cost in one place (hard rule #4).

Two reference implementations:
    EchoLLMTransport  — deterministic, no external calls. Returns a
                        templated response derived from the prompt
                        (suitable for tests + dev environments where
                        no API key is configured).
    BatmanLLMTransport — adapter that routes through the existing
                         ``jarvis_identity/batman/batman_bridge.py``
                         pipeline (VPS-local claude → eta queue → API).

Production wiring picks one via a factory in ``eta_engine.brain.model_policy``;
tests inject EchoLLMTransport directly.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMResult:
    """Structured response from any LLMTransport.

    Cost is in USD. Latency is wall-clock seconds. ``raw`` is the
    underlying provider-specific response shape; callers should treat
    it as opaque except for diagnostics.
    """

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_s: float
    raw: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""


@runtime_checkable
class LLMTransport(Protocol):
    """Synchronous LLM call surface. Async batching wraps multiple calls."""

    name: str  # human-readable identifier for the audit log

    def complete(
        self,
        *,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model_hint: str | None = None,
    ) -> LLMResult: ...


# ---------------------------------------------------------------------------
# Reference implementation: deterministic echo
# ---------------------------------------------------------------------------
class EchoLLMTransport:
    """Returns a deterministic response derived from the prompt.

    The response shape matches what real Claude returns enough that
    Pydantic-validated specialists can parse it. Cost + latency are
    synthesized from prompt length so cost-tracking tests have signal.

    Usage in tests:

        transport = EchoLLMTransport(name="test-echo")
        result = transport.complete(prompt="...")

    The returned text is JSON-shaped when the prompt requests
    structured output (the marker ``RESPOND_AS_JSON`` somewhere in
    prompt or system); otherwise it's plain text.
    """

    name = "echo"

    def __init__(
        self,
        *,
        name: str = "echo",
        cost_per_1k_prompt: float = 0.003,
        cost_per_1k_completion: float = 0.015,
        latency_floor_s: float = 0.001,
    ) -> None:
        self.name = name
        self._cost_in = cost_per_1k_prompt
        self._cost_out = cost_per_1k_completion
        self._latency_floor = latency_floor_s

    def complete(
        self,
        *,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model_hint: str | None = None,
    ) -> LLMResult:
        t0 = time.monotonic()
        full = (system + "\n" + prompt).strip()
        # ~4 chars per token, common rule of thumb.
        prompt_tokens = max(1, len(full) // 4)
        completion_tokens = min(max_tokens, max(8, prompt_tokens // 2))

        if "RESPOND_AS_JSON" in full or "respond_as_json" in full:
            # Synthesize a JSON payload that any reasonable specialist
            # validator can ingest. Real model would build this from
            # actual reasoning; we derive deterministically.
            tag = hashlib.sha1(full.encode()).hexdigest()[:8]
            text = (
                '{"hypothesis": "echo:' + tag + '", '
                '"evidence": ["prompt-derived stub"], '
                '"signal": "neutral", '
                '"confidence": 0.5, '
                '"falsification": "real LLM would replace this"}'
            )
        else:
            text = f"[echo:{model_hint or 'default'}] {full[:200]}"

        cost = prompt_tokens / 1000.0 * self._cost_in + completion_tokens / 1000.0 * self._cost_out
        latency = max(self._latency_floor, time.monotonic() - t0)
        return LLMResult(
            text=text,
            model=model_hint or "echo-stub",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=round(cost, 6),
            latency_s=round(latency, 4),
            raw={"transport": self.name, "prompt_len": len(full)},
            request_id=hashlib.sha1(f"{datetime.now(UTC).isoformat()}|{full}".encode()).hexdigest()[:16],
        )


# ---------------------------------------------------------------------------
# Adapter: route through batman_bridge
# ---------------------------------------------------------------------------
class BatmanLLMTransport:
    """Routes LLM calls through the existing batman_bridge pipeline.

    NEVER invoked in tests (would burn the operator's API budget). Only
    used when explicitly wired via the factory; the factory checks the
    model_policy tier and the operator's APEX_LLM_TRANSPORT env var.
    """

    name = "batman"

    def __init__(
        self,
        *,
        timeout_s: float = 120.0,
        force: str | None = None,
    ) -> None:
        self.timeout_s = timeout_s
        self.force = force

    def complete(
        self,
        *,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model_hint: str | None = None,
    ) -> LLMResult:
        # Lazy import: jarvis_identity isn't on every host's path.
        try:
            sys_path_parent = "C:/Users/edwar/OneDrive/Desktop/Base"
            import sys as _sys

            if sys_path_parent not in _sys.path:
                _sys.path.insert(0, sys_path_parent)
            from jarvis_identity.batman.batman_bridge import batman_call  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                f"BatmanLLMTransport requires jarvis_identity.batman to be on sys.path. Original error: {e}"
            ) from e
        full = (system + "\n\n" + prompt).strip()
        t0 = time.monotonic()
        result = batman_call(full, timeout=self.timeout_s, force=self.force)
        latency = time.monotonic() - t0
        text = str(result.get("response", ""))
        # batman_bridge's return doesn't include token counts; estimate.
        prompt_tokens = max(1, len(full) // 4)
        completion_tokens = max(1, len(text) // 4)
        usage = result.get("usage") or {}
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("input_tokens", prompt_tokens))
            completion_tokens = int(usage.get("output_tokens", completion_tokens))
        # No cost passthrough from batman_bridge; default to 0 and let the
        # audit log surface it as "cost_unknown".
        return LLMResult(
            text=text,
            model=str(result.get("model", "batman-routed")),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=float(result.get("cost_usd", 0.0)),
            latency_s=round(latency, 4),
            raw=result,
            request_id=str(result.get("task_id", "")),
        )
