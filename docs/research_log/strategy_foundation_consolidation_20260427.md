# Strategy foundation consolidation — six core strategies, 2026-04-27

User mandate (verbatim):
> "i think we need to reconsider our core strategies use this as the
> foundation to branch from take everything that helps leave behind
> the fluff i need mnq and btc strategies i can backtest also grid
> bot trading styles that work"

Followed by the detailed strategy spec for:
* MNQ futures (ORB / EMA-VWAP pullback / liquidity sweep)
* BTC futures (compression breakout / EMA-VWAP pullback / sweep-reclaim)
* Crypto grid (neutral / long-trend / short-trend / adaptive-vol)

This doc is the consolidation map: **what we keep, what we drop,
what we built.**

## The Six Core Strategies (final roster)

| # | Strategy | Asset | Module |
|---|---|---|---|
| 1 | MNQ ORB Continuation | MNQ 5m | `orb_strategy.py` |
| 2 | MNQ EMA/VWAP Pullback | MNQ 5m | `crypto_regime_trend_strategy.py` (asset-agnostic; configure for MNQ) |
| 3 | MNQ Liquidity Sweep / Reclaim | MNQ 5m | **NEW** `sweep_reclaim_strategy.py` |
| 4 | BTC Compression Breakout | BTC 1h | **NEW** `compression_breakout_strategy.py` |
| 5 | BTC EMA/VWAP Pullback | BTC 1h | `crypto_regime_trend_strategy.py` |
| 6 | BTC Sweep / Reclaim | BTC 1h | **NEW** `sweep_reclaim_strategy.py` (BTC preset) |

Plus crypto grid:
| Strategy | Asset | Module |
|---|---|---|
| Crypto Adaptive Volatility Grid | BTC/ETH 1h | `grid_trading_strategy.py` (extended with adaptive mode) |

That's 7 backtestable systems total, mapped 1:1 to the user spec.

## What we KEPT (and why)

| File | Kept because |
|---|---|
| `orb_strategy.py` | The MNQ-A ORB strategy. Already promoted as `mnq_orb_sage_v1`. |
| `crypto_regime_trend_strategy.py` | Generic EMA-stack pullback continuation. Same mechanic for MNQ-B and BTC-B; just different config. |
| `crypto_macro_confluence_strategy.py` | Existing filter framework (ETF flow, on-chain, sentiment). Useful when wired with new providers. |
| `sage_daily_gated_strategy.py` | Daily-cadence directional veto. Was the +6.00 BTC champion's wrapper. |
| `regime_gated_strategy.py` | Generic regime-conditional gate (asset-class presets in place). |
| `feature_regime_classifier.py` | First gate to deliver +0.30 OOS lift on the +1.77 baseline. |
| `multi_strategy_composite.py` | Lets one bot run N strategies in parallel (user mandate). |
| `mtf_scalp_strategy.py` | 15m + 1m micro-entry scalper (user mandate). |
| `adaptive_kelly_sizing.py` | Engine-callback-driven sizing wrapper (still useful for regime-invariant strategies). |
| `grid_trading_strategy.py` | Extended with adaptive volatility mode this commit. |
| `funding_divergence_strategy.py` | Even though standalone showed no edge, the 5y BitMEX funding feed is now wired into the macro confluence filter — same provider used by `FeatureRegimeClassifier`. |

## What we BUILT (gap fillers)

| File | What it adds |
|---|---|
| **`sweep_reclaim_strategy.py`** | Mechanical Wyckoff spring/upthrust. Single class with MNQ + BTC preset factories. Translates the user-spec'd liquidity-sweep pattern into pure mechanical triggers (recent N-bar high/low pierce + reclaim within window + wick quality + volume z-score gate). Rep'd by 4 unit tests. |
| **`compression_breakout_strategy.py`** | Volatility-compression release breakout. BB-width percentile + ATR-MA dual compression detector; recency window so breakout fires on expansion bars (not just compressed bars). Trend EMA + volume z + close-location gates. MNQ + BTC presets. Rep'd by 3 unit tests. |
| **`confluence_scorecard.py`** | Reusable wrapper: scores any sub-strategy's proposed entry on 0-N factors (trend / VWAP / ATR regime / volume + caller-attached HTF / session / liquidity predicates). Min-score gate + A+ size boost. Implements the user-spec'd "3-of-5 minimum, 4-5 A+, increase size only at 4+" rule. Rep'd by 4 unit tests. |
| **`grid_trading_strategy.py` (extended)** | Adaptive volatility mode: spacing scales linearly with current ATR percentile rank in [adaptive_atr_pct_min, adaptive_atr_pct_max] band; kill switch fires when rank exceeds `adaptive_kill_atr_pct`; range-break kill switch when price closes beyond grid range. Rep'd by 3 unit tests. |

