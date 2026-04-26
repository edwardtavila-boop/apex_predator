"""
EVOLUTIONARY TRADING ALGO  //  tests.test_alert_transports
==============================================
Exercise the concrete transport functions in obs.alert_dispatcher:
    _send_pushover, _send_email, _send_sms.

Uses monkeypatched urllib / smtplib so no real network.
"""

from __future__ import annotations

import base64
import io
import urllib.error
from typing import Any

import pytest  # noqa: TC002 - used for pytest.MonkeyPatch type hint under `from __future__ import annotations`

from eta_engine.obs import alert_dispatcher as mod


# --------------------------------------------------------------------------- #
# Pushover
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *a: Any) -> None:  # noqa: ANN401 - exit signature must accept arbitrary args
        return None


def test_send_pushover_returns_true_on_api_status_1(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        captured["url"] = req.full_url
        captured["data"] = req.data
        return _FakeResp(200, b'{"status":1, "request":"abc"}')

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    ok = mod._send_pushover("USER", "TOKEN", "hello", "world", priority=1)
    assert ok is True
    assert "pushover.net" in captured["url"]
    # Body is URL-encoded form
    assert b"user=USER" in captured["data"]
    assert b"token=TOKEN" in captured["data"]
    assert b"priority=1" in captured["data"]


def test_send_pushover_returns_false_on_api_status_0(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        return _FakeResp(200, b'{"status":0, "errors":["invalid token"]}')

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod._send_pushover("u", "t", "title", "body") is False


def test_send_pushover_returns_false_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod._send_pushover("u", "t", "title", "body") is False


def test_send_pushover_truncates_long_title_and_message(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        captured["data"] = req.data
        return _FakeResp(200, b'{"status":1}')

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    long_title = "X" * 500
    long_msg = "Y" * 2000
    mod._send_pushover("u", "t", long_title, long_msg)
    # Title capped at 250, body capped at 1024.
    assert b"X" * 250 in captured["data"]
    assert b"X" * 251 not in captured["data"]
    assert b"Y" * 1024 in captured["data"]
    assert b"Y" * 1025 not in captured["data"]


# --------------------------------------------------------------------------- #
# SMTP email
# --------------------------------------------------------------------------- #
class _FakeSMTP:
    def __init__(self, host: str, port: int, timeout: float = 10) -> None:  # noqa: ARG002
        self.host = host
        self.port = port
        self.ehlo_called = 0
        self.starttls_called = False
        self.logged_in_with: tuple[str, str] | None = None
        self.sent: list[tuple[str, list[str], str]] = []
        self._has_starttls = True
        self.quit_called = False

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *a: Any) -> None:  # noqa: ANN401 - context-manager exit signature
        self.quit_called = True

    def ehlo(self) -> None:
        self.ehlo_called += 1

    def has_extn(self, name: str) -> bool:
        return name == "STARTTLS" and self._has_starttls

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, user: str, password: str) -> None:
        self.logged_in_with = (user, password)

    def sendmail(self, from_addr: str, to_addrs: list[str], msg: str) -> None:
        self.sent.append((from_addr, to_addrs, msg))


def test_send_email_login_and_sendmail(monkeypatch: pytest.MonkeyPatch) -> None:
    holder: dict[str, _FakeSMTP] = {}

    def factory(host: str, port: int, timeout: float = 10) -> _FakeSMTP:
        smtp = _FakeSMTP(host, port, timeout)
        holder["smtp"] = smtp
        return smtp

    monkeypatch.setattr(mod.smtplib, "SMTP", factory)
    ok = mod._send_email(
        "smtp.example.com", 587, "user@x", "secret",
        "from@x", "to@x", "APEX KILL", "Body here",
    )
    assert ok is True
    smtp = holder["smtp"]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.starttls_called is True
    assert smtp.logged_in_with == ("user@x", "secret")
    assert len(smtp.sent) == 1
    from_addr, to_addrs, msg = smtp.sent[0]
    assert from_addr == "from@x"
    assert to_addrs == ["to@x"]
    assert "APEX KILL" in msg
    # MIMEText base64-encodes utf-8 bodies by default.
    assert base64.b64encode(b"Body here").decode() in msg


def test_send_email_returns_false_on_smtp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import smtplib

    class _Boom:
        def __init__(self, *a: Any, **kw: Any) -> None:  # noqa: ANN401 - fake factory accepts any SMTP ctor args
            raise smtplib.SMTPException("connection refused")

    monkeypatch.setattr(mod.smtplib, "SMTP", _Boom)
    ok = mod._send_email("h", 587, "u", "p", "f@x", "t@x", "s", "b")
    assert ok is False


def test_send_email_without_starttls_still_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plain-text SMTP path (server doesn't advertise STARTTLS)."""

    def factory(host: str, port: int, timeout: float = 10) -> _FakeSMTP:
        smtp = _FakeSMTP(host, port, timeout)
        smtp._has_starttls = False
        return smtp

    monkeypatch.setattr(mod.smtplib, "SMTP", factory)
    ok = mod._send_email("h", 25, "u", "p", "f@x", "t@x", "s", "b")
    assert ok is True


# --------------------------------------------------------------------------- #
# Twilio SMS
# --------------------------------------------------------------------------- #
def test_send_sms_posts_with_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["headers"] = dict(req.header_items())
        return _FakeResp(201, b"")

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    ok = mod._send_sms("SID123", "TOKEN456", "+10000000000", "+15555550123", "kill fired")
    assert ok is True
    # URL must contain the SID
    assert "SID123" in captured["url"]
    # Basic auth header with correct b64 payload
    expected = base64.b64encode(b"SID123:TOKEN456").decode()
    assert any(h.lower() == "authorization" and v == f"Basic {expected}" for h, v in captured["headers"].items())
    # Form body contains From/To/Body
    body = captured["data"].decode()
    assert "From=%2B10000000000" in body
    assert "To=%2B15555550123" in body
    assert "Body=kill+fired" in body


def test_send_sms_returns_false_on_non_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        raise urllib.error.HTTPError(req.full_url, 400, "bad request", {}, io.BytesIO(b"bad"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod._send_sms("s", "t", "+1", "+2", "x") is False


def test_send_sms_truncates_body_to_1600(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        captured["data"] = req.data
        return _FakeResp(201, b"")

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    mod._send_sms("s", "t", "+1", "+2", "Z" * 2000)
    # Inspect URL-decoded body length for Body= param
    import urllib.parse as up
    parsed = dict(up.parse_qsl(captured["data"].decode()))
    assert len(parsed["Body"]) == 1600


# --------------------------------------------------------------------------- #
# Resend
# --------------------------------------------------------------------------- #
def test_send_resend_returns_true_on_id_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["data"] = req.data
        return _FakeResp(200, b'{"id":"6f3aa9c2-7b52-4f92-b9f9-7c6e6abf"}')

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    ok = mod._send_resend(
        "re_TEST_KEY",
        "Apex Alerts <alerts@evolutionarytradingalgo.live>",
        "edward.t.avila@gmail.com",
        "[apex] kill switch tripped",
        "tier_a cushion 0",
    )
    assert ok is True
    assert captured["url"] == "https://api.resend.com/emails"
    # bearer auth + JSON content-type
    assert any(h.lower() == "authorization" and v == "Bearer re_TEST_KEY"
               for h, v in captured["headers"].items())
    assert any(h.lower() == "content-type" and v == "application/json"
               for h, v in captured["headers"].items())
    # body shape — minimal fields, list-wrapped recipient
    import json as _json
    payload = _json.loads(captured["data"].decode())
    assert payload["from"] == "Apex Alerts <alerts@evolutionarytradingalgo.live>"
    assert payload["to"] == ["edward.t.avila@gmail.com"]
    assert payload["subject"] == "[apex] kill switch tripped"
    assert payload["text"] == "tier_a cushion 0"


def test_send_resend_returns_false_when_id_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 with no id is a malformed Resend response — treat as failure."""
    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        return _FakeResp(200, b'{}')

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod._send_resend("k", "f", "t", "s", "b") is False


def test_send_resend_returns_false_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """4xx from Resend (e.g. unverified domain, invalid key) is failure."""
    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        raise urllib.error.HTTPError(
            req.full_url, 422, "Unprocessable Entity",
            {}, io.BytesIO(b'{"message":"domain not verified"}'),
        )

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod._send_resend("k", "f", "t", "s", "b") is False


def test_send_resend_returns_false_on_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Network error is failure (no exception leaks)."""
    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod._send_resend("k", "f", "t", "s", "b") is False


def test_send_resend_truncates_subject_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """Long subject/body capped (Resend has limits + we don't want runaway logs)."""
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=None) -> _FakeResp:  # noqa: ANN001 - mirrors urlopen signature
        captured["data"] = req.data
        return _FakeResp(200, b'{"id":"x"}')

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    mod._send_resend("k", "f", "t", "S" * 500, "B" * 20000)
    import json as _json
    payload = _json.loads(captured["data"].decode())
    assert len(payload["subject"]) == 250
    assert len(payload["text"]) == 8192


def test_email_channel_prefers_resend_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """If RESEND_API_KEY is set, the email channel routes via Resend, not SMTP."""
    monkeypatch.setenv("RESEND_API_KEY", "re_FROM_OPERATOR_ENV")
    monkeypatch.setenv("FROM_EMAIL", "Apex Alerts <alerts@evolutionarytradingalgo.live>")

    resend_called: dict[str, Any] = {}
    smtp_called: dict[str, Any] = {}

    def fake_resend(api_key, from_addr, to_addr, subject, body):  # noqa: ANN001 - mirrors signature
        resend_called["api_key"] = api_key
        resend_called["from"] = from_addr
        resend_called["to"] = to_addr
        return True

    def fake_email(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003 - shouldn't be called
        smtp_called["called"] = True
        return True

    monkeypatch.setattr(mod, "_send_resend", fake_resend)
    monkeypatch.setattr(mod, "_send_email", fake_email)

    cfg = {
        "channels": {
            "email": {
                "enabled": True,
                "to": "edward.t.avila@gmail.com",
                "env_keys": {
                    "smtp_host": "SMTP_HOST",
                    "smtp_port": "SMTP_PORT",
                    "smtp_user": "SMTP_USER",
                    "smtp_pass": "SMTP_PASS",
                },
            },
        },
        "routing": {"events": {"kill_switch": {"level": "critical", "channels": ["email"]}}},
    }
    dispatcher = mod.AlertDispatcher(cfg)
    result = dispatcher.send("kill_switch", {"reason": "test"})
    # Resend was called, SMTP was not.
    assert resend_called["api_key"] == "re_FROM_OPERATOR_ENV"
    assert resend_called["to"] == "edward.t.avila@gmail.com"
    assert "called" not in smtp_called, "SMTP should NOT be invoked when RESEND_API_KEY is set"
    assert "email" in result.delivered
    assert "email" not in [b.split(":")[0] for b in result.blocked]


def test_email_channel_falls_back_to_smtp_when_resend_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """No RESEND_API_KEY → falls through to SMTP path (existing behavior)."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "u@x.com")
    monkeypatch.setenv("SMTP_PASS", "p")

    resend_called: dict[str, Any] = {}
    smtp_called: dict[str, Any] = {}

    def fake_resend(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003 - shouldn't be called
        resend_called["called"] = True
        return True

    def fake_email(host, port, user, pw, from_a, to_a, subj, body):  # noqa: ANN001 - mirrors signature
        smtp_called["host"] = host
        smtp_called["to"] = to_a
        return True

    monkeypatch.setattr(mod, "_send_resend", fake_resend)
    monkeypatch.setattr(mod, "_send_email", fake_email)

    cfg = {
        "channels": {
            "email": {
                "enabled": True,
                "to": "edward.t.avila@gmail.com",
                "env_keys": {
                    "smtp_host": "SMTP_HOST",
                    "smtp_port": "SMTP_PORT",
                    "smtp_user": "SMTP_USER",
                    "smtp_pass": "SMTP_PASS",
                },
            },
        },
        "routing": {"events": {"kill_switch": {"level": "critical", "channels": ["email"]}}},
    }
    dispatcher = mod.AlertDispatcher(cfg)
    dispatcher.send("kill_switch", {"reason": "test"})
    assert "called" not in resend_called, "Resend should NOT be invoked when key is missing"
    assert smtp_called["host"] == "smtp.gmail.com"
