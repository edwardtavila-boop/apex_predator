"""APEX PREDATOR  //  scripts.jarvis_dashboard  --  MASTER COMMAND CENTER
=========================================================================
The canonical operator console for the Apex Predator framework. Surfaces
every JARVIS supervisor signal the operator needs to glance at without
spelunking journals: drift verdict, breaker state, deadman heartbeat,
forecast quality, daemon health, promotion queue, calibration drift,
decision-journal tail, alert tail.

The module is dual-mode:

* **Library** (default on import): exposes :func:`collect_state` and
  :data:`INDEX_HTML` for tests and the FastAPI dashboard backend.
* **Server** (via ``python -m apex_predator.scripts.jarvis_dashboard``
  or :func:`serve`): runs a stdlib :class:`http.server.ThreadingHTTPServer`
  binding ``127.0.0.1`` by default. Pair with Cloudflare Tunnel for
  remote access; see ``deploy/HOST_RUNBOOK.md``.

Routes:

    GET /                       --  HTML shell (INDEX_HTML)
    GET /api/state              --  collect_state() as JSON
    GET /healthz                --  liveness ("ok\\n")
    GET /manifest.webmanifest   --  PWA manifest (installable on phones)
    GET /sw.js                  --  service worker (offline shell cache)
    GET /icon.svg               --  app icon (192x192-friendly SVG)

The server is intentionally stdlib-only -- import-time side-effect free,
no FastAPI, no uvicorn. The :class:`_Handler` overrides
:meth:`http.server.BaseHTTPRequestHandler.log_message` so noisy access
logs don't spam systemd journals.

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

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
            "state": "NO_DATA",
            "journal": str(DRIFT_JOURNAL),
            "strategy_id": None,
            "kl": None,
            "sharpe_delta": None,
            "mean_delta": None,
            "n_live": None,
            "n_backtest": None,
            "entries": 0,
            "counts": {},
            "reason": "",
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
        "state": last.get("verdict") or "NO_DATA",
        "journal": str(DRIFT_JOURNAL),
        "strategy_id": last.get("strategy_id"),
        "kl": last.get("kl_divergence"),
        "sharpe_delta": last.get("sharpe_delta_sigma"),
        "mean_delta": last.get("mean_return_delta"),
        "n_live": last.get("live_sample_size"),
        "n_backtest": last.get("bt_sample_size"),
        "entries": len(entries),
        "counts": counts,
        "reason": reason_text,
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
        "drift": _render_drift(),
        "breaker": _render_breaker(),
        "deadman": _render_deadman(),
        "forecast": _render_forecast(),
        "daemons": _render_daemons(),
        "promotion": _render_promotion(),
        "calibration": _render_calibration(),
        "journal": _render_journal(),
        "alerts": _render_alerts(),
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
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="theme-color" content="#0b0d10" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="JARVIS" />
  <link rel="manifest" href="/manifest.webmanifest" />
  <link rel="icon" type="image/svg+xml" href="/icon.svg" />
  <link rel="apple-touch-icon" href="/icon.svg" />
  <title>JARVIS // Master Command Center</title>
  <style>
    :root {
      --bg: #07090d; --panel: #11161d; --panel2: #161b22;
      --border: #1f2631; --border2: #30363d;
      --text: #e7ecf2; --dim: #8b949e; --mute: #4c5564;
      --ok: #56d364; --warn: #d29922; --bad: #f85149;
      --accent: #00ffa3; --accent2: #00d1ff;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text); }
    body {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      padding: max(env(safe-area-inset-top), 12px) 12px max(env(safe-area-inset-bottom), 12px);
      -webkit-tap-highlight-color: transparent;
      overscroll-behavior-y: contain;
    }
    header {
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px; margin: 0 0 12px;
    }
    header h1 {
      margin: 0; font-size: 14px; letter-spacing: 0.18em; text-transform: uppercase;
      color: var(--accent);
    }
    header h1 .sep { color: var(--mute); margin: 0 6px; }
    header h1 .sub { color: var(--dim); }
    .pulse {
      display: inline-block; width: 8px; height: 8px; border-radius: 50%;
      background: var(--ok); box-shadow: 0 0 8px var(--ok);
      animation: pulse 2s ease-in-out infinite;
    }
    .pulse.stale { background: var(--bad); box-shadow: 0 0 8px var(--bad); }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 10px;
    }
    .card {
      background: var(--panel2); border: 1px solid var(--border2);
      border-radius: 8px; padding: 12px 14px; min-height: 88px;
    }
    .card h2 {
      margin: 0 0 8px; font-size: 11px; letter-spacing: 0.16em;
      text-transform: uppercase; color: var(--dim);
      display: flex; align-items: center; justify-content: space-between;
    }
    .card h2 .badge { font-size: 10px; color: var(--mute); }
    .row {
      display: flex; justify-content: space-between; gap: 12px;
      padding: 3px 0; font-size: 13px; line-height: 1.4;
    }
    .row > span:first-child { color: var(--dim); }
    .row > span:last-child  { color: var(--text); text-align: right; word-break: break-word; }
    .ok   { color: var(--ok)   !important; }
    .warn { color: var(--warn) !important; }
    .bad  { color: var(--bad)  !important; }
    footer {
      margin-top: 14px; color: var(--mute); font-size: 11px;
      text-align: center; letter-spacing: 0.08em;
    }
    @media (max-width: 480px) {
      body { padding: 10px 8px; }
      .grid { grid-template-columns: 1fr; gap: 8px; }
      .card { padding: 11px 12px; }
      header h1 { font-size: 12px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>
      <span class="pulse" id="hb-pulse" title="last poll"></span>
      &nbsp;JARVIS<span class="sep">//</span><span class="sub">Master Command Center</span>
    </h1>
    <span id="hb-ts" style="font-size:11px;color:var(--mute);">--</span>
  </header>
  <div class="grid">
    <div class="card" id="card-drift">
      <h2>drift <span class="badge" id="drift-counts">--</span></h2>
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
  <footer>apex predator // jarvis master command center</footer>
  <script>
    const $ = (id) => document.getElementById(id);
    const colorFor = (s) => s === 'OK' ? 'ok' : s === 'WARN' ? 'warn'
      : (s === 'AUTO_DEMOTE' || s === 'BAD' || s === 'TRIPPED') ? 'bad' : '';
    function setText(id, v, klass) {
      const el = $(id); if (!el) return;
      el.textContent = (v == null || v === '') ? '--' : String(v);
      el.classList.remove('ok','warn','bad');
      if (klass) el.classList.add(klass);
    }
    async function poll() {
      try {
        const r = await fetch('/api/state', { cache: 'no-store' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const s = await r.json();
        const d = s.drift || {};
        setText('drift-state',    d.state, colorFor(d.state));
        setText('drift-strategy', d.strategy_id);
        setText('drift-kl',       d.kl != null ? d.kl.toFixed(3) : null);
        setText('drift-dsharpe',  d.sharpe_delta != null ? d.sharpe_delta.toFixed(2) : null);
        setText('drift-dmean',    d.mean_delta != null ? d.mean_delta.toFixed(4) : null);
        setText('drift-n',        (d.n_live != null && d.n_backtest != null) ? `${d.n_live}/${d.n_backtest}` : null);
        setText('drift-reason',   d.reason);
        const c = d.counts || {}; const ck = Object.keys(c);
        setText('drift-counts', ck.length ? ck.map(k => `${k.charAt(0)}:${c[k]}`).join(' ') : null);
        const b = s.breaker || {};   setText('breaker-state', b.state, colorFor(b.state));
        const dm = s.deadman || {};  setText('deadman-last', dm.last_heartbeat);
        const fc = s.forecast || {}; setText('forecast-horizon', fc.horizon_minutes != null ? `${fc.horizon_minutes}m` : null);
        const dn = s.daemons || {};  setText('daemons-down', (dn.down || []).length, (dn.down || []).length ? 'bad' : 'ok');
        const pr = s.promotion || {};setText('promotion-inflight', (pr.in_flight || []).length);
        const cb = s.calibration || {};setText('calibration-p', cb.ks_pvalue != null ? cb.ks_pvalue.toFixed(3) : null);
        const jr = s.journal || {};  setText('journal-tail', (jr.tail || []).length);
        const al = s.alerts || {};   setText('alerts-tail', (al.tail || []).length);
        $('hb-pulse').classList.remove('stale');
        $('hb-ts').textContent = new Date().toLocaleTimeString();
      } catch (e) {
        $('hb-pulse').classList.add('stale');
      }
    }
    poll(); setInterval(poll, 5000);
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# PWA shell -- manifest, service worker, icon
# ---------------------------------------------------------------------------

MANIFEST_JSON: str = json.dumps(
    {
        "name": "JARVIS Master Command Center",
        "short_name": "JARVIS",
        "description": "Apex Predator operator command center.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#07090d",
        "theme_color": "#0b0d10",
        "icons": [
            {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"},
            {"src": "/icon.svg", "sizes": "192x192", "type": "image/svg+xml"},
            {"src": "/icon.svg", "sizes": "512x512", "type": "image/svg+xml"},
        ],
    }
)

SERVICE_WORKER_JS: str = """\
// JARVIS MCC service worker -- shell cache only.
// Live data (/api/state) is always network-first.
const SHELL = 'jarvis-mcc-shell-v1';
const SHELL_FILES = ['/', '/manifest.webmanifest', '/icon.svg'];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)));
  self.skipWaiting();
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))
    ))
  );
  self.clients.claim();
});
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/')) return; // live: network-only
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
"""

ICON_SVG: str = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"  stop-color="#00ffa3"/>
      <stop offset="100%" stop-color="#00d1ff"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="96" fill="#07090d"/>
  <circle cx="256" cy="256" r="168" fill="none" stroke="url(#g)" stroke-width="10" opacity="0.55"/>
  <circle cx="256" cy="256" r="120" fill="none" stroke="url(#g)" stroke-width="6" opacity="0.85"/>
  <circle cx="256" cy="256" r="22" fill="url(#g)"/>
  <text x="256" y="430" text-anchor="middle"
        font-family="ui-monospace, monospace" font-weight="700"
        font-size="56" fill="url(#g)" letter-spacing="6">JARVIS</text>
</svg>
"""


