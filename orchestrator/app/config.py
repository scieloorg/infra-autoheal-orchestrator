from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProxmoxHostConfig(BaseModel):
    node: str
    vmid: int


class HostConfig(BaseModel):
    ssh_user: str
    ssh_private_key_path: Path | None = None
    ssh_known_hosts_path: Path | None = None
    services: dict[str, str] = Field(default_factory=dict)
    http_healthcheck: str | None = None
    proxmox: ProxmoxHostConfig | None = None


class HostsConfig(BaseModel):
    hosts: dict[str, HostConfig]


class LimitConfig(BaseModel):
    max_attempts: int
    window_minutes: int


class TimeoutConfig(BaseModel):
    ssh_seconds: int = 10
    command_seconds: int = 30
    http_check_seconds: int = 10


class RebootPreconditionConfig(BaseModel):
    min_alert_age_minutes: int = 5


class PoliciesConfig(BaseModel):
    limits: dict[str, LimitConfig]
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)
    reboot_preconditions: RebootPreconditionConfig = Field(default_factory=RebootPreconditionConfig)


class ProxmoxSettings(BaseModel):
    base_url: HttpUrl | None = None
    token_id: str | None = None
    token_secret: str | None = None
    verify_tls: bool = True


class OpenSearchSettings(BaseModel):
    enabled: bool = False
    hosts: list[str] = Field(default_factory=list)
    username: str | None = None
    password: str | None = None
    verify_certs: bool = True
    index_prefix: str = "infra-incidents"
    max_field_length: int = 8192


class SlackSettings(BaseModel):
    enabled: bool = False
    webhook_url: SecretStr | None = None
    timeout_seconds: int = 5


class SSHSettings(BaseModel):
    private_key_path: Path | None = None
    known_hosts_path: Path | None = None
    password_auth: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORCH_", env_nested_delimiter="__")

    hosts_config_path: Path = PROJECT_ROOT / "config" / "hosts.yaml"
    policies_config_path: Path = PROJECT_ROOT / "config" / "policies.yaml"
    sqlite_path: Path = PROJECT_ROOT / "data" / "orchestrator.sqlite3"
    log_level: str = "INFO"
    webhook_token: SecretStr | None = None
    ssh: SSHSettings = Field(default_factory=SSHSettings)
    proxmox: ProxmoxSettings = Field(default_factory=ProxmoxSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    slack: SlackSettings = Field(default_factory=SlackSettings)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_hosts_config() -> HostsConfig:
    return HostsConfig.model_validate(_load_yaml(get_settings().hosts_config_path))


@lru_cache
def get_policies_config() -> PoliciesConfig:
    return PoliciesConfig.model_validate(_load_yaml(get_settings().policies_config_path))
