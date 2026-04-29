from __future__ import annotations

import ast
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_bars_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "load_bars":
                calls.append(node)
    return calls


def _requires_positive_prices(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "require_positive_prices":
            return isinstance(kw.value, ast.Constant) and kw.value.value is True
    return False


def test_strategy_script_load_bars_calls_request_tradable_prices() -> None:
    offenders: list[str] = []
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        for call in _load_bars_calls(path):
            if not _requires_positive_prices(call):
                offenders.append(f"{path.name}:{call.lineno}")

    assert offenders == []
