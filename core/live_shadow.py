"""APEX PREDATOR  //  core.live_shadow
==========================================
Paper-fill simulator that mirrors the live order path against a real L2
book snapshot. Output feeds the TCA refit dataset and the
``live_shadow_guard`` chaos drill.

Design contract
---------------
* **Walk the book** in price-time priority. BUY consumes asks bottom-up;
  SELL consumes bids top-down. Each level fills until either the order
  size is satisfied or the level is exhausted.
* **Slippage in bps** is computed against the book mid:
      slippage_bps = (vwap_fill - mid) / mid * 1e4   (BUY)
      slippage_bps = (mid - vwap_fill) / mid * 1e4   (SELL)
  Plus the taker_fee_bps charged by the venue.
* **Partial fill** when the book is exhausted -- ok=False with reason
  ``book_exhausted`` so callers can tell apart a fully-OK fill (TCA
  noise) from a failed fill (venue/liquidity problem).
* **Invalid order** (zero/negative size, zero/negative price) returns a
  non-ok fill with reason ``invalid_order``. Never raises.

This module has no IO and no venue dependency. It is pure simulation
fed a snapshot. Live correlation lives in scripts/live_shadow_compare.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class BookLevel:
    """One price level in the L2 book."""
    price: float
    size: float


@dataclass(frozen=True)
class BookSnapshot:
    """L2 book at a point in time."""
    symbol: str
    venue: str
    ts_iso: str
    bids: tuple[BookLevel, ...]   # sorted high-to-low (best bid first)
    asks: tuple[BookLevel, ...]   # sorted low-to-high (best ask first)
    mid: float


@dataclass(frozen=True)
class ShadowOrder:
    """Intent to trade as it would be sent to the venue."""
    symbol: str
    side: Side
    size: float
    requested_px: float
    regime: str
    session: str
    taker_fee_bps: float = 0.0


@dataclass(frozen=True)
class ShadowFill:
    """Result of walking the book."""
    ok: bool
    size_filled: float
    vwap_fill: float
    slippage_bps: float
    fee_bps: float
    reason: str = ""
    levels_consumed: int = 0


def simulate_fill(order: ShadowOrder, book: BookSnapshot) -> ShadowFill:
    """Walk the book and return the resulting fill.

    Never raises. Invalid input -> ok=False with reason 'invalid_order'.
    Book exhaustion -> ok=False with reason 'book_exhausted' and the
    partial-fill stats so callers can still log them.
    """
    if order.size <= 0.0 or order.requested_px <= 0.0 or book.mid <= 0.0:
        return ShadowFill(
            ok=False,
            size_filled=0.0,
            vwap_fill=0.0,
            slippage_bps=0.0,
            fee_bps=0.0,
            reason="invalid_order",
        )

    levels = book.asks if order.side == "BUY" else book.bids
    if not levels:
        return ShadowFill(
            ok=False,
            size_filled=0.0,
            vwap_fill=0.0,
            slippage_bps=0.0,
            fee_bps=order.taker_fee_bps,
            reason="book_exhausted",
        )

    remaining = order.size
    notional = 0.0
    consumed = 0
    for lvl in levels:
        if remaining <= 0.0:
            break
        take = min(remaining, lvl.size)
        notional += take * lvl.price
        remaining -= take
        consumed += 1

    filled = order.size - remaining
    if filled <= 0.0:
        return ShadowFill(
            ok=False,
            size_filled=0.0,
            vwap_fill=0.0,
            slippage_bps=0.0,
            fee_bps=order.taker_fee_bps,
            reason="book_exhausted",
            levels_consumed=consumed,
        )

    vwap = notional / filled
    slip = (
        (vwap - book.mid) / book.mid * 1e4
        if order.side == "BUY"
        else (book.mid - vwap) / book.mid * 1e4
    )

    if remaining > 1e-12:
        return ShadowFill(
            ok=False,
            size_filled=filled,
            vwap_fill=vwap,
            slippage_bps=slip,
            fee_bps=order.taker_fee_bps,
            reason="book_exhausted",
            levels_consumed=consumed,
        )

    return ShadowFill(
        ok=True,
        size_filled=filled,
        vwap_fill=vwap,
        slippage_bps=slip,
        fee_bps=order.taker_fee_bps,
        reason="",
        levels_consumed=consumed,
    )
