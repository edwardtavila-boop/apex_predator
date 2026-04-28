# Full asset coverage matrix — every strategy works for every bot, 2026-04-27

User mandate: "we need to make sure we have equivalent strategies
for all of the crypto bots and nq".

After commit 945b00a built the foundation strategies (sweep_reclaim,
compression_breakout, ConfluenceScorecard, adaptive grid), this
commit closes the asset-coverage gap. Now every supported asset
has a preset for every foundation strategy, with cross-asset
separation guaranteed by parity tests.

## Coverage matrix (15 cells, all populated)

| Asset | Sweep + Reclaim | Compression Breakout | Regime Gate |
|---|---|---|---|
| **MNQ** | `mnq_intraday_sweep_preset()` | `mnq_compression_preset()` | `mnq_intraday_preset()` |
| **NQ** | `nq_intraday_sweep_preset()` ✨ | `nq_compression_preset()` ✨ | `nq_intraday_preset()` ✨ |
| **BTC** | `btc_daily_sweep_preset()` | `btc_compression_preset()` | `btc_daily_preset()` |
| **ETH** | `eth_daily_sweep_preset()` ✨ | `eth_compression_preset()` ✨ | `eth_daily_preset()` |
| **SOL** | `sol_daily_sweep_preset()` ✨ | `sol_compression_preset()` ✨ | `sol_daily_preset()` ✨ |

✨ = added in this commit. 5 of the 15 cells already existed.

13/13 parity tests confirm:
* Every cell returns a valid config
* Crypto presets ladder by vol class (BTC < ETH < SOL on ATR-stop)
* Intraday futures presets differ from daily-cadence crypto presets
  (warmup, EMA periods, breakout window, cooldowns)
* Sister-index presets (MNQ ↔ NQ) share bar-cadence-sensitive
  knobs but are separate factories so future asset-specific tuning
  has a clean home

## Cross-asset separation rules (enforced by tests)

### Volatility ladder (crypto)

The ATR-stop multiplier widens as vol increases:

```
BTC:  1.5  (baseline)
ETH:  1.8  (~1.3x BTC vol)
SOL:  2.2  (~1.5-2x BTC vol)
```

