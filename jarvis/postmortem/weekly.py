"""
EVOLUTIONARY TRADING ALGO // jarvis.postmortem.weekly
=========================================
Phase 5 weekly autonomous post-mortem.

Trigger: Saturday 9am cron (operator wires via apex schedule-nightly's
sibling apex schedule-postmortem). Reads the past week's closed trades
from the EpisodicMemory store, picks the 5 worst, attributes errors
to specialists whose vote disagreed with the loss, drafts a markdown
findings memo, and proposes calibration deltas.

Hard rule: NO autonomous code change. Recommendations are surfaced
for operator approval via apex confirm. Auto-apply is gated by the
ForecastAccuracyTracker reaching the 60% precision floor (#69b).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from eta_engine.jarvis.memory.store import EpisodicMemory, MemoryStore


@dataclass
class PostMortemRecommendation:
    """One proposed calibration change."""

    target: str  # specialist name | "regime_threshold:vix" | ...
    kind: str  # "confidence_recalibration" | "regime_shift" | "freeze"
    delta: float  # signed magnitude
    rationale: str
    auto_applyable: bool  # only confidence_recalibration is auto-apply

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PostMortemReport:
    week_starting_utc: str
    week_ending_utc: str
    n_decisions: int
    n_losses: int
    n_wins: int
    worst_trades: list[dict[str, Any]] = field(default_factory=list)
    specialist_error_counts: dict[str, int] = field(default_factory=dict)
    recommendations: list[PostMortemRecommendation] = field(default_factory=list)
    memo_md: str = ""
    generated_at_utc: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["recommendations"] = [r.as_dict() for r in self.recommendations]
        return d


class WeeklyPostMortem:
    """Pure-Python deterministic post-mortem.

    Production wiring can subclass `WeeklyPostMortem` and override
    `_draft_memo` to call Opus for richer reasoning; the base class
    produces a structured memo from the available data so every step
    of the pipeline is testable + replayable.
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        outcome_key: str = "+5_bars",
        loss_threshold_r: float = -0.5,
        worst_n: int = 5,
        confidence_recalibration_step: float = 0.05,
    ) -> None:
        self.store = store
        self.outcome_key = outcome_key
        self.loss_threshold_r = loss_threshold_r
        self.worst_n = worst_n
        self.recalib_step = confidence_recalibration_step

    def run(
        self,
        *,
        as_of: datetime | None = None,
        window_days: int = 7,
    ) -> PostMortemReport:
        as_of = as_of or datetime.now(UTC)
        week_start = as_of - timedelta(days=window_days)

        decisions = [
            m
            for m in self.store.all()
            if self._in_window(m.ts_utc, week_start, as_of) and self.outcome_key in m.outcomes
        ]
        wins = [m for m in decisions if float(m.outcomes.get(self.outcome_key, 0.0)) > 0]
        losses = [m for m in decisions if float(m.outcomes.get(self.outcome_key, 0.0)) <= self.loss_threshold_r]
        # Sort losses ascending (worst first)
        losses_sorted = sorted(
            losses,
            key=lambda m: float(m.outcomes.get(self.outcome_key, 0.0)),
        )
        worst = losses_sorted[: self.worst_n]

        # Specialist error attribution: for each worst trade, which
        # specialists voted in the SAME direction as the (now-known
        # bad) PM action? Those specialists were systematically wrong
        # on those trades.
        specialist_errors: Counter[str] = Counter()
        for m in worst:
            losing_action = m.pm_action  # fire_long / fire_short
            losing_signal = (
                "long" if losing_action == "fire_long" else "short" if losing_action == "fire_short" else None
            )
            if losing_signal is None:
                continue
            for spec_name, vote in m.votes.items():
                if vote == losing_signal:
                    specialist_errors[spec_name] += 1

        recommendations = self._build_recommendations(
            specialist_errors=specialist_errors,
            worst=worst,
            n_losses=len(losses),
            n_decisions=len(decisions),
        )
        memo = self._draft_memo(
            week_start=week_start,
            as_of=as_of,
            decisions=decisions,
            losses=losses,
            worst=worst,
            specialist_errors=specialist_errors,
            recommendations=recommendations,
        )

        return PostMortemReport(
            week_starting_utc=week_start.isoformat(timespec="seconds"),
            week_ending_utc=as_of.isoformat(timespec="seconds"),
            n_decisions=len(decisions),
            n_losses=len(losses),
            n_wins=len(wins),
            worst_trades=[self._summarize_trade(m) for m in worst],
            specialist_error_counts=dict(specialist_errors),
            recommendations=recommendations,
            memo_md=memo,
            generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    @staticmethod
    def _in_window(ts_str: str, start: datetime, end: datetime) -> bool:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            return False
        return start <= ts <= end

    @staticmethod
    def _summarize_trade(m: EpisodicMemory) -> dict[str, Any]:
        return {
            "decision_id": m.decision_id,
            "ts_utc": m.ts_utc,
            "regime": m.regime,
            "setup_name": m.setup_name,
            "pm_action": m.pm_action,
            "outcomes": dict(m.outcomes),
            "votes": dict(m.votes),
        }

    def _build_recommendations(
        self,
        *,
        specialist_errors: Counter,
        worst: list[EpisodicMemory],
        n_losses: int,
        n_decisions: int,
    ) -> list[PostMortemRecommendation]:
        out: list[PostMortemRecommendation] = []
        if not worst or not n_decisions:
            return out
        loss_rate = n_losses / max(1, n_decisions)
        if loss_rate > 0.6:
            out.append(
                PostMortemRecommendation(
                    target="ensemble",
                    kind="freeze",
                    delta=0.0,
                    rationale=(
                        f"loss rate {loss_rate:.0%} > 60%; freeze adaptation until next Court of Appeals review"
                    ),
                    auto_applyable=False,
                )
            )
        # Confidence recalibration for the most-wrong specialist
        if specialist_errors:
            worst_spec, count = specialist_errors.most_common(1)[0]
            out.append(
                PostMortemRecommendation(
                    target=worst_spec,
                    kind="confidence_recalibration",
                    delta=-self.recalib_step,
                    rationale=(
                        f"specialist {worst_spec} voted with the losing "
                        f"side on {count}/{len(worst)} of the worst trades"
                    ),
                    auto_applyable=True,  # the only auto-apply class
                )
            )
        return out

    def _draft_memo(
        self,
        *,
        week_start: datetime,
        as_of: datetime,
        decisions: list[EpisodicMemory],
        losses: list[EpisodicMemory],
        worst: list[EpisodicMemory],
        specialist_errors: Counter,
        recommendations: list[PostMortemRecommendation],
    ) -> str:
        """Produce a JIRA-style markdown findings memo. Subclasses may
        override to call an LLM."""
        lines = [
            f"# Weekly Post-Mortem — {week_start.date()} → {as_of.date()}",
            "",
            f"**Decisions:** {len(decisions)}  ",
            f"**Wins:** {len(decisions) - len(losses)}  **Losses:** {len(losses)}  ",
            "",
            "## Worst trades",
            "",
        ]
        for m in worst:
            r = float(m.outcomes.get(self.outcome_key, 0.0))
            lines.append(f"- `{m.decision_id}` {m.ts_utc} {m.setup_name} ({m.regime}) → {m.pm_action} → R={r:+.2f}")
        lines.append("")
        lines.append("## Specialist error attribution")
        lines.append("")
        if not specialist_errors:
            lines.append("_No attribution data._")
        else:
            for name, n in specialist_errors.most_common():
                lines.append(f"- **{name}**: voted with losing side on {n} of {len(worst)} worst trades")
        lines.append("")
        lines.append("## Recommendations")
        lines.append("")
        if not recommendations:
            lines.append("_No actionable recommendations this week._")
        else:
            for r in recommendations:
                tag = "AUTO-APPLY" if r.auto_applyable else "OPERATOR APPROVAL"
                lines.append(f"- [{tag}] **{r.target}** — {r.kind} (delta={r.delta:+.3f})")
                lines.append(f"  - rationale: {r.rationale}")
        lines.append("")
        lines.append("---")
        lines.append("_Generated by `apex post-mortem`. No code was modified._")
        return "\n".join(lines)
