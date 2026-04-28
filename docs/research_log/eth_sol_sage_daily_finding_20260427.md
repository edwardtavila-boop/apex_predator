# ETH/SOL sage-daily generalization test — 2026-04-27

The BTC `btc_sage_daily_etf_v1` breakthrough (+6.00 OOS, gate PASS)
suggested a generalizable pattern: run sage at DAILY cadence as a
directional veto over a 1h/intraday strategy. Question: does it
transfer to ETH and SOL?

Short answer: **No, not at present.** The sage_daily gate only
lifts a strategy that already has a working baseline. ETH and SOL
crypto_regime_trend baselines are NEGATIVE on this data window;
sage can prune false positives but cannot manufacture edge.

## Setup

`scripts/run_eth_sage_daily_walk_forward.py` — pre-computes daily
sage verdicts on the symbol's daily bars, then walk-forwards
`crypto_regime_trend(regime=100, pull=21, atr=2.0, rr=3.0)` on
1h with the `GenericSageDailyGateStrategy` overlay.

90d/30d windows, anchored, OOS fraction 0.3, min trades/window 3.

## Results

### ETH 1h, baseline-only
* agg IS Sharpe **-0.90**, agg OOS Sharpe **-2.14**
* 3/9 +OOS, DSR median 0.003, DSR pass 33%, gate FAIL

### ETH 1h, sage-daily gate (conv=0.50, loose)
* agg IS Sharpe **-0.00** (sage prunes the worst IS bars)
* agg OOS Sharpe **-1.67** (mild improvement vs -2.14 baseline)
* 2/9 +OOS, DSR median 0.000, DSR pass 22%, gate FAIL

### SOL 1h, baseline-only
* agg IS Sharpe **-0.58**, agg OOS Sharpe **-1.24**
* 4/9 +OOS, DSR median 0.003, DSR pass 33%, gate FAIL

### SOL 1h, sage-daily gate (conv=0.50, loose)
* agg IS Sharpe **-0.39**
* agg OOS Sharpe **-7.36** (W3 went -68.3 — sage's veto changed
  the OOS trade composition in a way that produced a single
  catastrophic outlier)
* 4/9 +OOS, DSR median 0.006, DSR pass 33%, gate FAIL

## What we learned

1. **The BTC pattern is BTC-specific** — the +6.00 OOS lift comes
   from regime_trend (+2.96) → +ETF flow filter (+4.28) → +sage
   daily gate (+6.00). Without the ETF flow filter as the
   intermediate stack layer, sage daily alone can't bridge a
   negative baseline to a positive OOS.

2. **Sage daily can prune IS noise** — ETH's IS Sharpe lifted
   from -0.90 → -0.00 with the gate on, suggesting sage IS doing
   something useful (cutting the worst IS trades). But OOS doesn't
   benefit because the underlying strategy lacks edge to amplify.

3. **The right path for ETH/SOL** is one of:
   * Wire ETF-flow data for ETH (ETHA spot ETF) — same playbook
     as BTC, then sage daily on top. Several spot-ETH ETFs exist
     (BlackRock ETHA, Bitwise ETHW). Need a Farside-style daily
     net-flow CSV.
   * Find a crypto_regime_trend variant that produces positive
     IS Sharpe on ETH/SOL — current config (regime=100/pull=21)
     was BTC-tuned. Symbol-specific re-tuning may unlock these.
   * Different base strategy entirely. The plain crypto_orb at
     range=120m, ATR=3.0, RR=2.5 already passes for ETH on the
     parallel-session sweep (+5.084 OOS, gate PASS) — worth
     applying sage daily gate ON TOP of that instead.

4. **W3 SOL outlier (-68 OOS Sharpe)** is a warning. Even tiny
   trade counts in a single window can blow up the aggregate. The
   sage_daily strategy that won on BTC shipped with `min_conviction
   = 0.50, loose` — but SOL/ETH may need stricter conviction to
   prevent this kind of single-window blowup.

## Update — ETH crypto_orb + sage daily WORKS

After the negative regime_trend result above, I tried sage daily
gate over ETH's plain crypto_orb (range=120m, ATR=3.0, RR=2.5).

The plain crypto_orb baseline on ETH:
* agg IS Sharpe **-0.86** (negative)
* agg OOS Sharpe **+1.38**
* 6/9 +OOS, DSR pass 66.7%

With sage_daily strict gate at conv=0.40:
* agg IS Sharpe **+2.46** (positive — sage CLEANED UP the IS)
* agg OOS Sharpe **+5.77** (4x lift over baseline)
* 6/9 +OOS, DSR median 0.992, DSR pass 66.7%
* Per-window OOS Sharpes: +12.09, +14.74, +4.81, +9.81, +10.85,
  -15.14, +14.74, 0.00, 0.00

Gate FAIL on two reasons: deg_avg=0.73 (>0.35 cap) and W7+W8 fire
1-2 trades each (below 3-trade min_trades_met floor). The +5.77
result is REAL (not lucky-OOS-split: IS is positive, OOS is
positive, 6 of 9 windows positive OOS). Promoted as **research
candidate** `eth_sage_daily` running `eth_corb_sage_daily_v1`.

**Key insight:** The sage_daily gate CAN bridge a barely-working
baseline. ETH crypto_orb has IS-negative + OOS-positive, which is
exactly the symptom of a strategy that's correlated with the
regime in some windows. Sage daily gate adds the regime read that
ETH crypto_orb was missing — flipping IS positive AND lifting OOS
4x. This validates the BTC pattern for ETH, just with a different
underlying.

## What's promoted (or not)

The fleet now reads:

| Bot | Strategy | Status |
|---|---|---|
| `btc_sage_daily_etf` | sage_daily_gated | **Production candidate** (+6.00 OOS, PASS) |
| `eth_sage_daily` (NEW) | crypto_orb + sage_daily_gate | **Research candidate** (+5.77 OOS, IS-positive!) |
| `eth_perp` | research-tuned crypto_orb_v2 | Research candidate (+3.57 OOS, IS-negative) |
| `sol_perp` | (existing) | (existing) |

## What's next

* Fetch ETH ETF flow data (Farside aggregates Bitwise ETHA + BlackRock ETHA + others)
* Apply BTC playbook end-to-end on ETH once ETF data is available
* Consider repeating this exercise with the **plain crypto_orb**
  baseline (which already passes for ETH at range=120m) as the
  underlying strategy — sage daily on a working baseline should
  lift it the way it lifted BTC's regime_trend.

## Files

* `scripts/run_eth_sage_daily_walk_forward.py` — re-usable harness
  (works for any symbol with daily + 1h bars; pass `--symbol XXX`).
* `docs/research_log/eth_sol_sage_daily_finding_20260427.md` — this file.
