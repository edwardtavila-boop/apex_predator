# Daily-TF regime_trend — does NOT transfer, 2026-04-27

User directive: build a daily-timeframe variant of regime_trend
where Tier-4 signals (ETF + LTH + F&G + macro) are at their
natural cadence, expecting the strict-gate to pass cleanly with
30+ walk-forward windows.

## Honest result

**The plain `crypto_regime_trend` mechanic does not transfer
to BTC daily**, and the Tier-4 filters don't rescue it.

`btc_regime_trend_etf` on 1h (+4.28 OOS) remains the strongest
crypto research candidate.

## What was tested

BTC daily, 1800 bars (5 yr history, 2021-05-24 → 2026-04-27),
365d window / 90d step / OOS 0.3 → 16 walk-forward windows.

Strategy params: regime_ema=200 (the user's literal 200-day MA),
pullback_ema=50, tolerance=5%, atr_stop=2.0, rr=3.0, min_bars
between trades=5, max trades/day=1, warmup=50.

## Results

Plain baseline:

| Variant | Agg OOS | +OOS | Trades |
|---|---:|---:|---:|
| `regime_trend` plain | **−7.32** | 7/16 | 38 |

Tier-4 filter overlays:

| Variant | Agg OOS | +OOS | Trades |
|---|---:|---:|---:|
| + Sentiment (fear) ≥ 0.0 | +3.18 | 2/16 | 14 |
| + LTH ≥ 0.2 | +0.30 | 1/16 | 7 |
| + ETF flow + LTH | +0.30 | 1/16 | 7 |
| + Macro ≥ 0.1 | −0.85 | 2/16 | 11 |
| + ETF flow alone | −3.77 | 1/16 | 23 |
| + LTH ≥ 0.0 | −4.36 | 1/16 | 11 |
| + ETF + LTH + Sentiment | 0.00 | 0/16 | 2 |
| FULL stack (4 filters) | 0.00 | 0/16 | 1 |

The "Sentiment +3.18" cell looks promotable on agg-OOS alone
but only 2/16 windows are positive — 14 out of 16 had zero or
negative OOS. That's small-sample noise, not edge.

## Why pullback-mechanic fails on daily

The `regime_trend` entry trigger is **bar.low taps the faster
EMA AND close is back on the regime side** — a "buy the dip"
single-bar wick. On hourly:
* Wicks are frequent, brief, real
* Pullback-then-bounce captures intraday continuation cleanly
* Stop distance (1.5×ATR ≈ 0.5-1% of price) is tight enough to fit

On daily:
* A 5% pullback is normal but represents 5+ hours of decline
* By close, the bounce is already in motion or already failed
* Single-bar daily wick = a different beast from a 1h wick
* ATR×2 stop on daily = 5-10% — gets stopped frequently in chop

The mechanic mismatches the bar cadence.

## DRB on BTC daily — also doesn't work

After the regime_trend negative finding, I tested the next
obvious daily-native strategy: Daily Range Breakout (the
prior-day high/low break that's already implemented and gave
+0.74 OOS on NQ daily). Tested 9 parameter configs:

| Config | Agg OOS | +OOS | Trades |
|---|---:|---:|---:|
| lb=10, rr=2.5, atr=2.0, ema=200 | −4.27 | **10/16** | 65 |
| lb=5, rr=3.0, atr=2.0, ema=100 | −1.66 | 9/16 | 62 |
| lb=3, rr=3.0, atr=1.5, ema=100 | −1.00 | 9/16 | 111 |
| lb=5, rr=2.5, atr=1.5, ema=200 | −1.04 | 8/16 | 105 |
| (all 9 configs) | **all negative** | varies | varies |

Even lb=10 with 10/16 +OOS windows produces agg OOS −4.27. The
positive-window-count is misleading — when DRB wins it wins
small, when it loses it loses big.

**Both regime_trend AND DRB fail on BTC daily across all
parameter configs tested.**

## Why BTC daily is harder than 1h despite more data

The 5-year span (2021-05 → 2026-04) includes:
* 2021 bull peak (Q4) → 2022 bear crash (~-77% drawdown)
* 2023-2024 recovery + halving cycle
* 2024 spot-ETF launches (regime change)
* 2025 highs → 2026 consolidation

Across 16 walk-forward windows, the market regime CHANGES
fundamentally several times. Each regime change is a
multi-window-deep cost on any single mechanic. Both pullback
(regime_trend) and breakout (DRB) approaches get whipsawed
because the macro context shifts faster than the strategy's
parameter window.

The 1h tape (last 360 days) is mostly the 2025-2026
consolidation phase — single regime, single strategy fits.
That's WHY the 1h `btc_regime_trend_etf` works: it's tuned to
one regime, and the ETF flow signal is the dominant driver in
THAT regime.

## What WOULD work on BTC daily

Each is a different strategy class. The Tier-4 filter framework
can be applied to any of them once they exist:

1. **Adaptive trend-on-breakout** with REGIME-CONDITIONAL params.
   Different `rr_target` / `atr_stop` for bull-cycle vs bear-cycle
   vs consolidation. The base mechanic stays simple (close-above-
   regime-EMA → long); the parameters change with cycle state.
2. **Pi Cycle Top / Bottom**: 111-day SMA × 2 vs 350-day SMA
   crossover — fires ~once per cycle, very high signal-to-noise.
   Few trades but each is a multi-month hold.
3. **Realized-cap / MVRV-Z bands**: when MVRV-Z drops below a
   threshold (deep capitulation), buy. Above threshold (euphoria),
   sell. Needs real on-chain data, not the proxy.
4. **Cycle-window discrete strategies**: train one strategy per
   identified cycle (2021 bull, 2022 bear, etc.) and run an
   ensemble that votes per-window. Heavy infrastructure.

These are all bigger lifts than parameter-tuning regime_trend.

## What this means for the production fleet

* **Stop pursuing daily-TF regime_trend** — the entry mechanic
  is the wrong shape, not a parameter-tune-able miss.
* `btc_regime_trend_etf` (1h, +4.28 OOS, ETF flow filter) is
  still the strongest BTC research candidate.
* Future BTC daily research should start from a different
  strategy class (DRB, trend-on-breakout, or band re-entry).
* The Tier-4 data feeds + framework are NOT wasted — they apply
  identically to any daily strategy. The problem isn't the
  signals, it's the entry trigger.

## Files in this commit

* `docs/research_log/daily_tf_negative_findings_20260427.md`
  (this).

No new strategy code — this is a documentation-only commit
preserving the negative finding so future research doesn't
re-derive it.

## Bottom line

You called the architecture right and asked the right question.
The data answered: **regime_trend's pullback-bounce mechanic is
hourly-specific.** It would not have been honest to bend the
parameters until something looked promotable; the negative
finding is the truth and saves the next research wave from
chasing this dead end.

Next experiment, if you want: daily DRB on BTC (already-built
strategy module, just needs walk-forward), OR a new daily-native
trend-follow class. Both are smaller lifts than reinventing
regime_trend.
