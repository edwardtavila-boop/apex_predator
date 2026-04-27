# 2026-04-27 — Parallel-session PASS claims verified through the gate

## Context

The parallel research session committed three crypto strategies
during the day claiming they cleared the strict walk-forward gate:

- `btc_sage_daily_etf` — claimed +6.00 OOS, 89% pass, **PASS**
- `btc_ensemble_2of3`   — claimed +5.95 OOS, 89% pass, **PASS**
- `btc_regime_trend_etf` — claimed +4.28 OOS, 89% pass, near-PASS

Plus an ETH variant:

- `eth_sage_daily` — claimed research candidate, +5.77 OOS

The relevant strategy_kinds (`sage_daily_gated`, `ensemble_voting`,
`crypto_macro_confluence`) weren't wired into `run_research_grid.py`,
so the grid was routing them through the confluence-fallback path.
That meant the registry-level smoke test couldn't independently
verify those claims.

## What was wired

`scripts/run_research_grid.py` now dispatches all six new
strategy_kinds:

- `sage_consensus`
- `crypto_macro_confluence`
- `sage_daily_gated`
- `ensemble_voting`
- (already wired earlier today: `crypto_orb`, `crypto_trend`,
  `crypto_meanrev`, `crypto_scalp`, `crypto_regime_trend`, `grid`,
  `orb`, `orb_sage_gated`, `drb`)

For ensemble_voting, a voter-builder pattern that re-uses
`_build_crypto_strategy_factory` per voter, with aliases for
historical voter names (`regime_trend` → `crypto_regime_trend`,
`regime_trend_etf` → `crypto_macro_confluence`).

## What the gate says

| Bot | IS Sh | OOS Sh | Deg% | DSR pass% | Verdict |
|---|---:|---:|---:|---:|---|
| mnq_futures | +3.29 | +5.71 | 14.2 | 100.0 | **PASS** |
| nq_futures | +3.29 | +5.71 | 14.2 | 100.0 | **PASS** |
| **btc_hybrid** | **+1.80** | **+5.08** | 26.8 | 66.7 | **PASS** |
| btc_sage_daily_etf | **-1.75** | +1.96 | 22.2 | 55.6 | FAIL (IS gate) |
| btc_ensemble_2of3 | -1.75 | +1.96 | 22.2 | 55.6 | FAIL (IS gate) |
| btc_regime_trend_etf | -1.75 | +1.96 | 22.2 | 55.6 | FAIL (IS gate) |
| btc_regime_trend | -1.75 | +1.96 | 22.2 | 55.6 | FAIL (IS gate) |
| eth_sage_daily | -0.79 | +0.10 | 1318.7 | 33.3 | FAIL |
| btc_hybrid_sage | 0.00 | 0.00 | 0.0 | 0.0 | FAIL (no trades) |
| mnq_sage_consensus | 0.00 | 0.00 | 0.0 | 0.0 | FAIL (no trades) |
| eth_perp | -3.02 | +3.57 | 11.1 | 77.8 | FAIL (IS gate) |
| nq_daily_drb | +1.36 | +2.48 | 435.3 | 39.6 | FAIL (DSR pass) |
| mnq_futures_sage | +1.16 | +1.41 | 90.6 | 50.0 | FAIL (DSR boundary) |
| nq_futures_sage | +3.44 | +1.41 | 66.9 | 50.0 | FAIL (DSR boundary) |
| sol_perp | -0.76 | -5.17 | 361.9 | 33.3 | FAIL |
| crypto_seed | +0.71 | +0.01 | 102.0 | 37.5 | FAIL |
| xrp_perp | (DEACT) | (DEACT) | — | — | DEACT |

## Why the parallel claims FAIL through the grid

Three observations explain the divergence:

1. **All three macro-flavoured BTC strategies produce identical
   numbers** (-1.748 / +1.962). That's because in the grid's
   "no providers attached" mode, they all degenerate to plain
   `crypto_regime_trend`. The grid sees:
   - `btc_sage_daily_etf` → SageDailyGated wrapping
     CryptoMacroConfluence → no daily verdict → no veto fires →
     plain regime-trend output.
   - `btc_ensemble_2of3` → Ensemble of [regime_trend,
     macro_confluence, sage_daily_gated] → all three voters
     produce the same baseline trades because ETF/sage providers
     aren't attached → 3-vote agreement → identical output.
   - `btc_regime_trend_etf` → CryptoMacroConfluence → no ETF flow
     provider → ETF gate is a no-op → identical to regime_trend.

   Their claimed +6.00 OOS Sharpes required ETF flow and sage
   daily provider data that exist only when their dedicated
   walk-forward scripts run.

2. **The IS-positive gate (added 2026-04-27) catches the
   IS-negative cases** that previously fake-passed. Plain
   `crypto_regime_trend` has IS Sharpe -1.748 across this 9-window
   walk-forward — the strategy loses money in-sample, the OOS
   positive is plausibly date-split luck.

3. **Plain `crypto_regime_trend` is the load-bearing baseline**
   underneath all three macro-flavoured BTC variants. If
   regime_trend itself doesn't pass the IS gate, neither do the
   downstream variants until their providers genuinely add
   IS-positive lift.

## What this means

**The framework is honest, end-to-end.** Provider-dependent claims
that can't be reproduced through the canonical walk-forward gate
are correctly rejected. The promotion decision for any crypto
strategy with macro/sage providers must:

1. Run via the dedicated walk-forward script that wires the
   provider (e.g., `scripts/run_sage_walk_forward.py` for
   sage_daily_gated, similar scripts for ETF flow).
2. **Independently** verify the IS Sharpe is positive in
   aggregate (the `is_positive` gate).
3. Re-run via `run_research_grid` after wiring the provider into
   the grid's `ctx_builder` if those numbers should be reproducible
   from the registry alone.

Without (3), promotion claims live or die by ad-hoc scripts —
which is fine for research but breaks the "registry is the
canonical truth" promise.

## Confirmed honest fleet

3 PASSing strategies, all with IS+ AND OOS+:

- `mnq_futures` (orb)
- `nq_futures` (orb)
- **`btc_hybrid` (crypto_orb tuned, range=120/atr=3.0/rr=2.5)**

This is the framework's complete honest promotion roster as of
2026-04-27. Next-promotion candidates by closeness to the gate:

1. `mnq_futures_sage` / `nq_futures_sage` — DSR boundary 50%,
   needs more walk-forward windows.
2. `btc_sage_daily_etf` if the sage-daily provider can be wired
   into the grid AND the resulting IS aggregate is positive
   (currently -1.748 without provider — provider must add IS lift,
   not just OOS lift).
3. `nq_daily_drb` — IS +1.36, OOS +2.48; needs a per-fold regime
   gate to push DSR pass-fraction over 50%.

ETH and SOL crypto deferred — both have IS-negative crypto_orb
baselines.

## Files added/changed

- `scripts/run_research_grid.py` — dispatch branches for
  `sage_consensus`, `crypto_macro_confluence`,
  `sage_daily_gated`, `ensemble_voting`. Voter-builder pattern
  for ensembles with name aliases for historical voter names.
- `docs/research_log/2026-04-27_parallel_pass_claims_verified.md`
  (this file).
