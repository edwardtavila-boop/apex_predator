from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from eta_engine.scripts import hydrate_canonical_market_data as hydrate
from eta_engine.scripts.hydrate_canonical_market_data import (
    CryptoPlan,
    ImportCandidate,
    _canonical_history_name_from_databento,
    _canonical_history_name_from_main,
    _convert_main_to_history,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_canonical_history_name_from_databento_normalizes_legacy_names() -> None:
    assert _canonical_history_name_from_databento("mnq1_5m.csv") == "MNQ1_5m.csv"
    assert _canonical_history_name_from_databento("nq_1m.csv") == "NQ1_1m.csv"
    assert _canonical_history_name_from_databento("es_5m.csv") == "ES1_5m.csv"
    assert _canonical_history_name_from_databento("vix_yf_d.csv") == "VIX_D.csv"


def test_canonical_history_name_from_main_promotes_root_futures_names() -> None:
    assert _canonical_history_name_from_main("mnq_5m.csv") == "MNQ1_5m.csv"
    assert _canonical_history_name_from_main("mnq_es1_5.csv") == "ES1_5m.csv"
    assert _canonical_history_name_from_main("nq_D.csv") == "NQ1_D.csv"


def test_convert_main_to_history_rewrites_schema(tmp_path: Path) -> None:
    source = tmp_path / "nq_D.csv"
    target = tmp_path / "history" / "NQ1_D.csv"
    with source.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["timestamp_utc", "epoch_s", "open", "high", "low", "close", "volume", "session"],
        )
        writer.writerow(["2026-01-01T00:00:00Z", 1735689600, 100.0, 101.0, 99.0, 100.5, 1000, "ETH"])
        writer.writerow(["2026-01-02T00:00:00Z", 1735776000, 100.5, 102.0, 100.0, 101.5, 1200, "ETH"])

    rows = _convert_main_to_history(source, target)

    assert rows == 2
    assert target.exists()
    with target.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        materialized = list(reader)
    assert reader.fieldnames == ["time", "open", "high", "low", "close", "volume"]
    assert materialized[0]["time"] == "1735689600"
    assert materialized[1]["close"] == "101.5"


def test_import_futures_dry_run_does_not_write_target(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.csv"
    target = tmp_path / "history" / "MNQ1_5m.csv"
    source.write_text("time,open,high,low,close,volume\n1,1,1,1,1,1\n", encoding="utf-8")
    candidate = ImportCandidate(
        source=source,
        target=target,
        source_kind="history",
        note="test",
        row_count=1,
    )

    monkeypatch.setattr(hydrate, "MNQ_HISTORY_ROOT", tmp_path / "unused")
    monkeypatch.setattr(hydrate, "ensure_dir", lambda path: path)
    monkeypatch.setattr(hydrate, "_collect_futures_candidates", lambda: {target: candidate})
    monkeypatch.setattr(hydrate, "_probe_rows", lambda path, source_kind: 0)

    imported, skipped = hydrate._import_futures(dry_run=True)

    assert (imported, skipped) == (0, 1)
    assert not target.exists()


def test_crypto_price_dry_run_does_not_fetch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(hydrate, "CRYPTO_HISTORY_ROOT", tmp_path)
    monkeypatch.setattr(hydrate, "ensure_dir", lambda path: path)
    monkeypatch.setattr(hydrate, "_CRYPTO_BAR_PLAN", (CryptoPlan("BTC", "1h", 1),))

    def fail_fetch(**_: object) -> list[list[float]]:
        raise AssertionError("dry-run must not fetch")

    monkeypatch.setattr(hydrate, "fetch_crypto_bars", fail_fetch)

    written, skipped = hydrate._fetch_crypto_prices(dry_run=True)

    assert (written, skipped) == (0, 1)
