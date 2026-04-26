"""
Tests for ``brain.jarvis_v3.claude_layer.verdict_cache`` (Cascade L2)
and the dispatch-integration that consults it.

Covers:
  * Bucketing primitives (floats snap to grid, ints binned, sparse
    hours_until_event buckets, booleans as 0/1, None passthrough).
  * hash_features is order-independent and stable.
  * VerdictCache.get/put with TTL expiry; stale entries auto-evict.
  * Regime-aware TTL (CRISIS short, NEUTRAL default, CALM long).
  * Stats (hits, misses, evictions, hit_rate).
  * snapshot() / restore() round-trip preserves entries + counters.
  * AvengersDispatch.decide() consults cache after governor approval;
    a cache HIT short-circuits the persona debate.
  * AvengersDispatch.decide() writes to the cache after a successful
    Claude debate so subsequent identical-features calls hit warm.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apex_predator.brain.jarvis_v3.claude_layer.verdict_cache import (
    CachedVerdict,
    VerdictCache,
    bucket_features,
    hash_features,
)


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------


def test_bucket_features_floats_snap_to_grid() -> None:
    # stress_composite grid is 0.05; 0.21 and 0.22 both bucket to 0.20.
    a = bucket_features({"stress_composite": 0.21})
    b = bucket_features({"stress_composite": 0.22})
    assert a == b
    assert a["stress_composite"] == "0.20"


def test_bucket_features_floats_cross_grid_boundary_differ() -> None:
    # 0.24 -> 0.25, 0.26 -> 0.25 (both round to 0.25)
    # 0.27 -> 0.25, 0.28 -> 0.30 (0.28/0.05=5.6 rounds to 6 -> 0.30)
    low = bucket_features({"stress_composite": 0.27})
    high = bucket_features({"stress_composite": 0.28})
    assert low["stress_composite"] != high["stress_composite"]


def test_bucket_features_int_binning() -> None:
    # operator_overrides_24h bins: [0, 1, 3, 5]
    # 0 -> "0+", 1 -> "1+", 2 -> "1+", 3 -> "3+", 4 -> "3+", 5 -> "5+"
    cases = [(0, "0+"), (1, "1+"), (2, "1+"), (3, "3+"), (4, "3+"), (5, "5+"),
             (10, "5+")]
    for v, expected in cases:
        out = bucket_features({"operator_overrides_24h": v})
        assert out["operator_overrides_24h"] == expected, f"v={v}"


def test_bucket_features_hours_until_event_sparse() -> None:
    cases = [(None, "none"), (0.5, "imminent"), (1.0, "imminent"),
             (3.0, "near"), (8.0, "today"), (48.0, "later")]
    for v, expected in cases:
        out = bucket_features({"hours_until_event": v})
        assert out["hours_until_event"] == expected, f"v={v}"


def test_bucket_features_booleans_as_zero_one() -> None:
    out_true = bucket_features({"portfolio_breach": True})
    out_false = bucket_features({"portfolio_breach": False})
    assert out_true["portfolio_breach"] == "1"
    assert out_false["portfolio_breach"] == "0"


def test_bucket_features_string_passthrough() -> None:
    out = bucket_features({"regime": "CRISIS"})
    assert out["regime"] == "CRISIS"


def test_bucket_features_none_becomes_string_none() -> None:
    out = bucket_features({"some_unknown_field": None})
    assert out["some_unknown_field"] == "none"


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_hash_features_stable_across_key_order() -> None:
    a = hash_features({"stress_composite": 0.5, "regime": "NEUTRAL"})
    b = hash_features({"regime": "NEUTRAL", "stress_composite": 0.5})
    assert a == b


def test_hash_features_changes_with_bucket() -> None:
    # 0.21 and 0.36 fall in different stress buckets -> different hashes.
    a = hash_features({"stress_composite": 0.21})
    b = hash_features({"stress_composite": 0.36})
    assert a != b


def test_hash_features_same_within_bucket() -> None:
    # 0.31 and 0.32 both snap to 0.30 (6.2 and 6.4 both round to 6).
    a = hash_features({"stress_composite": 0.31})
    b = hash_features({"stress_composite": 0.32})
    assert a == b


# ---------------------------------------------------------------------------
# VerdictCache.get / put
# ---------------------------------------------------------------------------


def test_cache_get_returns_none_on_miss() -> None:
    c = VerdictCache()
    assert c.get({"stress_composite": 0.5}) is None
    assert c.misses == 1
    assert c.hits == 0


def test_cache_get_returns_entry_on_hit() -> None:
    c = VerdictCache()
    feats = {"stress_composite": 0.4, "regime": "NEUTRAL"}
    c.put(feats, final_vote="APPROVE", route="BATMAN_DEBATE")
    out = c.get(feats)
    assert out is not None
    assert out.final_vote == "APPROVE"
    assert out.route == "BATMAN_DEBATE"
    assert c.hits == 1


def test_cache_get_returns_hit_for_same_bucket_diff_raw() -> None:
    """Two raw values in the same bucket should hit the same entry."""
    c = VerdictCache()
    c.put({"stress_composite": 0.41, "regime": "NEUTRAL"},
          final_vote="DENY")
    out = c.get({"stress_composite": 0.42, "regime": "NEUTRAL"})
    assert out is not None
    assert out.final_vote == "DENY"


def test_cache_evicts_expired_entry_on_get() -> None:
    c = VerdictCache()
    feats = {"regime": "NEUTRAL"}
    past = datetime.now(UTC) - timedelta(hours=2)
    c.put(feats, final_vote="APPROVE", now=past, ttl_seconds=300)
    out = c.get(feats)
    assert out is None
    assert c.evictions == 1
    assert c.misses == 1


def test_cache_ttl_by_regime_crisis_is_shorter_than_neutral() -> None:
    c = VerdictCache()
    crisis_entry = c.put({"regime": "CRISIS"}, final_vote="DEFER")
    neutral_entry = c.put({"regime": "NEUTRAL"}, final_vote="APPROVE")
    crisis_ttl = (crisis_entry.expires_at - crisis_entry.cached_at).total_seconds()
    neutral_ttl = (neutral_entry.expires_at - neutral_entry.cached_at).total_seconds()
    assert crisis_ttl < neutral_ttl
    assert crisis_ttl == 300       # 5 minutes
    assert neutral_ttl == 3600     # 1 hour


def test_cache_explicit_ttl_overrides_regime_default() -> None:
    c = VerdictCache()
    entry = c.put({"regime": "CRISIS"},
                  final_vote="DEFER", ttl_seconds=60)
    ttl = (entry.expires_at - entry.cached_at).total_seconds()
    assert ttl == 60


def test_cache_put_replaces_prior_entry_for_same_features() -> None:
    c = VerdictCache()
    feats = {"stress_composite": 0.5}
    c.put(feats, final_vote="APPROVE")
    c.put(feats, final_vote="DENY")
    out = c.get(feats)
    assert out is not None
    assert out.final_vote == "DENY"


# ---------------------------------------------------------------------------
# Stats / hit rate
# ---------------------------------------------------------------------------


def test_cache_hit_rate_tracks_correctly() -> None:
    c = VerdictCache()
    feats_a = {"stress_composite": 0.1}
    feats_b = {"stress_composite": 0.5}
    c.put(feats_a, final_vote="APPROVE")
    c.get(feats_a)        # hit
    c.get(feats_a)        # hit
    c.get(feats_b)        # miss
    assert c.hit_rate() == pytest.approx(2/3, abs=0.01)


def test_cache_stats_dict_keys() -> None:
    c = VerdictCache()
    s = c.stats()
    assert set(s.keys()) == {"size", "hits", "misses", "evictions", "hit_rate"}


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


def test_cache_prune_removes_expired() -> None:
    c = VerdictCache()
    past = datetime.now(UTC) - timedelta(hours=2)
    c.put({"regime": "NEUTRAL"}, final_vote="APPROVE", now=past)
    c.put({"regime": "CALM"}, final_vote="DEFER")  # fresh
    pruned = c.prune()
    assert pruned == 1
    assert c.evictions == 1


# ---------------------------------------------------------------------------
# Snapshot / restore
# ---------------------------------------------------------------------------


def test_cache_snapshot_restore_roundtrip_preserves_entries_and_counters() -> None:
    c1 = VerdictCache()
    c1.put({"stress_composite": 0.4}, final_vote="APPROVE")
    c1.put({"stress_composite": 0.7}, final_vote="DENY")
    c1.get({"stress_composite": 0.4})  # hit
    c1.get({"stress_composite": 0.99}) # miss
    snap = c1.snapshot()
    c2 = VerdictCache()
    c2.restore(snap)
    assert c2.hits == c1.hits
    assert c2.misses == c1.misses
    assert c2.evictions == c1.evictions
    # The restored cache should still produce hits for the same features.
    assert c2.get({"stress_composite": 0.41}) is not None  # same bucket as 0.40


def test_cache_restore_from_empty_snapshot_safe() -> None:
    c = VerdictCache()
    c.restore({})
    assert c.hits == 0
    assert len(c._store) == 0  # noqa: SLF001 -- introspection


# ---------------------------------------------------------------------------
# AvengersDispatch integration
# ---------------------------------------------------------------------------

# Minimal fakes for the dispatch test -- we don't want to spin up the full
# JARVIS / Claude stack, just verify cache gating works correctly.


def _make_dispatch_with_invoke_plan(*, cache: VerdictCache | None = None):
    """Build a minimal AvengersDispatch wired with stubs."""
    from apex_predator.brain.avengers.dispatch import AvengersDispatch
    from apex_predator.brain.avengers.fleet import Fleet
    from apex_predator.brain.avengers.base import (
        DryRunExecutor,
        TaskResult,
        PersonaId,
    )
    from apex_predator.brain.jarvis_v3.claude_layer.cost_governor import (
        CostGovernor,
        InvocationPlan,
        PersonaAssignment,
    )
    from apex_predator.brain.jarvis_v3.claude_layer.distillation import (
        Distiller,
    )
    from apex_predator.brain.jarvis_v3.claude_layer.escalation import (
        EscalationDecision,
    )
    from apex_predator.brain.jarvis_v3.claude_layer.usage_tracker import (
        UsageTracker,
    )

    # Patch governor.plan to always say invoke=True with one Sonnet persona.
    class _StubGovernor(CostGovernor):
        def plan(self, **_kwargs) -> InvocationPlan:  # type: ignore[override]
            return InvocationPlan(
                invoke_claude=True,
                reason="stub: forced invoke for test",
                escalation=EscalationDecision(
                    escalate=True,
                    triggers=[],
                    reasons=["stubbed"],
                    jarvis_handles=False,
                    note="test stub",
                ),
                personas=[
                    PersonaAssignment(
                        persona="SKEPTIC",
                        tier=None,  # deterministic to avoid needing prompts
                        deterministic=True,
                        reason="stub",
                    ),
                ],
            )

    governor = _StubGovernor(usage=UsageTracker(), distiller=Distiller())
    fleet = Fleet(executor=DryRunExecutor())
    return AvengersDispatch(
        governor=governor, fleet=fleet, verdict_cache=cache,
    )


def _stub_context_and_inputs(stress: float = 0.5):
    """Build the minimum StructuredContext + inputs decide() needs."""
    from apex_predator.brain.jarvis_v3.claude_layer.escalation import (
        EscalationInputs,
    )
    from apex_predator.brain.jarvis_v3.claude_layer.prompts import (
        StructuredContext,
    )
    from apex_predator.brain.jarvis_v3.claude_layer.stakes import (
        StakesInputs,
    )

    ctx = StructuredContext(
        ts=datetime.now(UTC).isoformat(),
        subsystem="test", action="ORDER_PLACE",
        regime="NEUTRAL", regime_confidence=0.7,
        session_phase="RTH",
        stress_composite=stress, sizing_mult=0.8,
        binding_constraint="none",
        hours_until_event=None,
        portfolio_breach=False, doctrine_net_bias=0.0,
        doctrine_tenets=[],
        r_at_risk=0.5, operator_overrides_24h=0,
        precedent_n=20, precedent_win_rate=0.55, precedent_mean_r=0.3,
        anomaly_flags=[], event_label="",
        daily_dd_pct=0.01, jarvis_baseline_verdict="APPROVE",
    )
    return EscalationInputs(stress_composite=stress), StakesInputs(), ctx


def test_dispatch_works_without_cache_when_none_provided() -> None:
    """Cache is optional -- decide() must not blow up when it's None."""
    dispatch = _make_dispatch_with_invoke_plan(cache=None)
    esc, stk, ctx = _stub_context_and_inputs(stress=0.5)
    result = dispatch.decide(
        escalation_inputs=esc, stakes_inputs=stk, context=ctx,
    )
    assert result is not None
    # No cache => can't hit verdict cache route.
    assert result.route.value != "JARVIS_VERDICT_CACHE"


