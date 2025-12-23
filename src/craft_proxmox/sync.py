"""
Sync engine for synchronizing Proxmox data to Craft Docs.

This module handles the logic for inserting Proxmox cluster data
into Craft documents as markdown content with hierarchical subpages.
"""

import re
from datetime import datetime
from typing import Any, Optional

from .config import AlertConfig, AppConfig
from .craft_client import CraftClient, MarkdownBuilder
from .models import (
    AlertSeverity,
    AlertType,
    BackupInfo,
    NetworkInterface,
    ProxmoxCluster,
    ProxmoxContainer,
    ProxmoxNode,
    ProxmoxVM,
    ResourceAlert,
    ResourceStatus,
    Snapshot,
    StoragePool,
)
from .proxmox_client import ProxmoxClient


def strip_html(text: str) -> str:
    """
    Remove HTML tags from text.
    """
    if not text:
        return text
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Clean up extra whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def format_uptime(seconds: Optional[int]) -> str:
    """
    Format uptime in seconds to human-readable string.
    """
    if seconds is None:
        return "Unknown"

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or not parts:
        parts.append(f"{minutes}m")

    return " ".join(parts)


def format_memory(mb: Optional[int]) -> str:
    """
    Format memory in MB to human-readable string.
    """
    if mb is None:
        return "Unknown"

    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb} MB"


def format_disk(gb: Optional[float]) -> str:
    """
    Format disk size in GB to human-readable string.
    """
    if gb is None:
        return "Unknown"

    if gb >= 1024:
        return f"{gb / 1024:.1f} TB"
    return f"{gb:.1f} GB"


def format_snapshot_time(timestamp: Optional[int]) -> str:
    """
    Format snapshot timestamp to human-readable string.
    """
    if timestamp is None:
        return "Unknown"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def format_bytes(bytes_val: Optional[int]) -> str:
    """
    Format bytes to human-readable string.
    """
    if bytes_val is None:
        return "Unknown"

    if bytes_val >= 1024 ** 4:
        return f"{bytes_val / (1024 ** 4):.1f} TB"
    elif bytes_val >= 1024 ** 3:
        return f"{bytes_val / (1024 ** 3):.1f} GB"
    elif bytes_val >= 1024 ** 2:
        return f"{bytes_val / (1024 ** 2):.1f} MB"
    return f"{bytes_val} B"


class AlertEvaluator:
    """
    Evaluates resources against alert thresholds.
    """

    def __init__(self, config: AlertConfig):
        """
        Initialize the alert evaluator.

        Args:
            config: AlertConfig with threshold settings.
        """
        self.config = config

    def evaluate_vm(self, vm: ProxmoxVM) -> list[ResourceAlert]:
        """
        Evaluate a VM for alert conditions.

        Args:
            vm: The VM to evaluate.

        Returns:
            List of ResourceAlert instances.
        """
        alerts = []

        # CPU usage alerts
        if vm.cpu_usage is not None:
            cpu_pct = vm.cpu_usage * 100
            if cpu_pct >= self.config.cpu_critical_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.HIGH_CPU,
                    severity=AlertSeverity.CRITICAL,
                    message=f"CPU usage critical: {cpu_pct:.1f}%",
                    value=cpu_pct,
                    threshold=self.config.cpu_critical_threshold,
                ))
            elif cpu_pct >= self.config.cpu_warning_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.HIGH_CPU,
                    severity=AlertSeverity.WARNING,
                    message=f"CPU usage high: {cpu_pct:.1f}%",
                    value=cpu_pct,
                    threshold=self.config.cpu_warning_threshold,
                ))

        # Memory usage alerts
        if vm.memory_usage is not None:
            mem_pct = vm.memory_usage * 100
            if mem_pct >= self.config.memory_critical_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.HIGH_MEMORY,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Memory usage critical: {mem_pct:.1f}%",
                    value=mem_pct,
                    threshold=self.config.memory_critical_threshold,
                ))
            elif mem_pct >= self.config.memory_warning_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.HIGH_MEMORY,
                    severity=AlertSeverity.WARNING,
                    message=f"Memory usage high: {mem_pct:.1f}%",
                    value=mem_pct,
                    threshold=self.config.memory_warning_threshold,
                ))

        # Backup alerts
        if vm.backup_info:
            age = vm.backup_info.last_backup_age_days
            if age is None:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.NO_BACKUP,
                    severity=AlertSeverity.CRITICAL,
                    message="No backups found",
                ))
            elif age >= self.config.backup_critical_days:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.OLD_BACKUP,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Last backup {age} days ago",
                    value=float(age),
                    threshold=float(self.config.backup_critical_days),
                ))
            elif age >= self.config.backup_warning_days:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.OLD_BACKUP,
                    severity=AlertSeverity.WARNING,
                    message=f"Last backup {age} days ago",
                    value=float(age),
                    threshold=float(self.config.backup_warning_days),
                ))

        # Stopped resource info
        if self.config.alert_on_stopped and vm.status == ResourceStatus.STOPPED:
            alerts.append(ResourceAlert(
                alert_type=AlertType.STOPPED,
                severity=AlertSeverity.INFO,
                message="Resource is stopped",
            ))

        return alerts

    def evaluate_container(self, ct: ProxmoxContainer) -> list[ResourceAlert]:
        """
        Evaluate a container for alert conditions.

        Args:
            ct: The container to evaluate.

        Returns:
            List of ResourceAlert instances.
        """
        alerts = []

        # CPU usage alerts
        if ct.cpu_usage is not None:
            cpu_pct = ct.cpu_usage * 100
            if cpu_pct >= self.config.cpu_critical_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.HIGH_CPU,
                    severity=AlertSeverity.CRITICAL,
                    message=f"CPU usage critical: {cpu_pct:.1f}%",
                    value=cpu_pct,
                    threshold=self.config.cpu_critical_threshold,
                ))
            elif cpu_pct >= self.config.cpu_warning_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.HIGH_CPU,
                    severity=AlertSeverity.WARNING,
                    message=f"CPU usage high: {cpu_pct:.1f}%",
                    value=cpu_pct,
                    threshold=self.config.cpu_warning_threshold,
                ))

        # Memory usage alerts
        if ct.memory_usage is not None:
            mem_pct = ct.memory_usage * 100
            if mem_pct >= self.config.memory_critical_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.HIGH_MEMORY,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Memory usage critical: {mem_pct:.1f}%",
                    value=mem_pct,
                    threshold=self.config.memory_critical_threshold,
                ))
            elif mem_pct >= self.config.memory_warning_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.HIGH_MEMORY,
                    severity=AlertSeverity.WARNING,
                    message=f"Memory usage high: {mem_pct:.1f}%",
                    value=mem_pct,
                    threshold=self.config.memory_warning_threshold,
                ))

        # Backup alerts
        if ct.backup_info:
            age = ct.backup_info.last_backup_age_days
            if age is None:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.NO_BACKUP,
                    severity=AlertSeverity.CRITICAL,
                    message="No backups found",
                ))
            elif age >= self.config.backup_critical_days:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.OLD_BACKUP,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Last backup {age} days ago",
                    value=float(age),
                    threshold=float(self.config.backup_critical_days),
                ))
            elif age >= self.config.backup_warning_days:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.OLD_BACKUP,
                    severity=AlertSeverity.WARNING,
                    message=f"Last backup {age} days ago",
                    value=float(age),
                    threshold=float(self.config.backup_warning_days),
                ))

        # Stopped resource info
        if self.config.alert_on_stopped and ct.status == ResourceStatus.STOPPED:
            alerts.append(ResourceAlert(
                alert_type=AlertType.STOPPED,
                severity=AlertSeverity.INFO,
                message="Resource is stopped",
            ))

        return alerts

    def evaluate_storage(self, pool: StoragePool) -> list[ResourceAlert]:
        """
        Evaluate a storage pool for low space alerts.

        Args:
            pool: The storage pool to evaluate.

        Returns:
            List of ResourceAlert instances.
        """
        alerts = []

        if pool.free_percent is not None:
            if pool.free_percent <= self.config.storage_critical_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.LOW_STORAGE,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Storage nearly full: {pool.free_percent:.1f}% free",
                    value=pool.free_percent,
                    threshold=self.config.storage_critical_threshold,
                ))
            elif pool.free_percent <= self.config.storage_warning_threshold:
                alerts.append(ResourceAlert(
                    alert_type=AlertType.LOW_STORAGE,
                    severity=AlertSeverity.WARNING,
                    message=f"Storage low: {pool.free_percent:.1f}% free",
                    value=pool.free_percent,
                    threshold=self.config.storage_warning_threshold,
                ))

        return alerts


