from __future__ import annotations

from app.actions.evidence import collect_linux_evidence
from app.actions.ssh import SSHExecutor
from app.config import HostConfig
from app.models import ActionDecision, ActionExecution, ValidationResult
from app.validators.http_check import HTTPValidator


async def restart_apache(
    *,
    decision: ActionDecision,
    host_config: HostConfig,
    ssh: SSHExecutor,
    http_validator: HTTPValidator,
) -> ActionExecution:
    service = host_config.services["apache"]
    commands = [
        await ssh.run_allowed(
            host=decision.host,
            user=host_config.ssh_user,
            command_key="restart_apache",
            service=service,
            private_key_path=host_config.ssh_private_key_path,
            known_hosts_path=host_config.ssh_known_hosts_path,
        ),
        await ssh.run_allowed(
            host=decision.host,
            user=host_config.ssh_user,
            command_key="is_active_apache",
            service=service,
            private_key_path=host_config.ssh_private_key_path,
            known_hosts_path=host_config.ssh_known_hosts_path,
        ),
    ]
    evidence = await collect_linux_evidence(ssh=ssh, host=decision.host, host_config=host_config)
    validation = ValidationResult(
        name="http_get",
        success=False,
        detail="http_healthcheck is not configured",
    )
    if host_config.http_healthcheck:
        validation = await http_validator.check(host_config.http_healthcheck)
    success = commands[0].exit_code == 0 and commands[1].exit_code == 0 and validation.success
    return ActionExecution(
        decision=decision,
        status="success" if success else "failed",
        commands=commands,
        validation=validation,
        evidence=evidence,
    )
