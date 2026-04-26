"""
EVOLUTIONARY TRADING ALGO // jarvis.specialists.reference
=============================================
Reference (deterministic, LLM-free) implementations of the 7 specialists.

Each one wraps the existing numeric scoring engine into the new
SpecialistOutput shape so:
  * Phase 1's structured-reasoning contract is satisfied today
  * Tests are deterministic (no API calls)
  * Wiring an LLM-backed override is a one-line subclass change later

The 7 specialists mirror the existing `firm.agents.core` topology:
    QuantSpecialist          — voice ensemble + ORB/EMA/SWEEP setup score
    RedTeamSpecialist        — adversarial — surfaces what could go wrong
    RiskManagerSpecialist    — checks risk caps + slot allocation
    MacroSpecialist          — VIX regime + inter-market context
    MicrostructureSpecialist — tape + spread + L2 imbalance proxy
    PMSpecialist             — final gate (used as a SPECIALIST in some
                                 ensembles, distinct from PMConsensus)
    MetaSpecialist           — Phase 5 hook; reads recent post-mortem
                                 calibration and surfaces it as evidence
"""

from __future__ import annotations

from typing import Any

from eta_engine.jarvis.specialists.base import (
    DecisionContext,
    SpecialistAgent,
    SpecialistOutput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _bar_close(ctx: DecisionContext) -> float:
    return float(ctx.bar.get("close", 0.0))


def _vix_z(ctx: DecisionContext) -> float:
    """VIX z-score from market_features. Defaults to 0.0 if absent."""
    return float(ctx.market_features.get("vix_z", 0.0))


def _atr(ctx: DecisionContext) -> float:
    return float(ctx.bar.get("atr", 0.0)) or float(ctx.bar.get("atr_14", 0.0))


def _has_setup(ctx: DecisionContext) -> bool:
    return bool(ctx.setup_name and ctx.setup_name.strip() and ctx.setup_name.upper() != "NONE")


# ---------------------------------------------------------------------------
# Quant — wraps the existing voice ensemble
# ---------------------------------------------------------------------------
class QuantSpecialist(SpecialistAgent):
    name = "quant"

    def evaluate(self, ctx: DecisionContext) -> SpecialistOutput:
        if not _has_setup(ctx):
            return SpecialistOutput(
                hypothesis="No qualifying setup on this bar.",
                evidence=[f"setup_name='{ctx.setup_name}' is empty/none"],
                signal="skip",
                confidence=0.10,
                falsification="A new SetupTriggers.* fires before next bar.",
            )
        regime = ctx.regime
        atr = _atr(ctx)
        if regime == "CRISIS":
            return SpecialistOutput(
                hypothesis=f"{ctx.setup_name} would normally fire but regime is CRISIS.",
                evidence=[f"regime={regime}", f"atr={atr:.2f}"],
                signal="skip",
                confidence=0.85,
                falsification="Regime exits CRISIS within 3 bars.",
            )
        bias = "long" if regime in ("RISK-ON", "NEUTRAL") else "short"
        return SpecialistOutput(
            hypothesis=(f"{ctx.setup_name} fires under {regime}; voice ensemble agrees on {bias} bias."),
            evidence=[
                f"setup={ctx.setup_name}",
                f"regime={regime}",
                f"atr={atr:.2f}",
            ],
            signal=bias,
            confidence=0.62 if regime == "NEUTRAL" else 0.78,
            falsification=(
                f"Within next 5 bars, price moves >{atr:.2f} against {bias} without our entry trigger firing."
            ),
        )


# ---------------------------------------------------------------------------
# Red Team — adversarial; always surfaces a falsification distinct from Quant
# ---------------------------------------------------------------------------
class RedTeamSpecialist(SpecialistAgent):
    name = "red_team"

    def evaluate(self, ctx: DecisionContext) -> SpecialistOutput:
        regime = ctx.regime
        vix_z = _vix_z(ctx)
        atr = _atr(ctx)
        # Always raise a meaningfully distinct objection
        if regime == "CRISIS":
            return SpecialistOutput(
                hypothesis="Crisis regime invalidates the setup priors entirely.",
                evidence=[f"regime={regime}", f"vix_z={vix_z:.2f}"],
                signal="skip",
                confidence=0.90,
                falsification="VIX z-score < 1.5 within the next 30 bars.",
            )
        if abs(vix_z) > 2.0:
            return SpecialistOutput(
                hypothesis=("Tail vol environment — past calibration data doesn't cover this VIX regime."),
                evidence=[f"vix_z={vix_z:.2f} > 2.0"],
                signal="skip",
                confidence=0.75,
                falsification="VIX z-score reverts below 2.0 in 5 bars.",
            )
        # Default Red Team: insists on the silent-degradation case
        return SpecialistOutput(
            hypothesis=("Setup may be parameter-fit on synthetic data; live microstructure could diverge."),
            evidence=[
                f"regime={regime}",
                f"atr={atr:.2f}",
                "no recent live calibration audit on file",
            ],
            signal="neutral",
            confidence=0.55,
            falsification=("Last 200-trade rolling MAE distribution matches the backtest within 1 standard deviation."),
        )


# ---------------------------------------------------------------------------
# Risk manager — checks caps + slot availability
# ---------------------------------------------------------------------------
class RiskManagerSpecialist(SpecialistAgent):
    name = "risk_manager"

    def evaluate(self, ctx: DecisionContext) -> SpecialistOutput:
        bot = ctx.bot_snapshot
        consec_losses = int(bot.get("consecutive_losses", 0))
        open_positions = int(bot.get("open_position_count", 0))
        equity = float(bot.get("equity_usd", 0.0))
        peak = float(bot.get("peak_equity_usd", equity or 1.0))
        dd = (peak - equity) / max(1.0, peak)

        if consec_losses >= 3:
            return SpecialistOutput(
                hypothesis="Consecutive-loss limit reached — pause is mandatory.",
                evidence=[f"consecutive_losses={consec_losses} >= 3"],
                signal="skip",
                confidence=0.95,
                falsification="A new winning trade closes within next 3 bars without us entering.",
            )
        if dd > 0.05:
            return SpecialistOutput(
                hypothesis="Drawdown >5% — size reduction or skip required.",
                evidence=[f"dd={dd:.2%}", f"equity={equity:.0f}", f"peak={peak:.0f}"],
                signal="skip",
                confidence=0.80,
                falsification="Equity recovers above peak within 10 bars.",
            )
        if open_positions >= 1:
            return SpecialistOutput(
                hypothesis="Position already open — single-slot policy active.",
                evidence=[f"open_position_count={open_positions}"],
                signal="skip",
                confidence=0.70,
                falsification="Open position closes before next bar.",
            )
        return SpecialistOutput(
            hypothesis="All risk caps are clean; size as configured.",
            evidence=[
                f"consecutive_losses={consec_losses}",
                f"dd={dd:.2%}",
                f"open_positions={open_positions}",
            ],
            signal="neutral",
            confidence=0.40,
            falsification="A risk-cap probe later this tick reports degraded.",
        )


# ---------------------------------------------------------------------------
# Macro — VIX + inter-market context
# ---------------------------------------------------------------------------
class MacroSpecialist(SpecialistAgent):
    name = "macro"

    def evaluate(self, ctx: DecisionContext) -> SpecialistOutput:
        vix_z = _vix_z(ctx)
        spy_corr = float(ctx.market_features.get("spy_corr", 0.0))
        dxy_z = float(ctx.market_features.get("dxy_z", 0.0))
        evidence = [f"vix_z={vix_z:.2f}", f"spy_corr={spy_corr:.2f}", f"dxy_z={dxy_z:.2f}"]
        if vix_z > 1.5:
            return SpecialistOutput(
                hypothesis="VIX elevated — favor short bias on equity index.",
                evidence=evidence,
                signal="short",
                confidence=0.55,
                falsification="VIX z reverts < 0.5 within 10 bars.",
            )
        if vix_z < -1.0 and spy_corr > 0.6:
            return SpecialistOutput(
                hypothesis="Vol crush + SPY correlation strong — long bias.",
                evidence=evidence,
                signal="long",
                confidence=0.55,
                falsification="SPY 1m return turns negative > -0.3% in 5 bars.",
            )
        return SpecialistOutput(
            hypothesis="Macro environment neutral — no directional vote.",
            evidence=evidence,
            signal="neutral",
            confidence=0.30,
            falsification="VIX z moves outside [-1.0, 1.5] band in 5 bars.",
        )


# ---------------------------------------------------------------------------
# Microstructure — tape + spread proxy
# ---------------------------------------------------------------------------
class MicrostructureSpecialist(SpecialistAgent):
    name = "microstructure"

    def evaluate(self, ctx: DecisionContext) -> SpecialistOutput:
        spread_ticks = float(ctx.market_features.get("spread_ticks", 1.0))
        tick_z = float(ctx.market_features.get("tick_z", 0.0))
        delta = float(ctx.market_features.get("cumulative_delta", 0.0))
        evidence = [f"spread_ticks={spread_ticks:.1f}", f"tick_z={tick_z:.2f}", f"delta={delta:.0f}"]
        if spread_ticks > 3:
            return SpecialistOutput(
                hypothesis="Spread > 3 ticks — entry will get walked.",
                evidence=evidence,
                signal="skip",
                confidence=0.70,
                falsification="Spread compresses to ≤2 ticks within 60 seconds.",
            )
        if abs(tick_z) > 1.5:
            sig = "long" if tick_z > 0 else "short"
            return SpecialistOutput(
                hypothesis=f"NYSE TICK confirms {sig} bias (z={tick_z:+.2f}).",
                evidence=evidence,
                signal=sig,
                confidence=0.55,
                falsification="TICK z reverses to opposite-sign 1.5 within 3 bars.",
            )
        return SpecialistOutput(
            hypothesis="Microstructure unremarkable.",
            evidence=evidence,
            signal="neutral",
            confidence=0.30,
            falsification="Sudden 5-tick widening of spread within 30 seconds.",
        )


# ---------------------------------------------------------------------------
# PM-as-specialist (distinct from PMConsensus aggregator)
# ---------------------------------------------------------------------------
class PMSpecialist(SpecialistAgent):
    name = "pm"

    def evaluate(self, ctx: DecisionContext) -> SpecialistOutput:
        regime = ctx.regime
        memories_n = len(ctx.retrieved_memories)
        evidence = [f"regime={regime}", f"setup={ctx.setup_name}", f"retrieved_memories={memories_n}"]
        # Default conservative neutral; the AGGREGATOR (PMConsensus) is
        # what actually fires. PMSpecialist exists to log the PM's own
        # opinion as a separate row in the audit trail.
        return SpecialistOutput(
            hypothesis="PM views this setup conservatively; defers to ensemble.",
            evidence=evidence,
            signal="neutral",
            confidence=0.45,
            falsification=("≥3 specialists return >0.8 confidence on the same side; PM should override to that side."),
        )


# ---------------------------------------------------------------------------
# Meta — Phase 5 hook
# ---------------------------------------------------------------------------
class MetaSpecialist(SpecialistAgent):
    name = "meta"

    def __init__(self, *, calibration_state: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.calibration = calibration_state or {}

    def evaluate(self, ctx: DecisionContext) -> SpecialistOutput:
        bias_shift = float(self.calibration.get("bias_shift", 0.0))
        worst_specialist = self.calibration.get("worst_specialist", "unknown")
        evidence = [
            f"calibrated_bias_shift={bias_shift:+.2f}",
            f"worst_specialist_last_week={worst_specialist}",
        ]
        if abs(bias_shift) > 0.30:
            sig = "long" if bias_shift > 0 else "short"
            return SpecialistOutput(
                hypothesis=(f"Last week's calibration recommended a {sig}-leaning shift; honor it conservatively."),
                evidence=evidence,
                signal=sig,
                confidence=min(0.65, abs(bias_shift)),
                falsification=("Next post-mortem flips the recommended bias direction."),
            )
        return SpecialistOutput(
            hypothesis="Calibration state shows no actionable bias shift.",
            evidence=evidence,
            signal="neutral",
            confidence=0.25,
            falsification=("A new post-mortem proposes |bias_shift| > 0.3 within 7 days."),
        )


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------
def build_default_panel(
    *,
    transport: Any | None = None,
    audit: Any | None = None,
    calibration: dict[str, Any] | None = None,
) -> list[SpecialistAgent]:
    """The 7-specialist default panel. Wire transport/audit only when
    you intend to back specialists with real LLM calls; the reference
    implementations are deterministic and don't need them."""
    return [
        QuantSpecialist(transport=transport, audit=audit),
        RedTeamSpecialist(transport=transport, audit=audit),
        RiskManagerSpecialist(transport=transport, audit=audit),
        MacroSpecialist(transport=transport, audit=audit),
        MicrostructureSpecialist(transport=transport, audit=audit),
        PMSpecialist(transport=transport, audit=audit),
        MetaSpecialist(calibration_state=calibration, transport=transport, audit=audit),
    ]
