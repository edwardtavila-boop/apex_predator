"""
EVOLUTIONARY TRADING ALGO  //  strategies.crypto_orb_strategy
==============================================================
Crypto ORB — UTC-anchored opening range for 24/7 markets.

Logic per the 2026-04-27 user directive on crypto bot strategies:

* "Hybrid Systems — ORB-style breakouts on 'session' opens (e.g.,
  UTC daily open or post-news windows)"

Crypto trades 24/7 with no traditional RTH session, but a **UTC
midnight rollover** is a meaningful synthetic anchor: it's when
funding-rate periods turn over on most exchanges, when daily
candles snap, and when Asia hands off to Europe in a clean way.
The first 60 minutes after UTC midnight produce a measurable
volume bump, which is the "open" we anchor on.

This module mirrors `ORBStrategy` but:
* ``rth_open_local`` defaults to 00:00 UTC
* ``range_minutes`` defaults to 60 (slower than MNQ's 15m)
* ``max_entry_local`` defaults to 06:00 UTC (block late-Asian and
  European opens since they're separate sessions)
* timezone defaults to UTC

For news-window breakouts (the other half of the user's hybrid
suggestion), the same class works — just point ``rth_open_local``
at the news minute (e.g., 13:30 UTC for FOMC) and shrink
``range_minutes``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from eta_engine.strategies.orb_strategy import ORBConfig, ORBStrategy


@dataclass(frozen=True)
class CryptoORBConfig(ORBConfig):
    """ORBConfig with crypto-friendly defaults.

    Inherits every knob from ORBConfig — overrides only the
    timezone + session window. Pass a custom config to point at a
    news event (e.g., FOMC or CPI release) instead.
    """

    range_minutes: int = 60
    rth_open_local: time = time(0, 0)
    rth_close_local: time = time(23, 59)
    max_entry_local: time = time(6, 0)
    flatten_at_local: time = time(23, 55)
    timezone_name: str = "UTC"
    # Crypto bars (1h+) tend to have wider individual bars than MNQ
    # 5m, so the stop multiplier benefits from a slight lift.
    atr_stop_mult: float = 2.5
    rr_target: float = 2.5  # crypto trends harder when they trend
    ema_bias_period: int = 100  # shorter than MNQ; crypto regimes shift faster
    max_trades_per_day: int = 2  # one Asian-session, one optional news


def crypto_orb_strategy(config: CryptoORBConfig | None = None) -> ORBStrategy:
    """Construct an ORBStrategy with crypto-defaults.

    Returns an ORBStrategy instance (not a subclass) so the engine
    plumbing is identical. CryptoORBConfig is frozen + dataclass-
    inherited, so all the knobs are still per-bot overrideable.
    """
    return ORBStrategy(config or CryptoORBConfig())
