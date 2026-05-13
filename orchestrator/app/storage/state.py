from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


class StateStore:
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
                CREATE TABLE IF NOT EXISTS action_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    host TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    correlation_id TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_attempts_target
                ON action_attempts(host, action_type, target, timestamp)
                """
            )

    def count_attempts(self, *, host: str, action_type: str, target: str, window_minutes: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM action_attempts
                WHERE host = ? AND action_type = ? AND target = ? AND timestamp >= ?
                """,
                (host, action_type, target, cutoff.isoformat()),
            ).fetchone()
        return int(row[0])

    def record_attempt(self, *, host: str, action_type: str, target: str, correlation_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO action_attempts(timestamp, host, action_type, target, correlation_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (datetime.now(UTC).isoformat(), host, action_type, target, correlation_id),
            )
