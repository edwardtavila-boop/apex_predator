# Fleet Strategy Optimization — 2026-04-28T06:24:29.667918+00:00

_Bots: 8_  _Total cells: 195_

## Summary — fleet PASS map

| Bot | Best verdict | Best strategy | Best OOS Sh | # PASS configs |
|---|---|---|---:|---:|
| mnq_futures | **PASS** | orb: r10/atr2.5/rr2.5 | +5.814 | 10 |
| nq_futures | **PASS** | orb: r15/atr2.0/rr2.0 | +5.706 | 12 |
| nq_daily_drb | FAIL | drb: drb atr2.0/rr2.0 | +9.047 | 0 |
| btc_hybrid | FAIL | crypto_orb: corb r120/atr3.0/rr2.0 | +2.888 | 0 |
| eth_perp | **PASS** | crypto_orb: corb r60/atr3.0/rr2.0 | +16.104 | 1 |
| sol_perp | FAIL | crypto_orb: corb r120/atr2.0/rr2.5 | +2.498 | 0 |
| crypto_seed | FAIL | crypto_trend: trend ema12/26 | -0.037 | 0 |
| grid_bot__btc | FAIL | grid: grid sp0.005/lvl4 | -6.410 | 0 |

## Per-bot ranked tables (top 6 each)

### mnq_futures

| Verdict | Strategy | IS Sh | OOS Sh | Deg% | DSR med | DSR pass% | W | +OOS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **PASS** | orb: r10/atr2.5/rr2.5 | +3.158 | +5.814 | 0.0 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r15/atr2.0/rr2.0 | +3.292 | +5.706 | 14.2 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r30/atr2.0/rr1.5 | +2.296 | +5.192 | 0.0 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r15/atr2.0/rr2.5 | +2.186 | +4.037 | 0.0 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r10/atr2.5/rr2.0 | +3.558 | +3.834 | 7.5 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r10/atr2.0/rr1.5 | +0.537 | +3.050 | 0.0 | 1.000 | 100.0 | 2 | 2 |

### nq_futures

| Verdict | Strategy | IS Sh | OOS Sh | Deg% | DSR med | DSR pass% | W | +OOS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **PASS** | orb: r15/atr2.0/rr2.0 | +3.292 | +5.706 | 14.2 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r10/atr2.5/rr2.5 | +2.952 | +5.205 | 0.0 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r30/atr2.0/rr1.5 | +2.785 | +5.192 | 0.0 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r10/atr2.0/rr1.5 | +0.537 | +4.356 | 0.0 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r15/atr2.0/rr2.5 | +2.186 | +4.037 | 0.0 | 1.000 | 100.0 | 2 | 2 |
| **PASS** | orb: r10/atr2.0/rr2.0 | +2.343 | +3.834 | 0.0 | 1.000 | 100.0 | 2 | 2 |

### nq_daily_drb

| Verdict | Strategy | IS Sh | OOS Sh | Deg% | DSR med | DSR pass% | W | +OOS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| FAIL | drb: drb atr2.0/rr2.0 | +0.921 | +9.047 | 42.1 | 0.006 | 39.6 | 53 | 31 |
| FAIL | drb: drb atr2.0/rr2.5 | +0.621 | +5.079 | 43.0 | 0.005 | 41.5 | 53 | 29 |
| FAIL | drb: drb atr2.0/rr1.5 | +0.677 | +4.400 | 46.3 | 0.003 | 37.7 | 53 | 28 |
| FAIL | drb: drb atr1.5/rr2.0 | +1.361 | +2.484 | 55.0 | 0.004 | 39.6 | 53 | 26 |
| FAIL | drb: drb atr1.5/rr2.5 | +0.364 | +1.673 | 40.1 | 0.008 | 41.5 | 53 | 30 |
| FAIL | drb: drb atr1.0/rr1.5 | +0.939 | +1.334 | 40.5 | 0.334 | 47.2 | 53 | 34 |

### btc_hybrid

| Verdict | Strategy | IS Sh | OOS Sh | Deg% | DSR med | DSR pass% | W | +OOS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| FAIL | crypto_orb: corb r120/atr3.0/rr2.0 | +0.148 | +2.888 | 33.3 | 0.442 | 49.1 | 57 | 33 |
| FAIL | crypto_orb: corb r120/atr2.5/rr2.5 | +0.966 | +2.862 | 32.8 | 0.010 | 49.1 | 57 | 37 |
| FAIL | crypto_orb: corb r240/atr2.0/rr2.5 | +0.342 | +2.736 | 34.4 | 0.010 | 43.9 | 57 | 31 |
| FAIL | crypto_orb: corb r120/atr3.0/rr2.5 | -0.559 | +2.552 | 26.4 | 0.010 | 47.4 | 57 | 36 |
| FAIL | crypto_orb: corb r240/atr2.0/rr2.0 | -0.758 | +2.480 | 29.8 | 0.010 | 42.1 | 57 | 27 |
| FAIL | crypto_orb: corb r120/atr3.0/rr1.5 | -0.184 | +2.293 | 33.3 | 0.468 | 49.1 | 57 | 37 |

