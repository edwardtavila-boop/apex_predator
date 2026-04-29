# MNQ ORB Latest-20k Candidate Sweep - MNQ1/5m

_Generated from canonical runtime artifact: `var/eta_engine/state/research_grid/orb_sweep_MNQ1_5m_20260429_155144.md`_

This latest-slice sweep checked 54 plain ORB cells on the most recent 20,000 imported MNQ1 5m bars using 60d/30d walk-forward windows. The best candidate remained research-only:

| Range | RR | ATR x | EMA | Windows | +OOS | IS Sh | OOS Sh | DSR med | DSR pass% | Verdict |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 5m | 3.0 | 1.5 | 50 | 2 | 1 | -6.750 | +1.788 | 0.651 | 50.0 | FAIL |

Result: latest-slice OOS improved versus the prior smoke, but strict gate still failed because DSR pass fraction was exactly 50% and only one OOS fold was positive.
