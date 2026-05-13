from __future__ import annotations

from app.config import PoliciesConfig
from app.models import ActionName
from app.storage.state import StateStore


class CircuitBreaker:
    def __init__(self, *, policies: PoliciesConfig, state_store: StateStore) -> None:
        self.policies = policies
        self.state_store = state_store

    def check(self, *, host: str, action: ActionName, target: str) -> tuple[bool, str]:
        action_type = "reboot_vm" if action == ActionName.REBOOT_VM else "restart_service"
        limit = self.policies.limits[action_type]
        attempts = self.state_store.count_attempts(
            host=host,
            action_type=action_type,
            target=target,
            window_minutes=limit.window_minutes,
        )
        if attempts >= limit.max_attempts:
            return (
                False,
                "circuit breaker open: "
                f"{attempts}/{limit.max_attempts} attempts for {target} in {limit.window_minutes}m",
            )
        return True, "circuit breaker closed"

    def record(self, *, host: str, action: ActionName, target: str, correlation_id: str) -> None:
        action_type = "reboot_vm" if action == ActionName.REBOOT_VM else "restart_service"
        self.state_store.record_attempt(
            host=host,
            action_type=action_type,
            target=target,
            correlation_id=correlation_id,
        )
