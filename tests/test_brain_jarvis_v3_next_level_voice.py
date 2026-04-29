from __future__ import annotations

import json
from datetime import UTC, datetime

from eta_engine.brain.jarvis_v3.next_level.voice import (
    Channel,
    InboundMessage,
    VoiceHub,
)


def test_voice_hub_strips_jarvis_prefix_and_dispatches_bounded_query(tmp_path) -> None:
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        json.dumps(
            {
                "ts": datetime(2026, 4, 29, tzinfo=UTC).isoformat(),
                "request_id": "abc123",
                "verdict": "DENIED",
                "reason": "risk cap breached",
                "reason_code": "risk_cap",
                "stress_composite": 0.72,
            }
        ),
        encoding="utf-8",
    )
    hub = VoiceHub(audit)
    msg = InboundMessage(
        ts=datetime(2026, 4, 29, tzinfo=UTC),
        channel=Channel.TELEGRAM,
        text="jarvis why denied request abc123",
    )

    reply = hub.handle_inbound(msg)

    assert reply.channel is Channel.TELEGRAM
    assert reply.priority == "INFO"
    assert reply.text.startswith("[WHY_VERDICT]")
    assert "risk cap breached" in reply.text


def test_voice_hub_builds_critical_fanout_and_briefing_highlights(tmp_path) -> None:
    hub = VoiceHub(tmp_path / "missing.jsonl")

    alerts = hub.emit_critical("KILL", "daily loss cap hit")
    briefing = hub.build_briefing(
        regime="CRISIS",
        session_phase="OPEN_DRIVE",
        stress=0.82,
        open_risk_r=1.5,
        daily_dd_pct=0.025,
        active_alerts=["kill-switch", "broker-latency"],
        top_subsystems=["JARVIS", "Sage", "Quantum"],
    )

    assert [a.channel for a in alerts] == [Channel.TELEGRAM, Channel.SMS]
    assert alerts[0].fanout_on_failure is True
    assert alerts[1].fanout_on_failure is False
    assert alerts[0].text == "[KILL] daily loss cap hit"
    assert "Capital-first" in briefing.script
    assert "kill-switch" in briefing.highlights
    assert "open_risk=1.50R" in briefing.highlights


async def test_voice_hub_send_uses_injected_sender(tmp_path) -> None:
    sent: list[tuple[Channel, str, str]] = []
    hub = VoiceHub(
        tmp_path / "missing.jsonl",
        sender=lambda channel, text, priority: sent.append((channel, text, priority)),
    )
    msg = hub.emit_critical("RED", "review required", channels=(Channel.CONSOLE,))[0]

    await hub.send(msg)

    assert sent == [(Channel.CONSOLE, "[RED] review required", "CRITICAL")]