14/14 unit tests pass on the new pieces.

## What we did NOT delete (despite "leave the fluff" directive)

The user said "leave the fluff" but didn't specify which files are
fluff. The honest call: existing strategies (especially registered
in `per_bot_registry.py` with active promotions) shouldn't be
deleted by my judgment alone. What I'm marking as candidates for
later cleanup:

| File | Verdict | Why marked but not deleted |
|---|---|---|
| `crypto_orb_strategy.py` | keep | crypto-side of ORB; used by ETH crypto-orb bot |
| `crypto_trend_strategy.py` | keep | sibling; lighter-weight than regime_trend |
| `crypto_meanrev_strategy.py` | keep | grid-mechanic-adjacent; useful in ranges |
| `crypto_scalp_strategy.py` | keep | currently inactive but documented |
| `crypto_ema_stack_strategy.py` | candidate | overlaps with regime_trend |
| `pi_cycle_strategy.py` | candidate | classical Pi Cycle; 0 fires on canonical params |
| `htf_routed_strategy.py` | keep | HTF + LTF execution router |
| `htf_regime_oracle.py` | keep | used by routed strategy |
| `sage_consensus_strategy.py` | candidate | early sage prototype; superseded by daily-gated |
| `sage_gated_orb_strategy.py` | keep | active in `mnq_orb_sage_v1` |
| `crypto_htf_conviction_strategy.py` | candidate | superseded by sage_daily_gated |
| `ensemble_voting_strategy.py` | keep | active as `btc_ensemble_2of3` |
| `drawdown_aware_sizing.py` | candidate | deprecated by adaptive_kelly canonical path |
| `generic_sage_daily_gate.py` | keep | the generic version of sage_daily_gated |
| `funding_divergence_strategy.py` | keep | mechanic real even if standalone weak |

If the user says "delete the candidates", I'll do so as a separate
commit. Defaulting to keep prevents file-loss surprises.

## How the pieces compose for a real backtest

The user can now compose a backtest like this:

### MNQ multi-strategy bot

```python
from eta_engine.strategies.orb_strategy import ORBStrategy, ORBConfig
from eta_engine.strategies.crypto_regime_trend_strategy import (
    CryptoRegimeTrendStrategy, CryptoRegimeTrendConfig,
)
from eta_engine.strategies.sweep_reclaim_strategy import (
    SweepReclaimStrategy, mnq_intraday_sweep_preset,
)
from eta_engine.strategies.confluence_scorecard import (
    ConfluenceScorecardStrategy, ConfluenceScorecardConfig,
)
from eta_engine.strategies.multi_strategy_composite import (
    MultiStrategyComposite, MultiStrategyConfig,
)

# Three strategies, all wrapped in the 3-of-N scorecard
orb = ConfluenceScorecardStrategy(
    ORBStrategy(ORBConfig(...)),
    ConfluenceScorecardConfig(min_score=3, a_plus_score=4),
)
pullback = ConfluenceScorecardStrategy(
    CryptoRegimeTrendStrategy(CryptoRegimeTrendConfig(...)),
    ConfluenceScorecardConfig(min_score=3, a_plus_score=4),
)
sweep = ConfluenceScorecardStrategy(
    SweepReclaimStrategy(mnq_intraday_sweep_preset()),
    ConfluenceScorecardConfig(min_score=3, a_plus_score=4),
)

bot_strategy = MultiStrategyComposite(
    [("orb", orb), ("pullback", pullback), ("sweep", sweep)],
    MultiStrategyConfig(conflict_policy="confluence_weighted"),
)
```

