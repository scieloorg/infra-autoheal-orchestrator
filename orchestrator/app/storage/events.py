from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models import ActionExecution


class EventStore:
    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    alertname TEXT NOT NULL,
                    host TEXT NOT NULL,
                    action TEXT,
                    status TEXT NOT NULL,
                    blocked_reason TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def record(self, execution: ActionExecution) -> None:
        payload = execution.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO action_events (
                    timestamp, correlation_id, alertname, host, action, status, blocked_reason, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.decision.timestamp.isoformat(),
                    execution.decision.correlation_id,
                    execution.decision.alertname,
                    execution.decision.host,
                    execution.decision.action.value if execution.decision.action else None,
                    execution.status,
                    execution.blocked_reason,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def list_events(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM action_events ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
