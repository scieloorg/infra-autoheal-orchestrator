from __future__ import annotations

from app.actions.evidence import collect_linux_evidence
from app.actions.ssh import SSHExecutor
from app.config import HostConfig
from app.models import ActionDecision, ActionExecution
from app.validators.mysql_check import MySQLValidator


async def restart_mariadb(
    *,
    decision: ActionDecision,
    host_config: HostConfig,
    ssh: SSHExecutor,
    mysql_validator: MySQLValidator,
) -> ActionExecution:
    service = host_config.services["mariadb"]
    commands = [
        await ssh.run_allowed(
            host=decision.host,
            user=host_config.ssh_user,
            command_key="restart_mariadb",
            service=service,
            private_key_path=host_config.ssh_private_key_path,
            known_hosts_path=host_config.ssh_known_hosts_path,
        ),
        await ssh.run_allowed(
            host=decision.host,
            user=host_config.ssh_user,
            command_key="is_active_mariadb",
            service=service,
            private_key_path=host_config.ssh_private_key_path,
            known_hosts_path=host_config.ssh_known_hosts_path,
        ),
    ]
    validation = await mysql_validator.check(
        host=decision.host,
        user=host_config.ssh_user,
        service=service,
        private_key_path=host_config.ssh_private_key_path,
        known_hosts_path=host_config.ssh_known_hosts_path,
    )
    commands.extend(validation.commands)
    evidence = await collect_linux_evidence(ssh=ssh, host=decision.host, host_config=host_config)
    success = commands[0].exit_code == 0 and commands[1].exit_code == 0 and validation.result.success
    return ActionExecution(
        decision=decision,
        status="success" if success else "failed",
        commands=commands,
        validation=validation.result,
        evidence=evidence,
    )
