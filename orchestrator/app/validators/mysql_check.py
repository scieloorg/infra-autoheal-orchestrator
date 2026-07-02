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
        success, detail = _mysqladmin_availability(result)
        return MySQLValidationBundle(
            result=ValidationResult(
                name="mysqladmin_ping",
                success=success,
                detail=detail,
            ),
            commands=[result],
        )


def _mysqladmin_availability(result: CommandResult) -> tuple[bool, str]:
    output = f"{result.stdout}\n{result.stderr}".lower()
    if "mysqld is alive" in output:
        return True, f"exit_code={result.exit_code}; server is alive"
    if "access denied" in output:
        return True, f"exit_code={result.exit_code}; server rejected authentication"
    return False, f"exit_code={result.exit_code}"
