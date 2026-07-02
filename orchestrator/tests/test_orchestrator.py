from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import HostConfig, HostsConfig, ProxmoxHostConfig
from app.models import AlertItem, AlertLabels

REBOOT_CONFIRMATIONS = {
    "node_exporter_down": "true",
    "blackbox_unavailable": "true",
}


def alert(
    alertname: str,
    instance: str,
    action: str | None = None,
    *,
    starts_at=None,
    annotations: dict | None = None,
    labels: dict | None = None,
) -> AlertItem:
    label_data = {"alertname": alertname, "instance": instance, "action": action}
    if labels:
        label_data.update(labels)
    return AlertItem(
        labels=AlertLabels.model_validate(label_data),
        startsAt=starts_at,
        annotations=annotations or {},
    )


@pytest.mark.asyncio
async def test_apache_down_restarts_only_httpd_on_allowed_host(orchestrator_factory):
    orchestrator, ssh, http, _ = orchestrator_factory()

    result = await orchestrator.process_alert(
        alert("ApacheDown", "app-node-01.example.local", "restart_apache")
    )

    assert result.status == "success"
    assert ("restart_apache", "httpd") in ssh.calls
    assert ("is_active_apache", "httpd") in ssh.calls
    assert all(call[1] != "mariadb" for call in ssh.calls if call[0].startswith("restart"))
    assert http.urls == ["https://app-node-01.example.local/"]


@pytest.mark.asyncio
async def test_mariadb_down_restarts_only_mariadb_on_allowed_host(orchestrator_factory):
    orchestrator, ssh, _, _ = orchestrator_factory()

    result = await orchestrator.process_alert(
        alert("MariaDBDown", "db-node-01.example.local", "restart_mariadb")
    )

    assert result.status == "success"
    assert ("restart_mariadb", "mariadb") in ssh.calls
    assert ("is_active_mariadb", "mariadb") in ssh.calls
    assert ("mysqladmin_ping", "mariadb") in ssh.calls
    assert ("restart_apache", "httpd") not in ssh.calls


@pytest.mark.asyncio
async def test_mysql_down_alias_restarts_mariadb_and_strips_exporter_port(orchestrator_factory):
    orchestrator, ssh, _, _ = orchestrator_factory()

    result = await orchestrator.process_alert(
        alert("MySQLDown", "db-node-01.example.local:9104", "restart_mariadb")
    )

    assert result.status == "success"
    assert result.decision.host == "db-node-01.example.local"
    assert result.decision.action == "restart_mariadb"
    assert ("restart_mariadb", "mariadb") in ssh.calls
    assert ("restart_apache", "httpd") not in ssh.calls


@pytest.mark.asyncio
async def test_mariadb_down_allows_any_configured_host_with_mariadb_service(
    orchestrator_factory,
):
    hosts_config = HostsConfig(
        hosts={
            "app-node-02.example.local": HostConfig(
                ssh_user="rundeck",
                services={"apache": "httpd", "mariadb": "mariadb"},
                http_healthcheck="https://app-node-02.example.local/",
                proxmox=ProxmoxHostConfig(node="nodeZZ", vmid=131),
            )
        }
    )
    orchestrator, ssh, _, _ = orchestrator_factory(hosts_config=hosts_config)

    result = await orchestrator.process_alert(
        alert("MariaDBDown", "app-node-02.example.local", "restart_mariadb")
    )

    assert result.status == "success"
    assert ("restart_mariadb", "mariadb") in ssh.calls
    assert ("restart_apache", "httpd") not in ssh.calls


@pytest.mark.asyncio
async def test_unknown_alert_is_ignored_and_recorded(orchestrator_factory):
    orchestrator, ssh, _, _ = orchestrator_factory()

    result = await orchestrator.process_alert(alert("SomethingElse", "db-node-01.example.local"))

    assert result.status == "ignored"
    assert result.blocked_reason == "unknown alertname"
    assert ssh.calls == []
    events = orchestrator.event_store.list_events()
    assert len(events) == 1
    assert events[0]["status"] == "ignored"


