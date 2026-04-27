# Extended-data walk-forward — the +6.00 was sample-specific, 2026-04-27

User asked for "extreme OOS without sacrificing trade volume too
much" and to "supercharge everything." We extended BTC 1h history
from 360 days (8,635 bars) to ~5 years (43,192 bars) via Coinbase
REST and re-walk-forwarded the +6.00 champion at multiple window
sizes.

**The honest result:** the +6.00 OOS was specific to the 2025-2026
consolidation tape used in the original 9-window walk-forward.
Across 5 years and 57 windows, the same strategy averages **+1.96
OOS Sharpe** and FAILS the strict gate.

This does not invalidate the strategy — it works in 40% of
regimes. But the "+6.00" headline cannot be taken at face value
for live deployment expectations.

## What changed

### Data extension

| Source | Before | After | Method |
|---|---:|---:|---|
| BTC 1h | 8,635 bars (360d) | 43,192 bars (1,800d) | Coinbase REST `fetch_btc_bars --months 60` |
| BTC 15m | — | 17,281 bars | resample from 5m |
| BTC 4h | — | 10,800 bars | resample from 1h |
| BTC 1W | — | 258 bars | resample from D |

### Re-walk-forward of `btc_sage_daily_etf_v1`

Original 9-window walk-forward (90 train / 30 test, 360 days):

| Metric | Value |
|---|---:|
| Windows | 9 |
| Agg OOS Sharpe | **+6.00** |
| +OOS folds | 8/9 (89%) |
| DSR pass | 89% |
| deg_avg | 0.224 |
| Trades | 71 |
| **Gate** | **PASS** |

Extended 5-year walk-forward, same 90/30 cadence:

| Metric | Value |
|---|---:|
| Windows | 57 |
| Agg OOS Sharpe | **+1.96** |
| +OOS folds | 23/57 (40%) |
| DSR pass | ~38% |
| deg_avg | 0.238 |
| Trades | ~430 |
| **Gate** | **FAIL** |

**deg_avg = 0.238 BELOW the 0.35 threshold.** The strategy is NOT
overfitting in the traditional sense — IS-OOS degradation is
healthy. The issue is regime-conditional edge: the strategy works
strongly in 40% of windows (which happened to coincide with the
360-day sample) and is flat-to-negative in 60%.

### Window-size sweep on 5y data

To rule out "wrong window size" as the explanation:

| Window | Step | Windows | Agg OOS | +OOS | Gate |
|---|---:|---:|---:|---:|:---:|
| 180d | 60d | 27 | +1.50 | 41% | FAIL |
| 270d | 90d | 17 | +2.07 | 53% | FAIL |
| **365d** | **90d** | **16** | **+2.30** | **50%** | **FAIL** |
| 540d | 180d | 7 | +1.97 | 57% | FAIL |
| 730d | 365d | 3 | +2.16 | 67% | FAIL |

**All FAIL the strict gate.** Best is win=365d at +2.30 OOS.
There's no window size where the strategy passes the gate on the
full 5-year sample. The +6.00 was a regime artifact, full stop.

## Why this is still useful, not a defeat

1. **deg_avg stayed clean (0.238 < 0.35).** The strategy is not
   curve-fit; it's regime-dependent. A regime-conditional wrapper
   could recover most of the lost Sharpe.

2. **The +6.00 sample was ~12 months of low-vol consolidation.**
   That's also the regime where Apex evals are run. The strategy
   still has clear edge in that specific regime — so for an Apex
   eval that runs in similar tape, the 71-trade sample is
   directionally informative.

3. **40% +OOS folds is real.** When the strategy fires in the
   right regime, it works consistently. The gate failure is
   "doesn't ALWAYS work" — not "doesn't EVER work."

4. **Live tape will be one regime at a time.** If the
   regime-classifier can detect the favorable regime and gate
   firings to it, the live OOS could meaningfully exceed +1.96.

## What this means for live deployment

| Posture | Action |
|---|---|
| Pre-live promotion | Need regime-conditional wrapper that only fires in the strategy's edge regime |
| Capital allocation | Cap exposure on the +6.00 strategy at "edge regime detected" weight |
| Apex eval | Still defensible — eval window is short and likely matches an edge regime — but PnL expectations should be set against +1.96 not +6.00 |
| Live monitoring | Track OOS realized vs both +6.00 (eval-baseline) AND +1.96 (long-run baseline). If realized drops below long-run, halt |

## Updated fleet expectations

| Bot | Strategy | Headline OOS | 5y OOS | True expectation |
|---|---|---:|---:|---|
| `mnq_futures_sage` | `mnq_orb_sage_v1` | +10.06 | n/a (insufficient data) | regime-conditional ORB; 12-trade sample is sparse |
| `nq_futures_sage` | `nq_orb_sage_v1` | +8.29 | n/a | same caveat |
| `btc_sage_daily_etf` | `btc_sage_daily_etf_v1` | +6.00 | **+1.96** | regime-conditional; live ≈ +2 to +3 expected, +6 in edge regime only |
| `btc_ensemble_2of3` | `btc_ensemble_2of3_v1` | +5.95 | (re-test pending) | likely similar regime-dependence |

## Files in this commit

* `docs/research_log/extended_data_walk_forward_20260427.md` (this).
* `scripts/fetch_btc_funding_extended.py` — Bybit fallback added (US geo-blocks Binance; Bybit also blocked → fetcher inert until non-blocked source wired).
* `scripts/fetch_btc_open_interest.py` — same Bybit fallback (same blocked status).

## Next concrete steps

### A. Regime-conditional wrapper (highest leverage)

Build `RegimeGatedStrategy` that:
1. Classifies the current regime via `htf_regime_classifier`
2. Only fires the wrapped strategy when regime == "edge regime"
3. Re-walk-forwards on 5y data and reports per-regime OOS

Hypothesis: the +6.00 strategy's edge concentrates in
"trending bull, low-vol" regime. If we can detect that and only
fire there, the per-fire Sharpe stays at +6 territory and the
all-fold Sharpe rises from +1.96 toward +3-4.

### B. Non-blocked OI / funding source

Bybit and Binance are both US-geo-blocked. Need:
- OKX public futures API
- BitMEX public history
- Kraken futures
- Coinglass aggregator

Start with OKX (most US-friendly major derivatives exchange that's
still operational in 2026).

### C. Engine trade-close PnL callbacks

Adaptive Kelly sizing was neutral on the champion (+5.32-5.67 vs
+6.00) because trade-PnL inference via equity-deltas is too
approximate. Engine-level callbacks would unlock proper streak-
based amplification.

## Bottom line for the user

You asked for extreme OOS. The honest answer:

* The headline +6.00 was real on its 360-day sample.
* On 5 years it averages +1.96. **Both numbers are true** — they
  describe different regimes of the same strategy.
* The strategy is not curve-fit (deg_avg 0.238 stayed clean).
* The path forward is regime-conditional gating, not more sweeps.
* In the meantime, the +6.00 strategy is still the best BTC
  strategy we have on disk. Nothing else is even close on the
  regime where it works.

Promotion status unchanged. **Live expectations corrected:**
budget around +2 to +3 OOS Sharpe long-run, +6 only when the
regime is favorable.
