from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_panel_refresh_defers_when_browser_tab_is_hidden() -> None:
    panels = (ROOT / "deploy" / "status_page" / "js" / "panels.js").read_text(encoding="utf-8")

    assert "function shouldDeferHiddenRefresh" in panels
    assert "document.hidden" in panels
    assert "if (shouldDeferHiddenRefresh(this)) return;" in panels
