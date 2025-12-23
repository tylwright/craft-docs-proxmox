"""
Data models for Proxmox resources and Craft document structures.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResourceStatus(str, Enum):
    """
    Status of a Proxmox resource.
    """

    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


class ResourceType(str, Enum):
    """
    Type of Proxmox resource.
    """

    VM = "qemu"
    LXC = "lxc"


class GroupBy(str, Enum):
    """
    Options for grouping resources in output.
    """

    NODE = "node"
    TAG = "tag"
    STATUS = "status"
    NONE = "none"


class AlertSeverity(str, Enum):
    """
    Severity levels for alerts.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """
    Types of alerts.
    """

    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    LOW_STORAGE = "low_storage"
    NO_BACKUP = "no_backup"
    OLD_BACKUP = "old_backup"
    STOPPED = "stopped"


class ResourceAlert(BaseModel):
    """
    Represents an alert condition for a resource.
    """

    alert_type: AlertType
    severity: AlertSeverity
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


class StoragePool(BaseModel):
    """
    Represents a Proxmox storage pool.
    """

    name: str
    node: str
    storage_type: str
    content: list[str] = Field(default_factory=list)
    total_bytes: Optional[int] = None
    used_bytes: Optional[int] = None
    available_bytes: Optional[int] = None
    enabled: bool = True
    shared: bool = False

    @property
    def usage_percent(self) -> Optional[float]:
        """
        Calculate storage usage percentage.
        """
        if self.total_bytes and self.used_bytes:
            return (self.used_bytes / self.total_bytes) * 100
        return None

    @property
    def free_percent(self) -> Optional[float]:
        """
        Calculate free space percentage.
        """
        if self.usage_percent is not None:
            return 100 - self.usage_percent
        return None


class Backup(BaseModel):
    """
    Represents a backup for a VM or container.
    """

    vmid: int
    node: str
    storage: str
    filename: str
    size_bytes: Optional[int] = None
    backup_time: Optional[int] = None
    backup_type: str = "vzdump"
    notes: Optional[str] = None

    @property
    def age_days(self) -> Optional[int]:
        """
        Calculate how many days old this backup is.
        """
        if self.backup_time:
            from datetime import datetime as dt
            age_seconds = dt.now().timestamp() - self.backup_time
            return int(age_seconds // 86400)
        return None


class BackupInfo(BaseModel):
    """
    Aggregated backup information for a VM or container.
    """

    vmid: int
    backups: list[Backup] = Field(default_factory=list)
    scheduled_job: Optional[str] = None

    @property
    def last_backup(self) -> Optional[Backup]:
        """
        Get the most recent backup.
        """
        if self.backups:
            return max(self.backups, key=lambda b: b.backup_time or 0)
        return None

    @property
    def last_backup_age_days(self) -> Optional[int]:
        """
        Days since last backup.
        """
        if self.last_backup:
            return self.last_backup.age_days
        return None

    @property
    def has_recent_backup(self) -> bool:
        """
        True if backup within last 7 days.
        """
        age = self.last_backup_age_days
        return age is not None and age <= 7


class ProxmoxNode(BaseModel):
    """
    Represents a Proxmox cluster node.
    """

    name: str
    status: str
    cpu_usage: Optional[float] = Field(None, ge=0, le=1)
    memory_used: Optional[int] = None
    memory_total: Optional[int] = None
    uptime: Optional[int] = None
    ip_address: Optional[str] = None
    storage_pools: list[StoragePool] = Field(default_factory=list)

    @property
    def memory_usage_percent(self) -> Optional[float]:
        if self.memory_used and self.memory_total:
            return (self.memory_used / self.memory_total) * 100
        return None


class Snapshot(BaseModel):
    """
    Represents a VM or container snapshot.
    """

    name: str
    description: Optional[str] = None
    snaptime: Optional[int] = None  # Unix timestamp


class NetworkInterface(BaseModel):
    """
    Represents a network interface configuration.
    """

    name: str  # e.g., "net0"
    bridge: Optional[str] = None
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None
    gateway: Optional[str] = None
    vlan_tag: Optional[int] = None
    model: Optional[str] = None  # virtio, e1000, etc.


class ProxmoxVM(BaseModel):
    """
    Represents a Proxmox VM (QEMU).
    """

    vmid: int
    name: str
    node: str
    status: ResourceStatus
    resource_type: ResourceType = ResourceType.VM
    cpu_cores: Optional[int] = None
    memory_mb: Optional[int] = None
    disk_gb: Optional[float] = None
    ip_addresses: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    template: bool = False
    uptime: Optional[int] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    os_type: Optional[str] = None
    # New fields
    snapshots: list[Snapshot] = Field(default_factory=list)
    network_interfaces: list[NetworkInterface] = Field(default_factory=list)
    disk_info: Optional[str] = None  # e.g., "scsi0: 64G"
    backup_info: Optional[BackupInfo] = None
    alerts: list[ResourceAlert] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or f"VM-{self.vmid}"

    @property
    def snapshot_count(self) -> int:
        # Exclude 'current' snapshot marker
        return len([s for s in self.snapshots if s.name != "current"])

    @property
    def has_warnings(self) -> bool:
        """
        True if resource has warning or critical alerts.
        """
        return any(
            a.severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL)
            for a in self.alerts
        )

    @property
    def has_critical(self) -> bool:
        """
        True if resource has critical alerts.
        """
        return any(a.severity == AlertSeverity.CRITICAL for a in self.alerts)


