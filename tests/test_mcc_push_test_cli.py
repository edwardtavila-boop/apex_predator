"""Tests for ``apex_predator.scripts._mcc_push_test`` CLI.

Pin the three exit-code branches:

* ``0`` -- at least one delivered.
* ``1`` -- attempted but every send failed.
* ``2`` -- nothing attempted (deps / env / subs missing).

The CLI delegates to :func:`obs.mcc_push_sender.send_to_all`; we stub
pywebpush at the sys.modules level so no real network sends fire.
"""

from __future__ import annotations

import json
import sys
import types
from typing import TYPE_CHECKING

import pytest

from apex_predator.obs import mcc_push_sender as ps
from apex_predator.scripts import _mcc_push_test as cli

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def push_state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ps, "PUSH_SUBSCRIPTIONS", tmp_path / "subs.jsonl")
    monkeypatch.setattr(ps, "DEAD_SUBSCRIPTIONS", tmp_path / "dead.jsonl")
    return tmp_path


def _write_subs(path: Path, subs: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(s) for s in subs) + "\n", encoding="utf-8")


def _install_stub_pywebpush(monkeypatch, *, fail_endpoints: set[str] | None = None) -> None:
    fail = fail_endpoints or set()

    class WebPushException(Exception):  # noqa: N818
        def __init__(self, message: str, response: object = None) -> None:
            super().__init__(message)
            self.response = response

    def webpush(**kwargs):
        if kwargs["subscription_info"]["endpoint"] in fail:
            raise WebPushException("simulated")
        return None

    stub = types.ModuleType("pywebpush")
    stub.webpush = webpush  # type: ignore[attr-defined]
    stub.WebPushException = WebPushException  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pywebpush", stub)


def _vapid(monkeypatch) -> None:
    monkeypatch.setenv("MCC_VAPID_PUBLIC_KEY", "p")
    monkeypatch.setenv("MCC_VAPID_PRIVATE_KEY", "k")
    monkeypatch.setenv("MCC_VAPID_SUBJECT", "mailto:o@example.com")


class TestExitCodes:
    def test_exit_0_on_at_least_one_delivered(
        self,
        push_state: Path,
        monkeypatch,
        capsys,
    ) -> None:
        _install_stub_pywebpush(monkeypatch)
        _vapid(monkeypatch)
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )
        rc = cli.main(["--severity", "info"])
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["delivered"] == 1
        assert parsed["ok"] is True

    def test_exit_1_when_attempted_but_all_failed(
        self,
        push_state: Path,
        monkeypatch,
        capsys,
    ) -> None:
        _install_stub_pywebpush(monkeypatch, fail_endpoints={"https://A"})
        _vapid(monkeypatch)
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )
        rc = cli.main([])
        assert rc == 1
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["attempted"] == 1
        assert parsed["delivered"] == 0
        assert parsed["failed"] == 1

    def test_exit_2_on_no_subscriptions(
        self,
        push_state: Path,
        monkeypatch,
        capsys,
    ) -> None:
        _install_stub_pywebpush(monkeypatch)
        _vapid(monkeypatch)
        # No subscriptions file.
        rc = cli.main([])
        assert rc == 2
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["attempted"] == 0
        assert "no-subscriptions" in parsed["skipped"]

    def test_exit_2_on_missing_vapid_env(
        self,
        push_state: Path,
        monkeypatch,
        capsys,
    ) -> None:
        _install_stub_pywebpush(monkeypatch)
        # No VAPID env set.
        for key in ("MCC_VAPID_PUBLIC_KEY", "MCC_VAPID_PRIVATE_KEY", "MCC_VAPID_SUBJECT"):
            monkeypatch.delenv(key, raising=False)
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )
        rc = cli.main([])
        assert rc == 2
        parsed = json.loads(capsys.readouterr().out)
        assert "vapid-env-missing" in parsed["skipped"]

    def test_severity_argument_propagates(
        self,
        push_state: Path,
        monkeypatch,
        capsys,
    ) -> None:
        # Capture the kwargs send_to_all sends to webpush -- urgency
        # should be 'high' for critical.
        captured = []

        class WebPushException(Exception):  # noqa: N818
            pass

        def webpush(**kwargs):
            captured.append(kwargs)
            return None

        stub = types.ModuleType("pywebpush")
        stub.webpush = webpush  # type: ignore[attr-defined]
        stub.WebPushException = WebPushException  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "pywebpush", stub)
        _vapid(monkeypatch)
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )

        rc = cli.main(["--severity", "critical"])
        assert rc == 0
        assert captured[0]["headers"]["Urgency"] == "high"
        # 'extra' field threads through the payload as 'mcc_self_test'.
        payload = json.loads(captured[0]["data"])
        assert payload["extra"]["event"] == "mcc_self_test"
        assert payload["severity"] == "critical"
