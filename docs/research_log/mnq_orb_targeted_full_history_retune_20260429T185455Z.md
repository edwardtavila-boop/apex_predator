# MNQ ORB Targeted Full-History Retune - MNQ1/5m

_Generated from canonical runtime artifact: `var/eta_engine/state/research_grid/orb_sweep_MNQ1_5m_20260429_185455_323601.md`_

This targeted full-history retune checked the registered cell plus five serious ORB alternatives over the canonical MNQ1 5m tape. No checked cell recovered promotion-grade behavior.

| Range | RR | ATR x | EMA | Windows | +OOS | IS Sh | OOS Sh | DSR med | DSR pass% | Verdict |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 15m | 3.0 | 2.0 | 200 | 83 | 32 | +0.324 | -2.815 | 0.000 | 25.3 | FAIL |
| 15m | 2.0 | 2.0 | 50 | 83 | 24 | -0.030 | -2.368 | 0.000 | 24.1 | FAIL |
| 5m | 3.0 | 2.0 | 50 | 83 | 31 | -0.335 | -2.750 | 0.000 | 20.5 | FAIL |
| 15m | 2.0 | 2.0 | 200 | 83 | 23 | +0.166 | -3.568 | 0.000 | 16.9 | FAIL |
| 5m | 3.0 | 1.5 | 200 | 83 | 24 | -0.832 | -3.158 | 0.000 | 13.2 | FAIL |

Result: best checked full-history OOS was still negative (-2.368) and best DSR pass fraction was only 25.3%. `mnq_futures` is retained as a shadow benchmark while `mnq_futures_sage` remains the launchable MNQ lane.
