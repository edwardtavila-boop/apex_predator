from __future__ import annotations

from types import SimpleNamespace

from eta_engine.scripts import paper_live_launch_check as mod


def test_deactivated_bot_is_ready_even_when_data_is_absent(monkeypatch) -> None:
    assignment = SimpleNamespace(
        bot_id="xrp_perp",
        strategy_id="xrp_DEACTIVATED",
        strategy_kind="confluence",
        symbol="MNQ1",
        timeframe="1h",
        extras={"deactivated": True},
    )
    monkeypatch.setattr(mod, "_check_data_available", lambda *_: False)
    monkeypatch.setattr(mod, "_check_bot_dir_exists", lambda *_: False)
    monkeypatch.setattr(mod, "_check_baseline_persisted", lambda *_: False)

    result = mod._audit_bot(assignment)

    assert result["status"] == "READY"
    assert result["promotion_status"] == "deactivated"
    assert result["issues"] == []
    assert result["warnings"] == []
