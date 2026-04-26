"""APEX PREDATOR  //  scripts.jarvis_dashboard
====================================================
Operator dashboard for JARVIS supervisor state. Surfaces the moving
parts the bot operator needs to glance at without spelunking journals:
breaker state, deadman timestamps, forecast quality, daemon health,
promotion queue, calibration drift, decision journal tail, alert tail,
and the **drift card** -- the most-recent verdict from
``brain.avengers.drift_detector.DriftDetector``.

This module is intentionally pure-Python. It serves a single static
HTML page (``INDEX_HTML``) with JS that polls ``/api/state``; the only
moving piece on the server side is :func:`collect_state`, which gathers
every panel into one dict. The render functions read journals -- they
do NOT mutate them.

Drift card schema (``_render_drift`` output):

    {
        "state":         <verdict>         # "OK" | "WARN" | "AUTO_DEMOTE" | "NO_DATA"
        "journal":       <str>             # path the panel reads
        "strategy_id":   <str | None>      # last entry's strategy
        "kl":            <float | None>    # kl_divergence of last entry
        "sharpe_delta":  <float | None>    # sharpe_delta_sigma of last entry
        "mean_delta":    <float | None>    # mean_return_delta of last entry
        "n_live":        <int | None>      # live_sample_size of last entry
        "n_backtest":    <int | None>      # bt_sample_size of last entry
        "entries":       <int>             # count of valid journal lines
        "counts":        {<verdict>: int}  # per-verdict count
        "reason":        <str>             # "; ".join(reasons) of last entry
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Module-level paths (monkeypatched by tests)
# ---------------------------------------------------------------------------

DRIFT_JOURNAL: Path = Path("~/.jarvis/drift.jsonl").expanduser()


# ---------------------------------------------------------------------------
# Drift card
# ---------------------------------------------------------------------------

def read_drift_journal(path: Path) -> list[dict[str, Any]]:
    """Return every well-formed JSON-line entry. Malformed lines skipped."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _render_drift() -> dict[str, Any]:
    """Build the drift card from the journal pointed at by ``DRIFT_JOURNAL``."""
    entries = read_drift_journal(DRIFT_JOURNAL)
    if not entries:
        return {
            "state":        "NO_DATA",
            "journal":      str(DRIFT_JOURNAL),
            "strategy_id":  None,
            "kl":           None,
            "sharpe_delta": None,
            "mean_delta":   None,
            "n_live":       None,
            "n_backtest":   None,
            "entries":      0,
            "counts":       {},
            "reason":       "",
        }

    counts: dict[str, int] = {}
    for e in entries:
        v = e.get("verdict")
        if isinstance(v, str):
            counts[v] = counts.get(v, 0) + 1

    last = entries[-1]
    reasons = last.get("reasons") or []
    reason_text = "; ".join(str(r) for r in reasons) if isinstance(reasons, list) else ""

    return {
        "state":        last.get("verdict") or "NO_DATA",
        "journal":      str(DRIFT_JOURNAL),
        "strategy_id":  last.get("strategy_id"),
        "kl":           last.get("kl_divergence"),
        "sharpe_delta": last.get("sharpe_delta_sigma"),
        "mean_delta":   last.get("mean_return_delta"),
        "n_live":       last.get("live_sample_size"),
        "n_backtest":   last.get("bt_sample_size"),
        "entries":      len(entries),
        "counts":       counts,
        "reason":       reason_text,
    }


# ---------------------------------------------------------------------------
# Per-panel placeholders
# ---------------------------------------------------------------------------
# Each panel below returns its own card dict. Panels backed by real
# subsystems (breaker, journal, alerts) read those subsystems' state.
# Panels for subsystems still under construction return a structured
# placeholder so the HTML layer always sees the key.
def _render_breaker() -> dict[str, Any]:
    return {"state": "UNKNOWN", "tripped_at": None}


def _render_deadman() -> dict[str, Any]:
    return {"last_heartbeat": None, "stale_seconds": None}


def _render_forecast() -> dict[str, Any]:
    return {"horizon_minutes": None, "confidence": None}


def _render_daemons() -> dict[str, Any]:
    return {"healthy": [], "down": []}


def _render_promotion() -> dict[str, Any]:
    return {"in_flight": []}


def _render_calibration() -> dict[str, Any]:
    return {"last_run": None, "ks_pvalue": None}


def _render_journal() -> dict[str, Any]:
    return {"tail": []}


def _render_alerts() -> dict[str, Any]:
    return {"tail": []}


