# Fleet-Wide Baseline Strategy Assignments — Sage Review 2026-04-27

## Trigger

User directive 2026-04-27: *"i need all the bots in jarvis fleet to have
there main stratagies discovered and and fine tuned this is a
supercharge lets optimize before we even begin also take into mind the
sages wisdom when doing this"*.

Premise check: a junior pass had wired `btc_hybrid`, `eth_perp`, and
`sol_perp` to `strategy_kind="grid"` on the assumption that grid is
"primary for crypto." The user corrected this — grid already exists in
the fleet (`firm/the_firm_complete/btc_firm/modes/grid.py`, regime-
gated, the production reference) and the simplified `eta_engine` grid
is NOT the right baseline to promote across the perps tier.

## Sages dispatched

Four parallel agents reviewed the fleet:

* **quant-researcher** — statistical fit, sample size, overfit risk
* **market-microstructure** — fill realism, spread/slippage gap
* **risk-execution** — fleet-level risk budget, kill-switch hygiene
* **devils-advocate** — null-hypothesis arguments per pick

## Convergence

Across the four perspectives, the recommendation converged on:

| Bot          | strategy_kind   | Rationale (1-line)                                     |
|--------------|-----------------|--------------------------------------------------------|
| mnq_futures  | orb (unchanged) | Walk-forward winner; OOS Sharpe +5.71, DSR 1.000       |
| nq_futures   | orb (unchanged) | Same family as MNQ; symbol-agnostic on liquid index    |
| nq_daily_drb | drb (unchanged) | Daily NQ, 27-yr history, research candidate            |
| btc_hybrid   | crypto_orb      | UTC-anchored; 8636 bars; ORB family already cleared    |
| eth_perp     | crypto_orb      | Apples-to-apples vs btc; let walk-forward decide       |
| sol_perp     | crypto_orb      | Same baseline; tighter risk; research candidate        |
| crypto_seed  | confluence      | DCA accumulator; thr=4.0; do NOT DSR-gate              |
| xrp_perp     | DEACTIVATED     | No news feed; muted via extras["deactivated"]=True     |

## Caveats captured in registry rationale

Each new assignment carries the sage's specific warning:

1. **btc_hybrid (crypto_orb)** — UTC midnight is a synthetic anchor;
   60-min range on 1h bars is degenerate (1 bar = full range), so
   `extras["crypto_orb_config"]` overrides `range_minutes=240`. Re-tune
   inside each train fold; do NOT inherit MNQ params verbatim.

2. **eth_perp (crypto_orb)** — Quant flag: ETH+BTC both on crypto_orb
   may be one strategy not two. `extras["fleet_corr_partner"]="btc_hybrid"`
   marks the pair so the drift_monitor can apply a correlation penalty.

3. **sol_perp (crypto_orb)** — Quant flag: SOL had the worst IS Sharpe
   (-0.696) under prior confluence; if crypto_orb also fails, *defer*
   SOL — don't switch strategy_kind looking for a winner.
   `extras["research_candidate"]=True` makes that explicit. SOL gets
   `max_trades_per_day=1` and `atr_stop_mult=3.0` to absorb 3-5bp
   spread + ~2.5x BTC beta.

4. **crypto_seed (confluence, unchanged)** — Quant flag: walk-forward
   gate is the wrong tool for a DCA accumulator. Future drift-monitor
   work should evaluate seed on tracking error vs naive DCA, not OOS
   Sharpe.

5. **Fleet kill-switch chokepoint** — Risk flag: `extras["deactivated"]
   =True` was previously enforced only in `tests/test_bots_registry_
   sync.py`, NOT in `engine_adapter`/`live_adapter`/`decision_sink`.
   New `is_active(assignment) -> bool` and `is_bot_active(bot_id) ->
   bool` helpers in `per_bot_registry.py` are the canonical chokepoint;
   covered by `test_is_active_chokepoint_returns_false_for_deactivated_bots`.

## Devils-advocate residual probability

Devils-advocate calibrated overall edge probability across the fleet
at **~25%** — only MNQ ORB has nominal walk-forward; the rest are
assertions until live walk-forward results land. Mitigation policy:

* Half-size all new perp baselines for the first 30 trading days.
* Per-bot daily loss cap (already enforced via `risk_per_trade_pct`
  and `max_trades_per_day`).
* Weekly OOS Sharpe gate; kill at < 0.
* `crypto_seed` deactivated until a regime gate lands (deferred).

## Action items not yet landed

* Wire `is_active(assignment)` into `engine_adapter.py` and
  `live_adapter.py` decision loops — risk-sage flagged this as the
  required two-layer gate. Currently the helper exists but only the
  registry-sync test calls it.
* `FleetRiskGate` upstream of `decision_sink.emit` — aggregate daily
  P&L across bots, halt all trading at -3.5% fleet drawdown. Spec'd by
  risk-sage; not yet implemented.
* Drift-monitor correlation penalty for `fleet_corr_partner` pairs —
  currently the marker exists in extras but nothing reads it.
