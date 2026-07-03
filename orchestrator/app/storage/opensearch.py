from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import structlog

from app.config import OpenSearchSettings
from app.models import ActionExecution, CommandResult

log = structlog.get_logger()

SENSITIVE_PATTERNS = [
    (
        re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
        r"\1***REDACTED***",
    ),
    (
        re.compile(r"(?i)((?:token|secret|password|passwd|pwd|api[_-]?key)\s*[=:]\s*)[^\s,;]+"),
        r"\1***REDACTED***",
    ),
    (
        re.compile(r"-----BEGIN [^-]+ PRIVATE KEY-----.*?-----END [^-]+ PRIVATE KEY-----", re.DOTALL),
        "***REDACTED_PRIVATE_KEY***",
    ),
]


class OpenSearchIndexer:
    def __init__(self, settings: OpenSearchSettings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return self.settings.enabled and bool(self.settings.hosts)

    def index_name(self) -> str:
        return f"{self.settings.index_prefix}-{datetime.now(UTC):%Y.%m.%d}"

    def document(self, execution: ActionExecution) -> dict[str, Any]:
        validation = execution.validation.model_dump(mode="json") if execution.validation else None
        return {
            "timestamp": execution.decision.timestamp.isoformat(),
            "correlation_id": execution.decision.correlation_id,
            "host": execution.decision.host,
            "alertname": execution.decision.alertname,
            "action": execution.decision.action.value if execution.decision.action else None,
            "allowed": execution.decision.allowed,
            "decision_reason": execution.decision.reason,
            "status": execution.status,
            "blocked_reason": execution.blocked_reason,
            "validation": _sanitize(validation, max_length=self.settings.max_field_length),
            "commands": [
                _command_document(command, max_length=self.settings.max_field_length)
                for command in execution.commands
            ],
            "evidence": _sanitize(
                execution.evidence.model_dump(mode="json") if execution.evidence else {},
                max_length=self.settings.max_field_length,
            ),
            "proxmox_response": _sanitize(
                execution.proxmox_response or {},
                max_length=self.settings.max_field_length,
            ),
        }

    def index(self, execution: ActionExecution) -> None:
        if not self.enabled():
            return
        try:
            from opensearchpy import OpenSearch

            client = OpenSearch(
                hosts=self.settings.hosts,
                http_auth=(self.settings.username, self.settings.password)
                if self.settings.username and self.settings.password
                else None,
                verify_certs=self.settings.verify_certs,
            )
            client.index(index=self.index_name(), body=self.document(execution))
        except Exception as exc:  # pragma: no cover - defensive logging around external dependency
            log.warning(
                "opensearch_index_failed",
                correlation_id=execution.decision.correlation_id,
                error=exc.__class__.__name__,
            )


def _command_document(command: CommandResult, *, max_length: int) -> dict[str, Any]:
    return {
        "command": command.command,
        "exit_code": command.exit_code,
        "stdout": _sanitize_text(command.stdout, max_length=max_length),
        "stderr": _sanitize_text(command.stderr, max_length=max_length),
    }


def _sanitize(value: Any, *, max_length: int) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value, max_length=max_length)
    if isinstance(value, list):
        return [_sanitize(item, max_length=max_length) for item in value]
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if _is_sensitive_key(str(key)) else _sanitize(item, max_length=max_length)
            for key, item in value.items()
        }
    return value


def _sanitize_text(value: str, *, max_length: int) -> str:
    sanitized = value
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    if len(sanitized) <= max_length:
        return sanitized
    return f"{sanitized[:max_length]}...<truncated {len(sanitized) - max_length} chars>"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("password", "passwd", "pwd", "token", "secret", "api_key"))
