"""
EVOLUTIONARY TRADING ALGO  //  brain.rl_agent
=================================
Reinforcement learning agent interface with a deterministic guardrail policy.

This is intentionally stdlib-first: no PyTorch/stable-baselines dependency is
required on the live box. The policy is conservative by default, updates small
per-action reward scores from replay feedback, and keeps the public API ready
for a future PPO/SAC implementation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from eta_engine.brain.regime import RegimeType

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class RLAction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    INCREASE_SIZE = "INCREASE_SIZE"
    DECREASE_SIZE = "DECREASE_SIZE"


class RLState(BaseModel):
    """Observable state vector for the RL agent."""

    features: list[float] = Field(description="Normalized feature vector")
    regime: RegimeType = RegimeType.TRANSITION
    confluence_score: float = Field(default=0.0, ge=0.0, le=10.0)
    position_pnl: float = 0.0


@dataclass(frozen=True)
class RLPolicyConfig:
    """Safety-first thresholds for the deterministic baseline policy."""

    low_confluence: float = 4.0
    high_confluence: float = 7.0
    strong_confluence: float = 8.5
    stop_loss_r: float = -1.0
    protect_profit_r: float = 1.5
    learning_rate: float = 0.20
    min_learned_edge: float = 0.10


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class RLAgent:
    """RL agent with pluggable policy.

    Current implementation: deterministic guardrail baseline with lightweight
    per-action reward scores. It never explores randomly; JARVIS and risk
    systems should not receive stochastic direction changes from this module.

    The interface is frozen: swap internals, keep the API.
    """

    def __init__(self, seed: int = 42, *, config: RLPolicyConfig | None = None) -> None:
        self._seed = seed
        self.config = config or RLPolicyConfig()
        self._replay_buffer: list[tuple[RLState, RLAction, float]] = []
        self._step_count: int = 0
        self._action_scores: dict[RLAction, float] = {action: 0.0 for action in RLAction}
        self._last_reason: str = "initialized"

    def select_action(self, state: RLState) -> RLAction:
        """Choose an action given current state.

        The baseline is deterministic and risk-first:
        * stop-loss / crisis guardrails override everything
        * low confluence holds
        * high confluence picks direction from feature sign
        * learned reward scores can only choose among the currently safe
          candidate actions
        """
        self._step_count += 1

        candidates, reason = self._safe_candidates(state)
        action = self._choose_with_learned_scores(candidates)
        self._last_reason = f"{reason}; selected={action.value}"
        return action

    def update(self, state: RLState, action: RLAction, reward: float) -> None:
        """Store experience and update the transparent action-score table."""
        self._replay_buffer.append((state, action, reward))
        old = self._action_scores.get(action, 0.0)
        self._action_scores[action] = old + self.config.learning_rate * (reward - old)

    def save_model(self, path: str | Path) -> None:
        """Serialize the guardrail policy state to disk."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "steps": self._step_count,
            "buffer_size": len(self._replay_buffer),
            "type": "deterministic_guardrail",
            "seed": self._seed,
            "config": asdict(self.config),
            "action_scores": {action.value: score for action, score in self._action_scores.items()},
            "last_reason": self._last_reason,
        }
        p.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def load_model(self, path: str | Path) -> None:
        """Load policy state from disk.

        Backward-compatible with older metadata-only files that only stored a
        step count.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Model not found at {p}")
        meta = json.loads(p.read_text(encoding="utf-8"))
        self._step_count = meta.get("steps", 0)
        for action_value, score in (meta.get("action_scores") or {}).items():
            try:
                action = RLAction(action_value)
            except ValueError:
                continue
            if isinstance(score, (int, float)):
                self._action_scores[action] = float(score)
        if isinstance(meta.get("last_reason"), str):
            self._last_reason = meta["last_reason"]

    def policy_snapshot(self) -> dict[str, object]:
        """Return a JSON-ready audit view of the current policy state."""
        return {
            "type": "deterministic_guardrail",
            "steps": self._step_count,
            "buffer_size": len(self._replay_buffer),
            "config": asdict(self.config),
            "action_scores": {action.value: round(score, 6) for action, score in self._action_scores.items()},
            "last_reason": self._last_reason,
        }

    def _safe_candidates(self, state: RLState) -> tuple[list[RLAction], str]:
        if state.position_pnl <= self.config.stop_loss_r:
            return [RLAction.CLOSE], "stop_loss_guardrail"

        if state.regime == RegimeType.CRISIS:
            if state.position_pnl < 0:
                return [RLAction.CLOSE], "crisis_close_loser"
            return [RLAction.HOLD], "crisis_hold"

        if state.confluence_score < self.config.low_confluence:
            if state.position_pnl >= self.config.protect_profit_r:
                return [RLAction.DECREASE_SIZE, RLAction.HOLD], "low_confluence_protect_profit"
            return [RLAction.HOLD], "low_confluence_hold"

        if state.position_pnl >= self.config.protect_profit_r:
            return [RLAction.DECREASE_SIZE, RLAction.HOLD], "profit_protection"

        if state.confluence_score >= self.config.high_confluence:
            direction = self._direction_from_features(state.features)
            candidates = [direction, RLAction.HOLD]
            if state.confluence_score >= self.config.strong_confluence and state.regime != RegimeType.HIGH_VOL:
                candidates.append(RLAction.INCREASE_SIZE)
            if state.regime == RegimeType.HIGH_VOL:
                candidates.append(RLAction.DECREASE_SIZE)
            return candidates, "high_confluence_directional"

        return [RLAction.HOLD, RLAction.DECREASE_SIZE], "mid_confluence_observe"

    def _choose_with_learned_scores(self, candidates: list[RLAction]) -> RLAction:
        base = candidates[0]
        base_score = self._action_scores.get(base, 0.0)
        best = max(
            candidates,
            key=lambda action: (
                self._action_scores.get(action, 0.0),
                -candidates.index(action),
            ),
        )
        if self._action_scores.get(best, 0.0) >= base_score + self.config.min_learned_edge:
            return best
        return base

    @staticmethod
    def _direction_from_features(features: list[float]) -> RLAction:
        if not features:
            return RLAction.HOLD
        directional_signal = sum(features[:3]) / min(len(features), 3)
        if directional_signal < 0:
            return RLAction.SHORT
        if directional_signal > 0:
            return RLAction.LONG
        return RLAction.HOLD