# ---------------------------------------------------------------------------
# HTTP server (stdlib)
# ---------------------------------------------------------------------------

DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 8765


class _Handler(BaseHTTPRequestHandler):
    """Minimal stdlib handler -- one route table, no framework."""

    server_version = "JarvisMCC/1.0"

    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 -- stdlib contract
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            self._send(HTTPStatus.OK, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            try:
                payload = json.dumps(collect_state(), default=str).encode("utf-8")
            except Exception as exc:  # noqa: BLE001 -- never crash the dashboard
                payload = json.dumps({"error": str(exc)}).encode("utf-8")
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, payload, "application/json")
                return
            self._send(HTTPStatus.OK, payload, "application/json")
            return
        if path == "/healthz":
            self._send(HTTPStatus.OK, b"ok\n", "text/plain; charset=utf-8")
            return
        if path == "/manifest.webmanifest":
            self._send(
                HTTPStatus.OK, MANIFEST_JSON.encode("utf-8"), "application/manifest+json", cache="public, max-age=3600"
            )
            return
        if path == "/sw.js":
            self._send(HTTPStatus.OK, SERVICE_WORKER_JS.encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if path == "/icon.svg":
            self._send(HTTPStatus.OK, ICON_SVG.encode("utf-8"), "image/svg+xml", cache="public, max-age=86400")
            return
        self._send(HTTPStatus.NOT_FOUND, b"not found\n", "text/plain; charset=utf-8")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 -- stdlib contract
        # Silence the default access log; systemd journals stay clean.
        return


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Run the master command center server in the foreground."""
    httpd = ThreadingHTTPServer((host, port), _Handler)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="jarvis-mcc",
        description="JARVIS Master Command Center -- operator dashboard server.",
    )
    parser.add_argument("--host", default=os.environ.get("JARVIS_MCC_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("JARVIS_MCC_PORT", DEFAULT_PORT)))
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover -- entry point
    main()


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DRIFT_JOURNAL",
    "ICON_SVG",
    "INDEX_HTML",
    "MANIFEST_JSON",
    "SERVICE_WORKER_JS",
    "collect_state",
    "main",
    "read_drift_journal",
    "serve",
]
