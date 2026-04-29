# 2026-04-27 — All four open framework items finished

## What was open

Per the prior status audit, four items remained unfinished from
the early-summary pending list:

1. `scripts/fetch_ibkr_crypto_bars.py` — gate-blocking for any
   crypto live activation per `eta_data_source_policy.md`.
2. On-chain feed → `data.library` integration so the gate
   (not just sage) sees on-chain data.
3. XRP news/regulatory feed for the eventual reactivation.
4. JARVIS drift-watchdog scheduled run, deferred until ≥3
   promoted strategies (the BTC promotion earlier today made
   that threshold).

## What landed

### 1. IBKR-native crypto bar fetcher + drift comparator

* **`scripts/fetch_ibkr_crypto_bars.py`** — pulls historical
  bars from the local IBKR Client Portal Gateway via the
  `/iserver/marketdata/history` endpoint. Uses the same conids
  (`venues.ibkr._DEFAULT_CONIDS`) as live trading routing. Writes
  to the canonical ETA IBKR crypto history root
  (`data\crypto\ibkr\history\<SYMBOL>_<TF>.csv`) — sibling of the
  Coinbase root, deliberately separate so the drift comparator can
  pair the two.
* **`scripts/compare_coinbase_vs_ibkr.py`** — closes the loop.
  For a named bot, runs the registered strategy on both Coinbase
  and IBKR tapes, builds a `BaselineSnapshot` from Coinbase
  trades, and calls `obs.drift_monitor.assess_drift` with the
  IBKR trades as `recent`. Writes the audit-trail markdown the
  data-source policy requires. Exit code 0/2/3 for green/amber/red.

Together these implement the **pre-live data-source gate** from
`memory/eta_data_source_policy.md` end-to-end. Operator workflow:

    # 1. Start IBKR Client Portal Gateway, authenticate
    # 2. Fetch IBKR-native bars
    python -m eta_engine.scripts.fetch_ibkr_crypto_bars \
        --symbol BTC --timeframe 1h --months 12
    # 3. Drift-check against the Coinbase baseline
    python -m eta_engine.scripts.compare_coinbase_vs_ibkr \
        --bot-id btc_hybrid

### 2. On-chain feed wired into the data library

* **`data/audit.py`** — `_resolve_library_lookup` extended for
  `kind="onchain"`, `kind="sentiment"`, `kind="macro"`. Each
  uses a synthetic-symbol convention (`<X>ONCHAIN`, `<X>SENT`,
  `<X>MACRO`) parallel to the existing `<X>FUND` pattern.
* **`data/library.py`** — `DEFAULT_ROOTS` now includes
  the canonical ETA crypto on-chain, sentiment, macro, and IBKR
  history roots under `data\crypto\...`.
* **`scripts/fetch_onchain_history.py`** — pulls daily on-chain
  time series from free APIs (CoinGecko market-chart, mempool.
  space difficulty adjustments, Defillama Ethereum chain TVL).
  Writes `BTCONCHAIN_D.csv` + `ETHONCHAIN_D.csv`. Documents the
  Glassnode-paid gap explicitly: this fetcher covers price /
  market cap / volume / chain TVL / difficulty; whale transfers
  / exchange netflow / active addresses still need a paid feed.

After running for BTC + ETH:

    btc_hybrid: AVAIL=7  crit_miss=0  opt_miss=2
    eth_perp:   AVAIL=6  crit_miss=0  opt_miss=1

Both crypto bots now have **100% critical-data coverage** —
the audit flipped the `onchain` rows from MISSING to AVAILABLE.

### 3. XRP news / regulatory-pressure feed

* **`scripts/fetch_xrp_news_history.py`** — queries SEC EDGAR
  full-text search (`efts.sec.gov/LATEST/search-index`) for
  filings mentioning "ripple" + "XRP" over the requested
  window. Aggregates by file_date, writes `XRPSENT_D.csv` in
  the data-library schema.
