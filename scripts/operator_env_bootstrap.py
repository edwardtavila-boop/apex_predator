"""Safe operator helper for the canonical eta_engine/.env file.

The command never prints secret values. By default it is read-only; pass
``--create`` to copy ``.env.example`` to ``.env`` if the real file is absent.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from eta_engine.scripts import vps_failover_drill  # noqa: E402


def build_status(*, create: bool = False) -> dict[str, Any]:
    """Return redacted canonical env status, optionally creating .env."""
    env_path = ROOT / ".env"
    template_path = ROOT / ".env.example"
    created = False
    create_error: str | None = None
    if create and not env_path.exists():
        if not template_path.exists():
            create_error = ".env.example missing"
        else:
            try:
                shutil.copyfile(template_path, env_path)
                created = True
            except OSError as exc:
                create_error = f"{type(exc).__name__}: {exc}"

    check = vps_failover_drill._check_secrets_present()
    details = check.details or {}
    return {
        "env_path": str(env_path),
        "template_path": str(template_path),
        "exists": env_path.exists(),
        "created": created,
        "create_error": create_error,
        "severity": check.severity,
        "summary": check.summary,
        "required_missing": details.get("required_missing", {}),
        "recommended_missing": details.get("recommended_missing", {}),
        "values_emitted": False,
        "check": asdict(check),
    }


def _print_human(status: dict[str, Any]) -> None:
    print(f"Canonical env: {status['env_path']}")
    print(f"Exists: {status['exists']}  Created: {status['created']}")
    if status.get("create_error"):
        print(f"Create error: {status['create_error']}")
    print(f"Severity: {str(status['severity']).upper()}")
    print(status["summary"])
    required_missing = status.get("required_missing") or {}
    if required_missing:
        print("Required missing:")
        for group, keys in required_missing.items():
            print(f"- {group}: {', '.join(keys)}")
    recommended_missing = status.get("recommended_missing") or {}
    if recommended_missing:
        print("Recommended missing:")
        for group, keys in recommended_missing.items():
            print(f"- {group}: {', '.join(keys)}")
    print("Secret values emitted: false")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="operator_env_bootstrap")
    parser.add_argument(
        "--create",
        action="store_true",
        help="copy .env.example to .env if .env is missing; never overwrites",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable redacted status")
    args = parser.parse_args(argv)

    status = build_status(create=args.create)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True, default=str))
    else:
        _print_human(status)
    if status.get("create_error"):
        return 3
    return 0 if status["severity"] == "green" else 2


if __name__ == "__main__":
    raise SystemExit(main())
