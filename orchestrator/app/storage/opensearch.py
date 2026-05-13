from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import OpenSearchSettings
from app.models import ActionExecution


class OpenSearchIndexer:
    def __init__(self, settings: OpenSearchSettings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return self.settings.enabled and bool(self.settings.hosts)

    def index_name(self) -> str:
        return f"infra-incidents-{datetime.now(UTC):%Y.%m.%d}"

    def document(self, execution: ActionExecution) -> dict[str, Any]:
        return {
            "timestamp": execution.decision.timestamp.isoformat(),
            "correlation_id": execution.decision.correlation_id,
            "host": execution.decision.host,
            "alertname": execution.decision.alertname,
            "action": execution.decision.action.value if execution.decision.action else None,
            "status": execution.status,
            "evidence": execution.evidence.model_dump(mode="json") if execution.evidence else {},
        }

    def index(self, execution: ActionExecution) -> None:
        if not self.enabled():
            return
        from opensearchpy import OpenSearch

        client = OpenSearch(
            hosts=self.settings.hosts,
            http_auth=(self.settings.username, self.settings.password)
            if self.settings.username and self.settings.password
            else None,
        )
        client.index(index=self.index_name(), body=self.document(execution))
