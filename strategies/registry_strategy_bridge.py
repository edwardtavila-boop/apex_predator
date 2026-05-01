"""Bridge: per_bot_registry strategy assignments → policy_router dispatch.

The DEFAULT_ELIGIBILITY in policy_router.py dispatches the 6 legacy SMC/ICT
strategies. The per_bot_registry.py promotes ORB, sage-gated ORB, DRB,
crypto_orb, sage_daily_gated, ensemble_voting, etc. — strategies with
proven +6 to +10 OOS Sharpes. Until now these were NEVER called at runtime.

This module connects the two worlds:
1. Maps registry strategy_kind → StrategyId enum value
2. Builds a dispatch-ready callable (bars, ctx) → StrategySignal for each kind
3. Returns (eligibility_map, registry_map) that RouterAdapter.push_bar can use

Usage (in RouterAdapter.push_bar):
    from eta_engine.strategies.registry_strategy_bridge import build_registry_dispatch
    eligibility, reg = build_registry_dispatch(self.bot_id)
    decision = dispatch(self.asset, bars, ctx, eligibility=eligibility, registry=reg)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eta_engine.strategies.models import Bar, Side, StrategyId, StrategySignal

if TYPE_CHECKING:
    from collections.abc import Callable

    from eta_engine.strategies.eta_policy import StrategyContext
    from eta_engine.strategies.per_bot_registry import StrategyAssignment

_KIND_TO_SID: dict[str, StrategyId] = {
    "orb": StrategyId.REGISTRY_ORB,
    "drb": StrategyId.REGISTRY_DRB,
    "orb_sage_gated": StrategyId.REGISTRY_ORB_SAGE_GATED,
    "sage_consensus": StrategyId.REGISTRY_SAGE_CONSENSUS,
    "crypto_orb": StrategyId.REGISTRY_CRYPTO_ORB,
    "crypto_trend": StrategyId.REGISTRY_CRYPTO_TREND,
    "crypto_regime_trend": StrategyId.REGISTRY_CRYPTO_REGRESSION,
    "sage_daily_gated": StrategyId.REGISTRY_SAGE_DAILY_GATED,
    "ensemble_voting": StrategyId.REGISTRY_ENSEMBLE_VOTING,
    "crypto_macro_confluence": StrategyId.REGISTRY_CRYPTO_MACRO_CONFLUENCE,
    "compression_breakout": StrategyId.REGISTRY_COMPRESSION_BREAKOUT,
    "crypto_meanrev": StrategyId.REGISTRY_CRYPTO_MEANREV,
    "confluence": StrategyId.REGISTRY_CONFLUENCE,
}


def _strategy_id_for(assignment: StrategyAssignment) -> StrategyId | None:
    return _KIND_TO_SID.get(assignment.strategy_kind)


def _build_callable_for_assignment(
    assignment: StrategyAssignment,
) -> Callable[..., StrategySignal] | None:
    kind = assignment.strategy_kind
    extras = dict(assignment.extras)

    if kind == "orb":
        from eta_engine.strategies.orb_strategy import ORBConfig, ORBStrategy

        cfg = extras.get("orb_config", {})
        orb_cfg = ORBConfig(
            range_minutes=cfg.get("range_minutes", 15),
            rr_target=cfg.get("rr_target", 3.0),
            atr_stop_mult=cfg.get("atr_stop_mult", 1.5),
            ema_bias_period=cfg.get("ema_bias_period", 50),
        )
        return _wrap_strategy(ORBStrategy(orb_cfg))

    if kind == "drb":
        from eta_engine.strategies.drb_strategy import DRBConfig, DRBStrategy

        cfg = extras.get("drb_config", {})
        drb_cfg = DRBConfig(
            atr_stop_mult=cfg.get("atr_stop_mult", 2.0),
            rr_target=cfg.get("rr_target", 2.0),
            ema_bias_period=cfg.get("ema_bias_period", 50),
        )
        return _wrap_strategy(DRBStrategy(drb_cfg))

    if kind == "orb_sage_gated":
        from eta_engine.strategies.orb_strategy import ORBConfig
        from eta_engine.strategies.sage_consensus_strategy import SageConsensusConfig
        from eta_engine.strategies.sage_gated_orb_strategy import (
            SageGatedORBConfig,
            SageGatedORBStrategy,
        )

        orb_cfg_raw = extras.get("orb_config", {})
        orb_cfg = ORBConfig(
            range_minutes=orb_cfg_raw.get("range_minutes", 15),
            rr_target=orb_cfg_raw.get("rr_target", 3.0),
            atr_stop_mult=orb_cfg_raw.get("atr_stop_mult", 1.5),
        )
        sage_raw = {
            "min_conviction": float(extras.get("sage_min_conviction", 0.65)),
            "sage_lookback_bars": int(extras.get("sage_lookback_bars", 200)),
        }
        sage_cfg = SageConsensusConfig(**sage_raw)  # type: ignore[arg-type]
        gated_cfg = SageGatedORBConfig(orb=orb_cfg, sage=sage_cfg)
        return _wrap_strategy(SageGatedORBStrategy(gated_cfg))

    if kind == "crypto_orb":
        from eta_engine.strategies.crypto_orb_strategy import CryptoORBConfig
        from eta_engine.strategies.orb_strategy import ORBConfig, ORBStrategy

        cfg = extras.get("crypto_orb_config", {})
        crypto_cfg = CryptoORBConfig(**{  # type: ignore[arg-type]
            k: v for k, v in cfg.items()
            if k in CryptoORBConfig.__dataclass_fields__  # type: ignore[attr-defined]
        })
        return _wrap_strategy(ORBStrategy(crypto_cfg))

    if kind in ("sage_daily_gated", "sage_consensus", "ensemble_voting",
                 "crypto_regime_trend", "crypto_macro_confluence",
                 "compression_breakout", "crypto_trend", "crypto_meanrev",
                 "confluence"):
        return _passthrough

    return None


def _wrap_strategy(
    strategy: object,
) -> Callable[..., StrategySignal]:
    def _evaluate(bars: list[Bar], ctx: StrategyContext) -> StrategySignal:
        if len(bars) < 2:
            return StrategySignal(
                strategy=StrategyId.REGISTRY_ORB,
                side=Side.FLAT,
                rationale_tags=("insufficient_bars",),
            )
        try:
            from eta_engine.backtest.models import BacktestConfig

            current = bars[-1]
            history = bars[:-1]
            hist_bar_data = _to_bar_data_list(history)
            current_bar_data = _to_bar_data(current)
            be_cfg = BacktestConfig(
                start_date=current_bar_data.timestamp,
                end_date=current_bar_data.timestamp,
                symbol=current_bar_data.symbol,
                initial_equity=10000.0,
                risk_per_trade_pct=0.01,
            )
            opened = strategy.maybe_enter(
                current_bar_data,
                hist_bar_data,
                equity=10000.0,
                config=be_cfg,
            )
            if opened is None:
                return StrategySignal(
                    strategy=StrategyId.REGISTRY_ORB,
                    side=Side.FLAT,
                    rationale_tags=("no_signal",),
                )
            side = Side.LONG if opened.side.upper() == "BUY" else Side.SHORT
            return StrategySignal(
                strategy=StrategyId.REGISTRY_ORB,
                side=side,
                entry=float(opened.entry_price),
                stop=float(opened.stop),
                target=float(opened.target),
                confidence=float(getattr(opened, "confluence", 5.0)),
                risk_mult=float(getattr(opened, "leverage", 1.0)),
            )
        except Exception:
            return StrategySignal(
                strategy=StrategyId.REGISTRY_ORB,
                side=Side.FLAT,
                rationale_tags=("bridge_error",),
            )
    return _evaluate


def _to_bar_data(bar: Bar) -> Any:  # noqa: ANN401
    from datetime import UTC, datetime

    from eta_engine.core.data_pipeline import BarData

    ts_raw = bar.ts if isinstance(bar.ts, int) else 0
    try:
        ts_dt = datetime.fromtimestamp(ts_raw / 1000.0, tz=UTC)
    except (ValueError, OSError, OverflowError):
        ts_dt = datetime.now(tz=UTC)

    return BarData(
        timestamp=ts_dt,
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume) if hasattr(bar, "volume") else 0.0,
        symbol="",
    )


def _to_bar_data_list(bars: list[Bar]) -> list[Any]:  # noqa: ANN401
    return [_to_bar_data(b) for b in bars]


def _passthrough(bars: list[Bar], ctx: StrategyContext) -> StrategySignal:
    return StrategySignal(
        strategy=StrategyId.REGISTRY_CONFLUENCE,
        side=Side.FLAT,
        rationale_tags=("bridge_not_yet_wired",),
    )


def build_registry_dispatch(
    bot_id: str,
) -> tuple[dict[str, tuple[StrategyId, ...]], dict[StrategyId, Callable[..., StrategySignal]]] | None:
    """Read per_bot_registry for bot_id, build a dispatch table that routes
    to the registry-assigned strategy instead of legacy SMC/ICT.

    Returns (eligibility_map, registry_map) suitable for policy_router.dispatch(),
    or None if the bot has no registry assignment.
    """
    from eta_engine.strategies.per_bot_registry import get_for_bot, is_bot_active

    if not is_bot_active(bot_id):
        return None

    assignment = get_for_bot(bot_id)
    if assignment is None:
        return None

    sid = _strategy_id_for(assignment)
    if sid is None:
        return None

    callable_fn = _build_callable_for_assignment(assignment)
    if callable_fn is None:
        return None

    eligibility = {assignment.symbol.upper(): (sid,)}
    registry = {sid: callable_fn}
    return eligibility, registry
