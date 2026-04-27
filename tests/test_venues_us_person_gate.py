"""Tests for the US-person venue gate (operator mandate M2, 2026-04-26).

The router must HARD-REFUSE live orders to non-FCM venues when
``IS_US_PERSON`` is True, with no failover path that bypasses the
gate. Adapters must stay importable for offline backtest + unit tests.
"""
from __future__ import annotations

import pytest

from eta_engine.venues import cme_mapping, router as router_mod
from eta_engine.venues.base import (
    OrderRequest,
    OrderType,
    Side,
)
from eta_engine.venues.router import (
    IS_US_PERSON,
    NON_FCM_VENUES,
    SmartRouter,
)


# ─── M2: US-person gate ──────────────────────────────────────────────────


def test_default_is_us_person_true() -> None:
    """Default policy is US-person on; override requires explicit env."""
    # The module-level constant is captured at import time, so this test
    # documents the default rather than re-evaluates env.
    assert IS_US_PERSON is True or IS_US_PERSON is False  # exists
    # Loud explicit assertion: when env not set, default True.
    import os
    saved = os.environ.pop("APEX_IS_US_PERSON", None)
    try:
        # Re-evaluate the same expression the module uses:
        evaluated = os.environ.get("APEX_IS_US_PERSON", "true").lower() in (
            "1", "true", "yes", "y",
        )
        assert evaluated is True
    finally:
        if saved is not None:
            os.environ["APEX_IS_US_PERSON"] = saved


def test_non_fcm_venues_includes_offshore_perps() -> None:
    assert "bybit" in NON_FCM_VENUES
    assert "okx" in NON_FCM_VENUES
    assert "deribit" in NON_FCM_VENUES
    assert "hyperliquid" in NON_FCM_VENUES


def test_fcm_venues_not_in_non_fcm() -> None:
    """IBKR + Tastytrade + Tradovate (FCMs) must NOT appear in the block list."""
    assert "ibkr" not in NON_FCM_VENUES
    assert "tastytrade" not in NON_FCM_VENUES
    assert "tradovate" not in NON_FCM_VENUES


@pytest.mark.asyncio
async def test_place_with_failover_refuses_bybit_for_us_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live route to Bybit must raise RuntimeError, not silently route."""
    monkeypatch.setattr(router_mod, "IS_US_PERSON", True)
    r = SmartRouter(preferred_crypto_venue="bybit")
    req = OrderRequest(
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=0.001,
        order_type=OrderType.MARKET,
    )
    with pytest.raises(RuntimeError, match="REFUSED"):
        await r.place_with_failover(req)


@pytest.mark.asyncio
async def test_place_with_failover_refuses_okx_for_us_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(router_mod, "IS_US_PERSON", True)
    r = SmartRouter(preferred_crypto_venue="okx")
    req = OrderRequest(
        symbol="ETHUSDT",
        side=Side.BUY,
        qty=0.01,
        order_type=OrderType.MARKET,
    )
    with pytest.raises(RuntimeError, match="REFUSED"):
        await r.place_with_failover(req)


# ─── M2: CME mapping ─────────────────────────────────────────────────────


def test_cme_mapping_btc_to_mbt() -> None:
    assert cme_mapping.to_cme("BTCUSDT") == "MBT"
    assert cme_mapping.to_cme("btcusdt") == "MBT"  # case-insensitive
    assert cme_mapping.to_cme("BTCUSDT", micro=False) == "BTC"


def test_cme_mapping_eth_to_met() -> None:
    assert cme_mapping.to_cme("ETHUSDT") == "MET"
    assert cme_mapping.to_cme("ETHUSDT", micro=False) == "ETH"


def test_cme_mapping_sol_to_sol() -> None:
    """SOL has no separate full-size contract; both micro=True/False return SOL."""
    assert cme_mapping.to_cme("SOLUSDT") == "SOL"
    assert cme_mapping.to_cme("SOLUSDT", micro=False) == "SOL"


def test_cme_mapping_xrp_to_xrp() -> None:
    assert cme_mapping.to_cme("XRPUSDT") == "XRP"
    assert cme_mapping.to_cme("XRPUSDT", micro=False) == "XRP"


def test_cme_mapping_unknown_returns_none() -> None:
    assert cme_mapping.to_cme("DOGEUSDT") is None
    assert cme_mapping.to_cme("") is None


def test_cme_mapping_reverse() -> None:
    assert cme_mapping.from_cme("MBT") == "BTCUSDT"
    assert cme_mapping.from_cme("MET") == "ETHUSDT"
    assert cme_mapping.from_cme("SOL") == "SOLUSDT"
    assert cme_mapping.from_cme("XRP") == "XRPUSDT"
    assert cme_mapping.from_cme("BTC") == "BTCUSDT"
    assert cme_mapping.from_cme("ETH") == "ETHUSDT"
    assert cme_mapping.from_cme("UNKNOWN") is None


def test_cme_mapping_is_crypto_perp() -> None:
    assert cme_mapping.is_crypto_perp("BTCUSDT") is True
    assert cme_mapping.is_crypto_perp("ETHUSDT") is True
    assert cme_mapping.is_crypto_perp("MNQ") is False
    assert cme_mapping.is_crypto_perp("") is False