class ProxmoxContainer(BaseModel):
    """
    Represents a Proxmox LXC container.
    """

    vmid: int
    name: str
    node: str
    status: ResourceStatus
    resource_type: ResourceType = ResourceType.LXC
    cpu_cores: Optional[int] = None
    memory_mb: Optional[int] = None
    disk_gb: Optional[float] = None
    ip_addresses: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    template: bool = False
    uptime: Optional[int] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    os_template: Optional[str] = None
    hostname: Optional[str] = None
    # New fields
    snapshots: list[Snapshot] = Field(default_factory=list)
    network_interfaces: list[NetworkInterface] = Field(default_factory=list)
    rootfs_size: Optional[str] = None
    backup_info: Optional[BackupInfo] = None
    alerts: list[ResourceAlert] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or self.hostname or f"CT-{self.vmid}"

    @property
    def snapshot_count(self) -> int:
        # Exclude 'current' snapshot marker
        return len([s for s in self.snapshots if s.name != "current"])

    @property
    def has_warnings(self) -> bool:
        """
        True if resource has warning or critical alerts.
        """
        return any(
            a.severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL)
            for a in self.alerts
        )

    @property
    def has_critical(self) -> bool:
        """
        True if resource has critical alerts.
        """
        return any(a.severity == AlertSeverity.CRITICAL for a in self.alerts)


class ProxmoxCluster(BaseModel):
    """
    Represents the entire Proxmox cluster state.
    """

    name: Optional[str] = None
    nodes: list[ProxmoxNode] = Field(default_factory=list)
    vms: list[ProxmoxVM] = Field(default_factory=list)
    containers: list[ProxmoxContainer] = Field(default_factory=list)
    last_sync: Optional[datetime] = None

    @property
    def total_vms(self) -> int:
        return len(self.vms)

    @property
    def total_containers(self) -> int:
        return len(self.containers)

    @property
    def running_vms(self) -> int:
        return sum(1 for vm in self.vms if vm.status == ResourceStatus.RUNNING)

    @property
    def running_containers(self) -> int:
        return sum(1 for ct in self.containers if ct.status == ResourceStatus.RUNNING)


class CraftBlock(BaseModel):
    """
    Represents a block in a Craft document.
    """

    id: Optional[str] = None
    type: str = "text"
    content: str = ""
    style: Optional[dict] = None
    children: list["CraftBlock"] = Field(default_factory=list)


class CraftDocument(BaseModel):
    """
    Represents a Craft document structure.
    """

    id: Optional[str] = None
    title: str
    blocks: list[CraftBlock] = Field(default_factory=list)
    parent_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SyncResult(BaseModel):
    """
    Result of a sync operation.
    """

    success: bool
    documents_created: int = 0
    documents_updated: int = 0
    documents_deleted: int = 0
    errors: list[str] = Field(default_factory=list)
    sync_time: datetime = Field(default_factory=datetime.now)
