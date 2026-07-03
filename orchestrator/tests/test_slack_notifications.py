from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.config import SlackSettings
from app.models import ActionDecision, ActionExecution, ActionName, ValidationResult
from app.notifications.webhook import SlackNotifier


@pytest.mark.asyncio
async def test_slack_notifier_sends_started_message(monkeypatch):
    payloads = []

    async def fake_post_webhook(url, payload, *, timeout):
        payloads.append((url, payload, timeout))

    monkeypatch.setattr("app.notifications.webhook.post_webhook", fake_post_webhook)
    notifier = SlackNotifier(
        SlackSettings(enabled=True, webhook_url=SecretStr("https://hooks.slack.test/abc"), timeout_seconds=3)
    )

    await notifier.action_started(
        ActionDecision(
            alertname="MySQLDown",
            host="db-node-01.example.local",
            action=ActionName.RESTART_MARIADB,
            allowed=True,
            reason="allowed",
        )
    )

    assert payloads[0][0] == "https://hooks.slack.test/abc"
    assert payloads[0][2] == 3
    assert "🚨 Autoheal iniciado" in payloads[0][1]["text"]
    assert "Ação: restart_mariadb" in payloads[0][1]["text"]


@pytest.mark.asyncio
async def test_slack_notifier_sends_finished_message(monkeypatch):
    payloads = []

    async def fake_post_webhook(url, payload, *, timeout):
        payloads.append(payload)

    monkeypatch.setattr("app.notifications.webhook.post_webhook", fake_post_webhook)
    notifier = SlackNotifier(SlackSettings(enabled=True, webhook_url=SecretStr("https://hooks.slack.test/abc")))
    execution = ActionExecution(
        decision=ActionDecision(
            alertname="MySQLDown",
            host="db-node-01.example.local",
            action=ActionName.RESTART_MARIADB,
            allowed=True,
            reason="allowed",
        ),
        status="success",
        validation=ValidationResult(name="mysqladmin_ping", success=True, detail="server is alive"),
    )

    await notifier.action_finished(execution, duration_seconds=8.2)

    assert "✅ Autoheal concluído" in payloads[0]["text"]
    assert "Validação: sucesso" in payloads[0]["text"]
    assert "Duração: 8s" in payloads[0]["text"]


@pytest.mark.asyncio
async def test_slack_notifier_sends_circuit_breaker_message(monkeypatch):
    payloads = []

    async def fake_post_webhook(url, payload, *, timeout):
        payloads.append(payload)

    monkeypatch.setattr("app.notifications.webhook.post_webhook", fake_post_webhook)
    notifier = SlackNotifier(SlackSettings(enabled=True, webhook_url=SecretStr("https://hooks.slack.test/abc")))
    execution = ActionExecution(
        decision=ActionDecision(
            alertname="MySQLDown",
            host="db-node-01.example.local",
            action=ActionName.RESTART_MARIADB,
            allowed=True,
            reason="allowed",
        ),
        status="blocked",
        blocked_reason="circuit breaker open: 2/2 attempts for mariadb in 15m",
    )

    await notifier.action_blocked(execution)

    assert "⚠️ Autoheal bloqueado por circuit breaker" in payloads[0]["text"]
    assert "Motivo: circuit breaker open" in payloads[0]["text"]
