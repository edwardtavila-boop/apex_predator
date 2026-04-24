# Red Team Review — D-series Apex Eval Hardening

**Date:** 2026-04-24 (v0.1.58) · updated 2026-04-24 (v0.1.59 residual-risk closure)
**Scope:** D2 (`TrailingDDTracker`) and D3 (`ConsistencyGuard`) modules and
their wiring into `scripts/run_eta_live.py`.
**Reviewer:** `risk-advocate` agent (Opus 4.7, adversarial posture).
**Outcome (v0.1.58):** 3 BLOCKERs identified, all closed.
**Outcome (v0.1.59):** 4 HIGH residual risks re-litigated — 3 closed
(R2/R3/R4), 1 scaffolded with enforcement deferred to v0.2.x (R1).

This document captures the adversarial teardown of the D-series work, the
fixes shipped in response, and the residual risks that remain (documented
so they cannot be forgotten).

---

## Executive summary

Before this review the D-series modules had unit-level coverage but the
**wiring** into `run_eta_live.py` had three gaps that could let an Apex
eval fail silently. The review classified them as BLOCKERs because each
could cause the runtime to *appear* correct (all alerts green, all tests
green) while the eval was either already busted or about to bust.

| ID | Finding | Severity | Status |
|---:|---|---|---|
| B1 | UTC-midnight day-bucketing splits overnight equity-futures sessions across two Apex day keys | CRITICAL | Closed |
| B2 | Legacy `build_apex_eval_snapshot` fallback lacks freeze rule; silently under-protects in live mode when tracker is not wired | CRITICAL | Closed |
| B3 | 30%-rule VIOLATION was advisory-only: alert + log, no enforcement action on `is_paused` | HIGH | Closed |

Plus several HIGH findings that were accepted as known residual risk (see
"Residual risks" below).

---

## B1 — Session-day bucketing bug

**Finding.** `run_eta_live.py` was keying today's consistency-guard entry
by `utc_today_iso()`, which buckets PnL by **UTC calendar midnight**. The
Apex trading day is defined as the 24-hour window ending at **17:00
US/Central** (CME Globex close convention, DST-aware). An overnight
equity-futures session that generates PnL at 22:30 UTC in July (17:30 CDT)
would be charged to a *different* UTC day than PnL generated at 02:00 UTC
the next morning (21:00 CDT the prior evening) — even though both events
belong to the same Apex trading day.

Effect: the *largest winning day* appears smaller and the *total net
profit* denominator includes extra zero-PnL buckets. Both errors bias the
30%-rule ratio **downward**, hiding a real concentration risk. The
runtime reports "OK" or "WARNING" when the true state is "VIOLATION",
and the operator flies blind until Apex itself closes the eval.

**Fix.** Added `apex_trading_day_iso()` in
`eta_engine/core/consistency_guard.py`. Uses
`zoneinfo.ZoneInfo("America/Chicago")` to compute the 17:00 local
rollover in DST-aware fashion, with a fixed 23:00-UTC fallback when
`zoneinfo` is unavailable (wrong by ≤ 1h in summer, never splits RTH).
`run_eta_live.py` now calls this helper; `utc_today_iso()` stays with a
deprecation note for backwards compatibility.

**Tests.** `TestApexTradingDayIso` (11 tests): CDT + CST before and after
rollover, exact boundary at 17:00 CT, one-second-before boundary,
overnight-session co-location, naive-datetime coercion, `ZoneInfo`-absent
fallback, and an explicit diff-test confirming the two helpers disagree
on an evening-session timestamp (the bug the fix closes).

---

## B2 — Live-mode gate on `TrailingDDTracker`

**Finding.** `run_eta_live.py` runs a tick-precise trailing-DD tracker
**when one is supplied via the constructor kwarg**. When the kwarg is
omitted (which is the default), the runtime falls back to
`build_apex_eval_snapshot()` — a bar-level proxy that does **not**
implement the Apex freeze rule (once `peak >= start + cap`, the floor
locks at `start` forever). The fallback silently under-protects: a live
account that has climbed above the initial cap will compute a floor that
keeps trailing the peak down, so a normal retrace through the *correct*
frozen floor appears safe when it is actually a bust.

Effect: a runtime constructed without a tracker in `--live` mode is a
footgun. The operator has to remember to pass the tracker; nothing in
the framework enforces it.

**Fix.** `ApexRuntime.__init__` now raises `RuntimeError` when
`cfg.live=True AND cfg.dry_run=False AND trailing_dd_tracker is None`.
The error message names the missing wiring explicitly and points at the
module. Dry-run, paper-sim, and unit tests stay permissive (the proxy is
acceptable for those modes).

**Tests.** `TestLiveModeTrackerGate` (4 tests): live without tracker
raises, live with tracker builds cleanly, dry-run without tracker builds
cleanly, `live=True + dry_run=True` builds cleanly (dry_run wins).

