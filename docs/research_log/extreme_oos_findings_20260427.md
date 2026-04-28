# Extreme-OOS sweep — practical ceiling found, 2026-04-27

User asked for "extreme OOS without sacrificing trade volume too
much." Tested four genuinely outside-the-box angles. Honest
result: the existing **+6.00 / +5.95 BTC strategies are at the
practical optimum** for our 360-day BTC 1h dataset.

Going meaningfully higher requires fundamentally NEW INFORMATION
that we don't have on disk yet. The next data source is
**paper-soak — actual live trading data — which expands the
dataset rather than re-mining the existing one.**

## What was tested

### 1. Faster timeframe execution (BTC 5m)

Hypothesis: 5m bars yield more entry opportunities. With 180 days
of BTC 5m, walk-forward 30/15 gives ~10 windows.

| Config | Agg OOS | +OOS | Trades | Gate |
|---|---:|---:|---:|:---:|
| regime=200 mbb=24 | +1.49 | 6/10 | 258 | FAIL |
| regime=300 mbb=36 | +2.28 | 6/10 | 200 | FAIL |
| regime=500 mbb=60 | +0.40 | 6/10 | 136 | FAIL |
| regime=1000 mbb=100 | +0.26 | 5/10 | 75 | FAIL |

**Result:** 5m fires lots of trades but each has materially
weaker per-trade Sharpe. The 1h timeframe is the sweet spot for
the regime_trend mechanic.

### 2. Multi-symbol portfolio (ETH/SOL on top of BTC)

Hypothesis: ETH/SOL share crypto-cycle macro structure with BTC;
running parallel bots gives 3x trade count.

| Symbol | Agg OOS | +OOS | DSR_pass | Trades | Gate |
|---|---:|---:|---:|---:|:---:|
| BTC (no ETF, sage only) | +2.79 | 7/9 | 78% | 93 | FAIL |
| **BTC (with ETF)** | **+6.00** | 8/9 | 89% | 71 | **PASS** |
| ETH (no ETF — n/a) | +1.97 | 6/9 | 44% | 91 | FAIL |
| SOL (no ETF — n/a) | +2.34 | 7/9 | 78% | 104 | FAIL |

**Result:** BTC's ETF flow filter is a UNIQUE signal. Without it,
BTC drops to +2.79; ETH/SOL only have sage-daily and land at
+1.97 / +2.34. Neither alone passes the strict gate.

A spot-ETH-ETF data feed (Farside has it; we'd need to add the
fetcher) might lift ETH similarly to how BTC's lifted. SOL has no
ETF approval yet so this angle doesn't apply.

### 3. Reduced cooldown / increased max-trades-per-day

Hypothesis: the +6.00 champion has cooldown=12h on 1h bars;
reducing this should add trades.

| Variant | Agg OOS | +OOS | Trades | vs +6.00 |
|---|---:|---:|---:|---:|
| **mbb=12 max=5 conv=0.50** (champion) | **+6.00** | 8/9 | 71 | — |
| mbb=8 max=4 conv=0.50 | +3.81 | 7/9 | 80 | -2.19 |
| mbb=6 max=4 conv=0.50 | +3.84 | 6/9 | 87 | -2.16 |
| mbb=4 max=8 conv=0.50 | +3.67 | 7/9 | 92 | -2.33 |
| mbb=6 max=4 conv=0.40 | +4.34 | 6/9 | 80 | -1.66 |

**Result:** Reducing cooldown adds trades but **dilutes edge
faster than trade count grows**. The +6.00 champion is at its
trade-count optimum.

### 4. Multi-asset sage gating (BTC+ETH+SOL daily-sage agreement)

Hypothesis: when all 3 cryptos' daily-sage agree, that's
crypto-wide directional conviction.

| Variant | Agg OOS | +OOS | Trades | Gate |
|---|---:|---:|---:|:---:|
| **BTC daily-sage only** (champion) | **+6.00** | 8/9 | 71 | **PASS** |
| Multi-asset majority (2 of 3) | +4.43 | 8/9 | 62 | PASS |
| Multi-asset unanimous (3 of 3) | +5.47 | 8/9 | 64 | PASS |