@pytest.mark.asyncio
async def test_unauthorized_host_is_blocked(orchestrator_factory):
    orchestrator, ssh, _, _ = orchestrator_factory()

    result = await orchestrator.process_alert(
        alert("ApacheDown", "db-node-01.example.local", "restart_apache")
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "host is not allowed for this alert: apache service is not configured"
    assert ssh.calls == []


@pytest.mark.asyncio
async def test_payload_cannot_swap_runbook_action(orchestrator_factory):
    orchestrator, ssh, _, _ = orchestrator_factory()

    result = await orchestrator.process_alert(
        alert("ApacheDown", "app-node-01.example.local", "reboot_vm")
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "payload action does not match configured runbook"
    assert ssh.calls == []


@pytest.mark.asyncio
async def test_restart_circuit_breaker_blocks_third_attempt(orchestrator_factory):
    orchestrator, ssh, _, _ = orchestrator_factory()
    item = alert("MariaDBDown", "db-node-01.example.local", "restart_mariadb")

    assert (await orchestrator.process_alert(item)).status == "success"
    assert (await orchestrator.process_alert(item)).status == "success"
    third = await orchestrator.process_alert(item)

    assert third.status == "blocked"
    assert "circuit breaker open" in (third.blocked_reason or "")
    assert [call for call in ssh.calls if call[0] == "restart_mariadb"] == [
        ("restart_mariadb", "mariadb"),
        ("restart_mariadb", "mariadb"),
    ]


@pytest.mark.asyncio
async def test_reboot_requires_all_preconditions(orchestrator_factory):
    starts_at = datetime.now(UTC) - timedelta(minutes=10)
    orchestrator, _, _, proxmox = orchestrator_factory(ssh_available=True, http_success=False)

    result = await orchestrator.process_alert(
        alert("HostUnreachable", "db-node-01.example.local", starts_at=starts_at)
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "reboot preconditions failed"
    assert proxmox.reboots == []


@pytest.mark.asyncio
async def test_reboot_via_proxmox_only_when_preconditions_are_true(orchestrator_factory):
    starts_at = datetime.now(UTC) - timedelta(minutes=10)
    orchestrator, _, _, proxmox = orchestrator_factory(ssh_available=False, http_success=False)

    result = await orchestrator.process_alert(
        alert(
            "HostUnreachable",
            "app-node-01.example.local",
            starts_at=starts_at,
            annotations=REBOOT_CONFIRMATIONS,
        )
    )

    assert result.status == "success"
    assert proxmox.reboots == [("nodeYY", 456)]


@pytest.mark.asyncio
async def test_reboot_circuit_breaker_blocks_second_attempt(orchestrator_factory):
    starts_at = datetime.now(UTC) - timedelta(minutes=10)
    orchestrator, _, _, proxmox = orchestrator_factory(ssh_available=False, http_success=False)
    item = alert(
        "HostUnreachable",
        "db-node-01.example.local",
        starts_at=starts_at,
        annotations=REBOOT_CONFIRMATIONS,
    )

    assert (await orchestrator.process_alert(item)).status == "success"
    second = await orchestrator.process_alert(item)

    assert second.status == "blocked"
    assert "circuit breaker open" in (second.blocked_reason or "")
    assert proxmox.reboots == [("nodeXX", 123)]


@pytest.mark.asyncio
async def test_reboot_precondition_failure_does_not_consume_circuit_breaker(orchestrator_factory):
    starts_at = datetime.now(UTC) - timedelta(minutes=10)
    orchestrator, _, _, proxmox = orchestrator_factory(ssh_available=False, http_success=False)

    first = await orchestrator.process_alert(
        alert("HostUnreachable", "db-node-01.example.local", starts_at=starts_at)
    )
    second = await orchestrator.process_alert(
        alert(
            "HostUnreachable",
            "db-node-01.example.local",
            starts_at=starts_at,
            annotations=REBOOT_CONFIRMATIONS,
        )
    )

    assert first.status == "blocked"
    assert first.blocked_reason == "reboot preconditions failed"
    assert second.status == "success"
    assert proxmox.reboots == [("nodeXX", 123)]
