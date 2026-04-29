from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eta_engine.brain.jarvis_v3.next_level.digital_twin import (
    DeltaKind,
    TwinComparator,
    TwinConfigDelta,
    TwinSignal,
)


def test_digital_twin_detects_divergence_and_avoids_noisy_config() -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    comparator = TwinComparator()
    for idx in range(4):
        comparator.ingest(
            TwinSignal(
                ts=now,
                source="PROD",
                signal_id=f"sig-{idx}",
                subsystem="bot.mnq",
                verdict="APPROVED",
                size_mult=1.0,
                realized_r=0.3,
            )
        )
        comparator.ingest(
            TwinSignal(
                ts=now,
                source="TWIN",
                signal_id=f"sig-{idx}",
                subsystem="bot.mnq",
                verdict="DENIED",
                size_mult=0.0,
                realized_r=0.0,
            )
        )

    divs = comparator.divergences(now=now)
    verdict = comparator.verdict(now=now)

    assert len(divs) == 4
    assert verdict.severity == "RED"
    assert verdict.verdict == "AVOID"


def test_digital_twin_promotes_when_signals_match_and_performance_has_parity() -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    comparator = TwinComparator()
    comparator.ingest(
        TwinSignal(ts=now, source="PROD", signal_id="sig", subsystem="bot.mnq", verdict="APPROVED", realized_r=0.4)
    )
    comparator.ingest(
        TwinSignal(ts=now, source="TWIN", signal_id="sig", subsystem="bot.mnq", verdict="APPROVED", realized_r=0.42)
    )

    verdict = comparator.verdict(now=now)

    assert verdict.matched_signals == 1
    assert verdict.divergences == 0
    assert verdict.verdict == "PROMOTE"
    assert verdict.mean_r_twin == 0.42


def test_digital_twin_prunes_old_signals_and_models_delta_contract() -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    comparator = TwinComparator()
    comparator.ingest(
        TwinSignal(
            ts=now - timedelta(days=3),
            source="PROD",
            signal_id="old",
            subsystem="bot.mnq",
            verdict="APPROVED",
        )
    )
    delta = TwinConfigDelta(
        delta_id="size-bump",
        kind=DeltaKind.SIZE_MULT_BUMP,
        description="raise size multiplier after soak",
        prod_value="0.5",
        twin_value="0.7",
    )

    assert comparator.prune(keep_hours=24, now=now) == 1
    assert delta.kind is DeltaKind.SIZE_MULT_BUMP
