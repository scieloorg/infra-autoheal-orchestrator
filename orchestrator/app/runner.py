from __future__ import annotations

import structlog

from app.actions.apache import restart_apache
from app.actions.evidence import collect_linux_evidence
from app.actions.mariadb import restart_mariadb
from app.actions.proxmox import ProxmoxClient, RebootPreconditionChecker, reboot_vm
from app.actions.ssh import SSHExecutor
from app.config import HostsConfig, PoliciesConfig, Settings
from app.models import ActionExecution, ActionName, AlertItem
from app.rules.policies import CircuitBreaker
from app.rules.router import RunbookRouter
from app.storage.events import EventStore
from app.storage.opensearch import OpenSearchIndexer
from app.validators.http_check import HTTPValidator
from app.validators.mysql_check import MySQLValidator

log = structlog.get_logger()


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        hosts_config: HostsConfig,
        policies: PoliciesConfig,
        event_store: EventStore,
        circuit_breaker: CircuitBreaker,
        ssh: SSHExecutor,
        http_validator: HTTPValidator,
        mysql_validator: MySQLValidator,
        proxmox_client: ProxmoxClient,
        opensearch: OpenSearchIndexer,
    ) -> None:
        self.settings = settings
        self.hosts_config = hosts_config
        self.policies = policies
        self.event_store = event_store
        self.circuit_breaker = circuit_breaker
        self.ssh = ssh
        self.http_validator = http_validator
        self.mysql_validator = mysql_validator
        self.proxmox_client = proxmox_client
        self.opensearch = opensearch
        self.router = RunbookRouter(hosts_config)

    async def process_alert(self, alert: AlertItem) -> ActionExecution:
        decision = self.router.decide(alert)
        log.info(
            "alert_decision",
            correlation_id=decision.correlation_id,
            alertname=decision.alertname,
            host=decision.host,
            action=decision.action.value if decision.action else None,
            allowed=decision.allowed,
            reason=decision.reason,
        )
        if not decision.allowed or decision.action is None:
            execution = ActionExecution(
                decision=decision,
                status="ignored" if decision.reason == "unknown alertname" else "blocked",
                blocked_reason=decision.reason,
            )
            self._record(execution)
            return execution

        host_config = self.hosts_config.hosts[decision.host]
        target = self._circuit_target(decision.action, host_config)
        breaker_allowed, breaker_reason = self.circuit_breaker.check(
            host=decision.host,
            action=decision.action,
            target=target,
        )
        if not breaker_allowed:
            execution = ActionExecution(
                decision=decision,
                status="blocked",
                blocked_reason=breaker_reason,
            )
            self._record(execution)
            return execution

        self.circuit_breaker.record(
            host=decision.host,
            action=decision.action,
            target=target,
            correlation_id=decision.correlation_id,
        )

        if decision.action == ActionName.RESTART_APACHE:
            execution = await restart_apache(
                decision=decision,
                host_config=host_config,
                ssh=self.ssh,
                http_validator=self.http_validator,
            )
        elif decision.action == ActionName.RESTART_MARIADB:
            execution = await restart_mariadb(
                decision=decision,
                host_config=host_config,
                ssh=self.ssh,
                mysql_validator=self.mysql_validator,
            )
        elif decision.action == ActionName.COLLECT_EVIDENCE:
            evidence = await collect_linux_evidence(
                ssh=self.ssh,
                host=decision.host,
                host_config=host_config,
            )
            execution = ActionExecution(
                decision=decision,
                status="success",
                evidence=evidence,
            )
        elif decision.action == ActionName.REBOOT_VM:
            precondition_checker = RebootPreconditionChecker(ssh=self.ssh, http_validator=self.http_validator)
            preconditions = await precondition_checker.check(
                decision=decision,
                host_config=host_config,
                alert_starts_at=alert.startsAt,
            )
            execution = await reboot_vm(
                decision=decision,
                host_config=host_config,
                proxmox_client=self.proxmox_client,
                preconditions=preconditions,
                ssh=self.ssh,
            )
        else:
            execution = ActionExecution(
                decision=decision,
                status="blocked",
                blocked_reason="unsupported action",
            )

        self._record(execution)
        return execution

    def _record(self, execution: ActionExecution) -> None:
        self.event_store.record(execution)
        self.opensearch.index(execution)
        log.info(
            "action_recorded",
            correlation_id=execution.decision.correlation_id,
            status=execution.status,
            blocked_reason=execution.blocked_reason,
        )

    @staticmethod
    def _circuit_target(action: ActionName, host_config) -> str:
        if action == ActionName.RESTART_APACHE:
            return host_config.services["apache"]
        if action == ActionName.RESTART_MARIADB:
            return host_config.services["mariadb"]
        if action == ActionName.REBOOT_VM and host_config.proxmox:
            return f"{host_config.proxmox.node}/{host_config.proxmox.vmid}"
        return action.value
