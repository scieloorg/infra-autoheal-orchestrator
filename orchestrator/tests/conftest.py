from __future__ import annotations

from pathlib import Path

import pytest

from app.actions.proxmox import ProxmoxClient
from app.config import (
    HostConfig,
    HostsConfig,
    PoliciesConfig,
    ProxmoxHostConfig,
    ProxmoxSettings,
    Settings,
    TimeoutConfig,
)
from app.models import CommandResult, ValidationResult
from app.rules.policies import CircuitBreaker
from app.runner import Orchestrator
from app.storage.events import EventStore
from app.storage.opensearch import OpenSearchIndexer
from app.storage.state import StateStore
from app.validators.mysql_check import MySQLValidationBundle, MySQLValidator


class FakeSSH:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls: list[tuple[str, str | None]] = []

    async def run_allowed(
        self,
        *,
        host: str,
        user: str,
        command_key: str,
        service: str | None = None,
        **kwargs,
    ):
        self.calls.append((command_key, service))
        stdout = "mysqld is alive" if command_key == "mysqladmin_ping" else "active"
        return CommandResult(command=f"{command_key}:{service}", exit_code=0, stdout=stdout)

    async def is_ssh_available(self, *, host: str, user: str, **kwargs) -> bool:
        return self.available


class FakeHTTPValidator:
    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.urls: list[str] = []

    async def check(self, url: str) -> ValidationResult:
        self.urls.append(url)
        return ValidationResult(name="http_get", success=self.success, detail="fake")


class FakeMySQLValidator(MySQLValidator):
    def __init__(self, ssh: FakeSSH, *, success: bool = True) -> None:
        self.ssh = ssh
        self.success = success

    async def check(self, *, host: str, user: str, service: str, **kwargs) -> MySQLValidationBundle:
        command = await self.ssh.run_allowed(
            host=host,
            user=user,
            command_key="mysqladmin_ping",
            service=service,
        )
        return MySQLValidationBundle(
            result=ValidationResult(name="mysqladmin_ping", success=self.success, detail="fake"),
            commands=[command],
        )


class FakeProxmoxClient(ProxmoxClient):
    def __init__(self) -> None:
        self.reboots: list[tuple[str, int]] = []

    async def reboot_vm(self, *, node: str, vmid: int):
        self.reboots.append((node, vmid))
        return {"data": "UPID:fake"}


class DisabledOpenSearch(OpenSearchIndexer):
    def __init__(self) -> None:
        pass

    def index(self, execution) -> None:
        return None


class FakeSlackNotifier:
    def __init__(self) -> None:
        self.started = []
        self.finished = []
        self.blocked = []

    async def action_started(self, decision) -> None:
        self.started.append(decision)

    async def action_finished(self, execution, *, duration_seconds: float) -> None:
        self.finished.append((execution, duration_seconds))

    async def action_blocked(self, execution) -> None:
        self.blocked.append(execution)


@pytest.fixture
def hosts_config() -> HostsConfig:
    return HostsConfig(
        hosts={
            "db-node-01.example.local": HostConfig(
                ssh_user="rundeck",
                services={"mariadb": "mariadb"},
                proxmox=ProxmoxHostConfig(node="nodeXX", vmid=123),
            ),
            "app-node-01.example.local": HostConfig(
                ssh_user="rundeck",
                services={"apache": "httpd", "mariadb": "mariadb"},
                http_healthcheck="https://app-node-01.example.local/",
                proxmox=ProxmoxHostConfig(node="nodeYY", vmid=456),
            ),
        }
    )


@pytest.fixture
def policies() -> PoliciesConfig:
    return PoliciesConfig(
        limits={
            "restart_service": {"max_attempts": 2, "window_minutes": 15},
            "reboot_vm": {"max_attempts": 1, "window_minutes": 60},
        },
        timeouts=TimeoutConfig(),
    )


@pytest.fixture
def orchestrator_factory(tmp_path: Path, hosts_config: HostsConfig, policies: PoliciesConfig):
    def build(
        *,
        hosts_config: HostsConfig = hosts_config,
        ssh_available: bool = True,
        http_success: bool = True,
        mysql_success: bool = True,
    ):
        sqlite_path = tmp_path / "test.sqlite3"
        ssh = FakeSSH(available=ssh_available)
        http = FakeHTTPValidator(success=http_success)
        proxmox = FakeProxmoxClient()
        notifier = FakeSlackNotifier()
        orchestrator = Orchestrator(
            settings=Settings(sqlite_path=sqlite_path, proxmox=ProxmoxSettings()),
            hosts_config=hosts_config,
            policies=policies,
            event_store=EventStore(sqlite_path),
            circuit_breaker=CircuitBreaker(policies=policies, state_store=StateStore(sqlite_path)),
            ssh=ssh,
            http_validator=http,
            mysql_validator=FakeMySQLValidator(ssh, success=mysql_success),
            proxmox_client=proxmox,
            opensearch=DisabledOpenSearch(),
            notifier=notifier,
        )
        return orchestrator, ssh, http, proxmox

    return build
