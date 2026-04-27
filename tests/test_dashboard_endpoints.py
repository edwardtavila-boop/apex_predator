# eta_engine/tests/test_dashboard_endpoints.py
"""General dashboard endpoint tests."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from eta_engine.deploy.scripts.dashboard_api import app
    return TestClient(app)


def test_serve_theme_css(client, tmp_path, monkeypatch) -> None:
    """The dashboard serves theme.css from the resolved status_page parent."""
    from eta_engine.deploy.scripts import dashboard_api
    monkeypatch.setattr(dashboard_api, "_STATUS_PAGE", tmp_path / "index.html")
    css_path = tmp_path / "theme.css"
    css_path.write_text("/* test css */", encoding="utf-8")

    r = client.get("/theme.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]
    assert "/* test css */" in r.text


def test_serve_js_module(client, tmp_path, monkeypatch) -> None:
    """The dashboard serves js modules from the resolved status_page/js dir."""
    from eta_engine.deploy.scripts import dashboard_api
    monkeypatch.setattr(dashboard_api, "_STATUS_PAGE", tmp_path / "index.html")
    js_dir = tmp_path / "js"
    js_dir.mkdir(parents=True, exist_ok=True)
    (js_dir / "auth.js").write_text("export const x = 1;", encoding="utf-8")

    r = client.get("/js/auth.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"].lower()
    assert "export const x" in r.text


def test_js_path_traversal_blocked(client, tmp_path, monkeypatch) -> None:
    """Reject path-traversal attempts."""
    from eta_engine.deploy.scripts import dashboard_api
    monkeypatch.setattr(dashboard_api, "_STATUS_PAGE", tmp_path / "index.html")
    r = client.get("/js/../dashboard_api.py")
    # FastAPI normalizes the path first, so this should 404
    assert r.status_code in (400, 404)


def test_js_module_rejects_dot_prefix(tmp_path, monkeypatch) -> None:
    """Directly exercise the 400-branch filename validator."""
    from eta_engine.deploy.scripts import dashboard_api
    monkeypatch.setattr(dashboard_api, "_STATUS_PAGE", tmp_path / "index.html")
    with pytest.raises(HTTPException) as exc:
        dashboard_api.serve_js_module(".env")
    assert exc.value.status_code == 400
