"""
EVOLUTIONARY TRADING ALGO  //  scripts.fetch_btc_funding_extended
==================================================================
Extend BTC perpetual-futures funding-rate history via Binance.

The existing BTCFUND_8h.csv has only 96 days. Funding-rate filters
need much more history to be statistically valid. Binance's funding
rate is paid every 8 hours and has been published since 2019, so
~7 years of history is freely available.

Source: Binance Futures public API
    GET https://fapi.binance.com/fapi/v1/fundingRate
        ?symbol=BTCUSDT&startTime=...&limit=1000

Limit per request is 1000. For 7 years × 365 days × 3 fundings/day
= ~7,650 records, paginated by cursor.

Output schema (drops in to data library as BTCFUND/8h):
    time,funding_rate

Usage::

    python -m eta_engine.scripts.fetch_btc_funding_extended
    python -m eta_engine.scripts.fetch_btc_funding_extended --years 5
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


_BASE = "https://fapi.binance.com/fapi/v1/fundingRate"
_USER_AGENT = "eta-engine/fetch_btc_funding_extended"


def _fetch_chunk(symbol: str, start_ms: int, end_ms: int) -> list[dict]:
    url = (
        f"{_BASE}?symbol={symbol}&startTime={start_ms}&endTime={end_ms}&limit=1000"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, list) else []
    except urllib.error.HTTPError as exc:
        body = exc.read()[:200] if hasattr(exc, "read") else b""
        print(f"  HTTP {exc.code}: {body!r}")
        return []
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"  fetch error: {exc!r}")
        return []


def fetch_funding(
    symbol: str = "BTCUSDT",
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Fetch funding-rate history. Returns list of dicts with time + rate."""
    if start is None:
        start = datetime.now(UTC) - timedelta(days=365 * 5)
    if end is None:
        end = datetime.now(UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    all_rows: list[dict] = []
    seen: set[int] = set()
    cursor_start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    # Funding events are 8h apart; 1000 events ≈ 333 days.
    chunk_ms = 333 * 86400 * 1000
    while cursor_start_ms < end_ms:
        chunk_end_ms = min(cursor_start_ms + chunk_ms, end_ms)
        print(
            f"  {symbol} "
            f"{datetime.fromtimestamp(cursor_start_ms/1000, UTC).date()} -> "
            f"{datetime.fromtimestamp(chunk_end_ms/1000, UTC).date()}"
        )
        rows = _fetch_chunk(symbol, cursor_start_ms, chunk_end_ms)
        if not rows:
            cursor_start_ms = chunk_end_ms
            continue
        for r in rows:
            ts = int(r["fundingTime"])
            if ts in seen:
                continue
            seen.add(ts)
            try:
                rate = float(r["fundingRate"])
            except (KeyError, ValueError):
                continue
            all_rows.append({"time": ts // 1000, "funding_rate": rate})
        # Advance: latest ts in chunk + 1
        latest_ts = max(int(r["fundingTime"]) for r in rows)
        cursor_start_ms = latest_ts + 1
        time.sleep(0.20)

    all_rows.sort(key=lambda r: r["time"])
    return all_rows


def write_csv(path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "funding_rate"])
        for r in rows:
            w.writerow([int(r["time"]), r["funding_rate"]])
    return len(rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--out", type=Path,
                   default=Path(r"C:\crypto_data\history\BTCFUND_8h.csv"))
    args = p.parse_args()

    end = datetime.now(UTC)
    start = end - timedelta(days=365 * args.years)
    print(f"[funding] {args.symbol} {start.date()} -> {end.date()}")
    rows = fetch_funding(args.symbol, start, end)
    if not rows:
        print("[funding] zero rows fetched")
        return 2
    n = write_csv(args.out, rows)
    last = rows[-1]
    print(
        f"[funding] wrote {n} rows to {args.out}; "
        f"last={datetime.fromtimestamp(last['time'], UTC).date()} "
        f"rate={last['funding_rate']*100:+.4f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
