"""Per-ticker optimal strategy stacks — the answer to "which tools work
best for this market?".

Each instrument needs different tools because what moves price differs:
- MNQ/NQ: RTH structure, ES correlation, SMC order-flow levels
- BTC: ETF flows, daily sage, on-chain LTH supply, macro tailwind
- ETH: oscillation regime, compression breakout, funding basis
- SOL: high-beta BTC proxy, wide stops, tight correlation gate

This module defines the optimal strategy STACK per ticker — not a single
strategy_kind, but a layered composition of:
  1. Regime classifier (market context → bias + mode)
  2. Entry strategy (per-bar signal generation)
  3. Gate layer (sage, confluence, correlation)
  4. Sizing (conviction-based, risk-adaptive)

The bridge reads this and builds the composed strategy at dispatch time.

Founded on the user's directive: "we study the market to hit the target
based on context we verify everything and strike when the iron is hot
be it scalp or swing taking advantage of imbalances."

2026-04-30.
"""

from __future__ import annotations

PER_TICKER_OPTIMAL: dict[str, dict] = {
    # ═══════════════════════════════════════════════════════════════
    # MNQ futures — micro E-mini Nasdaq
    # ═══════════════════════════════════════════════════════════════
    "MNQ": {
        "regime": {
            "module": "htf_regime_classifier",
            "params": {
                "ema_fast": 50, "ema_slow": 200,
                "trend_distance_pct": 0.015, "range_atr_pct_max": 0.008,
                "slope_lookback": 5, "slope_threshold": 0.0003,
                "warmup_bars": 200,
            },
            "allowed_modes": ["trend_follow", "mean_revert"],
            "skip_on": ["volatile", "skip"],
        },
        "entry": {
            "module": "htf_routed_strategy",
            "trend_follow": {
                "strategy": "orb_sage_gated",
                "params": {"range_minutes": 15, "rr_target": 3.0, "atr_stop_mult": 1.5,
                           "sage_min_conviction": 0.65, "sage_lookback_bars": 200},
            },
            "mean_revert": {
                "strategy": "sweep_reclaim",
                "params": {"level_lookback": 20, "reclaim_window": 3,
                           "wick_pct_min": 0.6, "volume_z_min": 0.8,
                           "rr_target": 2.0, "atr_stop_mult": 1.5,
                           "max_trades_per_day": 2},
                "preset": "mnq_intraday",
            },
            "enforce_htf_bias_alignment": True,
            "honor_htf_skip": True,
        },
        "gate": {
            "module": "confluence_scorecard",
            "min_score": 3, "a_plus_score": 4, "a_plus_size_mult": 1.5,
            "factors": {
                "trend_alignment": {"ema_periods": [9, 21, 50]},
                "vwap_alignment": True,
                "volume_z": {"lookback": 20, "min_z": 0.0},
                "liquidity_proximity": {"distance_pct": 0.003},
                "time_of_day": {"session_window": [2, 18]},
            },
        },
        "sizing": {"risk_pct": 0.01, "max_trades_per_day": 2},
        "sage_schools_hint": [
            "Dow", "Wyckoff", "Elliott", "SMC/ICT", "order flow",
            "trend", "volume_profile", "market_profile", "seasonality",
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # BTC — 24/7, ETF-flow-driven, trend-prone
    # ═══════════════════════════════════════════════════════════════
    "BTC": {
        "regime": {
            "module": "htf_regime_oracle",
            "params": {
                "weights": {"etf_flow": 0.30, "htf_ema": 0.25, "lth_proxy": 0.15,
                            "macro_tailwind": 0.15, "fear_greed": 0.15},
                "direction_threshold": 0.25,
                "smoothing_period_days": 3,
                "etf_flow_scale_usd_m": 500,
                "htf_ema_period": 100,
            },
        },
        "entry": {
            "module": "sage_daily_gated",
            "params": {
                "min_daily_conviction": 0.50, "strict_mode": False,
                "underlying": "crypto_macro_confluence",
                "crypto_regime_trend": {
                    "regime_ema": 100, "pullback_ema": 21,
                    "pullback_tolerance_pct": 3.0, "atr_stop_mult": 2.0,
                    "rr_target": 3.0, "warmup_bars": 120,
                },
                "macro_confluence": {
                    "require_etf_flow_alignment": True,
                    "require_eth_alignment": False,
                    "extreme_funding_threshold": 0.005,
                },
            },
        },
        "gate": {
            "module": "confluence_scorecard",
            "min_score": 2, "a_plus_score": 3, "a_plus_size_mult": 1.3,
            "factors": {
                "trend_alignment": {"ema_periods": [21, 50, 100]},
                "funding_skew": True,
                "etf_flow_alignment": True,
                "liquidity_proximity": {"distance_pct": 0.01},
            },
        },
        "sizing": {"risk_pct": 0.01, "max_trades_per_day": 2},
        "sage_schools_hint": [
            "Dow", "Elliott", "Fib", "on-chain", "funding", "cross-asset corr",
            "Gann", "NEoWave", "vol_regime", "sentiment", "ML",
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # ETH — oscillating crab regime, compression breakout
    # ═══════════════════════════════════════════════════════════════
    "ETH": {
        "regime": {
            "module": "htf_regime_classifier",
            "params": {
                "ema_fast": 50, "ema_slow": 200,
                "trend_distance_pct": 0.02, "range_atr_pct_max": 0.012,
                "slope_lookback": 5, "slope_threshold": 0.0002,
                "warmup_bars": 200,
            },
            "allowed_modes": ["trend_follow", "mean_revert"],
            "skip_on": ["volatile"],
        },
        "entry": {
            "module": "htf_routed_strategy",
            "trend_follow": {
                "strategy": "sage_daily_gated",
                "params": {"min_daily_conviction": 0.30, "strict_mode": False},
            },
            "mean_revert": {
                "strategy": "compression_breakout",
                "params": {"close_location_min": 0.65, "volume_z_min": 0.4,
                           "bb_width_pct_max": 0.30, "rr_target": 2.5,
                           "atr_stop_mult": 1.8, "cooldown_bars": 12},
                "preset": "eth",
            },
            "enforce_htf_bias_alignment": True,
            "honor_htf_skip": True,
        },
        "gate": {
            "module": "confluence_scorecard",
            "min_score": 2, "a_plus_score": 3, "a_plus_size_mult": 1.2,
            "factors": {
                "trend_alignment": {"ema_periods": [21, 50, 100]},
                "funding_skew": True,
                "volume_z": {"lookback": 20, "min_z": 0.2},
            },
        },
        "sizing": {"risk_pct": 0.01, "max_trades_per_day": 2},
        "sage_schools_hint": [
            "Dow", "Wyckoff", "Fib", "S/R", "trend", "volume_profile",
            "market_profile", "funding", "cross-asset corr", "vol_regime",
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # SOL — high-beta BTC proxy, wider stops
    # ═══════════════════════════════════════════════════════════════
    "SOL": {
        "regime": {
            "module": "feature_regime_classifier",
            "params": {
                "use_funding": True, "funding_extreme": 0.005,
                "bull_threshold": 0.25,
            },
        },
        "entry": {
            "module": "crypto_orb",
            "params": {
                "range_minutes": 240, "atr_stop_mult": 1.25,
                "rr_target": 2.5, "max_trades_per_day": 1,
            },
        },
        "gate": {
            "module": "regime_gated_strategy",
            "params": {
                "allowed_regimes": ["trending"],
                "allowed_biases": ["long", "short"],
                "require_bias_match_side": True,
            },
        },
        "sizing": {"risk_pct": 0.005, "max_trades_per_day": 1},
        "sage_schools_hint": [
            "Dow", "trend", "funding", "cross-asset corr", "vol_regime",
        ],
    },
}


def optimal_for(symbol: str) -> dict | None:
    """Return the optimal strategy stack config for a symbol, or None."""
    return PER_TICKER_OPTIMAL.get(symbol.upper())
