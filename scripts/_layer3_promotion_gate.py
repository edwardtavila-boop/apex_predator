"""Layer-3 promotion gate -- parallels mnq_bot's H4 9-gate set.

Operator update 2026-04-26: VPS rotated layer-3 from offshore perps
(Bybit) to **CME micro crypto futures (MBT/MET) on IBKR**. The mnq_bot
9-gate set (``mnq_bot/scripts/_promotion_gate.py``, shipped as H4 in
v0.2.4) gates MNQ live promotion. This script is the analogous gate
set for layer-3 routing -- it asks "can MBT/MET orders flow live?"
rather than "can MNQ orders flow live?"

Why a parallel gate set, not a shared one
-----------------------------------------
MNQ and MBT/MET are different instruments with different:

  * Tick economics (MNQ tick=$0.50; MBT tick=$5; MET tick=$0.05)
  * Venue stack (MNQ: IBKR direct; MBT/MET: IBKR + Kraken margin
    backup + optional Hyperliquid bridge)
  * Risk caps (perp_l3 caps: 1.5%/trade, 4% daily, 15% kill -- vs
    futures: 1.0%/trade, 2.5% daily, 8% kill)
  * Counterparty surfaces (MNQ: CME single counterparty; layer-3:
    CME + Kraken + bridge + USDC depeg risk)

The 9 statistical gates in mnq_bot are validated for MNQ tick
economics; MBT/MET would need a re-tuned threshold pass. Until that
calibration lands, this script enforces the **structural readiness
checks** that don't depend on specific tick economics.

The 8 layer-3 gates
-------------------
  L1. cme_micro_crypto_adapter   : module imports, MBT/MET
                                    canonical mapping intact
  L2. ibkr_adapter_active        : IBKR not in DORMANT_BROKERS
  L3. backup_venue_configured    : kraken_margin OR hyperliquid > 0
                                    in layer3_sub_allocation_pct
  L4. layer3_cap_floor            : layer3_max_fraction_of_total_pct
                                    <= 10 (operator-set ceiling)
  L5. perp_l3_risk_caps_sane     : perp_l3 risk profile present and
                                    each cap below the casino tier
  L6. depeg_floor_set            : stablecoin_depeg_floor configured
                                    and >= 0.98
  L7. capital_sweep_layer3_ok    : module importable, no missing dep
  L8. paper_soak_min_weeks       : layer-3 paper soak >= 2 weeks

Usage
-----
    python -m eta_engine.scripts._layer3_promotion_gate --all
    python -m eta_engine.scripts._layer3_promotion_gate --gate
        cme_micro_crypto_adapter
    python -m eta_engine.scripts._layer3_promotion_gate --all --json

Exit codes (per gate)
---------------------
  0 -- PASS
  1 -- FAIL (HOLD live promotion to layer-3)
  2 -- NO_DATA (artifact missing; cannot evaluate; treat as HOLD)

Exit codes (--all)
------------------
  0 -- every gate PASS
  1 -- at least one gate FAIL
  2 -- at least one gate NO_DATA, no FAILs

Operator override
-----------------
NO override flag. Failure is structural. To flip layer-3 to live, the
operator must (a) fix the failing gate's underlying source OR (b)
edit ``eta_engine/config.json::execution`` manually with a deliberate
operator action that's reviewable in git history. There is no
``--force`` here for the same reason mnq_bot's H4 gate has none -- a
silent "skip the gate" flag is what blows accounts.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
APEX_ROOT = REPO_ROOT / "eta_engine"

# Gate verdicts (match mnq_bot _promotion_gate.py exit codes).
PASS = 0
FAIL = 1
NO_DATA = 2

_VERDICT_NAME = {PASS: "PASS", FAIL: "FAIL", NO_DATA: "NO_DATA"}


@dataclass(frozen=True)
class GateResult:
    name: str
    verdict: int
    detail: str
    evidence: dict[str, Any]

    @property
    def verdict_name(self) -> str:
        return _VERDICT_NAME[self.verdict]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_config() -> dict[str, Any] | None:
    """Load eta_engine/config.json. Returns None on missing/broken."""
    cfg_path = APEX_ROOT / "config.json"
    if not cfg_path.exists():
        return None
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Individual gate evaluators
# ---------------------------------------------------------------------------


def _gate_cme_micro_crypto_adapter() -> GateResult:
    """The cme_micro_crypto adapter must be importable and the canonical
    BTC/USD->MBT and ETH/USD->MET mapping intact."""
    try:
        from eta_engine.venues import cme_micro_crypto as cmc
    except ImportError as exc:
        return GateResult(
            "cme_micro_crypto_adapter", FAIL,
            f"cannot import eta_engine.venues.cme_micro_crypto: {exc}",
            {"error": str(exc)},
        )
    # The module exposes SYMBOL_ROOT (canonical name); fall back to
    # other historical names if a future refactor renames it.
    sym_map = (
        getattr(cmc, "SYMBOL_ROOT", None)
        or getattr(cmc, "SYMBOL_MAP", None)
        or getattr(cmc, "_SYMBOL_MAP", None)
    )
    if not isinstance(sym_map, dict):
        return GateResult(
            "cme_micro_crypto_adapter", NO_DATA,
            "module imported but no SYMBOL_ROOT/SYMBOL_MAP attribute -- "
            "adapter shape may have changed; re-verify mapping",
            {},
        )
    btc_ok = sym_map.get("BTC/USD") == "MBT" or sym_map.get("MBT") == "MBT"
    eth_ok = sym_map.get("ETH/USD") == "MET" or sym_map.get("MET") == "MET"
    if btc_ok and eth_ok:
        return GateResult(
            "cme_micro_crypto_adapter", PASS,
            "MBT and MET symbol mapping present",
            {"map": {k: sym_map[k] for k in sym_map if k in {
                "BTC/USD", "ETH/USD", "MBT", "MET",
            }}},
        )
    return GateResult(
        "cme_micro_crypto_adapter", FAIL,
        f"symbol map incomplete: btc={btc_ok} eth={eth_ok}",
        {"keys": sorted(sym_map.keys())[:20]},
    )


def _gate_ibkr_adapter_active() -> GateResult:
    """IBKR must NOT be in DORMANT_BROKERS."""
    try:
        from eta_engine.venues.router import DORMANT_BROKERS
    except ImportError as exc:
        return GateResult(
            "ibkr_adapter_active", FAIL,
            f"cannot import DORMANT_BROKERS: {exc}",
            {"error": str(exc)},
        )
    if "ibkr" in DORMANT_BROKERS:
        return GateResult(
            "ibkr_adapter_active", FAIL,
            "IBKR is currently in DORMANT_BROKERS; layer-3 cannot "
            "route until dormancy clears",
            {"dormant": sorted(DORMANT_BROKERS)},
        )
    return GateResult(
        "ibkr_adapter_active", PASS,
        f"IBKR is active. Dormant brokers: {sorted(DORMANT_BROKERS) or '[]'}",
        {"dormant": sorted(DORMANT_BROKERS)},
    )


def _gate_backup_venue_configured() -> GateResult:
    """layer3_sub_allocation_pct must list at least one non-zero
    backup venue (kraken_margin, hyperliquid)."""
    cfg = _read_config()
    if cfg is None:
        return GateResult(
            "backup_venue_configured", NO_DATA,
            "missing eta_engine/config.json",
            {},
        )
    sub = (
        cfg.get("funnel", {})
        .get("sweep_policy", {})
        .get("layer3_sub_allocation_pct", {})
    )
    if not sub:
        return GateResult(
            "backup_venue_configured", FAIL,
            "config.json::funnel.sweep_policy.layer3_sub_allocation_pct "
            "is empty -- no venue allocation defined",
            {},
        )
    backups = {k: v for k, v in sub.items() if k != "cme_micro_crypto"}
    nonzero = {k: v for k, v in backups.items() if isinstance(v, (int, float)) and v > 0}
    if nonzero:
        return GateResult(
            "backup_venue_configured", PASS,
            f"backup venue(s) configured: {nonzero}",
            {"sub_allocation": sub},
        )
    return GateResult(
        "backup_venue_configured", FAIL,
        f"no backup venue with non-zero allocation; got {sub}. "
        "Layer-3 needs at least one failover route besides "
        "cme_micro_crypto.",
        {"sub_allocation": sub},
    )


def _gate_layer3_cap_floor() -> GateResult:
    """layer3_max_fraction_of_total_pct must be set and <= 10."""
    cfg = _read_config()
    if cfg is None:
        return GateResult(
            "layer3_cap_floor", NO_DATA, "missing config.json", {},
        )
    pct = (
        cfg.get("funnel", {})
        .get("sweep_policy", {})
        .get("layer3_max_fraction_of_total_pct")
    )
    if pct is None:
        return GateResult(
            "layer3_cap_floor", FAIL,
            "layer3_max_fraction_of_total_pct not configured",
            {},
        )
    if pct <= 10:
        return GateResult(
            "layer3_cap_floor", PASS,
            f"layer-3 capped at {pct}% of total NAV (<= 10% ceiling)",
            {"layer3_max_pct": pct, "ceiling": 10},
        )
    return GateResult(
        "layer3_cap_floor", FAIL,
        f"layer-3 cap {pct}% exceeds the 10% operator ceiling. "
        "Tighten the config before live promotion.",
        {"layer3_max_pct": pct, "ceiling": 10},
    )


def _gate_perp_l3_risk_caps_sane() -> GateResult:
    """perp_l3 risk profile must exist and each cap must be below or
    equal to the casino-tier (perp_casino) limits. The casino tier is
    DORMANT; layer-3 (active) MUST be at most as risky."""
    cfg = _read_config()
    if cfg is None:
        return GateResult(
            "perp_l3_risk_caps_sane", NO_DATA, "missing config.json", {},
        )
    risk = cfg.get("risk", {})
    l3 = risk.get("perp_l3")
    casino = risk.get("perp_casino", {})
    if not l3:
        return GateResult(
            "perp_l3_risk_caps_sane", FAIL,
            "config.json::risk.perp_l3 not present",
            {},
        )
    fields = (
        "per_trade_risk_pct",
        "daily_loss_cap_pct",
        "max_drawdown_kill_pct",
    )
    bad: list[str] = []
    for f in fields:
        l3_val = l3.get(f)
        casino_val = casino.get(f)
        if l3_val is None:
            bad.append(f"{f}=missing")
            continue
        if isinstance(l3_val, (int, float)) and isinstance(casino_val, (int, float)) and l3_val > casino_val:
            bad.append(f"{f}={l3_val}>{casino_val} (casino)")
    if not bad:
        return GateResult(
            "perp_l3_risk_caps_sane", PASS,
            "perp_l3 caps present and all <= casino tier",
            {"perp_l3": {f: l3.get(f) for f in fields}},
        )
    return GateResult(
        "perp_l3_risk_caps_sane", FAIL,
        f"perp_l3 risk caps unsafe: {', '.join(bad)}",
        {"perp_l3": {f: l3.get(f) for f in fields}, "issues": bad},
    )


def _gate_depeg_floor_set() -> GateResult:
    """stablecoin_depeg_floor must be configured and >= 0.98."""
    cfg = _read_config()
    if cfg is None:
        return GateResult(
            "depeg_floor_set", NO_DATA, "missing config.json", {},
        )
    floor = (
        cfg.get("funnel", {})
        .get("sweep_policy", {})
        .get("stablecoin_depeg_floor")
    )
    if floor is None:
        return GateResult(
            "depeg_floor_set", FAIL,
            "stablecoin_depeg_floor not configured -- layer-3 has no "
            "USDC/USDT depeg circuit breaker",
            {},
        )
    if floor >= 0.98:
        return GateResult(
            "depeg_floor_set", PASS,
            f"depeg floor = {floor} (>= 0.98 minimum)",
            {"floor": floor, "min": 0.98},
        )
    return GateResult(
        "depeg_floor_set", FAIL,
        f"depeg floor {floor} below 0.98 minimum -- stablecoin "
        "tolerance too lax for layer-3 collateral safety",
        {"floor": floor, "min": 0.98},
    )


def _gate_capital_sweep_layer3_ok() -> GateResult:
    """funnel.capital_sweep_layer3 must be importable."""
    try:
        from eta_engine.funnel import capital_sweep_layer3 as csl
    except ImportError as exc:
        return GateResult(
            "capital_sweep_layer3_ok", FAIL,
            f"cannot import capital_sweep_layer3: {exc}",
            {"error": str(exc)},
        )
    expected = (
        "compute_l3_sub_allocation",
        "compute_sweep_allocation",
        "should_sweep",
        "plan_l3_sweep",
        "enforce_cross_layer_caps",
    )
    missing = [n for n in expected if not hasattr(csl, n)]
    if missing:
        return GateResult(
            "capital_sweep_layer3_ok", FAIL,
            f"capital_sweep_layer3 missing API: {missing}",
            {"missing": missing},
        )
    return GateResult(
        "capital_sweep_layer3_ok", PASS,
        f"capital_sweep_layer3 has all {len(expected)} expected entries",
        {"api": list(expected)},
    )


def _gate_paper_soak_min_weeks() -> GateResult:
    """Layer-3 paper soak >= 2 weeks (artifact-driven, like mnq_bot)."""
    artifact = APEX_ROOT / "reports" / "layer3_paper_soak.json"
    if not artifact.exists():
        return GateResult(
            "paper_soak_min_weeks", NO_DATA,
            f"missing artifact: {artifact.relative_to(REPO_ROOT)}. "
            "Generate with the layer-3 paper soak harness once "
            "operator sets it up.",
            {"artifact": str(artifact)},
        )
    try:
        data = json.loads(artifact.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return GateResult(
            "paper_soak_min_weeks", NO_DATA,
            f"artifact unparseable: {exc}",
            {"artifact": str(artifact)},
        )
    weeks = data.get("weeks_clean")
    threshold = 2
    if weeks is None:
        return GateResult(
            "paper_soak_min_weeks", NO_DATA,
            "artifact missing 'weeks_clean'",
            {"keys": list(data.keys())},
        )
    if weeks >= threshold:
        return GateResult(
            "paper_soak_min_weeks", PASS,
            f"{weeks:.1f} weeks of clean paper >= {threshold}",
            {"weeks": weeks, "threshold": threshold},
        )
    return GateResult(
        "paper_soak_min_weeks", FAIL,
        f"only {weeks:.1f} weeks of clean paper (need {threshold})",
        {"weeks": weeks, "threshold": threshold},
    )


# Ordered registry. Keep names stable -- tests pin them.
_GATES = [
    ("cme_micro_crypto_adapter", _gate_cme_micro_crypto_adapter),
    ("ibkr_adapter_active",      _gate_ibkr_adapter_active),
    ("backup_venue_configured",  _gate_backup_venue_configured),
    ("layer3_cap_floor",         _gate_layer3_cap_floor),
    ("perp_l3_risk_caps_sane",   _gate_perp_l3_risk_caps_sane),
    ("depeg_floor_set",          _gate_depeg_floor_set),
    ("capital_sweep_layer3_ok",  _gate_capital_sweep_layer3_ok),
    ("paper_soak_min_weeks",     _gate_paper_soak_min_weeks),
]
_GATE_NAMES = [name for name, _ in _GATES]


def evaluate(name: str) -> GateResult:
    for gate_name, fn in _GATES:
        if gate_name == name:
            return fn()
    msg = (
        f"unknown gate: {name!r}. Known gates: {', '.join(_GATE_NAMES)}"
    )
    raise ValueError(msg)


def evaluate_all() -> list[GateResult]:
    return [fn() for _, fn in _GATES]


def aggregate_verdict(results: list[GateResult]) -> int:
    if any(r.verdict == FAIL for r in results):
        return 1
    if any(r.verdict == NO_DATA for r in results):
        return 2
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_human(result: GateResult) -> None:
    icon = {"PASS": "[+]", "FAIL": "[-]", "NO_DATA": "[?]"}[result.verdict_name]
    print(
        f"  {icon} {result.name:<30s} {result.verdict_name:<8s} {result.detail}",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--gate", choices=_GATE_NAMES,
        help="evaluate a single gate; exit code = its verdict",
    )
    g.add_argument(
        "--all", action="store_true",
        help="evaluate all 8 layer-3 gates; exit code = aggregate",
    )
    p.add_argument(
        "--json", action="store_true",
        help="emit JSON instead of human report",
    )
    args = p.parse_args(argv)

    if args.gate:
        result = evaluate(args.gate)
        if args.json:
            print(json.dumps({
                "gate": result.name,
                "verdict": result.verdict_name,
                "detail": result.detail,
                "evidence": result.evidence,
            }, indent=2))
        else:
            print(f"Gate: {result.name}")
            _print_human(result)
        return result.verdict

    # --all
    results = evaluate_all()
    rc = aggregate_verdict(results)
    if args.json:
        payload = {
            "rc": rc,
            "verdict": _VERDICT_NAME.get(rc, "?")
                if rc in _VERDICT_NAME else _VERDICT_NAME[rc] if rc < 3 else "?",
            "n_pass": sum(1 for r in results if r.verdict == PASS),
            "n_fail": sum(1 for r in results if r.verdict == FAIL),
            "n_no_data": sum(1 for r in results if r.verdict == NO_DATA),
            "gates": [
                {
                    "name": r.name,
                    "verdict": r.verdict_name,
                    "detail": r.detail,
                    "evidence": r.evidence,
                }
                for r in results
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print("Layer-3 promotion gates")
        for r in results:
            _print_human(r)
        n_pass = sum(1 for r in results if r.verdict == PASS)
        n_fail = sum(1 for r in results if r.verdict == FAIL)
        n_no_data = sum(1 for r in results if r.verdict == NO_DATA)
        verdict = "PASS" if rc == 0 else ("FAIL" if rc == 1 else "NO_DATA")
        print(
            f"\nVerdict: {verdict} ({n_pass} PASS, {n_fail} FAIL, "
            f"{n_no_data} NO_DATA)",
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
