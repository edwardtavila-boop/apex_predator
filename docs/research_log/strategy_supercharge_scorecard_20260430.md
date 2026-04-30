# Strategy Supercharge Scorecard, 2026-04-30

Operator direction:

> "all and ac then b"

Interpretation: supercharge the full fleet, but execute the conservative
`A+C` path first, then move to `B` live-preflight retunes only after the
scorecard and safety gates are stable.

## What landed

This batch adds a framework-native scorecard instead of immediately changing
live strategy behavior. The scorecard ranks every bot by current launch lane:

1. `A_C_PAPER_SOAK` - retune and re-soak bots that are already paper-ready.
2. `A_C_RESEARCH_RETEST` - improve research candidates under strict gates.
3. `A_C_SHADOW_REPAIR` / `A_C_DATA_REPAIR` - repair shadow or data-blocked
   strategies before considering promotion.
4. `B_LIVE_PREFLIGHT_LATER` - protect production/live-preflight bots until
   A+C work proves stable.
5. `HOLD_*` - keep non-edge and deactivated bots out of retune automation.

The scorecard is advisory. It never promotes a bot, never changes live routing,
and always sets `safe_to_mutate_live=false`.

## Runtime surfaces

```powershell
python -m eta_engine.scripts.strategy_supercharge_scorecard
curl http://127.0.0.1:8000/api/jarvis/strategy_supercharge_scorecard
```

The CLI writes:

`C:\EvolutionaryTradingAlgo\var\eta_engine\state\strategy_supercharge_scorecard_latest.json`

The generated snapshot from the first run reported:

| Bucket | Count |
| --- | ---: |
| A+C targets | 11 |
| B-later targets | 6 |
| Hold targets | 2 |
| Total bots | 19 |

Top A+C targets from the generated artifact:

1. `btc_ensemble_2of3`
2. `btc_sage_daily_etf`
3. `eth_compression`
4. `eth_perp`
5. `btc_hybrid_sage`

## Why this is the right first supercharge slice

The fleet already has live-preflight, paper-soak, research, shadow, non-edge,
and deactivated lanes. Directly retuning live-preflight bots first would create
regression risk. This scorecard gives JARVIS and the framework a stable queue:
improve lower-risk paper/research/shadow lanes first, then graduate to live
preflight only with explicit retune evidence.

## Files touched

- `scripts/strategy_supercharge_scorecard.py`
- `scripts/workspace_roots.py`
- `deploy/scripts/dashboard_api.py`
- `tests/test_strategy_supercharge_scorecard.py`
- `tests/test_dashboard_api.py`
- `docs/live_launch_runbook.md`
- `docs/research_log/strategy_supercharge_scorecard_20260430.md`
