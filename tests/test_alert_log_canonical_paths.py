from __future__ import annotations

from typing import TYPE_CHECKING

from eta_engine.scripts import _backup_state, _kill_switch_drift, _trade_journal_reconcile, workspace_roots

if TYPE_CHECKING:
    from pathlib import Path


def test_default_alerts_log_prefers_canonical_runtime_path(monkeypatch, tmp_path: Path) -> None:
    canonical = tmp_path / "logs" / "eta_engine" / "alerts_log.jsonl"
    legacy = tmp_path / "eta_engine" / "docs" / "alerts_log.jsonl"
    canonical.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    canonical.write_text('{"event":"runtime_start"}\n', encoding="utf-8")
    legacy.write_text('{"event":"legacy"}\n', encoding="utf-8")

    monkeypatch.setattr(workspace_roots, "ETA_RUNTIME_ALERTS_LOG_PATH", canonical)
    monkeypatch.setattr(workspace_roots, "ETA_LEGACY_DOCS_ALERTS_LOG_PATH", legacy)

    assert workspace_roots.default_alerts_log_path() == canonical


def test_default_alerts_log_falls_back_to_legacy_snapshot(monkeypatch, tmp_path: Path) -> None:
    canonical = tmp_path / "logs" / "eta_engine" / "missing.jsonl"
    legacy = tmp_path / "eta_engine" / "docs" / "alerts_log.jsonl"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"event":"legacy"}\n', encoding="utf-8")

    monkeypatch.setattr(workspace_roots, "ETA_RUNTIME_ALERTS_LOG_PATH", canonical)
    monkeypatch.setattr(workspace_roots, "ETA_LEGACY_DOCS_ALERTS_LOG_PATH", legacy)

    assert workspace_roots.default_alerts_log_path() == legacy


def test_alert_readers_default_to_canonical_runtime_log() -> None:
    assert _kill_switch_drift.DEFAULT_LOG == workspace_roots.ETA_RUNTIME_ALERTS_LOG_PATH
    assert _trade_journal_reconcile.DEFAULT_ALERTS == workspace_roots.ETA_RUNTIME_ALERTS_LOG_PATH


def test_default_runtime_log_falls_back_to_legacy_snapshot(monkeypatch, tmp_path: Path) -> None:
    canonical = tmp_path / "logs" / "eta_engine" / "missing_runtime.jsonl"
    legacy = tmp_path / "eta_engine" / "docs" / "runtime_log.jsonl"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"kind":"tick"}\n', encoding="utf-8")

    monkeypatch.setattr(workspace_roots, "ETA_RUNTIME_LOG_PATH", canonical)
    monkeypatch.setattr(workspace_roots, "ETA_LEGACY_DOCS_RUNTIME_LOG_PATH", legacy)

    assert workspace_roots.default_runtime_log_path() == legacy


def test_backup_state_tracks_resolved_alert_log_first(monkeypatch, tmp_path: Path) -> None:
    canonical = tmp_path / "logs" / "eta_engine" / "alerts_log.jsonl"
    canonical.parent.mkdir(parents=True)
    canonical.write_text('{"event":"runtime_start"}\n', encoding="utf-8")

    monkeypatch.setattr(workspace_roots, "ETA_RUNTIME_ALERTS_LOG_PATH", canonical)
    monkeypatch.setattr(workspace_roots, "ETA_LEGACY_DOCS_ALERTS_LOG_PATH", tmp_path / "legacy.jsonl")

    assert _backup_state.critical_files()[0] == canonical
