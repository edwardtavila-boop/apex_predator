# ETH sage-daily retune - 2026-04-29T18:30:30Z

Provider-backed daily sage verdicts over ETH daily bars, then 90d/30d walk-forward on ETH/1h using strict fold DSR gate and min 3 trades per window.

| Base | Strict | Conv | Gate | IS Sh | OOS Sh | Deg% | DSR pass% | +OOS | OOS trades |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| legacy120 | false | 0.30 | FAIL | +2.159 | +4.888 | 40.6 | 57.1 | 13/21 | 68 |
| legacy120 | false | 0.35 | FAIL | +2.159 | +4.888 | 40.6 | 57.1 | 13/21 | 68 |
| legacy120 | true | 0.30 | FAIL | +4.349 | +4.844 | 47.2 | 52.4 | 12/21 | 65 |
| legacy120 | true | 0.35 | FAIL | +4.267 | +4.844 | 47.2 | 52.4 | 12/21 | 65 |
| legacy120 | true | 0.40 | FAIL | +3.383 | +3.877 | 41.0 | 57.1 | 13/21 | 71 |
| v4registered | false | 0.50 | FAIL | +2.472 | +2.882 | 42.9 | 57.1 | 12/21 | 91 |

Best honest candidate: legacy120 base, loose daily sage gate, conviction >= 0.30. It improves OOS Sharpe versus the prior strict 0.40 registry candidate, but still fails the 35% degradation cap, so it remains research-only.
