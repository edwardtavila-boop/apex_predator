"""
EVOLUTIONARY TRADING ALGO // jarvis
=======================
LLM-backed reasoning agents (Phase 1), episodic memory + RAG (Phase 2),
tool use (Phase 3), bounded online adaptation (Phase 4), and weekly
meta-cognition (Phase 5).

Public surface:

    from eta_engine.jarvis import (
        # Phase 1
        SpecialistOutput, SpecialistAgent, PMConsensus,
        LLMTransport, EchoLLMTransport, LLMAuditLog,
        # Phase 2
        EpisodicMemory, LocalMemoryStore, DeterministicEmbedder,
        RetrievalEngine, OutcomeTracker,
        # Phase 3
        Tool, ToolRegistry, ToolBudgetEnforcer,
        # Phase 4
        ParameterRegistry, BayesianParameterAdapter,
        # Phase 5
        WeeklyPostMortem, ForecastAccuracyTracker,
    )

Hard rules enforced module-side:
  * Every LLM call routes through ``LLMTransport`` and is logged via
    ``LLMAuditLog`` (rule #4).
  * No agent class accepts a ``write_code`` tool; mutation goes through
    ``apex_confirm`` operator path only (rule #1).
  * ``Embargo`` guard refuses retrieval over the embargo window (rule #3).
"""

from __future__ import annotations

from eta_engine.jarvis.consensus import PMConsensus, PMVerdict
from eta_engine.jarvis.llm_audit import LLMAuditLog

# Phase 1
from eta_engine.jarvis.llm_transport import (
    EchoLLMTransport,
    LLMResult,
    LLMTransport,
)
from eta_engine.jarvis.specialists.base import (
    DecisionContext,
    SpecialistAgent,
    SpecialistOutput,
)
from eta_engine.jarvis.specialists.reference import (
    MacroSpecialist,
    MetaSpecialist,
    MicrostructureSpecialist,
    PMSpecialist,
    QuantSpecialist,
    RedTeamSpecialist,
    RiskManagerSpecialist,
    build_default_panel,
)

__all__ = [
    "DecisionContext",
    "EchoLLMTransport",
    "LLMAuditLog",
    "LLMResult",
    "LLMTransport",
    "MacroSpecialist",
    "MetaSpecialist",
    "MicrostructureSpecialist",
    "PMConsensus",
    "PMSpecialist",
    "PMVerdict",
    "QuantSpecialist",
    "RedTeamSpecialist",
    "RiskManagerSpecialist",
    "SpecialistAgent",
    "SpecialistOutput",
    "build_default_panel",
]