---

## B3 — VIOLATION enforcement (advisory → pause)

**Finding.** When the consistency guard returned
`ConsistencyStatus.VIOLATION`, the runtime sent an alert and wrote a
structured log line. Neither action prevented new trades. A bot already
concentrated on its largest winning day could continue to open positions
until the operator noticed the alert in Discord/Slack and manually
paused. For an automated system, "notify and keep trading" is not
enforcement — it is a different kind of silent failure.

Effect: the guard was correctly detecting the risk but the runtime was
not acting on it. Tests covered the detection path but not an
enforcement path (because none existed).

**Fix.** On `VIOLATION`, the runtime now synthesizes a
`KillVerdict(action=PAUSE_NEW_ENTRIES, severity=CRITICAL, scope="tier_a")`
and feeds it through the existing `apply_verdict` dispatch path, which
flips `bot.state.is_paused = True` on every tier-A bot. Existing
positions are **not** flattened — they close on their own signals — but
new entries are blocked until the operator clears the violation (close
the bucket, bank the win, or `ConsistencyGuard.reset()` for a fresh
eval). The verdict is also appended to the tick's verdict log so audit
history captures the enforcement.

**Tests.** `TestConsistencyViolationPauses` (2 tests): pre-seeded
VIOLATION fires PAUSE on the tick and persists in `runtime.jsonl`;
pre-seeded WARNING does NOT fire PAUSE.

---

## Residual risks (v0.1.58 state → v0.1.59 closure)

The four HIGH findings below were flagged during the D-series Red Team
but originally deferred as "accepted residual risks" for v0.2.x. In
v0.1.59 we re-litigated that call — three of the four were within reach
and the fourth had a clean scaffold-now-wire-later shape. All four are
tracked below with their current closure state.

### R1 — Logical equity vs broker MTM  |  SCAFFOLDED (enforcement deferred)

**Original finding.** The tracker consumes `sum(bot.state.equity)` — a
logical figure maintained by the bot's own PnL book. Apex accounts for
MTM at broker level (unrealized + realized + funding + fees). A
prolonged disconnect between these two could drift the floor calculation
from what Apex sees.