**Result:** ETH/SOL daily-sage correlates with BTC's, so
multi-asset agreement adds noise more than information. Both
multi-asset variants PASS the gate (8/9 +OOS, 89% pass) — but
neither beats the BTC-only +6.00.

## Why we've hit a practical ceiling

The +6.00 BTC sage-daily-gated strategy uses three signals:
1. **regime_trend** entry trigger (1h pullback + ATR exits)
2. **ETF flow filter** (daily institutional demand, BTC-unique)
3. **sage 22-school daily composite** (regime context)

Together these cover:
* Local price structure (regime_trend on 1h)
* Macro institutional flow (ETF)
* Multi-school market-theory wisdom (sage daily)

There aren't OBVIOUSLY-uncorrelated signals left to add at this
data density:
* Funding rates: have BTCFUND_8h (96 days) — too short
* On-chain: have LTH proxy (price-derived), not real metric
* Sentiment: have F&G index, but it correlates with price
* Volume profile: not in OHLCV
* Options skew: not on disk
* Order flow / depth: not on disk

## What WOULD push past +6.00

### A. More data (most leverage, lowest novelty)

Paper-soak the +6.00 / +5.95 candidates. Live trading data extends
the walk-forward sample. With 18+ months instead of 12:
* W5 (-4.19 OOS) ceases to dominate the average
* deg_avg falls further below 0.35
* Sharpe estimate stabilizes
* Confidence in promotion grows

### B. Tier-5 data (highest novelty, requires acquisition)

Real on-chain feed (Glassnode/CoinMetrics LTH supply, exchange
reserves, MVRV-Z). Currently we have a price-derived proxy that
correlates with price; a real on-chain feed would be genuinely
uncorrelated information.

ETH spot-ETF flow (Farside has it; needs fetcher addition).
Would let ETH replicate BTC's 1.32 Sharpe lift from ETF filter.

Options skew / put-call ratio (Deribit / CME). A "panic gauge"
that's uncorrelated with price-derived signals.

### C. Engine improvements (medium leverage)

Trade-close PnL callbacks would unlock proper Adaptive Kelly
sizing. Currently the wrapper approximates trade outcomes from
equity-deltas — too coarse. Engine-level callbacks would enable
genuine streak-based amplification.

## Updated fleet (no new entries this turn)

| Bot | Strategy | Agg OOS | Trades | Gate |
|---|---|---:|---:|:---:|
| `mnq_futures_sage` | `mnq_orb_sage_v1` | +10.06 | 12 | PASS |
| `nq_futures_sage` | `nq_orb_sage_v1` | +8.29 | 13 | PASS |
| `btc_sage_daily_etf` | `btc_sage_daily_etf_v1` | +6.00 | 71 | PASS |
| `btc_ensemble_2of3` | `btc_ensemble_2of3_v1` | +5.95 | 94 | PASS |

Four gate-passing strategies remain. No new promotion this turn —
the existing winners are at the practical edge.

## Files in this commit

* `docs/research_log/extreme_oos_findings_20260427.md` (this).

No new strategy code — this is a documentation-only commit
preserving the negative-result findings so future research
doesn't re-derive them.

## Bottom line for the user

You asked for extreme OOS without sacrificing trade count. We
already have it: **+6.00 / +5.95 OOS Sharpes with 71 / 94 trades,
both passing the strict walk-forward gate.** That's the practical
ceiling on the 360-day BTC 1h dataset.

To push truly higher requires fundamentally new information —
not more parameter tuning. The honest path forward:

1. **Paper-soak the existing winners** to expand the dataset
   with live data.
2. **Acquire Tier-5 data** (real on-chain, ETH ETF flows,
   options skew) and add as new providers — the framework is
   ready.
3. **Engine trade-close callbacks** to unlock genuine Adaptive
   Kelly sizing.

All three are bigger lifts than another sweep. The +6.00 / +5.95
candidates are ready for the next gate (paper-soak), and the
codebase has the framework to absorb new signals when they land.
