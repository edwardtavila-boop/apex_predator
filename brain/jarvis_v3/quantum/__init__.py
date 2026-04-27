"""Quantum-hybrid layer for JARVIS (Wave-9, 2026-04-27).

Public surface:

  * QuboProblem, simulated_annealing_solve  -- QUBO + SA solver
  * portfolio_allocation_qubo               -- Markowitz -> QUBO encoder
  * sizing_basket_qubo                      -- discrete sizing combo encoder
  * select_top_signal_combination           -- tensor-network signal picker
  * QuantumCloudAdapter                     -- optional Qiskit/PennyLane bridge
  * QuantumOptimizerAgent                   -- firm-board pluggable agent

All modules are pure-stdlib by default. Cloud quantum capabilities
auto-activate ONLY when qiskit / pennylane / dwave-ocean-sdk are
importable; otherwise the adapter falls back transparently to the
classical QUBO solver.
"""
from eta_engine.brain.jarvis_v3.quantum.cloud_adapter import (
    QuantumBackend,
    QuantumCloudAdapter,
)
from eta_engine.brain.jarvis_v3.quantum.quantum_agent import QuantumOptimizerAgent
from eta_engine.brain.jarvis_v3.quantum.qubo_solver import (
    QuboProblem,
    portfolio_allocation_qubo,
    simulated_annealing_solve,
    sizing_basket_qubo,
)
from eta_engine.brain.jarvis_v3.quantum.tensor_network import (
    SignalScore,
    select_top_signal_combination,
)

__all__ = [
    "QuantumBackend",
    "QuantumCloudAdapter",
    "QuantumOptimizerAgent",
    "QuboProblem",
    "SignalScore",
    "portfolio_allocation_qubo",
    "select_top_signal_combination",
    "simulated_annealing_solve",
    "sizing_basket_qubo",
]
