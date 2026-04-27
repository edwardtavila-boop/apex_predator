"""
EVOLUTIONARY TRADING ALGO  //  strategies.per_bot_registry
===========================================================
Per-bot strategy assignments — the canonical answer to "which
strategy should this bot run as its baseline?"

Why this exists
---------------
What moves the price differs across instruments:

  * **MNQ / NQ futures**: macro events, ES correlation, RTH structure,
    EoD rebalance, regime (trending vs choppy)
  * **BTC perps**: funding rate, on-chain activity (whale transfers,
    exchange netflow), Asian session timing, sentiment
  * **ETH / XRP / SOL perps**: same as BTC + token-specific
    catalysts (upgrades, ETF flows for ETH, regulation)
  * **Long-haul (daily / weekly)**: trend persistence, weekly options
    gamma, macro regime

Until now every bot in ``bots/`` shared one FeaturePipeline.default()
and one global scorer. That's wrong: a strategy that works on
choppy MNQ 5m will not work on BTC perps where funding is the
dominant signal.

This module is the registry that says, per bot:

  * which dataset (symbol + timeframe) to evaluate against
  * which scorer to use (global / MNQ-tuned / future BTC-tuned)
  * which regimes to block
  * what threshold to clear
  * the baseline metrics the strategy was promoted at, if any

The registry is **read-only** — every assignment is a frozen
dataclass — so no caller can mutate state at runtime. Updating a
bot's assignment is a code change reviewed via PR, not a
configuration drift.

Adoption
--------
* ``research_grid`` (``scripts.run_research_grid``) reads from this
  to run every bot's assigned strategy in one sweep.
* ``drift_check_all`` reads baselines from here when
  ``strategy_baselines.json`` doesn't have an entry for a bot.
* New bots get added in ``ASSIGNMENTS`` below and immediately get
  smoke-tested in the next research-grid run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eta_engine.obs.drift_monitor import BaselineSnapshot


@dataclass(frozen=True)
class StrategyAssignment:
    """Canonical strategy-for-this-bot record."""

    bot_id: str  # e.g. "mnq_futures", "btc_perp"
    strategy_id: str  # e.g. "mnq_v3_regime_gated"

    # Data binding
    symbol: str
    timeframe: str

    # Scoring
    scorer_name: str  # "global" or "mnq" (future: "btc", "long_haul")
    confluence_threshold: float

    # Regime gate
    block_regimes: frozenset[str]

    # Walk-forward / promotion config
    window_days: int
    step_days: int
    min_trades_per_window: int

    # Why this combination — short rationale, not a docstring novel
    rationale: str

    # Promotion-time baseline (may be None if not yet promoted)
    baseline: "BaselineSnapshot | None" = None

    # Free-form extras (e.g. EoD-flatten on/off, leverage caps).
    # Reserved for future engine knobs without breaking serialisation.
    extras: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-bot assignments
# ---------------------------------------------------------------------------
# Each bot here gets the best-known strategy for its instrument,
# based on the regime-gate findings and data-availability scan from
# 2026-04-27. These are *baselines to improve upon*, not finalised
# production picks.

_BASE_BLOCK = frozenset({"trending_up", "trending_down"})


ASSIGNMENTS: tuple[StrategyAssignment, ...] = (
    # MNQ futures — micro E-mini Nasdaq
    StrategyAssignment(
        bot_id="mnq_futures",
        strategy_id="mnq_v3_regime_gated",
        symbol="MNQ1",
        timeframe="4h",
        scorer_name="mnq",
        confluence_threshold=5.0,
        block_regimes=_BASE_BLOCK,
        window_days=180,
        step_days=60,
        min_trades_per_window=10,
        rationale=(
            "MNQ price moves are dominated by ES correlation + RTH "
            "structure + macro events. The MNQ-tuned scorer drops "
            "the crypto-only features (funding/onchain/sentiment) "
            "that were artificially inflating composite scores. The "
            "regime gate blocks trending bars where the strategy "
            "(mean-reversion) bleeds — Window 0 deep-dive on 5m "
            "showed +6R in choppy regimes, -2.5R in trending_up. "
            "4h timeframe gave the best DSR pass fraction (45%) in "
            "the 2026-04-27 research grid."
        ),
    ),
    # NQ futures — full E-mini Nasdaq, longer-haul lens
    StrategyAssignment(
        bot_id="nq_futures",
        strategy_id="nq_daily_regime_gated",
        symbol="NQ1",
        timeframe="D",
        scorer_name="mnq",
        confluence_threshold=5.0,
        block_regimes=_BASE_BLOCK,
        window_days=365,
        step_days=180,
        min_trades_per_window=10,
        rationale=(
            "NQ daily is the only configuration that produced "
            "POSITIVE aggregate OOS Sharpe (+0.157) across a 27-year "
            "history (1999-2026). Trade frequency is low (most "
            "windows have 0-3 trades) so promotion bar is high — "
            "this is a bias-test more than an active-trading config. "
            "Use as a sanity baseline; a real edge claim needs a "
            "regime+macro feature set that fires more often."
        ),
    ),
    # BTC hybrid — futures + perp blended bot
    StrategyAssignment(
        bot_id="btc_hybrid",
        strategy_id="btc_global_funding_skew",
        symbol="MNQ1",  # placeholder until we have BTC bars in the library
        timeframe="1h",
        scorer_name="global",  # use global until a BTC-tuned scorer exists
        confluence_threshold=7.0,
        block_regimes=frozenset(),  # no gate — funding/onchain ARE the signal
        window_days=90,
        step_days=30,
        min_trades_per_window=10,
        rationale=(
            "BTC perps are funding/on-chain dominated, not "
            "trend-bias dominated. The global scorer with all 5 "
            "features matters here — funding_skew (weight 2.0) and "
            "onchain_delta (weight 1.5) are real signals on crypto. "
            "Regime gate disabled because trending regimes ARE often "
            "the funding-arb opportunity (e.g. extreme positive "
            "funding in a trending-up move). Symbol/timeframe is a "
            "placeholder — wire to actual BTC bars once they're in "
            "the data library; until then this assignment runs "
            "against MNQ1 1h purely so the harness can exercise the "
            "global scorer pathway."
        ),
    ),
    # ETH perp — same family as BTC but with smart-contract catalysts
    StrategyAssignment(
        bot_id="eth_perp",
        strategy_id="eth_global_default",
        symbol="MNQ1",  # placeholder
        timeframe="1h",
        scorer_name="global",
        confluence_threshold=7.0,
        block_regimes=frozenset(),
        window_days=90,
        step_days=30,
        min_trades_per_window=10,
        rationale=(
            "ETH shares price drivers with BTC (funding, on-chain) "
            "but adds smart-contract / staking catalysts that aren't "
            "in our feature set yet. Until ETH-specific features "
            "(staking yield delta, gas fee regime, gas-price "
            "trending) are wired, ETH inherits the BTC global-scorer "
            "approach. Symbol placeholder same as btc_hybrid."
        ),
    ),
    # XRP perp — speculative, news-driven, low TVL
    StrategyAssignment(
        bot_id="xrp_perp",
        strategy_id="xrp_skip_baseline",
        symbol="MNQ1",  # placeholder
        timeframe="1h",
        scorer_name="global",
        confluence_threshold=8.0,  # higher bar — XRP is news-driven, fewer real signals
        block_regimes=frozenset(),
        window_days=90,
        step_days=30,
        min_trades_per_window=10,
        rationale=(
            "XRP is news/regulation-driven more than feature-driven. "
            "No baseline strategy exists; keep the threshold high "
            "(8.0 vs 7.0) so the bot fires only when ALL features "
            "agree. Better path: a news-event gate that pauses XRP "
            "around SEC headlines. Until that exists, XRP is "
            "effectively muted. Placeholder symbol/timeframe."
        ),
    ),
    # SOL perp — high-beta crypto, behaves like BTC * 2-3x
    StrategyAssignment(
        bot_id="sol_perp",
        strategy_id="sol_global_default",
        symbol="MNQ1",  # placeholder
        timeframe="1h",
        scorer_name="global",
        confluence_threshold=7.5,  # slight bump for higher noise
        block_regimes=frozenset(),
        window_days=90,
        step_days=30,
        min_trades_per_window=10,
        rationale=(
            "SOL behaves as a BTC-amplified beta. Same global "
            "scorer; threshold raised from 7.0 to 7.5 to dampen "
            "false fires from SOL's higher noise floor. Real upgrade: "
            "an explicit BTC-correlation feature so SOL only fires "
            "when BTC is also confirming. Placeholder symbol/timeframe."
        ),
    ),
    # Crypto seed — long-only DCA-style accumulator
    StrategyAssignment(
        bot_id="crypto_seed",
        strategy_id="crypto_seed_dca",
        symbol="MNQ1",  # placeholder
        timeframe="D",
        scorer_name="global",
        confluence_threshold=4.0,  # very low — DCA fires often by design
        block_regimes=frozenset(),
        window_days=365,
        step_days=180,
        min_trades_per_window=5,
        rationale=(
            "DCA accumulator — the strategy is to buy steadily at "
            "any non-distressed score. Threshold 4.0 (very low) "
            "ensures regular fires. Daily timeframe matches the "
            "accumulation cadence. Distinct from all other bots "
            "because the goal is *exposure*, not edge."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Lookup API
# ---------------------------------------------------------------------------


def get_for_bot(bot_id: str) -> StrategyAssignment | None:
    """Return the assignment for ``bot_id`` or None."""
    for a in ASSIGNMENTS:
        if a.bot_id == bot_id:
            return a
    return None


def all_assignments() -> list[StrategyAssignment]:
    """Stable-ordered list of every registered assignment."""
    return list(ASSIGNMENTS)


def bots() -> list[str]:
    """Stable-ordered list of every registered bot_id."""
    return [a.bot_id for a in ASSIGNMENTS]


def summary_markdown() -> str:
    """One-table dump of the registry, suitable for status pages."""
    lines = [
        "# Per-bot strategy assignments",
        "",
        "| Bot | Strategy | Sym/TF | Scorer | Thr | Gate | Win/Step (d) | Min trades |",
        "|---|---|---|---|---:|---|---|---:|",
    ]
    for a in ASSIGNMENTS:
        gate_str = "/".join(sorted(a.block_regimes)) if a.block_regimes else "—"
        lines.append(
            f"| {a.bot_id} | {a.strategy_id} | {a.symbol}/{a.timeframe} | "
            f"{a.scorer_name} | {a.confluence_threshold:.1f} | {gate_str} | "
            f"{a.window_days}/{a.step_days} | {a.min_trades_per_window} |"
        )
    return "\n".join(lines)