### eth_perp

| Verdict | Strategy | IS Sh | OOS Sh | Deg% | DSR med | DSR pass% | W | +OOS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **PASS** | crypto_orb: corb r60/atr3.0/rr2.0 | +0.212 | +16.104 | 11.1 | 1.000 | 88.9 | 9 | 8 |
| FAIL | crypto_orb: corb r240/atr2.5/rr1.5 | +0.952 | +6.096 | 44.4 | 0.985 | 55.6 | 9 | 5 |
| FAIL | crypto_orb: corb r120/atr3.0/rr1.5 | -0.151 | +5.819 | 11.1 | 0.988 | 88.9 | 9 | 8 |
| FAIL | crypto_orb: corb r60/atr2.5/rr2.5 | -2.251 | +5.571 | 22.2 | 1.000 | 66.7 | 9 | 6 |
| FAIL | crypto_orb: corb r60/atr3.0/rr2.5 | -0.795 | +5.401 | 22.2 | 1.000 | 66.7 | 9 | 7 |
| FAIL | crypto_orb: corb r120/atr2.5/rr2.0 | -0.962 | +5.273 | 11.1 | 0.991 | 88.9 | 9 | 8 |

### sol_perp

| Verdict | Strategy | IS Sh | OOS Sh | Deg% | DSR med | DSR pass% | W | +OOS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| FAIL | crypto_orb: corb r120/atr2.0/rr2.5 | -3.802 | +2.498 | 0.0 | 0.001 | 44.4 | 9 | 4 |
| FAIL | crypto_orb: corb r240/atr2.0/rr2.0 | +1.026 | +2.134 | 44.4 | 0.987 | 55.6 | 9 | 5 |
| FAIL | crypto_orb: corb r120/atr3.0/rr1.5 | -4.061 | +1.620 | 22.2 | 0.003 | 33.3 | 9 | 5 |
| FAIL | crypto_orb: corb r240/atr2.0/rr1.5 | +0.603 | +1.323 | 22.2 | 0.765 | 66.7 | 9 | 7 |
| FAIL | crypto_orb: corb r120/atr3.0/rr2.0 | -4.016 | +1.323 | 22.2 | 0.169 | 44.4 | 9 | 6 |
| FAIL | crypto_trend: trend ema9/21 | -2.075 | +1.149 | 44.4 | 0.009 | 44.4 | 9 | 5 |

### crypto_seed

| Verdict | Strategy | IS Sh | OOS Sh | Deg% | DSR med | DSR pass% | W | +OOS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| FAIL | crypto_trend: trend ema12/26 | -0.012 | -0.037 | 50.0 | 0.072 | 12.5 | 8 | 1 |
| FAIL | crypto_trend: trend ema9/21 | +1.283 | -0.179 | 66.4 | 0.072 | 0.0 | 8 | 1 |
| FAIL | drb: drb atr1.0/rr1.5 | -0.470 | -0.296 | 50.0 | 0.000 | 25.0 | 8 | 3 |
| FAIL | drb: drb atr1.0/rr2.0 | -1.251 | -0.489 | 37.5 | 0.037 | 12.5 | 8 | 4 |
| FAIL | drb: drb atr1.5/rr1.5 | -0.376 | -0.533 | 50.0 | 0.000 | 12.5 | 8 | 4 |
| FAIL | crypto_trend: trend ema20/50 | +6.768 | -0.981 | 75.0 | 0.072 | 0.0 | 8 | 0 |

### grid_bot__btc

| Verdict | Strategy | IS Sh | OOS Sh | Deg% | DSR med | DSR pass% | W | +OOS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| FAIL | grid: grid sp0.005/lvl4 | -4.645 | -6.410 | 64.9 | 0.000 | 0.0 | 57 | 1 |
| FAIL | grid: grid sp0.005/lvl6 | -9.389 | -11.584 | 64.9 | 0.000 | 0.0 | 57 | 0 |
| FAIL | grid: grid sp0.01/lvl4 | -10.666 | -12.387 | 61.4 | 0.000 | 0.0 | 57 | 0 |
| FAIL | grid: grid sp0.015/lvl4 | -12.211 | -13.104 | 45.6 | 0.000 | 0.0 | 57 | 0 |
| FAIL | grid: grid sp0.015/lvl6 | -13.015 | -13.899 | 50.9 | 0.000 | 0.0 | 57 | 0 |
| FAIL | grid: grid sp0.01/lvl6 | -12.251 | -14.289 | 59.7 | 0.000 | 0.0 | 57 | 0 |