class SyncEngine:
    """
    Engine for synchronizing Proxmox data to Craft Docs.

    Creates a hierarchical structure with:
    - Dashboard overview at the top
    - Sections for each node
    - Subpages for each VM and container with detailed information
    """

    def __init__(
        self,
        proxmox_client: ProxmoxClient,
        craft_client: CraftClient,
        config: AppConfig,
    ):
        """
        Initialize the sync engine.

        Args:
            proxmox_client: Configured Proxmox client.
            craft_client: Configured Craft client.
            config: Application configuration.
        """
        self.proxmox = proxmox_client
        self.craft = craft_client
        self.config = config
        self.md = MarkdownBuilder

    def _get_target_document(self) -> str:
        """
        Get the target document ID for syncing.

        Returns the configured root_document_id or the first available document.
        """
        if self.config.craft.root_document_id:
            return self.config.craft.root_document_id

        docs = self.craft.get_documents()
        if not docs:
            raise ValueError("No documents available in Craft API connection")

        return docs[0]["id"]

    def _get_proxmox_url(self, resource_type: str, node: str, vmid: int) -> str:
        """
        Generate a Proxmox web UI URL for a resource.

        Args:
            resource_type: Either "qemu" or "lxc".
            node: Node name.
            vmid: VM or container ID.

        Returns:
            URL to the Proxmox web UI for this resource.
        """
        host = self.config.proxmox.host
        port = self.config.proxmox.port
        return f"https://{host}:{port}/#v1:0:={resource_type}/{vmid}:4"

    def _format_status_legend(self) -> str:
        """
        Generate the status legend markdown.
        """
        return """**Status Legend:**
- 🟢 Running - Resource is active and operational
- 🔴 Stopped - Resource is powered off
- 🟡 Paused - Resource is temporarily suspended
- 🟠 Suspended - Resource is hibernated to disk
- ⚪ Unknown - Status could not be determined
"""

    def _format_cluster_overview(
        self,
        cluster: ProxmoxCluster,
        show_alerts: bool = True,
    ) -> str:
        """
        Generate markdown for cluster overview.
        """
        lines = [
            self.md.heading("Proxmox Infrastructure Dashboard", 1),
            "",
            f"*Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
        ]

        if cluster.name:
            lines.append(f"**Cluster:** {cluster.name}")
            lines.append("")

        lines.append(self.md.heading("Overview", 2))
        lines.append("")

        overview_items = [
            f"**Nodes:** {len(cluster.nodes)}",
            f"**Virtual Machines:** {cluster.total_vms} ({cluster.running_vms} running)",
            f"**Containers:** {cluster.total_containers} ({cluster.running_containers} running)",
        ]

        # Add health summary if alerts are enabled
        if show_alerts:
            overview_items.append(self._format_alerts_summary(cluster))

        lines.append(self.md.bullet_list(overview_items))
        lines.append("")

        # Add status legend
        lines.append(self._format_status_legend())
        lines.append("")
        lines.append(self.md.horizontal_rule())

        return "\n".join(lines)

    def _format_network_interfaces(self, interfaces: list[NetworkInterface]) -> str:
        """
        Format network interfaces as markdown.
        """
        if not interfaces:
            return ""

        lines = ["", "**Network Interfaces:**"]
        for iface in interfaces:
            parts = [f"**{iface.name}**"]
            if iface.bridge:
                parts.append(f"Bridge: {iface.bridge}")
            if iface.ip_address:
                parts.append(f"IP: {iface.ip_address}")
            if iface.gateway:
                parts.append(f"GW: {iface.gateway}")
            if iface.vlan_tag:
                parts.append(f"VLAN: {iface.vlan_tag}")
            if iface.mac_address:
                parts.append(f"MAC: {iface.mac_address}")
            if iface.model:
                parts.append(f"Model: {iface.model}")
            lines.append(f"- {' | '.join(parts)}")

        return "\n".join(lines)

    def _format_snapshots(self, snapshots: list[Snapshot]) -> str:
        """
        Format snapshots as markdown.
        """
        if not snapshots:
            return ""

        lines = ["", "**Snapshots:**"]
        for snap in snapshots:
            time_str = format_snapshot_time(snap.snaptime)
            desc = f" - {snap.description}" if snap.description else ""
            lines.append(f"- **{snap.name}** ({time_str}){desc}")

        return "\n".join(lines)

    def _format_storage_pools(self, pools: list[StoragePool]) -> str:
        """
        Format storage pools as markdown with alert indicators.
        """
        if not pools:
            return ""

        lines = ["", self.md.heading("Storage Pools", 3), ""]

        evaluator = AlertEvaluator(self.config.alerts)

        for pool in pools:
            alerts = evaluator.evaluate_storage(pool)
            has_critical = any(a.severity == AlertSeverity.CRITICAL for a in alerts)
            has_warning = any(a.severity == AlertSeverity.WARNING for a in alerts)

            # Status indicator
            if has_critical:
                indicator = "🚨"
            elif has_warning:
                indicator = "⚠️"
            else:
                indicator = "🟢"

            # Format size info
            size_info = ""
            if pool.total_bytes:
                size_info = f" | Size: {format_bytes(pool.total_bytes)}"
                if pool.usage_percent is not None:
                    size_info += f" ({pool.usage_percent:.0f}% used)"

            # Content types
            content = ""
            if pool.content:
                content = f" | Content: {', '.join(pool.content)}"

            shared = " | Shared" if pool.shared else ""

            lines.append(
                f"- {indicator} **{pool.name}** | Type: {pool.storage_type}"
                f"{size_info}{content}{shared}"
            )

        return "\n".join(lines)

    def _format_backup_info(self, backup_info: Optional[BackupInfo]) -> str:
        """
        Format backup information for a resource.
        """
        if not backup_info:
            return ""

        lines = ["", self.md.heading("Backups", 2)]

        last = backup_info.last_backup
        if last:
            age = backup_info.last_backup_age_days
            time_str = format_snapshot_time(last.backup_time)
            age_indicator = ""
            if age is not None:
                if age >= self.config.alerts.backup_critical_days:
                    age_indicator = " 🚨"
                elif age >= self.config.alerts.backup_warning_days:
                    age_indicator = " ⚠️"
                age_str = f" ({age} days ago)"
            else:
                age_str = ""
            lines.append(f"- **Last backup:** {time_str}{age_str}{age_indicator}")

            if last.size_bytes:
                lines.append(f"- **Size:** {format_bytes(last.size_bytes)}")
            if last.storage:
                lines.append(f"- **Storage:** {last.storage}")
        else:
            lines.append("- 🚨 **No backups found**")

        if backup_info.scheduled_job:
            lines.append(f"- **Scheduled:** Yes (Job: {backup_info.scheduled_job})")
        else:
            lines.append("- **Scheduled:** No")

        lines.append(f"- **Total backups:** {len(backup_info.backups)}")

        return "\n".join(lines)

    def _format_alerts_section(self, alerts: list[ResourceAlert]) -> str:
        """
        Format alerts as a markdown section.
        """
        if not alerts:
            return ""

        # Filter to only warning and critical
        significant_alerts = [
            a for a in alerts
            if a.severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL)
        ]

        if not significant_alerts:
            return ""

        lines = ["", "**Alerts:**"]
        for alert in significant_alerts:
            icon = "🚨" if alert.severity == AlertSeverity.CRITICAL else "⚠️"
            lines.append(f"- {icon} {alert.message}")

        return "\n".join(lines)

    def _format_deleted_resource_banner(
        self,
        resource_type: str,
        vmid: int,
        last_seen: str,
    ) -> str:
        """
        Format a banner for a resource that no longer exists in Proxmox.

        Args:
            resource_type: "VM" or "Container"
            vmid: The VMID/CTID of the deleted resource
            last_seen: Timestamp of when the resource was last synced

        Returns:
            Markdown string with deletion warning banner.
        """
        return f"""> **⚠️ RESOURCE NO LONGER EXISTS**
>
> This {resource_type} (ID: {vmid}) was not found in Proxmox during the last sync on {last_seen}.
>
> It may have been deleted, migrated to another cluster, or the sync filters may have changed.
>
> **Your notes below have been preserved.** Review and archive this page when ready.

---

"""

    def _format_deleted_vm_page(
        self,
        vmid: int,
        original_name: str,
        user_notes: Optional[str],
    ) -> str:
        """
        Format a page for a deleted VM, preserving user notes.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        banner = self._format_deleted_resource_banner("VM", vmid, timestamp)

        lines = [
            self.md.heading(f"⚠️ {original_name} (Deleted)", 1),
            "",
            banner,
            self.md.heading("Original Resource Info", 2),
            f"- **Type:** Virtual Machine",
            f"- **VMID:** {vmid}",
            f"- **Status:** Not found in Proxmox",
            "",
        ]

        # Preserve user notes
        lines.append(self.md.heading("Notes", 2))
        if user_notes:
            lines.append(user_notes)
        else:
            lines.append("*No notes were saved for this resource.*")
        lines.append("")

        return "\n".join(lines)

    def _format_deleted_container_page(
        self,
        vmid: int,
        original_name: str,
        user_notes: Optional[str],
    ) -> str:
        """
        Format a page for a deleted container, preserving user notes.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        banner = self._format_deleted_resource_banner("Container", vmid, timestamp)

        lines = [
            self.md.heading(f"⚠️ {original_name} (Deleted)", 1),
            "",
            banner,
            self.md.heading("Original Resource Info", 2),
            f"- **Type:** LXC Container",
            f"- **CTID:** {vmid}",
            f"- **Status:** Not found in Proxmox",
            "",
        ]

        # Preserve user notes
        lines.append(self.md.heading("Notes", 2))
        if user_notes:
            lines.append(user_notes)
        else:
            lines.append("*No notes were saved for this resource.*")
        lines.append("")

        return "\n".join(lines)

    def _format_alerts_summary(self, cluster: ProxmoxCluster) -> str:
        """
        Generate an alerts summary for the dashboard.
        """
        critical_count = 0
        warning_count = 0

        for vm in cluster.vms:
            for alert in vm.alerts:
                if alert.severity == AlertSeverity.CRITICAL:
                    critical_count += 1
                elif alert.severity == AlertSeverity.WARNING:
                    warning_count += 1

        for ct in cluster.containers:
            for alert in ct.alerts:
                if alert.severity == AlertSeverity.CRITICAL:
                    critical_count += 1
                elif alert.severity == AlertSeverity.WARNING:
                    warning_count += 1

        if critical_count == 0 and warning_count == 0:
            return "**Health:** ✅ All systems healthy"

        parts = []
        if critical_count > 0:
            parts.append(f"🚨 {critical_count} critical")
        if warning_count > 0:
            parts.append(f"⚠️ {warning_count} warnings")

        return f"**Health:** {', '.join(parts)}"

    def _get_alert_indicator(
        self,
        resource: ProxmoxVM | ProxmoxContainer,
    ) -> str:
        """
        Get an alert indicator prefix for a resource.
        """
        if resource.has_critical:
            return "🚨 "
        elif resource.has_warnings:
            return "⚠️ "
        return ""

    def _group_resources_by_tag(
        self,
        vms: list[ProxmoxVM],
        containers: list[ProxmoxContainer],
    ) -> dict[str, tuple[list[ProxmoxVM], list[ProxmoxContainer]]]:
        """
        Group resources by their tags.

        Resources with multiple tags appear under each tag.
        Resources without tags appear under "Untagged".
        """
        groups: dict[str, tuple[list[ProxmoxVM], list[ProxmoxContainer]]] = {}

        for vm in vms:
            tags = vm.tags if vm.tags else ["Untagged"]
            for tag in tags:
                if tag not in groups:
                    groups[tag] = ([], [])
                groups[tag][0].append(vm)

        for ct in containers:
            tags = ct.tags if ct.tags else ["Untagged"]
            for tag in tags:
                if tag not in groups:
                    groups[tag] = ([], [])
                groups[tag][1].append(ct)

        return groups

    def _group_resources_by_status(
        self,
        vms: list[ProxmoxVM],
        containers: list[ProxmoxContainer],
    ) -> dict[str, tuple[list[ProxmoxVM], list[ProxmoxContainer]]]:
        """
        Group resources by their status (running, stopped, etc.).
        """
        groups: dict[str, tuple[list[ProxmoxVM], list[ProxmoxContainer]]] = {}

        for vm in vms:
            status = vm.status.value.capitalize()
            if status not in groups:
                groups[status] = ([], [])
            groups[status][0].append(vm)

        for ct in containers:
            status = ct.status.value.capitalize()
            if status not in groups:
                groups[status] = ([], [])
            groups[status][1].append(ct)

        return groups

    def _evaluate_alerts(self, cluster: ProxmoxCluster) -> None:
        """
        Evaluate alerts for all resources in a cluster.

        This mutates the cluster objects, adding alerts to each VM and container.
        """
        evaluator = AlertEvaluator(self.config.alerts)

        for vm in cluster.vms:
            vm.alerts = evaluator.evaluate_vm(vm)

        for ct in cluster.containers:
            ct.alerts = evaluator.evaluate_container(ct)

    def _format_vm_summary(self, vm: ProxmoxVM) -> str:
        """
        Generate a brief summary line for a VM (for the main list).
        """
        status_badge = self.md.status_badge(vm.status.value)
        ip_info = f" | {vm.ip_addresses[0]}" if vm.ip_addresses else ""
        return f"- {status_badge} **{vm.display_name}** (VMID: {vm.vmid}){ip_info}"

    def _format_vm_detail(self, vm: ProxmoxVM) -> str:
        """
        Generate detailed markdown for a VM (for its subpage).
        """
        status_badge = self.md.status_badge(vm.status.value)
        proxmox_url = self._get_proxmox_url("qemu", vm.node, vm.vmid)
        alert_indicator = self._get_alert_indicator(vm)

        lines = [
            self.md.heading(f"{alert_indicator}{vm.display_name}", 1),
            "",
            f"{status_badge} | VMID: {vm.vmid} | Node: {vm.node}",
            "",
            f"[Open in Proxmox]({proxmox_url})",
            "",
        ]

        # Alerts section (if any)
        if vm.alerts:
            lines.append(self._format_alerts_section(vm.alerts))
            lines.append("")

        # Specs section
        lines.append(self.md.heading("Specifications", 2))
        specs = []
        if vm.cpu_cores:
            specs.append(f"**CPU:** {vm.cpu_cores} cores")
        if vm.memory_mb:
            specs.append(f"**Memory:** {format_memory(vm.memory_mb)}")
        if vm.disk_gb:
            specs.append(f"**Disk:** {format_disk(vm.disk_gb)}")
        if vm.disk_info:
            specs.append(f"**Storage:** {vm.disk_info}")
        if vm.os_type:
            specs.append(f"**OS Type:** {vm.os_type}")
        if vm.uptime:
            specs.append(f"**Uptime:** {format_uptime(vm.uptime)}")

        if specs:
            lines.append(self.md.bullet_list(specs))
        lines.append("")

        # Network section
        if vm.ip_addresses or vm.network_interfaces:
            lines.append(self.md.heading("Network", 2))
            if vm.ip_addresses:
                lines.append(f"**IP Addresses:** {', '.join(vm.ip_addresses)}")
            lines.append(self._format_network_interfaces(vm.network_interfaces))
            lines.append("")

        # Backups section
        if vm.backup_info:
            lines.append(self._format_backup_info(vm.backup_info))
            lines.append("")

        # Snapshots section
        if vm.snapshots:
            lines.append(self.md.heading("Snapshots", 2))
            lines.append(f"Total: {vm.snapshot_count}")
            lines.append(self._format_snapshots(vm.snapshots))
            lines.append("")

        # Tags
        if vm.tags:
            lines.append(self.md.heading("Tags", 2))
            lines.append(f"{', '.join(vm.tags)}")
            lines.append("")

        # Description
        if vm.description:
            clean_desc = strip_html(vm.description)
            if clean_desc:
                lines.append(self.md.heading("Description", 2))
                lines.append(clean_desc)
                lines.append("")

        # Notes section for user content
        lines.append(self.md.heading("Notes", 2))
        lines.append("*Add your notes, runbooks, and documentation here...*")
        lines.append("")

        return "\n".join(lines)

    def _format_container_summary(self, ct: ProxmoxContainer) -> str:
        """
        Generate a brief summary line for a container (for the main list).
        """
        status_badge = self.md.status_badge(ct.status.value)
        ip_info = f" | {ct.ip_addresses[0]}" if ct.ip_addresses else ""
        return f"- {status_badge} **{ct.display_name}** (CTID: {ct.vmid}){ip_info}"

    def _format_container_detail(self, ct: ProxmoxContainer) -> str:
        """
        Generate detailed markdown for a container (for its subpage).
        """
        status_badge = self.md.status_badge(ct.status.value)
        proxmox_url = self._get_proxmox_url("lxc", ct.node, ct.vmid)
        alert_indicator = self._get_alert_indicator(ct)

        lines = [
            self.md.heading(f"{alert_indicator}{ct.display_name}", 1),
            "",
            f"{status_badge} | CTID: {ct.vmid} | Node: {ct.node}",
            "",
            f"[Open in Proxmox]({proxmox_url})",
            "",
        ]

        # Alerts section (if any)
        if ct.alerts:
            lines.append(self._format_alerts_section(ct.alerts))
            lines.append("")

        # Specs section
        lines.append(self.md.heading("Specifications", 2))
        specs = []
        if ct.cpu_cores:
            specs.append(f"**CPU:** {ct.cpu_cores} cores")
        if ct.memory_mb:
            specs.append(f"**Memory:** {format_memory(ct.memory_mb)}")
        if ct.disk_gb:
            specs.append(f"**Disk:** {format_disk(ct.disk_gb)}")
        if ct.rootfs_size:
            specs.append(f"**Root FS:** {ct.rootfs_size}")
        if ct.hostname:
            specs.append(f"**Hostname:** {ct.hostname}")
        if ct.os_template:
            specs.append(f"**Template:** {ct.os_template}")
        if ct.uptime:
            specs.append(f"**Uptime:** {format_uptime(ct.uptime)}")

        if specs:
            lines.append(self.md.bullet_list(specs))
        lines.append("")

        # Network section
        if ct.ip_addresses or ct.network_interfaces:
            lines.append(self.md.heading("Network", 2))
            if ct.ip_addresses:
                lines.append(f"**IP Addresses:** {', '.join(ct.ip_addresses)}")
            lines.append(self._format_network_interfaces(ct.network_interfaces))
            lines.append("")

        # Backups section
        if ct.backup_info:
            lines.append(self._format_backup_info(ct.backup_info))
            lines.append("")

        # Snapshots section
        if ct.snapshots:
            lines.append(self.md.heading("Snapshots", 2))
            lines.append(f"Total: {ct.snapshot_count}")
            lines.append(self._format_snapshots(ct.snapshots))
            lines.append("")

        # Tags
        if ct.tags:
            lines.append(self.md.heading("Tags", 2))
            lines.append(f"{', '.join(ct.tags)}")
            lines.append("")

        # Description
        if ct.description:
            clean_desc = strip_html(ct.description)
            if clean_desc:
                lines.append(self.md.heading("Description", 2))
                lines.append(clean_desc)
                lines.append("")

        # Notes section for user content
        lines.append(self.md.heading("Notes", 2))
        lines.append("*Add your notes, runbooks, and documentation here...*")
        lines.append("")

        return "\n".join(lines)

    def _format_node_section(
        self,
        node: ProxmoxNode,
        vms: list[ProxmoxVM],
        containers: list[ProxmoxContainer],
        include_storage: bool = False,
    ) -> str:
        """
        Generate markdown for a node section header.
        """
        status_icon = "🟢" if node.status == "online" else "🔴"
        lines = [
            "",
            self.md.heading(f"{status_icon} Node: {node.name}", 2),
            "",
        ]

        info_items = [f"**Status:** {node.status.capitalize()}"]

        if node.uptime:
            info_items.append(f"**Uptime:** {format_uptime(node.uptime)}")
        if node.cpu_usage is not None:
            info_items.append(f"**CPU Usage:** {node.cpu_usage * 100:.1f}%")
        if node.memory_usage_percent is not None:
            info_items.append(f"**Memory Usage:** {node.memory_usage_percent:.1f}%")

        # Add Proxmox URL for node
        host = self.config.proxmox.host
        port = self.config.proxmox.port
        node_url = f"https://{host}:{port}/#v1:0:=node/{node.name}:4"
        info_items.append(f"[Open in Proxmox]({node_url})")

        lines.append(self.md.bullet_list(info_items))
        lines.append("")

        # Add storage pools if requested
        if include_storage and node.storage_pools:
            lines.append(self._format_storage_pools(node.storage_pools))
            lines.append("")

        return "\n".join(lines)

    def _format_quick_reference(self, cluster: ProxmoxCluster) -> str:
        """
        Generate a quick reference table.
        """
        lines = [
            "",
            self.md.heading("Quick Reference", 2),
            "",
        ]

        if cluster.vms:
            lines.append(self.md.heading("VMs", 3))
            headers = ["VMID", "Name", "Node", "Status", "CPU", "Memory", "IPs"]
            rows = []
            for vm in sorted(cluster.vms, key=lambda v: v.vmid):
                rows.append([
                    str(vm.vmid),
                    vm.display_name,
                    vm.node,
                    vm.status.value,
                    str(vm.cpu_cores or "-"),
                    format_memory(vm.memory_mb),
                    ", ".join(vm.ip_addresses) if vm.ip_addresses else "-",
                ])
            lines.append(self.md.table(headers, rows))
            lines.append("")

        if cluster.containers:
            lines.append(self.md.heading("Containers", 3))
            headers = ["CTID", "Name", "Node", "Status", "CPU", "Memory", "IPs"]
            rows = []
            for ct in sorted(cluster.containers, key=lambda c: c.vmid):
                rows.append([
                    str(ct.vmid),
                    ct.display_name,
                    ct.node,
                    ct.status.value,
                    str(ct.cpu_cores or "-"),
                    format_memory(ct.memory_mb),
                    ", ".join(ct.ip_addresses) if ct.ip_addresses else "-",
                ])
            lines.append(self.md.table(headers, rows))
            lines.append("")

        return "\n".join(lines)

    def _create_subpage(
        self,
        parent_block_id: str,
        content: str,
    ) -> Optional[str]:
        """
        Create a subpage by inserting content into a parent block.

        When you insert content into a block (not a document), Craft
        automatically converts it to a page.

        Args:
            parent_block_id: ID of the parent block to nest under.
            content: Markdown content for the subpage.

        Returns:
            ID of the first created block, or None on failure.
        """
        try:
            items = self.craft.insert_markdown(content, parent_block_id, position="end")
            if items:
                return items[0].get("id")
        except Exception:
            pass
        return None

    def _find_existing_resource_blocks(
        self,
        document_id: str,
    ) -> dict[str, dict[str, Any]]:
        """
        Find existing VM/container blocks in the document.

        Returns a dict mapping resource identifiers (e.g., "vm-100", "ct-200")
        to their block data including IDs and any user-added notes.

        Args:
            document_id: The document to scan.

        Returns:
            Dictionary mapping resource IDs to block data.
        """
        existing = {}
        try:
            doc_data = self.craft.get_block(document_id)
            content = doc_data.get("content", [])

            for block in content:
                block_text = block.get("markdown", "") or block.get("content", "")
                block_id = block.get("id")

                # Look for VM blocks (contain "VMID: XXX")
                if "VMID:" in block_text:
                    import re
                    match = re.search(r'VMID:\s*(\d+)', block_text)
                    if match:
                        vmid = match.group(1)
                        existing[f"vm-{vmid}"] = {
                            "block_id": block_id,
                            "block": block,
                        }

                # Look for container blocks (contain "CTID: XXX")
                elif "CTID:" in block_text:
                    import re
                    match = re.search(r'CTID:\s*(\d+)', block_text)
                    if match:
                        ctid = match.group(1)
                        existing[f"ct-{ctid}"] = {
                            "block_id": block_id,
                            "block": block,
                        }
        except Exception:
            pass

        return existing

    def _extract_user_notes(self, block_id: str) -> Optional[str]:
        """
        Extract user-added notes from a resource's subpage.

        Looks for content under the "Notes" heading that isn't
        the default placeholder text.

        Args:
            block_id: The block ID to check for notes.

        Returns:
            User notes content if found, None otherwise.
        """
        try:
            block_data = self.craft.get_block(block_id)
            content = block_data.get("content", [])

            in_notes_section = False
            notes_content = []

            for item in content:
                text = item.get("markdown", "") or item.get("content", "")

                # Check if this is the Notes heading
                if "## Notes" in text or "# Notes" in text:
                    in_notes_section = True
                    continue

                # Check if we've hit another heading (end of notes section)
                if in_notes_section and text.startswith("#"):
                    break

                # Collect notes content (skip placeholder)
                if in_notes_section:
                    if "*Add your notes" not in text and text.strip():
                        notes_content.append(text)

            if notes_content:
                return "\n".join(notes_content)
        except Exception:
            pass

        return None

    def sync_incremental(self) -> dict[str, Any]:
        """
        Perform an incremental sync that preserves user notes.

        This method:
        1. Scans existing document for VM/container blocks
        2. Extracts any user-added notes from subpages
        3. Updates content while preserving notes
        4. Only adds/removes changed resources
        5. Flags deleted resources with a warning banner

        Returns:
            Dictionary with sync results.
        """
        result = {
            "success": True,
            "blocks_updated": 0,
            "blocks_inserted": 0,
            "subpages_created": 0,
            "notes_preserved": 0,
            "resources_flagged_deleted": 0,
            "errors": [],
        }

        # Fetch Proxmox data
        try:
            cluster = self.proxmox.get_cluster(
                node_filter=self.config.sync.node_filter,
                include_templates=self.config.sync.include_templates,
                include_stopped=self.config.sync.include_stopped,
                tag_filter=self.config.sync.tag_filter,
            )
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"Failed to fetch Proxmox data: {e}")
            return result

        # Get target document
        try:
            target_doc = self._get_target_document()
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"Failed to get target document: {e}")
            return result

        # Find existing resource blocks and extract notes
        existing_blocks = self._find_existing_resource_blocks(target_doc)
        preserved_notes: dict[str, str] = {}

        for resource_id, block_data in existing_blocks.items():
            block_id = block_data.get("block_id")
            if block_id:
                notes = self._extract_user_notes(block_id)
                if notes:
                    preserved_notes[resource_id] = notes
                    result["notes_preserved"] += 1

        # If no existing content, do a full sync
        if not existing_blocks:
            full_result = self.sync(clear_first=True)
            return full_result

        # Update last sync time in overview
        try:
            items = self.craft.insert_markdown(
                self._format_cluster_overview(cluster),
                target_doc,
                position="start"
            )
            result["blocks_updated"] += len(items)
        except Exception as e:
            result["errors"].append(f"Failed to update overview: {e}")

        # Process VMs - update existing or add new
        for vm in cluster.vms:
            resource_id = f"vm-{vm.vmid}"

            # Get preserved notes if any
            user_notes = preserved_notes.get(resource_id)

            if resource_id in existing_blocks:
                # Update existing block
                block_data = existing_blocks[resource_id]
                block_id = block_data.get("block_id")

                if block_id:
                    try:
                        # Clear and re-insert subpage content
                        detail_content = self._format_vm_detail(vm)

                        # Append preserved notes if any
                        if user_notes:
                            detail_content = detail_content.replace(
                                "*Add your notes, runbooks, and documentation here...*",
                                user_notes
                            )

                        # Update the subpage
                        self._create_subpage(block_id, detail_content)
                        result["blocks_updated"] += 1
                    except Exception as e:
                        result["errors"].append(f"Failed to update VM {vm.vmid}: {e}")
            else:
                # This is a new VM - add it
                try:
                    vm_items = self.craft.insert_markdown(
                        f"### {vm.display_name}",
                        target_doc,
                        position="end"
                    )
                    result["blocks_inserted"] += len(vm_items)

                    if vm_items:
                        parent_id = vm_items[0].get("id")
                        if parent_id:
                            subpage_id = self._create_subpage(
                                parent_id,
                                self._format_vm_detail(vm)
                            )
                            if subpage_id:
                                result["subpages_created"] += 1
                except Exception as e:
                    result["errors"].append(f"Failed to add new VM {vm.vmid}: {e}")

        # Process containers - update existing or add new
        for ct in cluster.containers:
            resource_id = f"ct-{ct.vmid}"

            # Get preserved notes if any
            user_notes = preserved_notes.get(resource_id)

            if resource_id in existing_blocks:
                # Update existing block
                block_data = existing_blocks[resource_id]
                block_id = block_data.get("block_id")

                if block_id:
                    try:
                        # Clear and re-insert subpage content
                        detail_content = self._format_container_detail(ct)

                        # Append preserved notes if any
                        if user_notes:
                            detail_content = detail_content.replace(
                                "*Add your notes, runbooks, and documentation here...*",
                                user_notes
                            )

                        # Update the subpage
                        self._create_subpage(block_id, detail_content)
                        result["blocks_updated"] += 1
                    except Exception as e:
                        result["errors"].append(f"Failed to update container {ct.vmid}: {e}")
            else:
                # This is a new container - add it
                try:
                    ct_items = self.craft.insert_markdown(
                        f"### {ct.display_name}",
                        target_doc,
                        position="end"
                    )
                    result["blocks_inserted"] += len(ct_items)

                    if ct_items:
                        parent_id = ct_items[0].get("id")
                        if parent_id:
                            subpage_id = self._create_subpage(
                                parent_id,
                                self._format_container_detail(ct)
                            )
                            if subpage_id:
                                result["subpages_created"] += 1
                except Exception as e:
                    result["errors"].append(f"Failed to add new container {ct.vmid}: {e}")

        # Detect and flag deleted resources
        # Build set of current resource IDs from Proxmox
        current_resource_ids = set()
        for vm in cluster.vms:
            current_resource_ids.add(f"vm-{vm.vmid}")
        for ct in cluster.containers:
            current_resource_ids.add(f"ct-{ct.vmid}")

        # Find resources that exist in Craft but not in Proxmox
        for resource_id, block_data in existing_blocks.items():
            if resource_id not in current_resource_ids:
                # This resource was deleted from Proxmox
                block_id = block_data.get("block_id")
                if not block_id:
                    continue

                # Extract user notes before flagging
                user_notes = preserved_notes.get(resource_id)

                # Parse resource type and ID
                if resource_id.startswith("vm-"):
                    vmid = int(resource_id[3:])
                    resource_type = "vm"
                elif resource_id.startswith("ct-"):
                    vmid = int(resource_id[3:])
                    resource_type = "ct"
                else:
                    continue

                # Try to extract original name from existing block
                original_name = f"Resource {vmid}"
                block = block_data.get("block", {})
                block_text = block.get("markdown", "") or block.get("content", "")
                # Look for name pattern like "# name" or "### name"
                name_match = re.search(r'#+ (?:⚠️ |🚨 )?([^\n(]+)', block_text)
                if name_match:
                    original_name = name_match.group(1).strip()

                try:
                    # Format the deleted resource page
                    if resource_type == "vm":
                        deleted_content = self._format_deleted_vm_page(
                            vmid, original_name, user_notes
                        )
                    else:
                        deleted_content = self._format_deleted_container_page(
                            vmid, original_name, user_notes
                        )

                    # Update the subpage with deletion warning
                    self._create_subpage(block_id, deleted_content)
                    result["resources_flagged_deleted"] += 1
                except Exception as e:
                    result["errors"].append(
                        f"Failed to flag deleted resource {resource_id}: {e}"
                    )

        if result["errors"] and result["blocks_updated"] == 0 and result["blocks_inserted"] == 0:
            result["success"] = False

        return result

    def sync(self, clear_first: bool = True) -> dict[str, Any]:
        """
        Perform a full sync from Proxmox to Craft Docs.

        Args:
            clear_first: If True, clear existing content before syncing.

        Returns:
            Dictionary with sync results.
        """
        result = {
            "success": True,
            "blocks_inserted": 0,
            "subpages_created": 0,
            "alerts_critical": 0,
            "alerts_warning": 0,
            "errors": [],
        }

        # Get config options
        include_storage = self.config.sync.include_storage
        include_backups = self.config.sync.include_backups
        show_alerts = self.config.sync.show_alerts
        group_by = self.config.sync.group_by

        # Fetch Proxmox data
        try:
            cluster = self.proxmox.get_cluster(
                node_filter=self.config.sync.node_filter,
                include_templates=self.config.sync.include_templates,
                include_stopped=self.config.sync.include_stopped,
                tag_filter=self.config.sync.tag_filter,
                include_storage=include_storage,
                include_backups=include_backups,
            )
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"Failed to fetch Proxmox data: {e}")
            return result

        # Evaluate alerts if enabled
        if show_alerts:
            self._evaluate_alerts(cluster)
            # Count alerts
            for vm in cluster.vms:
                for alert in vm.alerts:
                    if alert.severity == AlertSeverity.CRITICAL:
                        result["alerts_critical"] += 1
                    elif alert.severity == AlertSeverity.WARNING:
                        result["alerts_warning"] += 1
            for ct in cluster.containers:
                for alert in ct.alerts:
                    if alert.severity == AlertSeverity.CRITICAL:
                        result["alerts_critical"] += 1
                    elif alert.severity == AlertSeverity.WARNING:
                        result["alerts_warning"] += 1

        # Get target document
        try:
            target_doc = self._get_target_document()
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"Failed to get target document: {e}")
            return result

        # Clear existing content if requested
        if clear_first:
            try:
                self.craft.clear_document(target_doc)
            except Exception as e:
                result["errors"].append(f"Warning: Failed to clear document: {e}")

        # Insert cluster overview
        try:
            items = self.craft.insert_markdown(
                self._format_cluster_overview(cluster, show_alerts=show_alerts),
                target_doc,
                position="end"
            )
            result["blocks_inserted"] += len(items)
        except Exception as e:
            result["errors"].append(f"Failed to insert overview: {e}")

        # Choose grouping strategy
        if group_by == "tag":
            self._sync_grouped_by_tag(
                cluster, target_doc, result, include_storage
            )
        elif group_by == "status":
            self._sync_grouped_by_status(
                cluster, target_doc, result, include_storage
            )
        else:
            # Default: group by node
            self._sync_grouped_by_node(
                cluster, target_doc, result, include_storage
            )

        # Quick reference tables - skip if too many items
        if cluster.total_vms + cluster.total_containers <= 30:
            try:
                items = self.craft.insert_markdown(
                    self._format_quick_reference(cluster),
                    target_doc,
                    position="end"
                )
                result["blocks_inserted"] += len(items)
            except Exception as e:
                result["errors"].append(f"Failed to insert quick reference: {e}")

        if result["errors"] and result["blocks_inserted"] == 0:
            result["success"] = False

        return result

    def _sync_grouped_by_node(
        self,
        cluster: ProxmoxCluster,
        target_doc: str,
        result: dict[str, Any],
        include_storage: bool,
    ) -> None:
        """
        Sync resources grouped by node (default behavior).
        """
        for node in cluster.nodes:
            node_vms = [vm for vm in cluster.vms if vm.node == node.name]
            node_containers = [ct for ct in cluster.containers if ct.node == node.name]

            try:
                items = self.craft.insert_markdown(
                    self._format_node_section(
                        node, node_vms, node_containers, include_storage
                    ),
                    target_doc,
                    position="end"
                )
                result["blocks_inserted"] += len(items)
            except Exception as e:
                result["errors"].append(f"Failed to insert node {node.name}: {e}")
                continue

            self._sync_vm_section(node_vms, target_doc, result)
            self._sync_container_section(node_containers, target_doc, result)

            # Insert separator
            try:
                items = self.craft.insert_markdown(
                    self.md.horizontal_rule(),
                    target_doc,
                    position="end"
                )
                result["blocks_inserted"] += len(items)
            except Exception:
                pass

    def _sync_grouped_by_tag(
        self,
        cluster: ProxmoxCluster,
        target_doc: str,
        result: dict[str, Any],
        include_storage: bool,
    ) -> None:
        """
        Sync resources grouped by tag.
        """
        groups = self._group_resources_by_tag(cluster.vms, cluster.containers)

        # Sort tags alphabetically, but put "Untagged" last
        sorted_tags = sorted(
            groups.keys(),
            key=lambda t: (t == "Untagged", t.lower())
        )

        for tag in sorted_tags:
            tag_vms, tag_containers = groups[tag]

            try:
                items = self.craft.insert_markdown(
                    f"\n{self.md.heading(f'Tag: {tag}', 2)}\n",
                    target_doc,
                    position="end"
                )
                result["blocks_inserted"] += len(items)
            except Exception as e:
                result["errors"].append(f"Failed to insert tag section {tag}: {e}")
                continue

            self._sync_vm_section(tag_vms, target_doc, result)
            self._sync_container_section(tag_containers, target_doc, result)

            # Insert separator
            try:
                items = self.craft.insert_markdown(
                    self.md.horizontal_rule(),
                    target_doc,
                    position="end"
                )
                result["blocks_inserted"] += len(items)
            except Exception:
                pass

    def _sync_grouped_by_status(
        self,
        cluster: ProxmoxCluster,
        target_doc: str,
        result: dict[str, Any],
        include_storage: bool,
    ) -> None:
        """
        Sync resources grouped by status.
        """
        groups = self._group_resources_by_status(cluster.vms, cluster.containers)

        # Order statuses: Running first, then others
        status_order = ["Running", "Stopped", "Paused", "Suspended", "Unknown"]
        sorted_statuses = sorted(
            groups.keys(),
            key=lambda s: (
                status_order.index(s) if s in status_order else len(status_order)
            )
        )

        for status in sorted_statuses:
            status_vms, status_containers = groups[status]

            # Status icons
            status_icons = {
                "Running": "🟢",
                "Stopped": "🔴",
                "Paused": "🟡",
                "Suspended": "🟠",
            }
            icon = status_icons.get(status, "⚪")

            try:
                items = self.craft.insert_markdown(
                    f"\n{self.md.heading(f'{icon} {status}', 2)}\n",
                    target_doc,
                    position="end"
                )
                result["blocks_inserted"] += len(items)
            except Exception as e:
                result["errors"].append(f"Failed to insert status section {status}: {e}")
                continue

            self._sync_vm_section(status_vms, target_doc, result)
            self._sync_container_section(status_containers, target_doc, result)

            # Insert separator
            try:
                items = self.craft.insert_markdown(
                    self.md.horizontal_rule(),
                    target_doc,
                    position="end"
                )
                result["blocks_inserted"] += len(items)
            except Exception:
                pass

    def _sync_vm_section(
        self,
        vms: list[ProxmoxVM],
        target_doc: str,
        result: dict[str, Any],
    ) -> None:
        """
        Sync a list of VMs as a section with subpages.
        """
        if not vms:
            return

        try:
            items = self.craft.insert_markdown(
                self.md.heading("Virtual Machines", 3),
                target_doc,
                position="end"
            )
            result["blocks_inserted"] += len(items)

            for vm in sorted(vms, key=lambda v: v.vmid):
                try:
                    alert_indicator = self._get_alert_indicator(vm)
                    vm_items = self.craft.insert_markdown(
                        f"### {alert_indicator}{vm.display_name}",
                        target_doc,
                        position="end"
                    )
                    result["blocks_inserted"] += len(vm_items)

                    if vm_items:
                        parent_id = vm_items[0].get("id")
                        if parent_id:
                            subpage_id = self._create_subpage(
                                parent_id,
                                self._format_vm_detail(vm)
                            )
                            if subpage_id:
                                result["subpages_created"] += 1
                except Exception as e:
                    result["errors"].append(f"Failed to create VM subpage {vm.vmid}: {e}")

        except Exception as e:
            result["errors"].append(f"Failed to insert VMs section: {e}")

    def _sync_container_section(
        self,
        containers: list[ProxmoxContainer],
        target_doc: str,
        result: dict[str, Any],
    ) -> None:
        """
        Sync a list of containers as a section with subpages.
        """
        if not containers:
            return

        try:
            items = self.craft.insert_markdown(
                self.md.heading("Containers", 3),
                target_doc,
                position="end"
            )
            result["blocks_inserted"] += len(items)

            for ct in sorted(containers, key=lambda c: c.vmid):
                try:
                    alert_indicator = self._get_alert_indicator(ct)
                    ct_items = self.craft.insert_markdown(
                        f"### {alert_indicator}{ct.display_name}",
                        target_doc,
                        position="end"
                    )
                    result["blocks_inserted"] += len(ct_items)

                    if ct_items:
                        parent_id = ct_items[0].get("id")
                        if parent_id:
                            subpage_id = self._create_subpage(
                                parent_id,
                                self._format_container_detail(ct)
                            )
                            if subpage_id:
                                result["subpages_created"] += 1
                except Exception as e:
                    result["errors"].append(f"Failed to create container subpage {ct.vmid}: {e}")

        except Exception as e:
            result["errors"].append(f"Failed to insert containers section: {e}")


def create_sync_engine(config: AppConfig) -> SyncEngine:
    """
    Create a configured SyncEngine instance.

    Args:
        config: Application configuration.

    Returns:
        Configured SyncEngine.
    """
    proxmox_client = ProxmoxClient(config.proxmox)
    craft_client = CraftClient(config.craft)

    return SyncEngine(proxmox_client, craft_client, config)
