"""Direct coverage for BTC market-quality helper math."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eta_engine.core.market_quality import (
    build_market_context_summary,
    derive_order_book_metrics,
    format_market_context_summary,
    order_book_age_ms,
    order_book_depth_score,
    order_book_freshness_score,
    order_book_quality,
    order_book_quality_bucket,
)


def test_order_book_age_accepts_explicit_age_and_timestamp_pairs() -> None:
    assert order_book_age_ms({"order_book_age_ms": -5}) == 0.0
    assert order_book_age_ms({"book_staleness_ms": "250.5"}) == 250.5

    bar_ts = datetime(2026, 4, 29, 12, 0, 1, tzinfo=UTC)
    snapshot_ts = datetime(2026, 4, 29, 12, 0, 0, 750_000, tzinfo=UTC)

    assert order_book_age_ms({"order_book_ts": snapshot_ts}, bar_ts=bar_ts) == pytest.approx(250.0)


def test_order_book_depth_score_prefers_explicit_score_and_clamps() -> None:
    assert order_book_depth_score({"depth_score": 14.0}) == 10.0
    assert order_book_depth_score({"book_depth_score": -1.0}) == 0.0


def test_order_book_metrics_score_deep_fresh_tight_book_high_quality() -> None:
    metrics = derive_order_book_metrics(
        {
            "bid_price": 60_000.0,
            "ask_price": 60_006.0,
            "bid_depth": 500.0,
            "ask_depth": 520.0,
            "order_book_age_ms": 125.0,
            "close": 60_003.0,
        }
    )

    assert metrics["order_book_age_ms"] == 125.0
    assert metrics["order_book_depth_score"] > 7.0
    assert metrics["order_book_freshness_score"] == 9.5
    assert metrics["order_book_quality"] > 7.0
    assert metrics["order_book_quality_bucket"] in {"Q6_8", "Q8_10"}


def test_order_book_freshness_and_quality_degrade_when_stale_wide_and_imbalanced() -> None:
    freshness = order_book_freshness_score({}, age_ms=12_000.0)
    quality = order_book_quality(
        {},
        age_ms=12_000.0,
        spread_bps=40.0,
        book_imbalance=1.0,
        depth_score=1.0,
        freshness_score=freshness,
    )

    assert freshness == 1.0
    assert quality < 2.0
    assert order_book_quality_bucket(quality) == "Q0_2"


def test_market_context_summary_prefers_nested_external_context() -> None:
    summary = build_market_context_summary(
        {
            "market_context": {
                "market_regime": "trend_up",
                "market_quality": 8.25,
                "external_score": 7.75,
                "asset": "BTC",
                "venue": "BYBIT",
                "updated_utc": "2026-04-29T12:00:00Z",
            },
            "market_quality_label": "GOOD",
            "spread_regime": "TIGHT",
            "spread_bps": 1.2,
            "book_imbalance": 0.2,
            "microstructure_score": 8.0,
            "pattern_edge_score": 7.5,
            "session_phase": "OPEN_DRIVE",
            "timeframe_label": "M1",
            "session_timeframe_key": "OPEN_DRIVE::M1",
            "order_book_quality_bucket": "Q8_10",
            "order_book_quality": 8.8,
        }
    )

    assert summary["market_context_regime"] == "trend_up"
    assert summary["market_context_quality"] == 8.25
    assert summary["market_context_external_score"] == 7.75
    assert summary["market_context_asset"] == "BTC"
    assert summary["order_book_quality_bucket"] == "Q8_10"
    assert summary["market_context"]["venue"] == "BYBIT"


def test_format_market_context_summary_includes_operator_critical_fields() -> None:
    line = format_market_context_summary(
        {
            "market_context_regime": "trend_up",
            "market_context_quality": 8.25,
            "market_context_external_score": 7.75,
            "session_timeframe_key": "OPEN_DRIVE::M1",
            "spread_regime": "tight",
            "market_context_asset": "BTC",
            "market_context_venue": "BYBIT",
            "order_book_quality_bucket": "Q8_10",
            "order_book_quality": 8.8,
            "microstructure_score": 8.0,
            "pattern_edge_score": 7.5,
        }
    )

    assert "market_context=TREND_UP" in line
    assert "quality=8.25" in line
    assert "tf=OPEN_DRIVE::M1" in line
    assert "asset=BTC" in line
    assert "venue=BYBIT" in line
    assert "ext=7.75" in line
    assert "ob=Q8_10" in line
