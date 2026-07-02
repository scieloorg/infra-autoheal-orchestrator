from __future__ import annotations

from app.config import HostsConfig
from app.models import ActionDecision, ActionName, AlertItem

ALERT_ACTION_MAP: dict[str, ActionName] = {
    "ApacheDown": ActionName.RESTART_APACHE,
    "MariaDBDown": ActionName.RESTART_MARIADB,
    "MySQLDown": ActionName.RESTART_MARIADB,
    "HostUnreachable": ActionName.REBOOT_VM,
}


class RunbookRouter:
    def __init__(self, hosts_config: HostsConfig) -> None:
        self.hosts_config = hosts_config

    def decide(self, alert: AlertItem) -> ActionDecision:
        labels = alert.labels
        action = ALERT_ACTION_MAP.get(labels.alertname)
        host = _normalize_instance(labels.instance)
        decision = ActionDecision(alertname=labels.alertname, host=host, action=action)
        if action is None:
            decision.reason = "unknown alertname"
            return decision
        if labels.action and labels.action != action.value:
            decision.reason = "payload action does not match configured runbook"
            return decision
        if action.value not in {allowed.value for allowed in ActionName}:
            decision.reason = "action is not allowlisted"
            return decision
        if host not in self.hosts_config.hosts:
            decision.reason = "host is not configured"
            return decision
        host_config = self.hosts_config.hosts[host]
        if action == ActionName.RESTART_APACHE and "apache" not in host_config.services:
            decision.reason = "host is not allowed for this alert: apache service is not configured"
            return decision
        if action == ActionName.RESTART_MARIADB and "mariadb" not in host_config.services:
            decision.reason = "host is not allowed for this alert: mariadb service is not configured"
            return decision
        if action == ActionName.REBOOT_VM and host_config.proxmox is None:
            decision.reason = "host is not allowed for this alert: proxmox mapping is not configured"
            return decision
        decision.allowed = True
        decision.reason = "allowed"
        return decision


def _normalize_instance(instance: str) -> str:
    if instance.startswith("[") and "]" in instance:
        return instance[1 : instance.index("]")]
    if instance.count(":") == 1:
        host, port = instance.rsplit(":", 1)
        if port.isdigit():
            return host
    return instance
