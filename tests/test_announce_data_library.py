from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from eta_engine.data.audit import BotAudit
from eta_engine.data.library import DataLibrary
from eta_engine.data.requirements import DataRequirement
from eta_engine.scripts import announce_data_library
from eta_engine.scripts.workspace_roots import (
    ETA_DATA_INVENTORY_SNAPSHOT_PATH,
    ETA_RUNTIME_STATE_DIR,
)


def _write_history_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        writer.writerow([1_735_689_600, 100.0, 101.0, 99.0, 100.5, 10_000.0])
        writer.writerow([1_735_693_200, 100.5, 101.5, 100.0, 101.0, 12_000.0])


def test_default_snapshot_path_is_canonical_runtime_state() -> None:
    assert announce_data_library._DEFAULT_SNAPSHOT == ETA_DATA_INVENTORY_SNAPSHOT_PATH
    assert announce_data_library._DEFAULT_SNAPSHOT.parent == ETA_RUNTIME_STATE_DIR
    assert announce_data_library._DEFAULT_SNAPSHOT.name == "data_inventory_latest.json"


def test_build_inventory_snapshot_includes_dataset_and_bot_coverage(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    _write_history_csv(history / "BTC_1h.csv")
    lib = DataLibrary(roots=[history])
    dataset = lib.get(symbol="BTC", timeframe="1h")
    assert dataset is not None

    available_req = DataRequirement("bars", "BTC", "1h")
    missing_req = DataRequirement("funding", "BTC", "8h")
    audits = [
        BotAudit(
            bot_id="btc_test",
            available=[(available_req, dataset)],
            missing_critical=[missing_req],
            sources_hint=("scripts/fetch_funding_rates.py",),
        ),
        BotAudit(bot_id="xrp_perp", deactivated=True),
    ]

    payload = announce_data_library.build_inventory_snapshot(
        lib,
        audits,
        generated_at=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )

    assert payload["schema_version"] == 1
    assert payload["generated_at"] == "2026-04-29T12:00:00+00:00"
    assert payload["dataset_count"] == 1
    assert payload["datasets"][0]["symbol"] == "BTC"
    assert payload["bot_coverage"]["total"] == 2
    assert payload["bot_coverage"]["blocked_count"] == 1
    assert payload["bot_coverage"]["deactivated_count"] == 1
    assert payload["bot_coverage"]["deactivated"] == ["xrp_perp"]
    assert payload["bot_coverage"]["blocked"]["btc_test"]["missing_critical"][0] == {
        "kind": "funding",
        "symbol": "BTC",
        "timeframe": "8h",
        "critical": True,
        "note": "",
    }
    assert payload["bot_coverage"]["items"][0]["available"][0]["dataset"]["key"] == "BTC/1h/history"


def test_write_inventory_snapshot_creates_parent_and_pretty_json(tmp_path: Path) -> None:
    target = tmp_path / "var" / "eta_engine" / "state" / "data_inventory_latest.json"
    payload = {
        "schema_version": 1,
        "generated_at": "2026-04-29T12:00:00+00:00",
        "datasets": [],
        "bot_coverage": {"blocked_count": 0},
    }

    written = announce_data_library.write_inventory_snapshot(target, payload)

    assert written == target
    assert target.exists()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == payload
    assert target.read_text(encoding="utf-8").endswith("\n")