Same direction on RR-target widening for SOL (3.0 vs BTC's 2.5)
to keep per-trade reward comparable to wider stops.

Same direction on `risk_per_trade_pct` for SOL (0.4% vs 0.5%) —
smaller risk because vol is wider.

### Wick threshold (crypto sweep_reclaim)

Wick threshold loosens as vol increases (proportionally larger
wicks are normal, not "real" sweeps):

```
BTC:  0.30
ETH:  0.25
SOL:  0.20
```

### Volume z-score floor

Volume confirmation floor loosens as vol increases (higher-vol
markets have more bursty volume so a constant z-score over-filters):

```
BTC:  0.30
ETH:  0.20
SOL:  0.10
```

### Compression band (BB-width percentile cap)

Wider compression band as vol increases (true compression is
proportionally rarer on high-vol assets):

```
BTC:  0.30  (bottom 30%)
ETH:  0.35  (bottom 35%)
SOL:  0.40  (bottom 40%)
```

### Futures vs crypto (intraday vs daily)

| Knob | MNQ/NQ 5m | BTC/ETH/SOL 1h |
|---|---|---|
| `warmup_bars` | 78 | 220 |
| `trend_ema_period` | 50 | 200 |
| `breakout_lookback` | 10 | 20 |
| `min_bars_between_trades` | 6 | 12 |
| `max_trades_per_day` | 4 | 2 |

The intraday cadence + RTH-bounded session naturally allows more
trades per day with shorter cooldown.

## What this unlocks

**Every existing bot in the registry can now be wrapped in the
foundation strategies with the right preset.** No bot is a "first
class" target with the rest being afterthoughts.

Per-bot strategy stack examples:

### MNQ futures bot
```python
# 3-strategy multi-strategy with confluence scoring + regime gating
orb = ORBStrategy(...)
pullback = CryptoRegimeTrendStrategy(...)  # asset-agnostic
sweep = SweepReclaimStrategy(mnq_intraday_sweep_preset())
compression = CompressionBreakoutStrategy(mnq_compression_preset())

bot = MultiStrategyComposite(
    [
        ("orb", ConfluenceScorecardStrategy(orb, scorecard_cfg)),
        ("pullback", ConfluenceScorecardStrategy(pullback, scorecard_cfg)),
        ("sweep", ConfluenceScorecardStrategy(sweep, scorecard_cfg)),
        ("compression", ConfluenceScorecardStrategy(compression, scorecard_cfg)),
    ],
    MultiStrategyConfig(conflict_policy="confluence_weighted"),
)
```

### NQ futures bot
Same pattern, swap `mnq_*_preset()` → `nq_*_preset()`. Strategies
are identical in mechanic; preset factories are separate so
future per-asset tuning doesn't bleed.

### BTC bot
```python
sweep = SweepReclaimStrategy(btc_daily_sweep_preset())
compression = CompressionBreakoutStrategy(btc_compression_preset())
pullback = CryptoRegimeTrendStrategy(btc_pullback_cfg)

# Wrap each in feature regime gate (the +0.30 lift winner)
gated_compression = RegimeGatedStrategy(
    compression, btc_daily_provider_preset(),
)
gated_compression.attach_regime_provider(feature_regime_provider)
# ... same for the others

bot = MultiStrategyComposite(
    [("compression", gated_compression),
     ("pullback", gated_pullback),
     ("sweep", gated_sweep)],
    MultiStrategyConfig(conflict_policy="confluence_weighted"),
)
```

### ETH bot
Same pattern as BTC, swap `btc_*_preset()` → `eth_*_preset()`.

### SOL bot
Same pattern, swap to `sol_*_preset()`. SOL vol is wider so the
preset auto-adjusts (wider stops, looser wick/volume thresholds,
smaller risk_per_trade_pct).

### Crypto adaptive grid bot (BTC, ETH, SOL)
```python
grid = GridTradingStrategy(GridConfig(
    adaptive_volatility=True,
    adaptive_atr_pct_lookback=100,
    adaptive_min_spacing_pct=0.0025,
    adaptive_max_spacing_pct=0.012,
    adaptive_kill_atr_pct=0.85,  # shut down on trending tape
    range_break_mult=1.0,
))
```

The grid's adaptive mode is asset-agnostic — its knobs scale by
ATR percentile rank, which is a relative measure that naturally
adjusts to the asset's vol baseline. No asset-specific preset
needed.

## Files in this commit

* `strategies/sweep_reclaim_strategy.py` — added `nq_intraday_sweep_preset`,
  `eth_daily_sweep_preset`, `sol_daily_sweep_preset`
* `strategies/compression_breakout_strategy.py` — added `nq_compression_preset`,
  `eth_compression_preset`, `sol_compression_preset`
* `strategies/regime_gated_strategy.py` — added `nq_intraday_preset`,
  `sol_daily_preset`
* `tests/test_cross_asset_parity.py` — 13 new parity tests
* `docs/research_log/full_asset_coverage_matrix_20260427.md` (this)

## Bottom line

The foundation is now SOLID across MNQ, NQ, BTC, ETH, SOL. Every
bot in the registry can be configured with the right preset for
its asset class, and there's no "first-class vs second-class"
asymmetry. Cross-asset separation is guaranteed by 13 parity
tests — any future refactor that flattens the differences will
break CI.

Next concrete moves:
1. Walk-forward each new strategy on each asset (where data
   permits)
2. Walk-forward multi-strategy combos per asset
3. Promote winners to per_bot_registry
4. Launch all promoted bots to paper-live

Foundation work is complete.
