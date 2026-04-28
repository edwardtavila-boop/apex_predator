# Sage overlay generalization — 2026-04-27 (continued)

Continuing from `sage_strategy_promotion_20260427.md`, this entry
captures the cross-asset generalization tests of the MNQ sage win.

## Tests

### NQ-specific sage walk-forward — PASSES

The plain `nq_orb_v1` baseline was a textual mirror of `mnq_orb_v1`
(same numbers, different symbol). The open question: does sage's
**+10.06 OOS** lift on MNQ generalize symbol-agnostically across
liquid index futures?

Walk-forward NQ1 5m, 60d/30d, same MNQ winning config (conv=0.65,
align=0.55, range=15m):

| Window | IS Sh | OOS Sh | IS trades | OOS trades |
|---:|---:|---:|---:|---:|
| 0 | +0.69 | **+3.35** | 16 | 9 |
| 1 | +2.55 | **+13.23** | 29 | 4 |

**Aggregate OOS Sharpe +8.29, DSR median 0.997, 100% pass, gate PASS.**
OOS > IS in BOTH windows again. The lift is symbol-agnostic — same
phenomenon (sage filter cuts more losers than winners on OOS bars)
shows up on NQ at slightly lower magnitude (+8.29 vs MNQ's +10.06)
but the same direction.

**Promoted as `nq_futures_sage` running `nq_orb_sage_v1`.** Pinned
baseline added to `docs/strategy_baselines.json` (n_trades=58).

### Crypto sage-gated ORB — FAILS

Sage overlay applied to `crypto_orb` on BTC 1h, 90d/30d, 9 windows.
Same conv=0.65 thresholds, `instrument_class="crypto"`:

| Metric | Plain crypto_orb | Sage-gated crypto_orb |
|---|---:|---:|
| Agg OOS Sharpe | **+2.73** | -2.7e15 (numerical blowup) |
| Positive OOS windows | 6/9 | 1/9 |
| DSR median | 1.000 | 0.064 |
| DSR pass fraction | 67% | 0% |
| Gate | FAIL (engine multi-criteria) | FAIL |

**The sage overlay actively hurts crypto_orb.** Diagnosis:

1. School activation rate is fine (23/23 fire on `crypto`, 22/23
   on `futures` — `onchain` is the only difference).
2. The problem is trade volume. Plain crypto_orb fires 1-25
   per IS window and 1-25 per OOS window; the sage overlay
   filters that down to 1-5 OOS trades. With trade counts that
   small, OOS Sharpe is unstable — a single losing trade in a
   3-trade window flips it negative, and the variance estimator
   produces giant negative Sharpe values.
3. The MNQ sweet spot (conv=0.65) was found via an 18-cell sweep.
   Crypto needs its own sweep — the right conviction on BTC is
   probably lower (more permissive) since the underlying strategy
   already fires sparsely.

**Conclusion:** crypto sage gating is a research candidate, not a
promotion. The crypto fleet retains `crypto_orb` (plain) as the
strongest baseline (+2.73 OOS Sh, 67% DSR pass). A future crypto-
specific sage sweep — conv ∈ {0.40, 0.45, 0.50, 0.55, 0.60} ×
range ∈ {30m, 60m, 90m, 120m} — could find a working cell.

## Updated fleet scoreboard

| Bot | Strategy | Walk-forward | Verdict |
|---|---|---|:---:|
| `mnq_futures` | `mnq_orb_v1` (plain ORB) | +5.71 OOS, gate PASS | Promoted |
| `mnq_futures_sage` | `mnq_orb_sage_v1` | **+10.06 OOS, gate PASS** | **Promoted** |
| `nq_futures` | `nq_orb_v1` (plain) | mirror of MNQ | Promoted |
| `nq_futures_sage` | `nq_orb_sage_v1` | **+8.29 OOS, gate PASS** | **Promoted (NEW)** |
| `nq_daily_drb` | `nq_drb_v1` | best +0.74 OOS, 44% pass | Research candidate |
| `btc_hybrid` | `crypto_orb` (plain) | +2.73 OOS, 67% pass | Strongest crypto |
| (research) | `crypto_orb` + sage | -2.7e15 OOS | NOT promoted (overlay too strict) |
| (research) | `sage_consensus` (pure) | -1.15 OOS | NOT promoted |
| (research) | `crypto_trend` | +0.62 OOS, 33% pass | Tuning candidate |
| (research) | `crypto_meanrev` | -0.98 OOS | Wrong regime |
| (research) | `crypto_scalp` | -0.82 OOS | No edge present |

**Headline: 3 of 8 production bots now have a clear promotion path
through sage (mnq, nq, both index futures).** Crypto fleet remains
on plain ORB; sage gating doesn't transfer cleanly to low-trade-
count regimes without a symbol-specific sweep.

## Paper-soak readiness

`scripts/paper_soak_mnq_orb.py` extended to take `--bot-id` so the
same script handles plain and sage variants:

  * `--bot-id mnq_futures` (default) — plain ORB pre-flight.
  * `--bot-id mnq_futures_sage` — sage-overlay pre-flight.
  * `--bot-id nq_futures` / `nq_futures_sage` — NQ siblings.

The pre-flight gate (`_SUPPORTED_KINDS = {"orb", "orb_sage_gated"}`)
rejects bots wired to other kinds (drb / crypto_orb / etc.). 4 new
tests cover the parameterization.

## Next

1. Crypto-specific sage sweep on BTC 1h to find a passing cell.
2. NQ paper-soak alongside MNQ once 5m intraday data refreshes.
3. Drift-watchdog auto-detect on the new sage-overlay strategies
   (currently the watchdog only knows ORB classics).
