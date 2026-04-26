"""Tests for ``apex_predator.scripts._mcc_push_housekeeping``.

Two layers:

1. **Capture** -- when ``obs.mcc_push_sender.send_to_all`` hits a
   :class:`pywebpush.WebPushException` with ``status_code == 410``,
   the dead endpoint must (a) appear in ``PushResult.dead_endpoints``
   and (b) be appended to the side-channel ``DEAD_SUBSCRIPTIONS`` file.
2. **Prune** -- the housekeeping script reads that side-channel,
   rewrites the live subscriptions file (atomic), and truncates the
   dead-list. Idempotent and crash-safe.
"""

from __future__ import annotations

import json
import sys
import types
from typing import TYPE_CHECKING

import pytest

from apex_predator.obs import mcc_push_sender as ps
from apex_predator.scripts import _mcc_push_housekeeping as hk

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def push_state(tmp_path: Path, monkeypatch):
    """Redirect every MCC push file path into tmp."""
    monkeypatch.setattr(ps, "PUSH_SUBSCRIPTIONS", tmp_path / "subs.jsonl")
    monkeypatch.setattr(ps, "DEAD_SUBSCRIPTIONS", tmp_path / "dead.jsonl")
    monkeypatch.setattr(hk, "PUSH_SUBSCRIPTIONS", tmp_path / "subs.jsonl")
    monkeypatch.setattr(hk, "DEAD_SUBSCRIPTIONS", tmp_path / "dead.jsonl")
    return tmp_path


def _write_subs(path: Path, subs: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(s) for s in subs) + "\n", encoding="utf-8")


def _install_stub_pywebpush(monkeypatch, *, dead_endpoints: set[str] | None = None) -> list[dict]:
    """Install a stub pywebpush. Endpoints in ``dead_endpoints`` raise 410."""
    received: list[dict] = []
    dead_endpoints = dead_endpoints or set()

    class WebPushException(Exception):  # noqa: N818 -- mirror real name
        def __init__(self, message: str, response: object = None) -> None:
            super().__init__(message)
            self.response = response

    class _Resp:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    def webpush(**kwargs):
        endpoint = kwargs["subscription_info"]["endpoint"]
        received.append(kwargs)
        if endpoint in dead_endpoints:
            raise WebPushException("simulated 410", response=_Resp(410))
        return None

    stub = types.ModuleType("pywebpush")
    stub.webpush = webpush  # type: ignore[attr-defined]
    stub.WebPushException = WebPushException  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pywebpush", stub)
    return received


def _vapid(monkeypatch) -> None:
    monkeypatch.setenv("MCC_VAPID_PUBLIC_KEY", "p")
    monkeypatch.setenv("MCC_VAPID_PRIVATE_KEY", "k")
    monkeypatch.setenv("MCC_VAPID_SUBJECT", "mailto:o@example.com")


# ---------------------------------------------------------------------------
# Capture: 410 lands in PushResult.dead_endpoints AND in dead.jsonl
# ---------------------------------------------------------------------------


class TestCapture:
    def test_410_records_dead_endpoint_in_result_and_file(
        self,
        push_state: Path,
        monkeypatch,
    ) -> None:
        _install_stub_pywebpush(monkeypatch, dead_endpoints={"https://B"})
        _vapid(monkeypatch)
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
                {"endpoint": "https://B", "keys": {"p256dh": "k", "auth": "a"}},
                {"endpoint": "https://C", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )

        result = ps.send_to_all("warn", "t", "b")
        # Result surfaces the dead endpoint.
        assert result.dead_endpoints == ["https://B"]
        # Counts unchanged: B failed, A and C delivered.
        assert result.delivered == 2
        assert result.failed == 1
        # Dead-list file was appended to.
        dead_lines = (push_state / "dead.jsonl").read_text().strip().splitlines()
        assert len(dead_lines) == 1
        assert json.loads(dead_lines[0])["endpoint"] == "https://B"

    def test_non_410_failure_is_not_recorded_as_dead(
        self,
        push_state: Path,
        monkeypatch,
    ) -> None:
        # Stub that raises a non-410 for every send (e.g. transient 500).
        received: list[dict] = []

        class WebPushException(Exception):  # noqa: N818
            def __init__(self, message: str, response: object = None) -> None:
                super().__init__(message)
                self.response = response

        class _Resp:
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code

        def webpush(**kwargs):
            received.append(kwargs)
            raise WebPushException("transient", response=_Resp(500))

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

        result = ps.send_to_all("info", "t", "b")
        # Failure was counted but the endpoint is NOT dead -- transient 500.
        assert result.failed == 1
        assert result.dead_endpoints == []
        # Dead file is empty / nonexistent.
        dead_path = push_state / "dead.jsonl"
        assert (not dead_path.exists()) or dead_path.read_text().strip() == ""

    def test_410_via_no_response_object_does_not_crash(
        self,
        push_state: Path,
        monkeypatch,
    ) -> None:
        # Defensive: WebPushException with response=None should be treated
        # as "not 410" (status==None) -- the sender must not raise.
        class WebPushException(Exception):  # noqa: N818
            def __init__(self, message: str) -> None:
                super().__init__(message)
                self.response = None

        def webpush(**kwargs):
            raise WebPushException("no response")

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

        result = ps.send_to_all("info", "t", "b")
        assert result.failed == 1
        assert result.dead_endpoints == []


