from __future__ import annotations

from pydantic import BaseModel

from app.actions.ssh import SSHExecutor
from app.models import CommandResult, ValidationResult


class MySQLValidationBundle(BaseModel):
    result: ValidationResult
    commands: list[CommandResult]


class MySQLValidator:
    def __init__(self, ssh: SSHExecutor) -> None:
        self.ssh = ssh

    async def check(
        self,
        *,
        host: str,
        user: str,
        service: str,
        private_key_path=None,
        known_hosts_path=None,
    ) -> MySQLValidationBundle:
        result = await self.ssh.run_allowed(
            host=host,
            user=user,
            command_key="mysqladmin_ping",
            service=service,
            private_key_path=private_key_path,
            known_hosts_path=known_hosts_path,
        )
        return MySQLValidationBundle(
            result=ValidationResult(
                name="mysqladmin_ping",
                success=result.exit_code == 0 and "alive" in result.stdout.lower(),
                detail=f"exit_code={result.exit_code}",
            ),
            commands=[result],
        )
