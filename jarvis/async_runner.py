"""
EVOLUTIONARY TRADING ALGO // jarvis.async_runner
====================================
Phase 1 stack: async batching for the 7 specialist calls.

The roadmap quotes ~$0.40/decision @ Sonnet over ~150 decisions/day, with
per-decision latency 2-6s if the 7 specialists run sequentially. Running
them concurrently drops the wall-clock to ~max(per-call latency).

This module provides ``AsyncSpecialistRunner`` that executes a panel
in parallel via ``asyncio.gather``, with a per-specialist timeout and
deterministic crash-handling: a specialist that crashes returns a
"neutral / falsification: crashed" output (same shape as
ReasoningQualityEvaluator) so the PM aggregator never gets fewer than
N outputs from N specialists.

Specialists themselves remain SYNCHRONOUS — that's the right contract
because the deterministic reference implementations don't need async.
The runner adapts them via asyncio.to_thread, which is cheap and lets
us keep one source of truth for the specialist class.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from eta_engine.jarvis.specialists.base import (
    DecisionContext,
    SpecialistAgent,
    SpecialistOutput,
)


@dataclass
class SpecialistRunRecord:
    name: str
    elapsed_s: float
    succeeded: bool
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


@dataclass
class AsyncRunResult:
    outputs: list[SpecialistOutput]
    records: list[SpecialistRunRecord] = field(default_factory=list)
    wall_clock_s: float = 0.0


class AsyncSpecialistRunner:
    """Run a panel of synchronous SpecialistAgents in parallel."""

    def __init__(
        self,
        specialists: list[SpecialistAgent],
        *,
        per_specialist_timeout_s: float = 8.0,
    ) -> None:
        self.specialists = list(specialists)
        self.per_specialist_timeout_s = per_specialist_timeout_s

    async def run(self, ctx: DecisionContext) -> AsyncRunResult:
        t0 = time.monotonic()
        tasks = [asyncio.create_task(self._run_one(s, ctx)) for s in self.specialists]
        finished = await asyncio.gather(*tasks, return_exceptions=False)
        wall = time.monotonic() - t0
        outputs = [out for out, _ in finished]
        records = [rec for _, rec in finished]
        return AsyncRunResult(
            outputs=outputs,
            records=records,
            wall_clock_s=round(wall, 4),
        )

    def run_sync(self, ctx: DecisionContext) -> AsyncRunResult:
        """Convenience for callers that aren't already in an event loop."""
        return asyncio.run(self.run(ctx))

    async def _run_one(
        self,
        spec: SpecialistAgent,
        ctx: DecisionContext,
    ) -> tuple[SpecialistOutput, SpecialistRunRecord]:
        t0 = time.monotonic()
        try:
            out = await asyncio.wait_for(
                asyncio.to_thread(spec.evaluate, ctx),
                timeout=self.per_specialist_timeout_s,
            )
            elapsed = time.monotonic() - t0
            return out, SpecialistRunRecord(
                name=spec.name,
                elapsed_s=round(elapsed, 4),
                succeeded=True,
            )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            return (
                SpecialistOutput(
                    hypothesis=f"{spec.name} TIMEOUT",
                    evidence=[f"timed out after {self.per_specialist_timeout_s}s"],
                    signal="neutral",
                    confidence=0.0,
                    falsification=f"{spec.name} returns within timeout",
                ),
                SpecialistRunRecord(
                    name=spec.name,
                    elapsed_s=round(elapsed, 4),
                    succeeded=False,
                    error="timeout",
                ),
            )
        except Exception as e:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            return (
                SpecialistOutput(
                    hypothesis=f"{spec.name} CRASHED",
                    evidence=[f"{type(e).__name__}: {e}"],
                    signal="neutral",
                    confidence=0.0,
                    falsification=f"{spec.name} runs without exception",
                ),
                SpecialistRunRecord(
                    name=spec.name,
                    elapsed_s=round(elapsed, 4),
                    succeeded=False,
                    error=f"{type(e).__name__}: {e}",
                ),
            )