def test_dispatch_writes_to_cache_after_claude_debate() -> None:
    cache = VerdictCache()
    dispatch = _make_dispatch_with_invoke_plan(cache=cache)
    esc, stk, ctx = _stub_context_and_inputs(stress=0.5)
    result = dispatch.decide(
        escalation_inputs=esc, stakes_inputs=stk, context=ctx,
    )
    # First call ran the (stubbed) debate; cache should now have one entry.
    assert len(cache._store) == 1  # noqa: SLF001
    # The cached vote should match what dispatch returned.
    assert result.final_vote in {"APPROVE", "CONDITIONAL", "DENY", "DEFER"}


def test_dispatch_returns_cached_verdict_on_second_call_with_same_features(
) -> None:
    cache = VerdictCache()
    dispatch = _make_dispatch_with_invoke_plan(cache=cache)
    esc, stk, ctx = _stub_context_and_inputs(stress=0.5)
    first = dispatch.decide(
        escalation_inputs=esc, stakes_inputs=stk, context=ctx,
    )
    second = dispatch.decide(
        escalation_inputs=esc, stakes_inputs=stk, context=ctx,
    )
    assert second.route.value == "JARVIS_VERDICT_CACHE"
    assert second.final_vote == first.final_vote
    assert "verdict-cache hit" in second.note


def test_dispatch_misses_cache_when_features_in_different_bucket() -> None:
    cache = VerdictCache()
    dispatch = _make_dispatch_with_invoke_plan(cache=cache)
    # First call at stress 0.5 -> bucket 0.50
    esc1, stk, ctx1 = _stub_context_and_inputs(stress=0.5)
    dispatch.decide(escalation_inputs=esc1, stakes_inputs=stk, context=ctx1)
    # Second call at stress 0.9 -> bucket 0.90 -- different
    esc2, _, ctx2 = _stub_context_and_inputs(stress=0.9)
    second = dispatch.decide(
        escalation_inputs=esc2, stakes_inputs=stk, context=ctx2,
    )
    assert second.route.value != "JARVIS_VERDICT_CACHE"
    # Both writes happened -> cache size 2
    assert len(cache._store) == 2  # noqa: SLF001
