"""RL agent baseline tests - P10_AI ppo_sac_agent."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from eta_engine.brain.regime import RegimeType
from eta_engine.brain.rl_agent import RLAction, RLAgent, RLPolicyConfig, RLState

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# RLState + RLAction types
# ---------------------------------------------------------------------------


def test_rl_state_defaults() -> None:
    s = RLState(features=[0.1, 0.2])
    assert s.regime == RegimeType.TRANSITION
    assert s.confluence_score == 0.0
    assert s.position_pnl == 0.0


def test_rl_state_enforces_confluence_score_bounds() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RLState(features=[], confluence_score=11.0)


def test_rl_action_enum_covers_expected_actions() -> None:
    names = {a.value for a in RLAction}
    assert names == {
        "LONG",
        "SHORT",
        "HOLD",
        "CLOSE",
        "INCREASE_SIZE",
        "DECREASE_SIZE",
    }


# ---------------------------------------------------------------------------
# RLAgent.select_action - deterministic guardrail policy
# ---------------------------------------------------------------------------


def test_select_action_is_deterministic_without_random_exploration() -> None:
    a = RLAgent(seed=123)
    b = RLAgent(seed=999)
    state = RLState(features=[0.3, 0.2, 0.1], regime=RegimeType.TRENDING, confluence_score=8.0)

    seq_a = [a.select_action(state) for _ in range(10)]
    seq_b = [b.select_action(state) for _ in range(10)]

    assert seq_a == [RLAction.LONG] * 10
    assert seq_b == seq_a


def test_select_action_holds_when_confluence_low() -> None:
    agent = RLAgent(seed=7)
    state = RLState(features=[1.0], confluence_score=1.0)

    assert [agent.select_action(state) for _ in range(20)] == [RLAction.HOLD] * 20


def test_select_action_uses_feature_sign_when_confluence_high() -> None:
    agent = RLAgent(seed=11)

    long_state = RLState(features=[0.7, 0.1, 0.2], regime=RegimeType.TRENDING, confluence_score=9.0)
    short_state = RLState(features=[-0.7, -0.1, -0.2], regime=RegimeType.TRENDING, confluence_score=9.0)
    flat_state = RLState(features=[0.0, 0.0, 0.0], regime=RegimeType.TRENDING, confluence_score=9.0)

    assert agent.select_action(long_state) == RLAction.LONG
    assert agent.select_action(short_state) == RLAction.SHORT
    assert agent.select_action(flat_state) == RLAction.HOLD


def test_select_action_guardrails_override_directional_signal() -> None:
    agent = RLAgent(seed=0)

    stop_loss = RLState(features=[1.0], confluence_score=10.0, position_pnl=-1.5)
    crisis = RLState(features=[1.0], regime=RegimeType.CRISIS, confluence_score=10.0)
    profit = RLState(features=[1.0], confluence_score=10.0, position_pnl=2.0)

    assert agent.select_action(stop_loss) == RLAction.CLOSE
    assert agent.select_action(crisis) == RLAction.HOLD
    assert agent.select_action(profit) == RLAction.DECREASE_SIZE


def test_select_action_increments_step_count() -> None:
    agent = RLAgent(seed=0)
    state = RLState(features=[0.0])
    agent.select_action(state)
    agent.select_action(state)
    agent.select_action(state)
    assert agent.policy_snapshot()["steps"] == 3


# ---------------------------------------------------------------------------
# RLAgent.update - replay buffer and transparent reward scores
# ---------------------------------------------------------------------------


def test_update_stores_experience_and_updates_action_scores() -> None:
    agent = RLAgent(seed=0)
    state = RLState(features=[0.1])
    agent.update(state, RLAction.LONG, reward=1.25)
    agent.update(state, RLAction.HOLD, reward=0.0)

    snapshot = agent.policy_snapshot()
    assert len(agent._replay_buffer) == 2
    assert agent._replay_buffer[0][1] == RLAction.LONG
    assert agent._replay_buffer[0][2] == 1.25
    assert snapshot["action_scores"]["LONG"] == pytest.approx(0.25)


def test_learned_scores_can_only_choose_currently_safe_candidates() -> None:
    agent = RLAgent(seed=0, config=RLPolicyConfig(learning_rate=1.0, min_learned_edge=0.1))
    high_conf_state = RLState(features=[1.0], regime=RegimeType.TRENDING, confluence_score=9.0)
    low_conf_state = RLState(features=[1.0], regime=RegimeType.TRENDING, confluence_score=1.0)

    agent.update(high_conf_state, RLAction.HOLD, reward=2.0)

    assert agent.select_action(high_conf_state) == RLAction.HOLD
    assert agent.select_action(low_conf_state) == RLAction.HOLD


# ---------------------------------------------------------------------------
# RLAgent.save_model + load_model
# ---------------------------------------------------------------------------


def test_save_model_writes_metadata_json(tmp_path: Path) -> None:
    agent = RLAgent(seed=0)
    state = RLState(features=[0.1])
    for _ in range(5):
        agent.select_action(state)
    agent.update(state, RLAction.HOLD, 0.0)
    agent.update(state, RLAction.LONG, 1.0)

    out = tmp_path / "weights" / "rl_model.json"
    agent.save_model(out)

    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["steps"] == 5
    assert payload["buffer_size"] == 2
    assert payload["type"] == "deterministic_guardrail"
    assert payload["action_scores"]["LONG"] == pytest.approx(0.2)
    assert payload["config"]["high_confluence"] == 7.0


def test_save_model_creates_parent_directories(tmp_path: Path) -> None:
    agent = RLAgent(seed=0)
    nested = tmp_path / "a" / "b" / "c" / "model.json"
    agent.save_model(nested)
    assert nested.exists()


def test_load_model_restores_step_count_and_scores(tmp_path: Path) -> None:
    agent = RLAgent(seed=0)
    state = RLState(features=[0.1])
    for _ in range(7):
        agent.select_action(state)
    agent.update(state, RLAction.SHORT, 1.5)
    out = tmp_path / "model.json"
    agent.save_model(out)

    fresh = RLAgent(seed=0)
    assert fresh.policy_snapshot()["steps"] == 0
    fresh.load_model(out)
    snapshot = fresh.policy_snapshot()
    assert snapshot["steps"] == 7
    assert snapshot["action_scores"]["SHORT"] == pytest.approx(0.3)


def test_load_model_accepts_old_metadata_only_files(tmp_path: Path) -> None:
    path = tmp_path / "old_model.json"
    path.write_text(json.dumps({"steps": 7, "type": "random_baseline"}), encoding="utf-8")

    agent = RLAgent(seed=0)
    agent.load_model(path)

    assert agent.policy_snapshot()["steps"] == 7


def test_load_model_raises_when_file_missing(tmp_path: Path) -> None:
    agent = RLAgent(seed=0)
    with pytest.raises(FileNotFoundError):
        agent.load_model(tmp_path / "does_not_exist.json")