**v0.1.59 closure (partial).** Added
`eta_engine/core/broker_equity_reconciler.py` —
`BrokerEquityReconciler` accepts a caller-supplied
`broker_equity_source: Callable[[], float | None]`, compares logical
equity to broker equity on every reconcile tick, and classifies drift
against configurable USD/pct tolerances. The dangerous case
(`broker_below_logical` = cushion over-stated) emits a WARNING log; the
inverse (`broker_above_logical` = cushion under-stated, merely early
flatten) emits INFO. Source exceptions are swallowed and classified as
`no_broker_data` (in-tolerance by convention — we can't assert drift we
can't see). The module **does not** pause, flatten, or synthesize a
KillVerdict — this is pure observation.

**Still deferred to v0.2.x:** wiring each broker adapter's
`get_balance()` / account-value endpoint to the reconciler, and
deciding whether the runtime should **replace** logical equity with
`broker_equity - sum(open_pnl)` as the tracker input. Today IBKR's
`get_balance()` returns an empty dict and Tastytrade/Tradovate wiring is
venue-specific; both are v0.2.x scope.

**Tests.** `tests/test_broker_equity_reconciler.py` — 21 tests across
8 classes: no-broker-data path, within-tolerance, broker-below-logical
(dangerous), broker-above-logical, USD/pct tolerance boundaries, zero
logical equity, source-raising treated as no_data, running stats
counters, result-shape contract.

### R2 — Tick-interval latency  |  CLOSED

**Original finding.** The runtime polls on a 5-second tick by default.
A fast retrace during that window could cross the floor before the next
update.

**v0.1.59 closure.** Added
`validate_apex_tick_cadence(...)` in
`eta_engine/core/kill_switch_runtime.py` — a pure-function validator
enforcing the invariant
`tick_interval_s * max_usd_move_per_sec * safety_factor <= cushion_usd`.
Default `max_usd_move_per_sec=300.0` and `safety_factor=2.0` bound the
worst-case single-tick retrace. Default `RuntimeConfig.tick_interval_s`
reduced **5.0 → 1.0**. In live mode (`live=True`) the validator raises
`ApexTickCadenceError` if the inequality fails; paper/dry-run no-ops.
`load_runtime_config()` calls the validator with the cushion read from
`kill_switch.tier_a.apex_eval_preemptive.cushion_usd`, so a mis-sized
config fails loudly at startup before a single tick runs.

**Tests.** `TestValidateApexTickCadence` (12 tests,
`test_kill_switch_runtime.py`) + `TestLoadRuntimeConfigTickCadence`
(4 tests, `test_run_eta_live.py`). Covers: invariant satisfied, fails
in live, no-op in paper, non-positive inputs rejected, default is 1.0s.

### R3 — Freeze-rule re-entrancy  |  CLOSED

**Original finding.** The tracker freezes when `peak >= start + cap`.
The risk is that if the tracker's state file is ever accidentally
deleted or the operator re-inits with a larger `trailing_dd_cap_usd`,
the freeze is lost and the floor resumes trailing.

**v0.1.59 closure.** Added `TrailingDDAuditLog` — an append-only JSONL
audit log co-located with the state file (default
`<state_path>.audit.jsonl`). `TrailingDDTracker` now emits immutable
events on every lifecycle transition: `init` (fresh create), `load`
(existing state), `freeze` (exactly once at the transition), `breach`
(each tick at/below floor), `reset` (with full `prior_state` snapshot,
operator name, reason). `append()` writes JSONL + fsyncs per append.
`reset()` now requires
`operator: str` (non-empty) and `acknowledge_destruction: bool=True` —
without the explicit ack the tracker raises
`ResetNotAcknowledgedError`. **Deleting the state file does not delete
the audit log**, so a forensic review can always detect a silent
re-init.

**Tests.** 6 new test classes in `test_trailing_dd_tracker.py`:
`TestAuditLogInitAndLoad`, `TestAuditLogFreezeAndBreach`,
`TestAuditLogSequenceMonotonicity`, `TestResetAcknowledgment`,
`TestAuditLogSurvivesStateDeletion`, `TestTrailingDDAuditLogUnit`.

### R4 — Session-day math vs weekends / holidays  |  CLOSED

**Original finding.** The 30% rule buckets by Apex trading day.
Weekends and US holidays don't exist in the calendar; the
`apex_trading_day_iso` helper keys a Saturday-morning timestamp to
"Saturday" which Apex probably ignores.

**v0.1.59 closure.** Added `eta_engine/core/events_calendar.py` —
CME Globex session calendar with `dateutil.easter`-driven Good Friday +
fixed-date closures (New Year, MLK, Presidents', Memorial, Juneteenth,
Independence, Labor, Thanksgiving, Christmas). `consistency_guard.py`
now routes `apex_trading_day_iso()` through the calendar so
Saturday/Sunday/holiday timestamps roll forward to the next regular
trading day instead of creating phantom buckets.

**Tests.** `test_core_events_calendar.py` covers the full CME calendar;
`test_consistency_guard.py` extended with rollover cases around each
closure type.

---

## Coverage delta

Before v0.1.58:
- `tests/test_consistency_guard.py` — 32 tests (guard logic, no
  session-day coverage).
- `tests/test_run_eta_live.py` — 60 tests (D2+D3 integration but no
  live-mode gate, no enforcement path).

After v0.1.58:
- `tests/test_consistency_guard.py` — **43 tests** (+11 `TestApexTradingDayIso`).
- `tests/test_run_eta_live.py` — **66 tests** (+4 `TestLiveModeTrackerGate`,
  +2 `TestConsistencyViolationPauses`).

After v0.1.59 (residual-risk closure):
- `tests/test_core_events_calendar.py` — **NEW** (R4: CME calendar).
- `tests/test_consistency_guard.py` — extended with calendar rollover cases.
- `tests/test_trailing_dd_tracker.py` — extended with 6 new audit-log
  classes (R3: init/load, freeze/breach, sequence monotonicity, reset
  acknowledgment, state-deletion survival, append-only unit).
- `tests/test_kill_switch_runtime.py` — +12 tests `TestValidateApexTickCadence` (R2).
- `tests/test_run_eta_live.py` — +4 tests `TestLoadRuntimeConfigTickCadence` (R2).
- `tests/test_broker_equity_reconciler.py` — **NEW**, 21 tests (R1).

Full regression: **3827 passed, 3 skipped** (Python 3.14.4 / Windows /
eta_engine) as of 2026-04-24. No regressions from v0.1.58 baseline.

---

## Quick-reference commands

```bash
# Single-module check
python -m ruff check eta_engine/core/consistency_guard.py \
                     eta_engine/scripts/run_eta_live.py

# D-series regression
python -m pytest \
    eta_engine/tests/test_run_eta_live.py \
    eta_engine/tests/test_consistency_guard.py \
    eta_engine/tests/test_trailing_dd_tracker.py \
    eta_engine/tests/test_kill_switch_latch.py \
    -x -q

# Chaos drills
python -m eta_engine.scripts.chaos_drills

# Kill-switch latch state
type eta_engine\state\kill_switch_latch.json

# Clear a tripped latch (requires operator name)
python -m eta_engine.scripts.clear_kill_switch --confirm --operator <name>
```
