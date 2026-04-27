# eta_engine/tests/test_dashboard_endpoints.py
"""General dashboard endpoint tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from eta_engine.deploy.scripts.dashboard_api import app
    return TestClient(app)


def test_serve_theme_css(client) -> None:
    """The dashboard serves theme.css from deploy/status_page/."""
    # Resolve the on-disk path the dashboard uses for static assets
    from eta_engine.deploy.scripts.dashboard_api import _STATUS_PAGE
    css_path = _STATUS_PAGE.parent / "theme.css"
    css_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.write_text("/* test css */", encoding="utf-8")

    r = client.get("/theme.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]
    assert "/* test css */" in r.text


def test_serve_js_module(client) -> None:
    from eta_engine.deploy.scripts.dashboard_api import _STATUS_PAGE
    js_dir = _STATUS_PAGE.parent / "js"
    js_dir.mkdir(parents=True, exist_ok=True)
    (js_dir / "auth.js").write_text("export const x = 1;", encoding="utf-8")

    r = client.get("/js/auth.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"].lower()
    assert "export const x" in r.text


def test_js_path_traversal_blocked(client) -> None:
    """Reject path-traversal attempts."""
    r = client.get("/js/../dashboard_api.py")
    # FastAPI normalizes the path first, so this should 404
    assert r.status_code in (400, 404)
