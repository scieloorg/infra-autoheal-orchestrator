from __future__ import annotations

from app.actions.ssh import SSHExecutor
from app.config import HostConfig
from app.models import EvidenceBundle

EVIDENCE_COMMANDS = ("uptime", "free", "df", "dmesg_tail", "journal_recent")


async def collect_linux_evidence(
    *,
    ssh: SSHExecutor,
    host: str,
    host_config: HostConfig,
) -> EvidenceBundle:
    commands = []
    for command_key in EVIDENCE_COMMANDS:
        commands.append(
            await ssh.run_allowed(
                host=host,
                user=host_config.ssh_user,
                command_key=command_key,
                private_key_path=host_config.ssh_private_key_path,
                known_hosts_path=host_config.ssh_known_hosts_path,
            )
        )
    return EvidenceBundle(commands=commands)
