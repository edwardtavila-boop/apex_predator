"""Specialist agent registry. Each specialist module registers a class."""

from __future__ import annotations

from eta_engine.jarvis.specialists.base import (
    DecisionContext,
    SpecialistAgent,
    SpecialistOutput,
)

__all__ = ["DecisionContext", "SpecialistAgent", "SpecialistOutput"]
