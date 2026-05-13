from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import asyncssh

from app.config import SSHSettings
from app.models import CommandResult


@dataclass(frozen=True)
class AllowedCommand:
    key: str
    command: tuple[str, ...]
    display: str


ALLOWED_COMMANDS: dict[str, AllowedCommand] = {
    "restart_apache": AllowedCommand(
        "restart_apache",
        ("sudo", "systemctl", "restart", "{service}"),
        "sudo systemctl restart {service}",
    ),
    "is_active_apache": AllowedCommand(
        "is_active_apache",
        ("sudo", "systemctl", "is-active", "{service}"),
        "sudo systemctl is-active {service}",
    ),
    "journal_apache": AllowedCommand(
        "journal_apache",
        ("journalctl", "-u", "{service}", "-n", "200", "--no-pager"),
        "journalctl -u {service} -n 200 --no-pager",
    ),
    "restart_mariadb": AllowedCommand(
        "restart_mariadb",
        ("sudo", "systemctl", "restart", "{service}"),
        "sudo systemctl restart {service}",
    ),
    "is_active_mariadb": AllowedCommand(
        "is_active_mariadb",
        ("sudo", "systemctl", "is-active", "{service}"),
        "sudo systemctl is-active {service}",
    ),
    "mysqladmin_ping": AllowedCommand(
        "mysqladmin_ping",
        ("mysqladmin", "ping", "--connect-timeout=5"),
        "mysqladmin ping --connect-timeout=5",
    ),
    "journal_mariadb": AllowedCommand(
        "journal_mariadb",
        ("journalctl", "-u", "{service}", "-n", "200", "--no-pager"),
        "journalctl -u {service} -n 200 --no-pager",
    ),
    "uptime": AllowedCommand("uptime", ("uptime",), "uptime"),
    "free": AllowedCommand("free", ("free", "-m"), "free -m"),
    "df": AllowedCommand("df", ("df", "-h"), "df -h"),
    "dmesg_tail": AllowedCommand(
        "dmesg_tail",
        ("sh", "-c", "dmesg -T | tail -100"),
        "dmesg -T | tail -100",
    ),
    "journal_recent": AllowedCommand(
        "journal_recent",
        ("journalctl", "-n", "300", "--no-pager"),
        "journalctl -n 300 --no-pager",
    ),
}


class SSHCommandError(ValueError):
    pass


class SSHExecutor:
    def __init__(
        self,
        command_timeout: int = 30,
        connect_timeout: int = 10,
        settings: SSHSettings | None = None,
    ) -> None:
        self.command_timeout = command_timeout
        self.connect_timeout = connect_timeout
        self.settings = settings or SSHSettings()

    async def run_allowed(
        self,
        *,
        host: str,
        user: str,
        command_key: str,
        service: str | None = None,
        private_key_path: Path | None = None,
        known_hosts_path: Path | None = None,
    ) -> CommandResult:
        command = render_allowed_command(command_key, service=service)
        display = render_allowed_display(command_key, service=service)
        try:
            async with asyncssh.connect(
                host,
                username=user,
                client_keys=self._client_keys(private_key_path),
                known_hosts=self._known_hosts(known_hosts_path),
                password_auth=self.settings.password_auth,
                preferred_auth="publickey",
                connect_timeout=self.connect_timeout,
            ) as conn:
                result = await asyncio.wait_for(
                    conn.run(command, check=False),
                    timeout=self.command_timeout,
                )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(command=display, exit_code=255, stderr=str(exc))

        return CommandResult(
            command=display,
            exit_code=result.exit_status,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    async def is_ssh_available(
        self,
        *,
        host: str,
        user: str,
        private_key_path: Path | None = None,
        known_hosts_path: Path | None = None,
    ) -> bool:
        try:
            async with asyncssh.connect(
                host,
                username=user,
                client_keys=self._client_keys(private_key_path),
                known_hosts=self._known_hosts(known_hosts_path),
                password_auth=self.settings.password_auth,
                preferred_auth="publickey",
                connect_timeout=self.connect_timeout,
            ):
                return True
        except Exception:  # noqa: BLE001
            return False

    def _client_keys(self, host_private_key_path: Path | None) -> list[str] | None:
        private_key_path = host_private_key_path or self.settings.private_key_path
        return [str(private_key_path)] if private_key_path else None

    def _known_hosts(self, host_known_hosts_path: Path | None) -> str | None:
        known_hosts_path = host_known_hosts_path or self.settings.known_hosts_path
        return str(known_hosts_path) if known_hosts_path else None


def render_allowed_command(command_key: str, *, service: str | None = None) -> str:
    allowed = ALLOWED_COMMANDS.get(command_key)
    if allowed is None:
        raise SSHCommandError(f"Command key is not allowlisted: {command_key}")
    rendered: list[str] = []
    for part in allowed.command:
        if part == "{service}":
            if not service:
                raise SSHCommandError(f"Service is required for {command_key}")
            rendered.append(service)
        elif "{service}" in part:
            if not service:
                raise SSHCommandError(f"Service is required for {command_key}")
            rendered.append(part.replace("{service}", service))
        else:
            rendered.append(part)
    return " ".join(rendered)


def render_allowed_display(command_key: str, *, service: str | None = None) -> str:
    allowed = ALLOWED_COMMANDS.get(command_key)
    if allowed is None:
        raise SSHCommandError(f"Command key is not allowlisted: {command_key}")
    if "{service}" in allowed.display:
        if not service:
            raise SSHCommandError(f"Service is required for {command_key}")
        return allowed.display.format(service=service)
    return allowed.display
