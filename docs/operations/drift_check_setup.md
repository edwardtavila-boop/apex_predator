# Drift check — operations setup

## Purpose

Run `obs.drift_watchdog.run_all` on a schedule so every promoted
strategy gets a drift assessment relative to its baseline, with the
result written back to the decision journal as a `GRADER` event.

## One-time setup

1. **Pin baselines.** Copy `docs/strategy_baselines.example.json` to
   `docs/strategy_baselines.json` (gitignored — never commit live
   baselines). Replace the example with one entry per promoted
   strategy. The schema is documented in the example file.

2. **Verify the script runs locally:**

   ```powershell
   cd C:\EvolutionaryTradingAlgo\eta_engine
   python -m eta_engine.scripts.drift_check_all --dry-run
   ```

   Output should be a one-line-per-strategy summary table. Exit code
   reflects worst severity across the portfolio (0 green, 1 amber,
   2 red).

3. **Wire the Windows scheduled task** (every hour during RTH; tune
   to taste):

   ```powershell
   $action = New-ScheduledTaskAction `
     -Execute "python" `
     -Argument "-m eta_engine.scripts.drift_check_all" `
     -WorkingDirectory "C:\EvolutionaryTradingAlgo\eta_engine"

   $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
     -RepetitionInterval (New-TimeSpan -Hours 1)

   Register-ScheduledTask `
     -TaskName "ETA-DriftCheck" `
     -Action $action `
     -Trigger $trigger `
     -Description "Hourly drift check for promoted strategies"
   ```

   Or via `schtasks.exe`:

   ```cmd
   schtasks /Create /SC HOURLY /TN ETA-DriftCheck ^
     /TR "python -m eta_engine.scripts.drift_check_all" ^
     /SD 2026-04-27 /ST 08:00
   ```

## Monitoring

- Each run appends one `Actor.GRADER` event per strategy to
  `var/eta_engine/state/decision_journal.jsonl`. Filter by
  `intent="drift_check:<strategy_id>"` to find them.

- For a quick read on current state without re-running:
  ```powershell
  python -m eta_engine.scripts.drift_check_all --dry-run
  ```

- The dashboard (when wired) should surface the most recent GRADER
  event per strategy with severity color-coded.

## Re-baselining

Whenever a strategy is intentionally re-tuned and re-promoted, update
its row in `docs/strategy_baselines.json`. The scheduled task picks
up the new baseline on its next tick — no restart needed.

If you DON'T re-baseline after a tune, the drift monitor will
correctly flag the (intentionally) different live behaviour as
"drift". That's a feature, not a bug — it forces an explicit
operator confirmation that a tune happened and was wanted.

## Troubleshooting

- `[drift_check_all] no baselines file at ...` → first run; create
  the file from the example.
- `severity: GREEN` with reason `insufficient sample` → the journal
  has fewer than `min_trades` (default 20) executed trades for that
  strategy. Lower `--min-trades` if you want earlier signal, or wait.
- `severity: RED` with `win rate ... vs baseline ...` → either the
  strategy has decayed in production OR the baseline is wrong.
  First-line response: re-read the most recent GRADER event's
  metadata to see the actual numbers, compare to a fresh manual
  backtest on recent data.

## Future iteration: JARVIS daemon adoption

Currently this runs as a separate scheduled task. Next step:
collapse it into the JARVIS daemon's tick (`brain/avengers/daemon.py`)
so the operator has one process to monitor instead of two. That
collapse is deferred until: (1) we have ≥3 promoted strategies, and
(2) the JARVIS daemon's existing test suite is fully green so the
adoption doesn't get muddled with unrelated test debt.
