"""
Configuration management for craft-proxmox.
"""

import json
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProxmoxConfig(BaseSettings):
    """
    Proxmox connection configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="PROXMOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(description="Proxmox host address (e.g., 192.168.1.100)")
    port: int = Field(default=8006, description="Proxmox API port")
    user: str = Field(description="Proxmox user (e.g., root@pam or apiuser@pve)")
    token_name: Optional[str] = Field(
        default=None,
        description="API token name (if using token auth)",
    )
    token_value: Optional[SecretStr] = Field(
        default=None,
        description="API token value (if using token auth)",
    )
    password: Optional[SecretStr] = Field(
        default=None,
        description="Password (if using password auth)",
    )
    verify_ssl: bool = Field(
        default=False,
        description="Verify SSL certificate",
    )

    @property
    def use_token_auth(self) -> bool:
        return self.token_name is not None and self.token_value is not None


class CraftConfig(BaseSettings):
    """
    Craft Docs API configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="CRAFT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_url: str = Field(description="Craft API endpoint URL")
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="Craft API key for authentication",
    )
    root_document_id: Optional[str] = Field(
        default=None,
        description="Root document ID to sync under",
    )


class AlertConfig(BaseSettings):
    """
    Alert threshold configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="ALERT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cpu_warning_threshold: float = Field(
        default=80.0,
        description="CPU usage percentage to trigger warning",
    )
    cpu_critical_threshold: float = Field(
        default=95.0,
        description="CPU usage percentage to trigger critical alert",
    )
    memory_warning_threshold: float = Field(
        default=80.0,
        description="Memory usage percentage to trigger warning",
    )
    memory_critical_threshold: float = Field(
        default=95.0,
        description="Memory usage percentage to trigger critical alert",
    )
    storage_warning_threshold: float = Field(
        default=20.0,
        description="Free storage percentage below which to warn",
    )
    storage_critical_threshold: float = Field(
        default=10.0,
        description="Free storage percentage below which to alert critical",
    )
    backup_warning_days: int = Field(
        default=7,
        description="Days without backup to trigger warning",
    )
    backup_critical_days: int = Field(
        default=30,
        description="Days without backup to trigger critical alert",
    )
    alert_on_stopped: bool = Field(
        default=False,
        description="Show info alerts for stopped resources",
    )


class SyncConfig(BaseSettings):
    """
    Sync behavior configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="SYNC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    include_templates: bool = Field(
        default=False,
        description="Include template VMs/containers in sync",
    )
    include_stopped: bool = Field(
        default=True,
        description="Include stopped VMs/containers in sync",
    )
    tag_filter: Optional[str] = Field(
        default=None,
        description="Only sync resources with this tag",
    )
    node_filter: Optional[str] = Field(
        default=None,
        description="Only sync resources from this node",
    )
    group_by: str = Field(
        default="node",
        description="Group resources by: node, tag, status, or none",
    )
    include_storage: bool = Field(
        default=False,
        description="Include storage pool information",
    )
    include_backups: bool = Field(
        default=False,
        description="Include backup status for each resource",
    )
    show_alerts: bool = Field(
        default=True,
        description="Show alert indicators for resources needing attention",
    )


class AppConfig(BaseSettings):
    """
    Combined application configuration.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    proxmox: ProxmoxConfig = Field(default_factory=ProxmoxConfig)
    craft: CraftConfig = Field(default_factory=CraftConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """
    Load configuration from file and environment variables.

    Args:
        config_path: Optional path to a JSON config file.

    Returns:
        AppConfig instance with merged configuration.
    """
    if config_path and config_path.exists():
        with open(config_path) as f:
            config_data = json.load(f)
        return AppConfig(**config_data)
    return AppConfig()


def save_config(config: AppConfig, config_path: Path) -> None:
    """
    Save configuration to a JSON file.

    Args:
        config: AppConfig instance to save.
        config_path: Path to save the config file.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "proxmox": {
            "host": config.proxmox.host,
            "port": config.proxmox.port,
            "user": config.proxmox.user,
            "token_name": config.proxmox.token_name,
            "verify_ssl": config.proxmox.verify_ssl,
        },
        "craft": {
            "api_url": config.craft.api_url,
            "root_document_id": config.craft.root_document_id,
        },
        "sync": {
            "include_templates": config.sync.include_templates,
            "include_stopped": config.sync.include_stopped,
            "tag_filter": config.sync.tag_filter,
            "node_filter": config.sync.node_filter,
        },
    }

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)
