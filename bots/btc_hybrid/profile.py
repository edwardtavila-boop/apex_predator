"""APEX PREDATOR  //  bots.btc_hybrid.profile
==================================================
Profile loader for the BTC-hybrid bot.

A profile is a dict of multipliers and thresholds the bot consults at
runtime to bias position size and edge scoring against the current
session/timeframe/spread/order-book bucket. Multipliers go through
``CryptoSeedBot._profile_bias`` which clamps every value to [0.5, 1.5]
so a corrupt profile cannot blow up risk; floats go through
``_profile_float`` which silently falls back to the default if a value
is missing or non-numeric.

Profiles ship as JSON under ``configs/`` so they can be diffed, code-
reviewed, and loaded without a Python import. The bot accepts either a
dict or a dataclass so producers stay flexible.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BTC_PROFILE_PATH: Path = _REPO_ROOT / "configs" / "btc_hybrid_profile.json"


def load_btc_hybrid_profile(path: Path | str = DEFAULT_BTC_PROFILE_PATH) -> dict[str, Any]:
    """Load a profile JSON into a plain dict.

    Missing file -> empty dict (bot falls back to neutral 1.0 biases).
    Malformed JSON -> empty dict + the bot logs the failure on first use.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


__all__ = [
    "DEFAULT_BTC_PROFILE_PATH",
    "load_btc_hybrid_profile",
]
