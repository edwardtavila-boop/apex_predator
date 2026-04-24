"""
APEX PREDATOR  //  brain.avengers
=================================
The Avengers fleet -- three development personas (Batman, Alfred, Robin)
plus the Fleet coordinator, all sitting beside JARVIS.

Why this package exists
-----------------------
JARVIS is the deterministic admin -- he runs the policy engine on the
risk-gate hot path with zero LLM latency. The Avengers are the
*development* side of the fleet, each locked to a model tier so cost is
predictable:

  * BATMAN  -> Opus 4.7  (architectural / adversarial work)
  * ALFRED  -> Sonnet 4.6 (routine dev work, the default)
  * ROBIN   -> Haiku 4.5 (mechanical grunt)

Any LLM-shaped work JARVIS might be tempted to run (log parsing, alert
drafting, post-hoc review) is offloaded to this fleet instead, keeping
JARVIS's hot path clean and the overall burn rate ~5x lower than if
everything defaulted to Opus.

Public API
----------
  * ``Fleet``           -- coordinator (one ``dispatch`` entrypoint)
  * ``Batman``/``Alfred``/``Robin`` -- concrete Persona subclasses
  * ``Persona``         -- abstract base for future personas
  * ``PersonaId``       -- enum of persona identities
  * ``TaskEnvelope``    -- pydantic request envelope
  * ``TaskResult``      -- pydantic response envelope
  * ``Executor``        -- Protocol for LLM runners (inject in tests)
  * ``DryRunExecutor``  -- deterministic default executor
  * ``make_envelope``   -- short-form factory for callers
  * ``AVENGERS_JOURNAL``-- default JSONL audit log path
"""
from apex_predator.brain.avengers.alfred import Alfred
from apex_predator.brain.avengers.base import (
    AVENGERS_JOURNAL,
    COST_RATIO,
    PERSONA_BUCKET,
    PERSONA_TIER,
    DryRunExecutor,
    Executor,
    Persona,
    PersonaId,
    TaskBucket,
    TaskCategory,
    TaskEnvelope,
    TaskResult,
    append_journal,
    bucket_for,
    describe_persona,
    make_envelope,
    select_model,
    tier_for,
)
from apex_predator.brain.avengers.batman import Batman
from apex_predator.brain.avengers.dispatch import (
    TASK_CADENCE,
    TASK_OWNERS,
    AvengersDispatch,
    BackgroundTask,
    DispatchResult,
    DispatchRoute,
)
from apex_predator.brain.avengers.fleet import Fleet, FleetMetrics
from apex_predator.brain.avengers.robin import Robin

__all__ = [
    "AVENGERS_JOURNAL",
    "COST_RATIO",
    "PERSONA_BUCKET",
    "PERSONA_TIER",
    "TASK_CADENCE",
    "TASK_OWNERS",
    "Alfred",
    "AvengersDispatch",
    "BackgroundTask",
    "Batman",
    "DispatchResult",
    "DispatchRoute",
    "DryRunExecutor",
    "Executor",
    "Fleet",
    "FleetMetrics",
    "Persona",
    "PersonaId",
    "Robin",
    "TaskBucket",
    "TaskCategory",
    "TaskEnvelope",
    "TaskResult",
    "append_journal",
    "bucket_for",
    "describe_persona",
    "make_envelope",
    "select_model",
    "tier_for",
]
