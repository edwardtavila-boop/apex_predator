# 2026-04-27 — First honest cross-asset grid (post crypto-symbol repoint)

## What happened

Re-ran `python -m eta_engine.scripts.run_research_grid --source registry`
after the crypto bots in `per_bot_registry.py` were repointed from MNQ1
placeholders to their real symbols (BTC/ETH/SOL via Coinbase 1h bars).
This is the first cross-asset evaluation the framework has produced
where each crypto bot is actually reading its own instrument's data.

## Result table

| Bot | Sym/TF | Strat | W | +OOS | OOS Sh | DSR med | DSR pass% | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| mnq_futures | MNQ1/5m | orb | 2 | 2 | +5.706 | 1.000 | 100.0 | **PASS** |
| nq_futures | NQ1/5m | orb | 2 | 2 | +5.706 | 1.000 | 100.0 | **PASS** |
| nq_daily_drb | NQ1/D | drb | 53 | 26 | +2.484 | 0.004 | 39.6 | FAIL |
| btc_hybrid | BTC/1h | btc-conf | 9 | 4 | +0.279 | 0.000 | 22.2 | FAIL |
| eth_perp | ETH/1h | btc-conf | 9 | 6 | -0.139 | 0.000 | 33.3 | FAIL |
| sol_perp | SOL/1h | btc-conf | 9 | 5 | -0.875 | 0.000 | 11.1 | FAIL |
| xrp_perp | (deact) | — | 46 | 0 | 0.000 | 0.012 | 0.0 | FAIL |
| crypto_seed | BTC/D | global-conf | 8 | 4 | +0.014 | 0.037 | 37.5 | FAIL |

## Findings

1. **Index futures ORB still passes.** Both MNQ and NQ ORB cleared the
   strict gate (DSR median 1.0, 100% fold pass). These are the only
   strategies in the framework's history to pass; baselines remain
   pinned in `docs/strategy_baselines.json`.
2. **DRB blow-up was a wiring bug, not a signal problem.** The previous
   grid run reported `nq_daily_drb` with OOS Sharpe -4.59e+14 — clearly
   numerical noise. Root cause: `run_research_grid.py` only special-cased
   `strategy_kind == "orb"`; DRB was silently falling through to the
   confluence-scorer path and being run on daily bars with a 5m-tuned
   scorer. Added an explicit `strategy_kind == "drb"` branch. After the
   fix DRB shows agg OOS Sharpe +2.48 with 26/53 positive windows — a
   real but not-yet-promotable signal (DSR median 0.004).
3. **Crypto bots all FAIL on a generic confluence scorer.** Expected.
   The `btc` confluence scorer is a placeholder — equal-weight, no
   funding/onchain inputs wired through the ctx_builder yet. The
   meaningful number here is that the *infrastructure* runs end-to-end:
   bars load, the engine produces walk-forward windows, the gate
   evaluates. Now there's a baseline to optimize against.
4. **XRP is correctly muted.** 46 windows on a 4-year dataset, zero
   trades, zero pass. The `extras["deactivated"] = True` marker plus
   the threshold=10.0 are doing their job.

## Pending

- BTC/ETH/SOL crypto bots need either (a) a crypto-specific scorer with
  funding-skew + onchain inputs, or (b) a strategy variant (e.g. crypto
  ORB on Asian-session ranges, mean-reversion on funding extremes).
  Stop trying to evaluate them under the index-futures-tuned scorer.
- DRB on NQ daily looks promising enough to investigate further. 39.6%
  pass fraction means a single regime gate (e.g. "skip windows where
  prior-month drawdown > X") could plausibly push it through the
  threshold. Defer until the crypto path lands.

## Files touched

- `scripts/run_research_grid.py` — added DRB branch in `_run_cell`.
- `docs/research_log/research_grid_20260427_111754.md` — full run output.
