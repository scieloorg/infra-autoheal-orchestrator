from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.actions.evidence import collect_linux_evidence
from app.actions.ssh import SSHExecutor
from app.config import HostConfig, ProxmoxSettings
from app.models import ActionDecision, ActionExecution, ValidationResult
from app.validators.http_check import HTTPValidator


class ProxmoxClient:
    def __init__(self, settings: ProxmoxSettings) -> None:
        self.settings = settings

    async def reboot_vm(self, *, node: str, vmid: int) -> dict[str, Any]:
        if not self.settings.base_url or not self.settings.token_id or not self.settings.token_secret:
            raise RuntimeError("Proxmox settings are incomplete")
        url = f"{str(self.settings.base_url).rstrip('/')}/api2/json/nodes/{node}/qemu/{vmid}/status/reboot"
        headers = {
            "Authorization": f"PVEAPIToken={self.settings.token_id}={self.settings.token_secret}",
        }
        async with httpx.AsyncClient(verify=self.settings.verify_tls, timeout=15) as client:
            response = await client.post(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}


class RebootPreconditionChecker:
    def __init__(self, *, ssh: SSHExecutor, http_validator: HTTPValidator) -> None:
        self.ssh = ssh
        self.http_validator = http_validator

    async def check(
        self,
        *,
        decision: ActionDecision,
        host_config: HostConfig,
        alert_starts_at: datetime | None,
    ) -> tuple[bool, dict[str, Any]]:
        now = datetime.now(UTC)
        if alert_starts_at is None:
            active_for_seconds = 0.0
        else:
            if alert_starts_at.tzinfo is None:
                alert_starts_at = alert_starts_at.replace(tzinfo=UTC)
            active_for_seconds = (now - alert_starts_at).total_seconds()

        ssh_available = await self.ssh.is_ssh_available(
            host=decision.host,
            user=host_config.ssh_user,
            private_key_path=host_config.ssh_private_key_path,
            known_hosts_path=host_config.ssh_known_hosts_path,
        )
        http_available = False
        http_detail = "no http_healthcheck configured"
        if host_config.http_healthcheck:
            http_result = await self.http_validator.check(host_config.http_healthcheck)
            http_available = http_result.success
            http_detail = http_result.detail

        details = {
            "alert_active_for_seconds": active_for_seconds,
            "alert_minimum_seconds": int(timedelta(minutes=5).total_seconds()),
            "node_exporter_down": True,
            "ssh_unavailable": not ssh_available,
            "blackbox_unavailable": not http_available,
            "blackbox_detail": http_detail,
        }
        allowed = (
            active_for_seconds >= timedelta(minutes=5).total_seconds()
            and details["node_exporter_down"]
            and details["ssh_unavailable"]
            and details["blackbox_unavailable"]
        )
        return allowed, details


async def reboot_vm(
    *,
    decision: ActionDecision,
    host_config: HostConfig,
    proxmox_client: ProxmoxClient,
    preconditions: tuple[bool, dict[str, Any]],
    ssh: SSHExecutor,
) -> ActionExecution:
    allowed, details = preconditions
    if not allowed:
        return ActionExecution(
            decision=decision,
            status="blocked",
            validation=ValidationResult(name="reboot_preconditions", success=False, detail=str(details)),
            blocked_reason="reboot preconditions failed",
        )
    if host_config.proxmox is None:
        return ActionExecution(
            decision=decision,
            status="blocked",
            validation=ValidationResult(
                name="proxmox_config",
                success=False,
                detail="host has no proxmox config",
            ),
            blocked_reason="missing proxmox configuration",
        )

    response = await proxmox_client.reboot_vm(node=host_config.proxmox.node, vmid=host_config.proxmox.vmid)
    evidence = await collect_linux_evidence(ssh=ssh, host=decision.host, host_config=host_config)
    return ActionExecution(
        decision=decision,
        status="success",
        validation=ValidationResult(name="reboot_preconditions", success=True, detail=str(details)),
        evidence=evidence,
        proxmox_response=response,
    )