def collect_state() -> dict[str, Any]:
    """Aggregate every panel into one snapshot for the HTML poller."""
    return {
        "drift":       _render_drift(),
        "breaker":     _render_breaker(),
        "deadman":     _render_deadman(),
        "forecast":    _render_forecast(),
        "daemons":     _render_daemons(),
        "promotion":   _render_promotion(),
        "calibration": _render_calibration(),
        "journal":     _render_journal(),
        "alerts":      _render_alerts(),
    }


# ---------------------------------------------------------------------------
# Static HTML template -- consumed by the dashboard server (deploy/scripts/
# dashboard_api.py) and asserted-against by test_jarvis_hardening.
# Element ids must match the JS poller; do not rename without updating both.
# ---------------------------------------------------------------------------
INDEX_HTML: str = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>JARVIS dashboard</title>
  <style>
    body { font-family: ui-monospace, monospace; background: #0b0d10; color: #e6edf3; margin: 0; padding: 16px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 12px; }
    .card h2 { margin: 0 0 8px; font-size: 13px; text-transform: uppercase; color: #8b949e; }
    .row { display: flex; justify-content: space-between; padding: 2px 0; font-size: 12px; }
    .ok { color: #56d364; } .warn { color: #d29922; } .bad { color: #f85149; }
  </style>
</head>
<body>
  <h1>JARVIS</h1>
  <div class="grid">
    <div class="card" id="card-drift">
      <h2>drift</h2>
      <div class="row"><span>state</span><span id="drift-state">--</span></div>
      <div class="row"><span>strategy</span><span id="drift-strategy">--</span></div>
      <div class="row"><span>kl</span><span id="drift-kl">--</span></div>
      <div class="row"><span>&Delta;sharpe</span><span id="drift-dsharpe">--</span></div>
      <div class="row"><span>&Delta;mean</span><span id="drift-dmean">--</span></div>
      <div class="row"><span>n</span><span id="drift-n">--</span></div>
      <div class="row"><span>reason</span><span id="drift-reason">--</span></div>
    </div>
    <div class="card" id="card-breaker"><h2>breaker</h2><div class="row"><span>state</span><span id="breaker-state">--</span></div></div>
    <div class="card" id="card-deadman"><h2>deadman</h2><div class="row"><span>last</span><span id="deadman-last">--</span></div></div>
    <div class="card" id="card-forecast"><h2>forecast</h2><div class="row"><span>horizon</span><span id="forecast-horizon">--</span></div></div>
    <div class="card" id="card-daemons"><h2>daemons</h2><div class="row"><span>down</span><span id="daemons-down">--</span></div></div>
    <div class="card" id="card-promotion"><h2>promotion</h2><div class="row"><span>in-flight</span><span id="promotion-inflight">--</span></div></div>
    <div class="card" id="card-calibration"><h2>calibration</h2><div class="row"><span>p-value</span><span id="calibration-p">--</span></div></div>
    <div class="card" id="card-journal"><h2>journal</h2><div class="row"><span>tail</span><span id="journal-tail">--</span></div></div>
    <div class="card" id="card-alerts"><h2>alerts</h2><div class="row"><span>tail</span><span id="alerts-tail">--</span></div></div>
  </div>
  <script>
    async function poll() {
      try {
        const r = await fetch('/api/state'); if (!r.ok) return;
        const s = await r.json();
        const d = s.drift || {};
        document.getElementById('drift-state').textContent = d.state || '--';
        document.getElementById('drift-strategy').textContent = d.strategy_id || '--';
        document.getElementById('drift-kl').textContent = d.kl != null ? d.kl.toFixed(3) : '--';
        document.getElementById('drift-dsharpe').textContent = d.sharpe_delta != null ? d.sharpe_delta.toFixed(2) : '--';
        document.getElementById('drift-dmean').textContent = d.mean_delta != null ? d.mean_delta.toFixed(4) : '--';
        document.getElementById('drift-n').textContent = (d.n_live != null && d.n_backtest != null) ? `${d.n_live}/${d.n_backtest}` : '--';
        document.getElementById('drift-reason').textContent = d.reason || '--';
      } catch (e) { /* ignore -- dashboard tolerates server hiccup */ }
    }
    poll(); setInterval(poll, 5000);
  </script>
</body>
</html>
"""


__all__ = [
    "DRIFT_JOURNAL",
    "INDEX_HTML",
    "collect_state",
    "read_drift_journal",
]
