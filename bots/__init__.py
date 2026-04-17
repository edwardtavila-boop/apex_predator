"""APEX PREDATOR 6-Bot Fleet — unified imports."""

from apex_predator.bots.base_bot import (
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
from apex_predator.bots.crypto_seed.bot import CryptoSeedBot
from apex_predator.bots.eth_perp.bot import EthPerpBot
from apex_predator.bots.mnq.bot import MnqBot
from apex_predator.bots.nq.bot import NqBot
from apex_predator.bots.sol_perp.bot import SolPerpBot
from apex_predator.bots.xrp_perp.bot import XrpPerpBot

ALL_BOTS: list[type[BaseBot]] = [MnqBot, NqBot, CryptoSeedBot, EthPerpBot, SolPerpBot, XrpPerpBot]

__all__ = [
    "ALL_BOTS",
    "BaseBot",
    "BotConfig",
    "BotState",
    "CryptoSeedBot",
    "EthPerpBot",
    "Fill",
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
