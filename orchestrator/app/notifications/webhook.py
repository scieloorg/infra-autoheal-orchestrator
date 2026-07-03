from __future__ import annotations

import httpx
import structlog

from app.config import SlackSettings
from app.models import ActionDecision, ActionExecution

log = structlog.get_logger()


async def post_webhook(url: str, payload: dict, *, timeout: int = 10) -> None:
    async with httpx.AsyncClient(timeout=timeout) as client:
        await client.post(url, json=payload)


class SlackNotifier:
    def __init__(self, settings: SlackSettings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return (
            self.settings.enabled
            and self.settings.webhook_url is not None
            and bool(self.settings.webhook_url.get_secret_value())
        )

    async def action_started(self, decision: ActionDecision) -> None:
        if decision.action is None:
            return
        await self._post(
            "\n".join(
                [
                    "🚨 Autoheal iniciado",
                    f"Host: {decision.host}",
                    f"Alerta: {decision.alertname}",
                    f"Ação: {decision.action.value}",
                    f"Correlation ID: {decision.correlation_id}",
                ]
            )
        )

    async def action_finished(self, execution: ActionExecution, *, duration_seconds: float) -> None:
        if execution.decision.action is None:
            return
        if execution.status == "success":
            validation = "sucesso" if not execution.validation or execution.validation.success else "falha"
            await self._post(
                "\n".join(
                    [
                        "✅ Autoheal concluído",
                        f"Host: {execution.decision.host}",
                        f"Ação: {execution.decision.action.value}",
                        f"Validação: {validation}",
                        f"Duração: {_format_duration(duration_seconds)}",
                        f"Correlation ID: {execution.decision.correlation_id}",
                    ]
                )
            )
            return

        reason = _failure_reason(execution)
        await self._post(
            "\n".join(
                [
                    "❌ Autoheal falhou",
                    f"Host: {execution.decision.host}",
                    f"Ação: {execution.decision.action.value}",
                    f"Motivo: {reason}",
                    "Próximo passo: intervenção humana",
                    f"Duração: {_format_duration(duration_seconds)}",
                    f"Correlation ID: {execution.decision.correlation_id}",
                ]
            )
        )

    async def action_blocked(self, execution: ActionExecution) -> None:
        if execution.status != "blocked":
            return
        title = (
            "⚠️ Autoheal bloqueado por circuit breaker"
            if execution.blocked_reason and "circuit breaker open" in execution.blocked_reason
            else "⚠️ Autoheal bloqueado"
        )
        action = execution.decision.action.value if execution.decision.action else "nenhuma"
        await self._post(
            "\n".join(
                [
                    title,
                    f"Host: {execution.decision.host}",
                    f"Alerta: {execution.decision.alertname}",
                    f"Ação: {action}",
                    f"Motivo: {execution.blocked_reason or execution.decision.reason}",
                    f"Correlation ID: {execution.decision.correlation_id}",
                ]
            )
        )

    async def _post(self, text: str) -> None:
        if not self.enabled() or self.settings.webhook_url is None:
            return
        try:
            await post_webhook(
                self.settings.webhook_url.get_secret_value(),
                {"text": text},
                timeout=self.settings.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - defensive logging around external dependency
            log.warning("slack_notification_failed", error=exc.__class__.__name__)


def _format_duration(duration_seconds: float) -> str:
    if duration_seconds < 1:
        return f"{duration_seconds:.1f}s"
    return f"{duration_seconds:.0f}s"


def _failure_reason(execution: ActionExecution) -> str:
    if execution.blocked_reason:
        return execution.blocked_reason
    if execution.validation and not execution.validation.success:
        return "validação falhou"
    failed_commands = [command for command in execution.commands if command.exit_code != 0]
    if failed_commands:
        return f"comando falhou: {failed_commands[0].command}"
    return "ação não concluída"
