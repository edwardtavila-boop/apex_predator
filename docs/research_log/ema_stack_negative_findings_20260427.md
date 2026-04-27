# EMA-stack variants — negative findings, 2026-04-27

User question: "what about when the 21 EMA above [the slow], for
scalping/swing 9 over 21 etc — what variants would increase this
strategy to where we need it the best?"

Answer: **on BTC 1h, none of the EMA-stack variants beat the
crypto_regime_trend baseline of +2.96 OOS Sharpe.** Documenting
this honestly because the result is informative for what to do
next.

## What was built

`strategies/crypto_ema_stack_strategy.py` ships six independently-
configurable upgrades on top of the regime-trend baseline:

* **A. Stack alignment** — require N EMAs to be ordered
  fast > slow (longs) for the trade to fire.
* **B. Configurable entry EMA** — pullback target = any EMA in
  the stack. (9 = scalp, 21 = swing, 50 = position.)
* **C. Stack separation filter** — require fastest−slowest EMA
  spread > N × ATR. Skips chop where EMAs hug.
* **D. Volume confirmation** — pullback bar volume > X × recent avg.
* **E. Adaptive RR** — bump the target multiplier when stack is
  tight (compressed). Compression → expansion thesis.
* **F. Soft stop on entry-EMA reclaim** — exit when close prints
  back through the entry EMA against the trade.

13 unit tests cover all six paths.

## Walk-forward results — BTC 1h, 90d/30d, 9 windows

Baseline reference (`crypto_regime_trend` at the winning cell):
**agg OOS Sharpe +2.96, 7/9 +OOS, 91 trades.**

Stack mode presets:

| Mode | Stack | Agg OOS | +OOS | Trades | Δ vs base |
|---|---|---:|---:|---:|---:|
| Scalp | 9/21 | +0.59 | 5/9 | 174 | -2.37 |
| Swing | 9/21/50 | +0.83 | 5/9 | 177 | -2.13 |
| Full | 9/21/50/200 | -0.71 | 5/9 | 109 | -3.67 |
| Full @ 21 | 9/21/50/200, entry=21 | -1.17 | 4/9 | 79 | -4.13 |
| Full @ 50 | 9/21/50/200, entry=50 | -1.56 | 4/9 | 82 | -4.52 |

Variant overlays on the 21/100 two-EMA setup:

| Variant | Agg OOS | +OOS | Trades | Δ vs base |
|---|---:|---:|---:|---:|
| Bare 21/100 | -0.03 | 6/9 | 114 | -2.99 |
| **+ sep ≥ 1×ATR** | **+2.67** | 6/9 | 87 | -0.29 |
| + sep ≥ 2×ATR | +0.09 | 4/9 | 74 | -2.87 |
| + vol ≥ 1.2× | +0.67 | 4/9 | 103 | -2.29 |
| + vol ≥ 1.5× | +0.08 | 5/9 | 98 | -2.88 |
| + adaptive RR | +0.86 | 7/9 | 103 | -2.10 |
| + soft stop | +0.27 | 5/9 | 198 | -2.69 |
| + ALL variants | -0.10 | 5/9 | 87 | -3.06 |

3-EMA stacks with separation filter:

| Stack | Sep | Agg OOS | +OOS | Trades |
|---|---:|---:|---:|---:|
| 21/50/100 | ≥1×ATR | +2.09 | 6/9 | 90 |
| 9/21/100 | ≥1×ATR | +2.35 | 7/9 | 86 |

## What this tells us

1. **More EMAs in the alignment rule makes it worse.** Going from
   regime_trend's effective 1-EMA gate to a 4-EMA full stack drops
   agg OOS from +2.96 to −0.71. The market doesn't reward strict
   ribbon ordering on BTC 1h — pullbacks fire even when the slow
   EMAs are crossing.
2. **Variant C (stack separation filter) is the only positive
   variant.** Adding a 1×ATR spread gate to the 2-EMA setup lifts
   it from −0.03 to +2.67 — a +2.7 Sharpe improvement. But that
   STILL undershoots the baseline by 0.29.
3. **Variants D / E / F net out negative.** Volume confirmation,
   adaptive RR, and soft stops each cut edge or add noise.
4. **The combined "ALL VARIANTS" cell underperforms the bare
   2-EMA setup.** Stacking filters compounds their costs (each
   one filters real signals along with noise).

## Why the simpler baseline wins

`crypto_regime_trend` uses a 2-EMA setup (regime=100, pull=21,
tol=3%) WITHOUT requiring strict stack ordering. The bull regime
is just `close > 100 EMA` — even when 9 < 21 momentarily, a
pullback to 21 in an ongoing macro-uptrend is a valid entry.

The EMA-stack rule rejects those moments because the strict
ordering condition fails. It's a stricter filter, but the strictness
costs more good trades than it saves bad ones.

## What WOULD move the needle (next experiments)

Three levers on different axes from "more EMAs":

1. **Time-of-day filter** — restrict trades to the 13:00–16:00
   UTC window (London/NY overlap). BTC's volume + ATR are
   2-3× the Asian session.
2. **HTF alignment** — keep the simple 1h regime gate, but ALSO
   check the 4h regime is the same direction. Captures the
   "scopes in and out of timeframes" insight directly.
3. **Volatility-regime filter** — skip when ATR is in the
   bottom or top decile of its rolling distribution. Trades
   only the "normal trending" middle band.

Of these, **HTF alignment** is the most direct upgrade to the
regime_trend strategy because it doesn't introduce new state types,
just consults a second EMA over a longer effective window
(approximated by a much longer EMA period on the same TF, e.g.
800 EMA on 1h ≈ 1d 33-period EMA).

## Files in this entry

* `strategies/crypto_ema_stack_strategy.py` — the supercharged
  variant module. Kept in the codebase even though it doesn't
  promote: it's a useful building block for future research, and
  the 13 unit tests document each variant's behavior precisely.
* `tests/test_crypto_ema_stack.py` — 13 unit tests.
* `docs/research_log/ema_stack_negative_findings_20260427.md`
  (this file).

## Recommendation

DO NOT promote any EMA-stack variant. Keep `crypto_regime_trend`
as the BTC research-candidate strategy. Next experiment: HTF
alignment (variant 2 above).