# ---------------------------------------------------------------------------
# Prune: housekeeping rewrites subs file + truncates dead file
# ---------------------------------------------------------------------------


class TestPrune:
    def test_no_dead_no_op(self, push_state: Path) -> None:
        subs = [{"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}}]
        _write_subs(push_state / "subs.jsonl", subs)
        # No dead file at all.
        summary = hk.prune()
        assert summary["dead_count"] == 0
        assert summary["pruned_count"] == 0
        # Subs file is untouched.
        assert ps.read_subscriptions() == subs

    def test_prunes_only_matching_endpoints(self, push_state: Path) -> None:
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
                {"endpoint": "https://B", "keys": {"p256dh": "k", "auth": "a"}},
                {"endpoint": "https://C", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )
        (push_state / "dead.jsonl").write_text(
            json.dumps({"endpoint": "https://B"}) + "\n" + json.dumps({"endpoint": "https://NOT_PRESENT"}) + "\n",
            encoding="utf-8",
        )

        summary = hk.prune()
        assert summary["dry_run"] is False
        assert summary["dead_count"] == 2
        assert summary["pruned_count"] == 1
        assert summary["pruned"] == ["https://B"]
        # Subs file no longer contains B.
        endpoints = [s["endpoint"] for s in ps.read_subscriptions()]
        assert endpoints == ["https://A", "https://C"]
        # Dead file is truncated to empty.
        assert (push_state / "dead.jsonl").read_text() == ""

    def test_dry_run_writes_nothing(self, push_state: Path) -> None:
        subs = [
            {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
            {"endpoint": "https://B", "keys": {"p256dh": "k", "auth": "a"}},
        ]
        _write_subs(push_state / "subs.jsonl", subs)
        (push_state / "dead.jsonl").write_text(
            json.dumps({"endpoint": "https://B"}) + "\n",
            encoding="utf-8",
        )

        summary = hk.prune(dry_run=True)
        assert summary["dry_run"] is True
        assert summary["pruned_count"] == 1
        # NEITHER file changed.
        assert ps.read_subscriptions() == subs
        assert (push_state / "dead.jsonl").read_text().strip() != ""

    def test_idempotent_rerun(self, push_state: Path) -> None:
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
                {"endpoint": "https://B", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )
        (push_state / "dead.jsonl").write_text(
            json.dumps({"endpoint": "https://B"}) + "\n",
            encoding="utf-8",
        )

        first = hk.prune()
        second = hk.prune()
        assert first["pruned_count"] == 1
        assert second["pruned_count"] == 0
        assert second["dead_count"] == 0
        # Subs file unchanged across the second run.
        endpoints = [s["endpoint"] for s in ps.read_subscriptions()]
        assert endpoints == ["https://A"]

    def test_atomic_write_uses_tmp_then_rename(self, push_state: Path, monkeypatch) -> None:
        """The .tmp file is created and replaced over the live file."""
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
                {"endpoint": "https://B", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )
        (push_state / "dead.jsonl").write_text(
            json.dumps({"endpoint": "https://B"}) + "\n",
            encoding="utf-8",
        )

        # Spy on Path.replace -- the atomic-write step must call it.
        original_replace = type(push_state).replace
        seen: list[tuple] = []

        def spy_replace(self, target):
            seen.append((str(self), str(target)))
            return original_replace(self, target)

        monkeypatch.setattr(type(push_state), "replace", spy_replace)
        hk.prune()
        # Expect exactly one tmp -> live rename for the subs file.
        assert any(src.endswith(".jsonl.tmp") and dst.endswith("subs.jsonl") for src, dst in seen)

    def test_corrupt_dead_file_lines_skipped(self, push_state: Path) -> None:
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )
        (push_state / "dead.jsonl").write_text(
            "not json\n" + json.dumps({"endpoint": "https://A"}) + "\n" + "{not_closed\n",
            encoding="utf-8",
        )
        summary = hk.prune()
        assert summary["pruned"] == ["https://A"]
        assert ps.read_subscriptions() == []


# ---------------------------------------------------------------------------
# CLI: main() returns 0; quiet mode prints single-line JSON
# ---------------------------------------------------------------------------


class TestCli:
    def test_main_returns_0_on_no_op(self, push_state: Path, capsys) -> None:
        rc = hk.main([])
        assert rc == 0
        out = capsys.readouterr().out
        # Default mode prints indented JSON.
        parsed = json.loads(out)
        assert parsed["dead_count"] == 0

    def test_main_quiet_prints_single_line(self, push_state: Path, capsys) -> None:
        rc = hk.main(["--quiet"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert "\n" not in out
        assert json.loads(out)["dead_count"] == 0

    def test_main_dry_run(self, push_state: Path, capsys) -> None:
        _write_subs(
            push_state / "subs.jsonl",
            [
                {"endpoint": "https://A", "keys": {"p256dh": "k", "auth": "a"}},
            ],
        )
        (push_state / "dead.jsonl").write_text(
            json.dumps({"endpoint": "https://A"}) + "\n",
            encoding="utf-8",
        )
        rc = hk.main(["--dry-run"])
        assert rc == 0
        # Subs file unchanged.
        assert len(ps.read_subscriptions()) == 1