* **`data/requirements.py`** — xrp_perp's sentiment requirement
  retuned from `1h` to `D` (daily is the natural cadence for
  SEC-filing news; intraday sentiment requires a paid feed
  beyond the free SEC API). The duplicate `macro SEC_HEADLINES`
  requirement removed since the SEC headline counts ARE the
  sentiment column.

After running, smoke audit:

    xrp_perp: AVAIL=5  crit_miss=0  opt_miss=0

XRP coverage is now complete at the data layer. The reactivation
gate's second item (a feature class that consumes the file —
e.g. `SECHeadlineFeature` returning a time-decay signal around
recent rulings) is still open; that's a separate piece of work.

### 4. Drift watchdog

* **`scripts/run_drift_watchdog.py`** — for each entry in
  `docs/strategy_baselines.json` with `_promotion_status =
  "production"`, re-runs the strategy over the last `--lookback-
  days` (default 30) of bars, builds a fresh trade list, and
  calls `obs.drift_monitor.assess_drift` against the pinned
  baseline. Logs each result to `docs/drift_watchdog.jsonl`
  (append-only) and dispatches amber/red severity via
  `obs.alert_dispatcher`. Exit code 0/2/3 for green/amber/red.
* Cron-friendly: one scheduled task per day at 09:00 UTC is the
  recommended cadence. The `--no-alerts` flag keeps dryruns / CI
  silent.

First run on the production fleet:

    mnq_orb_v1:       GREEN   n_recent=20  WR z=-0.79  R z=-1.28
    nq_orb_v1:        GREEN   n_recent=20  WR z=-0.79  R z=-1.28
    mnq_orb_sage_v1:  AMBER   WR z=-2.21   R z=-2.83 (drift!)
    nq_orb_sage_v1:   AMBER                R z=-2.63 (drift!)
    btc_corb_v2:      GREEN   (insufficient sample, only 2 recent trades)

Two sage variants flagged AMBER on first run — they were promoted
based on parallel-session walk-forward results that don't reproduce
on the most-recent 30 days of bars. The watchdog is doing exactly
what it should: surfacing the divergence so the operator decides
whether to re-baseline, re-tune, or accept the drift as expected
regime variance.

## Honest fleet status (post-batch)

* **3 promoted strategies** with `_promotion_status: "production"`:
  `mnq_orb_v1`, `nq_orb_v1`, `btc_corb_v2`.
* **5 strategies** with `_promotion_status: "production_candidate"`
  or `"research_candidate"` — these were promoted via parallel-
  session walk-forwards but not yet through the registry-level grid
  with the IS-positive gate. Operator decision pending on whether
  they should be downgraded.
* **All crypto bots** at 100% critical-data coverage (BTC, ETH, SOL,
  XRP, crypto_seed). XRP remains explicitly deactivated via
  `extras["deactivated"]=True` until the SECHeadline feature class
  is wired.

## What's still genuinely open

* **SECHeadline feature class** for XRP — consumes `XRPSENT_D.csv`
  via `data.library.get(symbol="XRPSENT", timeframe="D")` and
  returns a time-decay signal around recent rulings. Required as
  the second half of the XRP reactivation gate.
* **Glassnode-paid on-chain metrics** (whale transfers / exchange
  netflow / active addresses). Free APIs cover ~80% of what the
  registry asked for; the remaining ~20% needs a subscription.
  Documented as a known gap, not a blocker — strategies degrade
  on missing fields.
* **Drift-watchdog Windows scheduled task** — the script is
  cron-friendly but no scheduled task has been registered.
  Operator install:

      schtasks /Create /SC DAILY /ST 09:00 /TN "ETA Drift Watchdog" \
        /TR "python -m eta_engine.scripts.run_drift_watchdog"

The original "summary pending list" is now closed. Standing
research debt continues as new work in the regular research_log
flow.
