"""
EVOLUTIONARY TRADING ALGO // jarvis.transport_factory
=========================================
Factory for the right LLMTransport based on environment + model_policy.

Three tiers (mirror of CLAUDE.md model-tier routing):

    sonnet  -> BatmanLLMTransport(force=None) targeting claude-sonnet-4-5
    opus    -> BatmanLLMTransport(force=None) targeting claude-opus-4-7
    haiku   -> BatmanLLMTransport with shortest timeout
    echo    -> EchoLLMTransport (tests + dev when no API key)

`make_transport(role)` returns the right transport for a given role:

    role="specialist:quant"  -> sonnet
    role="pm"                -> opus
    role="post_mortem"       -> opus
    role="reasoning_eval"    -> sonnet

`make_transport_with_audit(role)` returns (transport, audit_log) for
direct use in SpecialistAgent constructors.

Operator overrides:
  APEX_LLM_TRANSPORT=echo|batman    forces transport regardless of role
  APEX_FORCE_TIER=sonnet|opus|haiku forces tier when transport=batman
"""

from __future__ import annotations

import os
from typing import Literal

from eta_engine.jarvis.llm_audit import LLMAuditLog
from eta_engine.jarvis.llm_transport import (
    BatmanLLMTransport,
    EchoLLMTransport,
    LLMTransport,
)

Tier = Literal["sonnet", "opus", "haiku", "echo"]


_ROLE_TO_TIER: dict[str, Tier] = {
    "specialist:quant": "sonnet",
    "specialist:red_team": "sonnet",
    "specialist:risk_manager": "sonnet",
    "specialist:macro": "sonnet",
    "specialist:microstructure": "sonnet",
    "specialist:pm": "opus",
    "specialist:meta": "sonnet",
    "pm": "opus",
    "post_mortem": "opus",
    "reasoning_eval": "sonnet",
}

_DEFAULT_TIER: Tier = "sonnet"


def tier_for_role(role: str) -> Tier:
    return _ROLE_TO_TIER.get(role, _DEFAULT_TIER)


def make_transport(role: str = "") -> LLMTransport:
    """Pick a transport for ``role``. Operator override wins.

    APEX_LLM_TRANSPORT=echo                  -> EchoLLMTransport
    APEX_LLM_TRANSPORT=batman                -> BatmanLLMTransport(role tier)
    (default)                                -> BatmanLLMTransport if env
                                               has Anthropic creds, else echo
    """
    forced = os.environ.get("APEX_LLM_TRANSPORT", "").strip().lower()
    if forced == "echo":
        return EchoLLMTransport(name="echo")
    if forced == "batman":
        return BatmanLLMTransport()
    # Auto-pick: prefer batman when an Anthropic key is configured.
    if os.environ.get("ANTHROPIC_API_KEY"):
        return BatmanLLMTransport()
    return EchoLLMTransport(name="echo-auto")


def make_transport_with_audit(
    role: str = "",
    *,
    audit: LLMAuditLog | None = None,
) -> tuple[LLMTransport, LLMAuditLog]:
    return make_transport(role), (audit or LLMAuditLog())
