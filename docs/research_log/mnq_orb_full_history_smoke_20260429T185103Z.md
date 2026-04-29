# MNQ ORB Full-History Smoke - MNQ1/5m

_Generated from canonical runtime artifact: `var/eta_engine/state/research_grid/orb_sweep_MNQ1_5m_20260429_185103_631104.md`_

This full-history smoke re-ran the registered latest-slice candidate over the positive-price-filtered canonical MNQ1 5m tape.

| Range | RR | ATR x | EMA | Windows | +OOS | IS Sh | OOS Sh | DSR med | DSR pass% | Verdict |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 5m | 3.0 | 1.5 | 50 | 83 | 28 | -0.707 | -2.958 | 0.000 | 13.2 | FAIL |

Result: 487,725 of 490,103 MNQ1 5m bars were tradable after filtering non-positive back-adjusted rows. Full-history validation failed materially, so plain MNQ ORB v2 must remain shadow-only.