### BTC multi-strategy bot

```python
from eta_engine.strategies.compression_breakout_strategy import (
    CompressionBreakoutStrategy, btc_compression_preset,
)
from eta_engine.strategies.crypto_regime_trend_strategy import (...)
from eta_engine.strategies.sweep_reclaim_strategy import (
    SweepReclaimStrategy, btc_daily_sweep_preset,
)

compression = CompressionBreakoutStrategy(btc_compression_preset())
pullback = CryptoRegimeTrendStrategy(CryptoRegimeTrendConfig(...))
sweep = SweepReclaimStrategy(btc_daily_sweep_preset())

# Wrap in feature-regime gate (the +0.30 lift winner)
gated_compression = RegimeGatedStrategy(compression, btc_daily_provider_preset())
gated_pullback = RegimeGatedStrategy(pullback, btc_daily_provider_preset())
gated_sweep = RegimeGatedStrategy(sweep, btc_daily_provider_preset())

bot_strategy = MultiStrategyComposite(
    [("compression", gated_compression),
     ("pullback", gated_pullback),
     ("sweep", gated_sweep)],
    MultiStrategyConfig(conflict_policy="confluence_weighted"),
)
```

### Crypto adaptive grid

```python
from eta_engine.strategies.grid_trading_strategy import (
    GridTradingStrategy, GridConfig,
)

grid = GridTradingStrategy(GridConfig(
    ref_lookback=50, n_levels=6, atr_period=14,
    adaptive_volatility=True,
    adaptive_atr_pct_lookback=100,
    adaptive_atr_pct_min=0.30, adaptive_atr_pct_max=0.70,
    adaptive_min_spacing_pct=0.0025,
    adaptive_max_spacing_pct=0.012,
    adaptive_kill_atr_pct=0.85,
    range_break_mult=1.0,
))
```

## What's still missing for full user-spec parity

These are listed in the user's "Next AI Improvements" section but
NOT implemented in this commit. They would be follow-on work:

* **Meta-labeling / win-probability model** — predict p_win, p_retest,
  p_adverse from pre-entry features. Requires labeled trade history;
  doable once 6 months of paper-soak data lands.
* **Entry optimizer** (market vs limit-retest vs stop vs skip) —
  needs the meta-label model first.
* **Exit selector by regime** — fixed vs partial+runner vs trail
  vs early-cut. Hooks into the engine's `on_trade_close` callback
  but needs the trade-feature stream to make per-trade decisions.
* **Funding-aware crowdedness filter for BTC** — funding z-score
  + OI delta + price-distance-from-VWAP composite. Funding data
  is on disk (5y BitMEX); OI requires paid aggregator (see
  `paid_data_aggregator_landscape_20260427.md`).
* **CME-aligned BTC bars for live drift comparison** — gated on
  IBKR Client Portal Gateway + CME Crypto subscription.

## Files in this commit

* `strategies/sweep_reclaim_strategy.py` — new (335 lines)
* `strategies/compression_breakout_strategy.py` — new (335 lines)
* `strategies/confluence_scorecard.py` — new (290 lines)
* `strategies/grid_trading_strategy.py` — extended (adaptive vol mode)
* `tests/test_foundation_strategies.py` — 14 tests, all pass
* `docs/research_log/strategy_foundation_consolidation_20260427.md` (this)

## Bottom line

You asked for backtestable rule sets, not vague signals. **Every
trigger in this commit is mechanical and per-bar.** Every config
knob is named, defaulted, and tunable. Every strategy is wrapped
in the same protocol so they compose into multi-strategy bots
without engine changes.

The six core strategies (plus the adaptive grid) match your spec.
The confluence scorecard gives you the 3-of-5 / 4-5 A+ filter you
asked for. The asset presets keep MNQ and BTC configs separate so
they don't accidentally cross-contaminate.

Walk-forward testing is unblocked on everything except the
user-spec'd 1m+15m MNQ scalper (gated on extending MNQ 1m data
beyond the current 22.7 days — see prior research log).
