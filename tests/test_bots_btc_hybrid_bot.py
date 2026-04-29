from __future__ import annotations

import pytest

from eta_engine.bots.base_bot import MarginMode, SignalType, Tier
from eta_engine.bots.btc_hybrid.bot import (
    BTC_HYBRID_CONFIG,
    BtcHybridProfile,
    HybridMode,
    _signal_to_side,
)
from eta_engine.venues.base import Side


def test_btc_hybrid_default_profile_and_config_are_btc_specific() -> None:
    profile = BtcHybridProfile(
        session_phase_edge_bias={"OPEN_DRIVE": 1.1},
        order_book_quality_size_bias={"strong": 1.2},
    )

    assert profile.adx_ranging_threshold < profile.adx_trending_threshold
    assert profile.grid_levels == 6
    assert profile.session_phase_edge_bias["OPEN_DRIVE"] == 1.1
    assert BTC_HYBRID_CONFIG.symbol == "BTCUSDT"
    assert BTC_HYBRID_CONFIG.tier is Tier.CASINO
    assert BTC_HYBRID_CONFIG.margin_mode is MarginMode.CROSS


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"grid_levels": 5}, "grid_levels must be an even integer"),
        ({"adx_ranging_threshold": 31.0}, "adx_ranging_threshold must be <"),
        ({"quality_size_floor": 0.0}, "quality_size_floor must be in"),
        ({"session_phase_edge_bias": {"": 1.0}}, "keys must be non-empty"),
        ({"timeframe_size_bias": {"5m": 2.5}}, "must be in"),
    ],
)
def test_btc_hybrid_profile_rejects_unsafe_geometry(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        BtcHybridProfile(**kwargs)


@pytest.mark.parametrize(
    ("signal_type", "side", "closing"),
    [
        (SignalType.LONG, Side.BUY, False),
        (SignalType.GRID_ADD, Side.BUY, False),
        (SignalType.SHORT, Side.SELL, False),
        (SignalType.GRID_REMOVE, Side.SELL, False),
        (SignalType.CLOSE_LONG, Side.SELL, True),
        (SignalType.CLOSE_SHORT, Side.BUY, True),
    ],
)
def test_signal_to_side_preserves_open_close_semantics(signal_type, side, closing) -> None:
    assert _signal_to_side(signal_type) == (side, closing)
    assert HybridMode.FLAT.value == "FLAT"
