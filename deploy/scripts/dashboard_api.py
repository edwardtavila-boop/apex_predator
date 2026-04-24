"""
Deploy // dashboard_api
=======================
Minimal FastAPI backend for the Apex Predator dashboard.

Reads the JSON state files written by the Avengers stack and exposes them
via a small REST API. Designed to be consumed by the React trading-dashboard
or hit directly from curl.

Run:
  uvicorn deploy.scripts.dashboard_api:app --host 127.0.0.1 --port 8000

Endpoints:
  GET  /health                       -- liveness
  GET  /api/heartbeat                -- avengers_heartbeat.json
  GET  /api/dashboard                -- dashboard_payload.json
  GET  /api/last-task                -- last_task.json
  GET  /api/kaizen                   -- kaizen_ledger.json summary
  GET  /api/state/{filename}         -- raw JSON file from state dir
  GET  /api/tasks                    -- list registered BackgroundTasks
  POST /api/tasks/{task}/fire        -- manually fire a BackgroundTask
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# State/log dirs: Windows defaults; overridable via env
if os.name == "nt":
    _DEFAULT_STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "apex_predator" / "state"
    _DEFAULT_LOG   = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "apex_predator" / "logs"
else:
    _DEFAULT_STATE = Path.home() / ".local" / "state" / "apex_predator"
    _DEFAULT_LOG   = Path.home() / ".local" / "log" / "apex_predator"

STATE_DIR = Path(os.environ.get("APEX_STATE_DIR", _DEFAULT_STATE))
LOG_DIR   = Path(os.environ.get("APEX_LOG_DIR",   _DEFAULT_LOG))


app = FastAPI(
    title="Apex Predator Dashboard",
    description="Read-only state surface for the JARVIS + Avengers stack",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _read_json(name: str) -> dict:
    path = STATE_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{name} not found in {STATE_DIR}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"parse error: {e}") from e


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {
        "status": "ok",
        "state_dir": str(STATE_DIR),
        "log_dir": str(LOG_DIR),
        "state_dir_exists": STATE_DIR.exists(),
    }


@app.get("/api/heartbeat")
def heartbeat() -> dict:
    """Latest Avengers daemon heartbeat."""
    return _read_json("avengers_heartbeat.json")


@app.get("/api/dashboard")
def dashboard_payload() -> dict:
    """Dashboard payload assembled by ROBIN every minute."""
    return _read_json("dashboard_payload.json")


@app.get("/api/last-task")
def last_task() -> dict:
    """Result of the most recent BackgroundTask invocation."""
    return _read_json("last_task.json")


@app.get("/api/kaizen")
def kaizen_summary() -> dict:
    """Kaizen ledger -- retrospectives + tickets."""
    data = _read_json("kaizen_ledger.json")
    return {
        "retrospectives": len(data.get("retrospectives", [])),
        "tickets_total":  len(data.get("tickets", [])),
        "tickets_open":   sum(1 for t in data.get("tickets", [])
                              if t.get("status") == "OPEN"),
        "tickets_shipped": sum(1 for t in data.get("tickets", [])
                               if t.get("status") == "SHIPPED"),
        "latest_tickets": data.get("tickets", [])[-5:],
    }


@app.get("/api/state/{filename}")
def get_state_file(filename: str) -> dict:
    """Fetch a raw JSON state file. Filename is safelisted."""
    safe = {
        "avengers_heartbeat.json", "dashboard_payload.json", "last_task.json",
        "kaizen_ledger.json", "shadow_ledger.json", "usage_tracker.json",
        "distiller.json", "precedent_graph.json", "strategy_candidates.json",
        "twin_verdict.json", "causal_review.json", "drift_summary.json",
        "cache_warmup.json", "audit_daily_summary.json",
    }
    if filename not in safe:
        raise HTTPException(status_code=403, detail="filename not on safelist")
    return _read_json(filename)


@app.get("/api/tasks")
def list_tasks() -> dict:
    """Return the 12 BackgroundTask names + owners + cadences."""
    from apex_predator.brain.avengers import TASK_CADENCE, TASK_OWNERS
    return {
        "tasks": [
            {"name": k.value, "owner": TASK_OWNERS[k], "cadence": TASK_CADENCE[k]}
            for k in TASK_CADENCE
        ],
    }


@app.post("/api/tasks/{task}/fire")
def fire_task(task: str) -> dict:
    """Manually fire a BackgroundTask. Useful for ad-hoc retrospectives."""
    from apex_predator.brain.avengers import BackgroundTask
    try:
        BackgroundTask(task.upper())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"unknown task: {task}") from exc
    # Fire async via subprocess so we don't block the response
    result = subprocess.run(
        [sys.executable, "-m", "deploy.scripts.run_task", task.upper(),
         "--state-dir", str(STATE_DIR), "--log-dir", str(LOG_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    return {
        "task": task.upper(),
        "returncode": result.returncode,
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }
