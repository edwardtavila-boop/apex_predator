"""
APEX PREDATOR  //  staking
==========================
Yield adapters for the Multiplier layer.
Idle capital is bleeding capital.

Adapters:
    Lido     - wstETH (ETH liquid staking + EigenLayer restaking)
    Jito     - JitoSOL (Solana MEV-boosted staking)
    Flare    - sFLR (XRP-adjacent staking)
    Ethena   - sUSDe (delta-neutral stablecoin yield)
"""

from apex_predator.staking.allocator import AllocationConfig, allocate, rebalance
from apex_predator.staking.base import StakingAdapter
from apex_predator.staking.ethena import EthenaAdapter
from apex_predator.staking.flare import FlareAdapter
from apex_predator.staking.jito import JitoAdapter
from apex_predator.staking.lido import LidoAdapter

__all__ = [
    "StakingAdapter",
    "LidoAdapter",
    "JitoAdapter",
    "FlareAdapter",
    "EthenaAdapter",
    "AllocationConfig",
    "allocate",
    "rebalance",
]
