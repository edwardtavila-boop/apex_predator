def _precompute_shared_features(ctx: MarketContext) -> None:
    """Eagerly compute shared features into the per-context cache.

    Every school that calls ``get_or_compute`` for these keys gets a
    cache hit instead of recomputing. This is a pure optimization --
    skipping it has zero behavioral impact.
    """
    from eta_engine.brain.jarvis_v3.sage.feature_cache import get_or_compute
    n = ctx.n_bars
    if n < 10:
        return
    closes = ctx.closes()
    highs = ctx.highs()
    lows = ctx.lows()
    volumes = ctx.volumes()
    # EMAs (used by trend_following, red_team, and possibly others)
    get_or_compute(ctx, "ema_20", lambda: _ema(closes, 20))
    get_or_compute(ctx, "ema_50", lambda: _ema(closes, 50))
    # Volume averages (used by wyckoff, vpa, red_team)
    get_or_compute(ctx, "avg_vol_20", lambda: sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0.0)
    # Pivots (used by support_resistance, smc_ict)
    get_or_compute(ctx, "pivot_highs", lambda: _find_pivots(highs, kind="high"))
    get_or_compute(ctx, "pivot_lows", lambda: _find_pivots(lows, kind="low"))
    # Range edges (used by wyckoff)
    get_or_compute(ctx, "range_high_20", lambda: max(highs[-21:-1]) if len(highs) >= 21 else 0.0)
    get_or_compute(ctx, "range_low_20", lambda: min(lows[-21:-1]) if len(lows) >= 21 else 0.0)


def _find_pivots(values: list[float], lookback: int = 3, *, kind: str = "high") -> list[tuple[int, float]]:
    """Inlined from support_resistance to avoid circular import."""
    if kind not in ("high", "low"):
        raise ValueError("kind must be 'high' or 'low'")
    out: list[tuple[int, float]] = []
    for i in range(lookback, len(values) - lookback):
        window = values[i - lookback : i + lookback + 1]
        if kind == "high" and values[i] == max(window) or kind == "low" and values[i] == min(window):
            out.append((i, values[i]))
    return out


def _ema(values: list[float], period: int) -> list[float]:
    """Inlined EMA from trend_following to avoid circular import."""
    if not values or period < 1:
        return []
    alpha = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out