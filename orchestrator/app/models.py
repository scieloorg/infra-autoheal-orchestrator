from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ActionName(StrEnum):
    RESTART_APACHE = "restart_apache"
    RESTART_MARIADB = "restart_mariadb"
    COLLECT_EVIDENCE = "collect_evidence"
    REBOOT_VM = "reboot_vm"


class AlertLabels(BaseModel):
    model_config = ConfigDict(extra="allow")

    alertname: str
    instance: str
    action: str | None = None


class AlertItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    labels: AlertLabels
    startsAt: datetime | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)


class AlertmanagerPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["firing", "resolved"] | str
    alerts: list[AlertItem] = Field(default_factory=list)


class CommandResult(BaseModel):
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class ValidationResult(BaseModel):
    name: str
    success: bool
    detail: str = ""


class EvidenceBundle(BaseModel):
    commands: list[CommandResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionDecision(BaseModel):
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    alertname: str
    host: str
    action: ActionName | None = None
    allowed: bool = False
    reason: str = ""


class ActionExecution(BaseModel):
    decision: ActionDecision
    status: Literal["success", "failed", "blocked", "ignored"]
    commands: list[CommandResult] = Field(default_factory=list)
    validation: ValidationResult | None = None
    evidence: EvidenceBundle | None = None
    blocked_reason: str | None = None
    proxmox_response: dict[str, Any] | None = None


class AlertProcessResponse(BaseModel):
    correlation_id: str
    processed: int
    results: list[ActionExecution]
