"""APEX PREDATOR  //  scripts.sample_size_calc
====================================================
Bootstrap sample-size solver for per-bot edge confirmation.

For each bot we hold a (mean, sigma, n_cur) triplet of per-trade R
multiples. We need n_required such that the CI95 lower bound on the
mean strictly exceeds zero:

    mean - z95 * sigma / sqrt(n) > 0
    n > (z95 * sigma / mean) ** 2     (positive mean)

For mean <= 0 the gate is unreachable -- no sample size lifts the CI95
lower bound past zero. Marked UNREACHABLE.

A "portfolio" pseudo-bot is appended whose mean is the n-weighted mean
across bots and whose sigma is the pooled stdev (sqrt of weighted
variance).

CLI:
    python -m apex_predator.scripts.sample_size_calc \\
        --report docs/bootstrap_ci_combined_v1.json \\
        --label v1
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

Z95: float = 1.959964    # two-sided z for 95% CI


def _compute_row(
    bot: str,
    *,
    n_cur: int,
    mean: float,
    sigma: float,
    weeks: int,
) -> dict[str, Any]:
    """Compute n_required and status for a single bot."""
    if mean <= 0.0:
        return {
            "bot": bot,
            "n_cur": n_cur,
            "mean": mean,
            "sigma": sigma,
            "weeks": weeks,
            "n_required": None,
            "n_delta": None,
            "status": "UNREACHABLE",
        }

    if sigma <= 0.0:
        # Degenerate variance -- treat as already met.
        return {
            "bot": bot,
            "n_cur": n_cur,
            "mean": mean,
            "sigma": sigma,
            "weeks": weeks,
            "n_required": 1,
            "n_delta": 0,
            "status": "MET",
        }

    n_required = int((Z95 * sigma / mean) ** 2) + 1
    delta = max(0, n_required - n_cur)
    status = "MET" if n_cur >= n_required else "PENDING"
    return {
        "bot": bot,
        "n_cur": n_cur,
        "mean": mean,
        "sigma": sigma,
        "weeks": weeks,
        "n_required": n_required,
        "n_delta": delta,
        "status": status,
    }


def _pool_portfolio(report: dict[str, Any]) -> tuple[int, float, float]:
    """Return (n_total, weighted_mean, pooled_sigma) across by_bot entries."""
    bots = report.get("by_bot", {}) or {}
    if not bots:
        return 0, 0.0, 0.0

    total_n = 0
    weighted_mean_num = 0.0
    weighted_var_num = 0.0
    for stats in bots.values():
        n = int(stats.get("n_trades", 0) or 0)
        m = float(stats.get("point_mean", 0.0) or 0.0)
        s = float(stats.get("point_stdev", 0.0) or 0.0)
        if n <= 0:
            continue
        total_n += n
        weighted_mean_num += m * n
        weighted_var_num += (s * s) * n

    if total_n == 0:
        return 0, 0.0, 0.0

    mean = weighted_mean_num / total_n
    pooled_var = weighted_var_num / total_n
    return total_n, mean, math.sqrt(max(pooled_var, 0.0))


def _render_markdown(rows: list[dict[str, Any]], label: str) -> str:
    lines = [
        f"# Sample-size requirements -- {label}",
        "",
        "| bot | n_cur | mean | sigma | weeks | n_required | n_delta | status |",
        "|-----|------:|-----:|------:|------:|-----------:|--------:|:-------|",
    ]
    for r in rows:
        n_req = r["n_required"] if r["n_required"] is not None else "-"
        n_delta = r["n_delta"] if r["n_delta"] is not None else "-"
        lines.append(
            f"| {r['bot']} | {r['n_cur']} | {r['mean']:.4f} | "
            f"{r['sigma']:.4f} | {r['weeks']} | {n_req} | {n_delta} | "
            f"{r['status']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--weeks", type=int, default=4)
    parser.add_argument("--out-dir", type=Path, default=Path("docs"))
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for bot, stats in (report.get("by_bot") or {}).items():
        rows.append(
            _compute_row(
                bot,
                n_cur=int(stats.get("n_trades", 0) or 0),
                mean=float(stats.get("point_mean", 0.0) or 0.0),
                sigma=float(stats.get("point_stdev", 0.0) or 0.0),
                weeks=args.weeks,
            )
        )
    n_p, mean_p, sigma_p = _pool_portfolio(report)
    rows.append(
        _compute_row(
            "portfolio",
            n_cur=n_p,
            mean=mean_p,
            sigma=sigma_p,
            weeks=args.weeks,
        )
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.out_dir / f"sample_size_{args.label}.json"
    out_md = args.out_dir / f"sample_size_{args.label}.md"
    out_json.write_text(
        json.dumps({"label": args.label, "rows": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    out_md.write_text(_render_markdown(rows, args.label), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
