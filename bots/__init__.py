"""EVOLUTIONARY TRADING ALGO 7-Bot Fleet — unified imports.

BtcHybridBot promoted to ALL_BOTS on 2026-04-26 after M2 (US-legal CME
routing) and M3 (JarvisAdmin policy authority) blockers cleared. The hybrid
bot was already running the M3 pattern before the rest of the fleet adopted
it; the M2 router-level symbol translation now lets it route BTCUSDT
(internal) to MBT (CME Micro Bitcoin via IBKR) automatically.
"""

from eta_engine.bots.base_bot import (
    BaseBot,
    BotConfig,
    BotState,
    Fill,
    MarginMode,
    Position,
    RegimeType,
    Signal,
    SignalType,
    SweepResult,
    Tier,
)
from eta_engine.bots.btc_hybrid.bot import BtcHybridBot, BtcHybridProfile, HybridMode
from eta_engine.bots.crypto_seed.bot import CryptoSeedBot
from eta_engine.bots.eth_perp.bot import EthPerpBot
from eta_engine.bots.mnq.bot import MnqBot
from eta_engine.bots.nq.bot import NqBot
from eta_engine.bots.sol_perp.bot import SolPerpBot
from eta_engine.bots.xrp_perp.bot import XrpPerpBot

ALL_BOTS: list[type[BaseBot]] = [
    MnqBot,
    NqBot,
    CryptoSeedBot,
    EthPerpBot,
    SolPerpBot,
    XrpPerpBot,
    BtcHybridBot,  # promoted 2026-04-26 (M2 + M3 cleared)
]

__all__ = [
    "ALL_BOTS",
    "BaseBot",
    "BotConfig",
    "BotState",
    "BtcHybridBot",
    "BtcHybridProfile",
    "CryptoSeedBot",
    "EthPerpBot",
    "Fill",
    "HybridMode",
    "MarginMode",
    "MnqBot",
    "NqBot",
    "Position",
    "RegimeType",
    "Signal",
    "SignalType",
    "SolPerpBot",
    "SweepResult",
    "Tier",
    "XrpPerpBot",
]
