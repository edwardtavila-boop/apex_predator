from __future__ import annotations

import pytest

from eta_engine.brain.jarvis_v3.next_level.causal import (
    CausalDAG,
    CausalNode,
    counterfactual_denied,
    propensity_match,
)


def test_causal_dag_stores_nodes_and_copies_observations() -> None:
    dag = CausalDAG()
    obs = {"verdict_denied": 1.0, "realized_r": -0.5}
    dag.add_node(CausalNode(name="verdict_denied", kind="binary", parents=["stress"]))
    dag.add_observation(obs)
    obs["realized_r"] = 99.0

    assert dag.nodes()[0].parents == ["stress"]
    assert dag.observations()[0]["realized_r"] == -0.5


def test_propensity_match_estimates_ate_with_confounder_overlap() -> None:
    dag = CausalDAG()
    dag.add_observation({"verdict_denied": 1.0, "realized_r": -0.4, "stress": 0.20})
    dag.add_observation({"verdict_denied": 0.0, "realized_r": 0.3, "stress": 0.21})
    dag.add_observation({"verdict_denied": 1.0, "realized_r": -0.2, "stress": 0.40})
    dag.add_observation({"verdict_denied": 0.0, "realized_r": 0.1, "stress": 0.39})

    result = propensity_match(
        dag,
        treatment="verdict_denied",
        treatment_value=1.0,
        outcome="realized_r",
        confounders=["stress"],
        tolerance=0.05,
    )

    assert result.treated_n == 2
    assert result.control_n == 2
    assert result.mean_treated == -0.3
    assert result.mean_control == 0.2
    assert result.ate == -0.5
    assert "matched 2 pairs" in result.note


def test_counterfactual_denied_returns_no_overlap_when_pairs_are_missing() -> None:
    dag = CausalDAG()
    dag.add_observation({"verdict_denied": 1.0, "realized_r": -1.0, "stress_composite": 0.1})
    dag.add_observation({"verdict_denied": 0.0, "realized_r": 1.0, "stress_composite": 0.9})

    result = counterfactual_denied(dag)

    assert result.sample_n == 2
    assert result.ate == 0.0
    assert result.note == "no matched pairs -- insufficient overlap"


def test_causal_node_validates_kind() -> None:
    with pytest.raises(ValueError):
        CausalNode(name="bad", kind="ordinal")
