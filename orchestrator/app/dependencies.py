from __future__ import annotations

from functools import lru_cache

from app.actions.proxmox import ProxmoxClient
from app.actions.ssh import SSHExecutor
from app.config import get_hosts_config, get_policies_config, get_settings
from app.rules.policies import CircuitBreaker
from app.runner import Orchestrator
from app.storage.events import EventStore
from app.storage.opensearch import OpenSearchIndexer
from app.storage.state import StateStore
from app.validators.http_check import HTTPValidator
from app.validators.mysql_check import MySQLValidator


@lru_cache
def get_event_store() -> EventStore:
    return EventStore(get_settings().sqlite_path)


@lru_cache
def get_state_store() -> StateStore:
    return StateStore(get_settings().sqlite_path)


@lru_cache
def get_ssh_executor() -> SSHExecutor:
    policies = get_policies_config()
    settings = get_settings()
    return SSHExecutor(
        command_timeout=policies.timeouts.command_seconds,
        connect_timeout=policies.timeouts.ssh_seconds,
        settings=settings.ssh,
    )


@lru_cache
def get_orchestrator() -> Orchestrator:
    settings = get_settings()
    policies = get_policies_config()
    ssh = get_ssh_executor()
    return Orchestrator(
        settings=settings,
        hosts_config=get_hosts_config(),
        policies=policies,
        event_store=get_event_store(),
        circuit_breaker=CircuitBreaker(policies=policies, state_store=get_state_store()),
        ssh=ssh,
        http_validator=HTTPValidator(timeout_seconds=policies.timeouts.http_check_seconds),
        mysql_validator=MySQLValidator(ssh),
        proxmox_client=ProxmoxClient(settings.proxmox),
        opensearch=OpenSearchIndexer(settings.opensearch),
    )
