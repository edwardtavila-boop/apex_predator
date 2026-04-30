"""
EVOLUTIONARY TRADING ALGO  //  data.tradingview
==============================================
Headless-Chrome capture of TradingView state from a logged-in session.

Pulls four streams without a private API key:

* **Bars**       intercepted from ``wss://prodata.tradingview.com/socket.io``
                 (realtime tick + minute kline frames).
* **Indicators** sampled from the chart's right-hand status row tooltips
                 (DOM scrape, fallback to ``window.TradingView`` chart-internals).
* **Watchlist**  scraped from the right sidebar's symbol list (last + chg%).
* **Alerts**     scraped from ``/alerts/`` page + alert-fired notifications.

The capture daemon (``scripts.run_tradingview_capture``) runs the
``TradingViewClient`` in a long-lived loop, persisting:

* ``var/eta_engine/state/live_data/tradingview/bars/<symbol>/<YYYY-MM-DD>.jsonl.gz``
* ``var/eta_engine/state/live_data/tradingview/indicators.jsonl``
* ``var/eta_engine/state/live_data/tradingview/watchlist.json``
* ``var/eta_engine/state/live_data/tradingview/alerts.jsonl``

Auth state (cookies + localStorage) lives under
``var/eta_engine/state/tradingview_auth.json``. Operators run
``scripts.tradingview_auth_refresh`` locally (a real Chrome window pops up
for the manual login), then ``rsync`` the resulting auth-state file to the
VPS. The VPS-side capture daemon is fully headless.

Playwright is an *optional* dependency: the package is importable even
when ``playwright`` is missing -- only ``TradingViewClient.run()`` needs
the runtime.
"""

from eta_engine.data.tradingview.auth import (
    AuthState,
    AuthStateError,
    load_auth_state,
    save_auth_state,
)
from eta_engine.data.tradingview.client import (
    TradingViewClient,
    TradingViewClientError,
    TradingViewUnavailable,
)
from eta_engine.data.tradingview.journal import (
    AlertEntry,
    BarEntry,
    IndicatorEntry,
    TradingViewJournal,
    WatchlistSnapshot,
)
from eta_engine.data.tradingview.parsers import (
    parse_alert_row,
    parse_indicator_tooltip,
    parse_quote_frame,
    parse_watchlist_row,
)

__all__ = [
    "AlertEntry",
    "AuthState",
    "AuthStateError",
    "BarEntry",
    "IndicatorEntry",
    "TradingViewClient",
    "TradingViewClientError",
    "TradingViewJournal",
    "TradingViewUnavailable",
    "WatchlistSnapshot",
    "load_auth_state",
    "parse_alert_row",
    "parse_indicator_tooltip",
    "parse_quote_frame",
    "parse_watchlist_row",
    "save_auth_state",
]
