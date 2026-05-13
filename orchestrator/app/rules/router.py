from __future__ import annotations

from app.config import HostsConfig
from app.models import ActionDecision, ActionName, AlertItem

ALERT_ACTION_MAP: dict[str, ActionName] = {
    "ApacheDown": ActionName.RESTART_APACHE,
    "MariaDBDown": ActionName.RESTART_MARIADB,
    "HostUnreachable": ActionName.REBOOT_VM,
}

ALERT_ALLOWED_HOSTS: dict[str, set[str]] = {
    "ApacheDown": {"app-node-01.example.local"},
    "MariaDBDown": {"db-node-01.example.local", "app-node-01.example.local"},
    "HostUnreachable": {"db-node-01.example.local", "app-node-01.example.local"},
}


class RunbookRouter:
    def __init__(self, hosts_config: HostsConfig) -> None:
        self.hosts_config = hosts_config

    def decide(self, alert: AlertItem) -> ActionDecision:
        labels = alert.labels
        action = ALERT_ACTION_MAP.get(labels.alertname)
        decision = ActionDecision(alertname=labels.alertname, host=labels.instance, action=action)
        if action is None:
            decision.reason = "unknown alertname"
            return decision
        if labels.action and labels.action != action.value:
            decision.reason = "payload action does not match configured runbook"
            return decision
        if action.value not in {allowed.value for allowed in ActionName}:
            decision.reason = "action is not allowlisted"
            return decision
        if labels.instance not in self.hosts_config.hosts:
            decision.reason = "host is not configured"
            return decision
        if labels.instance not in ALERT_ALLOWED_HOSTS.get(labels.alertname, set()):
            decision.reason = "host is not allowed for this alert"
            return decision
        host_config = self.hosts_config.hosts[labels.instance]
        if action == ActionName.RESTART_APACHE and "apache" not in host_config.services:
            decision.reason = "apache service is not configured for host"
            return decision
        if action == ActionName.RESTART_MARIADB and "mariadb" not in host_config.services:
            decision.reason = "mariadb service is not configured for host"
            return decision
        if action == ActionName.REBOOT_VM and host_config.proxmox is None:
            decision.reason = "proxmox mapping is not configured for host"
            return decision
        decision.allowed = True
        decision.reason = "allowed"
        return decision
