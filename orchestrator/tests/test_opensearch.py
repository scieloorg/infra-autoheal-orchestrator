from __future__ import annotations

from app.config import OpenSearchSettings
from app.models import ActionDecision, ActionExecution, ActionName, CommandResult, ValidationResult
from app.storage.opensearch import OpenSearchIndexer


def test_opensearch_document_includes_execution_evidence():
    execution = ActionExecution(
        decision=ActionDecision(
            alertname="MariaDBDown",
            host="db-node-01.example.local",
            action=ActionName.RESTART_MARIADB,
            allowed=True,
            reason="allowed",
        ),
        status="success",
        commands=[
            CommandResult(
                command="mysqladmin ping --connect-timeout=5",
                exit_code=0,
                stdout="mysqld is alive\n",
            )
        ],
        validation=ValidationResult(name="mysqladmin_ping", success=True, detail="server is alive"),
    )

    document = OpenSearchIndexer(OpenSearchSettings()).document(execution)

    assert document["correlation_id"] == execution.decision.correlation_id
    assert document["alertname"] == "MariaDBDown"
    assert document["action"] == "restart_mariadb"
    assert document["status"] == "success"
    assert document["commands"][0]["exit_code"] == 0
    assert document["validation"]["success"] is True


def test_opensearch_document_redacts_and_truncates_command_output():
    execution = ActionExecution(
        decision=ActionDecision(
            alertname="MariaDBDown",
            host="db-node-01.example.local",
            action=ActionName.RESTART_MARIADB,
            allowed=True,
            reason="allowed",
        ),
        status="failed",
        commands=[
            CommandResult(
                command="journalctl -n 300 --no-pager",
                exit_code=1,
                stdout="token=abc123 " + ("x" * 20),
                stderr="Authorization: Bearer very-secret-token",
            )
        ],
    )

    document = OpenSearchIndexer(OpenSearchSettings(max_field_length=12)).document(execution)

    assert "abc123" not in document["commands"][0]["stdout"]
    assert "very-secret-token" not in document["commands"][0]["stderr"]
    assert "truncated" in document["commands"][0]["stdout"]
