"""
Tests for deploy.scripts.dashboard_api -- FastAPI backend for the Apex
Predator dashboard.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Point dashboard_api at a temp state dir + return a TestClient."""
    monkeypatch.setenv("APEX_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("APEX_LOG_DIR", str(tmp_path / "logs"))
    (tmp_path / "state").mkdir()
    (tmp_path / "logs").mkdir()
    # Seed a couple of state files
    (tmp_path / "state" / "avengers_heartbeat.json").write_text(json.dumps({
        "ts": "2026-04-24T00:00:00+00:00",
        "quota_state": "OK", "hourly_pct": 0.0, "daily_pct": 0.0,
        "cache_hit_rate": 0.0, "distiller_version": 0,
        "distiller_trained": False,
    }))
    (tmp_path / "state" / "dashboard_payload.json").write_text(json.dumps({
        "ts": "2026-04-24T00:00:00+00:00",
        "health": "GREEN", "regime": "NEUTRAL", "session_phase": "MORNING",
        "suggestion": "TRADE",
        "stress": {"composite": 0.2, "binding": "equity_dd", "components": []},
        "horizons": {"now": 0.2, "next_15m": 0.2, "next_1h": 0.2, "overnight": 0.2},
        "projection": {"level": 0.2, "trend": 0.0, "forecast_5": 0.2},
    }))
    (tmp_path / "state" / "kaizen_ledger.json").write_text(json.dumps({
        "retrospectives": [{"ts": "2026-04-24T00:00:00+00:00"}],
        "tickets": [
            {"id": "KZN-1", "title": "Fix x", "status": "OPEN",
             "rationale": "r", "parent_retrospective_ts": "2026-04-24T00:00:00+00:00",
             "opened_at": "2026-04-24T00:00:00+00:00", "impact": "small",
             "owner": "op", "shipped_at": None, "drop_reason": ""},
        ],
    }))
    # Force reimport so env vars take effect
    import importlib

    import deploy.scripts.dashboard_api as mod
    importlib.reload(mod)
    return TestClient(mod.app)


class TestDashboardAPI:

    def test_health(self, app_client):
        r = app_client.get("/health")
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "ok"
        assert j["state_dir_exists"]

    def test_heartbeat(self, app_client):
        r = app_client.get("/api/heartbeat")
        assert r.status_code == 200
        assert r.json()["quota_state"] == "OK"

    def test_dashboard(self, app_client):
        r = app_client.get("/api/dashboard")
        assert r.status_code == 200
        assert r.json()["regime"] == "NEUTRAL"

    def test_kaizen_summary(self, app_client):
        r = app_client.get("/api/kaizen")
        assert r.status_code == 200
        j = r.json()
        assert j["retrospectives"] == 1
        assert j["tickets_total"] == 1
        assert j["tickets_open"] == 1

    def test_tasks_list(self, app_client):
        r = app_client.get("/api/tasks")
        assert r.status_code == 200
        assert len(r.json()["tasks"]) == 12

    def test_fire_unknown_task(self, app_client):
        r = app_client.post("/api/tasks/nonsense/fire")
        assert r.status_code == 404

    def test_state_file_safelist(self, app_client):
        r = app_client.get("/api/state/random_file.json")
        assert r.status_code == 403

    def test_state_file_allowed(self, app_client):
        r = app_client.get("/api/state/avengers_heartbeat.json")
        assert r.status_code == 200

    def test_missing_state_file(self, app_client):
        r = app_client.get("/api/state/shadow_ledger.json")
        assert r.status_code == 404
