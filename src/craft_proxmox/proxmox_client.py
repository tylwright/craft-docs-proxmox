"""
Proxmox API client for fetching cluster, node, VM, and container information.
"""

from typing import Any, Optional

from proxmoxer import ProxmoxAPI

from .config import ProxmoxConfig
from .models import (
    Backup,
    BackupInfo,
    NetworkInterface,
    ProxmoxCluster,
    ProxmoxContainer,
    ProxmoxNode,
    ProxmoxVM,
    ResourceStatus,
    ResourceType,
    Snapshot,
    StoragePool,
)


class ProxmoxClient:
    """
    Client for interacting with the Proxmox API.
    """

    def __init__(self, config: ProxmoxConfig):
        """
        Initialize the Proxmox client.

        Args:
            config: ProxmoxConfig instance with connection details.
        """
        self.config = config
        self._api: Optional[ProxmoxAPI] = None

    @property
    def api(self) -> ProxmoxAPI:
        """
        Get or create the Proxmox API connection.
        """
        if self._api is None:
            self._api = self._connect()
        return self._api

    def _connect(self) -> ProxmoxAPI:
        """
        Establish connection to Proxmox API.
        """
        if self.config.use_token_auth:
            return ProxmoxAPI(
                self.config.host,
                port=self.config.port,
                user=self.config.user,
                token_name=self.config.token_name,
                token_value=self.config.token_value.get_secret_value(),
                verify_ssl=self.config.verify_ssl,
            )
        else:
            return ProxmoxAPI(
                self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password.get_secret_value(),
                verify_ssl=self.config.verify_ssl,
            )

    def _parse_status(self, status: str) -> ResourceStatus:
        """
        Parse Proxmox status string to ResourceStatus enum.
        """
        status_map = {
            "running": ResourceStatus.RUNNING,
            "stopped": ResourceStatus.STOPPED,
            "paused": ResourceStatus.PAUSED,
            "suspended": ResourceStatus.SUSPENDED,
        }
        return status_map.get(status.lower(), ResourceStatus.UNKNOWN)

    def _parse_tags(self, tags: Optional[str]) -> list[str]:
        """
        Parse Proxmox tags string to list.
        """
        if not tags:
            return []
        return [t.strip() for t in tags.split(";") if t.strip()]

    def _bytes_to_mb(self, bytes_val: Optional[int]) -> Optional[int]:
        """
        Convert bytes to megabytes.
        """
        if bytes_val is None:
            return None
        return bytes_val // (1024 * 1024)

    def _bytes_to_gb(self, bytes_val: Optional[int]) -> Optional[float]:
        """
        Convert bytes to gigabytes.
        """
        if bytes_val is None:
            return None
        return round(bytes_val / (1024 * 1024 * 1024), 2)

    def get_storage_pools(self, node_name: str) -> list[StoragePool]:
        """
        Fetch storage pools for a node.

        Args:
            node_name: Name of the node.

        Returns:
            List of StoragePool instances.
        """
        pools = []
        try:
            storage_list = self.api.nodes(node_name).storage.get()
            for storage_data in storage_list:
                storage_name = storage_data.get("storage", "")
                try:
                    status = self.api.nodes(node_name).storage(storage_name).status.get()
                    pool = StoragePool(
                        name=storage_name,
                        node=node_name,
                        storage_type=storage_data.get("type", "unknown"),
                        content=storage_data.get("content", "").split(",") if storage_data.get("content") else [],
                        total_bytes=status.get("total"),
                        used_bytes=status.get("used"),
                        available_bytes=status.get("avail"),
                        enabled=storage_data.get("enabled", 1) == 1,
                        shared=storage_data.get("shared", 0) == 1,
                    )
                    pools.append(pool)
                except Exception:
                    # Fall back to basic info if status fails
                    pool = StoragePool(
                        name=storage_name,
                        node=node_name,
                        storage_type=storage_data.get("type", "unknown"),
                        content=storage_data.get("content", "").split(",") if storage_data.get("content") else [],
                        enabled=storage_data.get("enabled", 1) == 1,
                        shared=storage_data.get("shared", 0) == 1,
                    )
                    pools.append(pool)
        except Exception:
            pass
        return pools

    def get_backups_for_vmid(
        self,
        node_name: str,
        vmid: int,
        storage_filter: Optional[str] = None,
    ) -> list[Backup]:
        """
        Fetch backups for a specific VM or container.

        Args:
            node_name: Name of the node.
            vmid: VM or container ID.
            storage_filter: Optional storage name to search.

        Returns:
            List of Backup instances.
        """
        backups = []

        try:
            storage_list = self.api.nodes(node_name).storage.get()
            backup_storages = [
                s.get("storage") for s in storage_list
                if "backup" in s.get("content", "")
            ]

            if storage_filter:
                backup_storages = [s for s in backup_storages if s == storage_filter]

            for storage_name in backup_storages:
                try:
                    content = self.api.nodes(node_name).storage(storage_name).content.get(
                        content="backup",
                        vmid=vmid
                    )
                    for item in content:
                        backup = Backup(
                            vmid=vmid,
                            node=node_name,
                            storage=storage_name,
                            filename=item.get("volid", ""),
                            size_bytes=item.get("size"),
                            backup_time=item.get("ctime"),
                            notes=item.get("notes"),
                        )
                        backups.append(backup)
                except Exception:
                    continue
        except Exception:
            pass

        return backups

    def get_backup_info(self, node_name: str, vmid: int) -> BackupInfo:
        """
        Get aggregated backup information for a VM/container.

        Args:
            node_name: Name of the node.
            vmid: VM or container ID.

        Returns:
            BackupInfo instance with all backups and schedule info.
        """
        backups = self.get_backups_for_vmid(node_name, vmid)

        scheduled_job = None
        try:
            jobs = self.api.cluster.backup.get()
            for job in jobs:
                job_vmids = str(job.get("vmid", ""))
                if str(vmid) in job_vmids.split(",") or job.get("all", 0) == 1:
                    scheduled_job = job.get("id")
                    break
        except Exception:
            pass

        return BackupInfo(
            vmid=vmid,
            backups=backups,
            scheduled_job=scheduled_job,
        )

    def get_nodes(self, include_storage: bool = False) -> list[ProxmoxNode]:
        """
        Fetch all nodes in the cluster.

        Args:
            include_storage: Whether to include storage pool information.

        Returns:
            List of ProxmoxNode instances.
        """
        nodes = []
        for node_data in self.api.nodes.get():
            node = ProxmoxNode(
                name=node_data.get("node", ""),
                status=node_data.get("status", "unknown"),
                cpu_usage=node_data.get("cpu"),
                memory_used=node_data.get("mem"),
                memory_total=node_data.get("maxmem"),
                uptime=node_data.get("uptime"),
            )
            if include_storage:
                node.storage_pools = self.get_storage_pools(node.name)
            nodes.append(node)
        return nodes

    def get_vms(
        self,
        node_filter: Optional[str] = None,
        include_backups: bool = False,
    ) -> list[ProxmoxVM]:
        """
        Fetch all VMs across all nodes.

        Args:
            node_filter: Optional node name to filter by.
            include_backups: Whether to fetch backup information.

        Returns:
            List of ProxmoxVM instances.
        """
        vms = []
        nodes = self.get_nodes()

        for node in nodes:
            if node_filter and node.name != node_filter:
                continue

            try:
                vm_list = self.api.nodes(node.name).qemu.get()
                for vm_data in vm_list:
                    vm = self._parse_vm(vm_data, node.name)
                    vm = self._enrich_vm(vm, node.name)
                    if include_backups:
                        vm.backup_info = self.get_backup_info(node.name, vm.vmid)
                    vms.append(vm)
            except Exception:
                continue

        return vms

    def _parse_vm(self, vm_data: dict[str, Any], node_name: str) -> ProxmoxVM:
        """
        Parse VM data from Proxmox API response.
        """
        return ProxmoxVM(
            vmid=vm_data.get("vmid", 0),
            name=vm_data.get("name", ""),
            node=node_name,
            status=self._parse_status(vm_data.get("status", "unknown")),
            resource_type=ResourceType.VM,
            cpu_cores=vm_data.get("cpus"),
            memory_mb=self._bytes_to_mb(vm_data.get("maxmem")),
            disk_gb=self._bytes_to_gb(vm_data.get("maxdisk")),
            tags=self._parse_tags(vm_data.get("tags")),
            template=vm_data.get("template", 0) == 1,
            uptime=vm_data.get("uptime"),
            cpu_usage=vm_data.get("cpu"),
            memory_usage=(
                vm_data.get("mem", 0) / vm_data.get("maxmem", 1)
                if vm_data.get("maxmem")
                else None
            ),
        )

    def _parse_network_config(self, net_string: str, net_name: str) -> NetworkInterface:
        """
        Parse network configuration string from Proxmox config.

        Example: "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0,tag=100"
        """
        parts = {}
        for part in net_string.split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                parts[key] = value
            else:
                # First part might be model=mac format like "virtio=AA:BB:..."
                if "=" not in part:
                    continue

        # Handle model=mac format (e.g., "virtio=AA:BB:CC:DD:EE:FF")
        model = None
        mac = None
        for key in ["virtio", "e1000", "rtl8139", "vmxnet3"]:
            if key in parts:
                model = key
                mac = parts[key]
                break

        return NetworkInterface(
            name=net_name,
            bridge=parts.get("bridge"),
            mac_address=mac,
            ip_address=parts.get("ip", "").split("/")[0] if parts.get("ip") else None,
            gateway=parts.get("gw"),
            vlan_tag=int(parts["tag"]) if parts.get("tag") else None,
            model=model,
        )

    def _get_snapshots(self, node_name: str, vmid: int, resource_type: str) -> list[Snapshot]:
        """
        Fetch snapshots for a VM or container.

        Args:
            node_name: Name of the node.
            vmid: VM or container ID.
            resource_type: Either "qemu" or "lxc".

        Returns:
            List of Snapshot instances.
        """
        snapshots = []
        try:
            if resource_type == "qemu":
                snap_list = self.api.nodes(node_name).qemu(vmid).snapshot.get()
            else:
                snap_list = self.api.nodes(node_name).lxc(vmid).snapshot.get()

            for snap in snap_list:
                name = snap.get("name", "")
                if name and name != "current":  # Skip 'current' marker
                    snapshots.append(Snapshot(
                        name=name,
                        description=snap.get("description"),
                        snaptime=snap.get("snaptime"),
                    ))
        except Exception:
            pass

        return snapshots

    def _enrich_vm(self, vm: ProxmoxVM, node_name: str) -> ProxmoxVM:
        """
        Enrich VM with additional configuration details.
        """
        try:
            config = self.api.nodes(node_name).qemu(vm.vmid).config.get()
            vm.description = config.get("description")
            vm.os_type = config.get("ostype")

            # Parse network interfaces
            network_interfaces = []
            for i in range(10):  # Check net0 through net9
                net_key = f"net{i}"
                if net_key in config:
                    iface = self._parse_network_config(config[net_key], net_key)
                    network_interfaces.append(iface)
            vm.network_interfaces = network_interfaces

            # Parse disk info
            disk_parts = []
            for key in ["scsi0", "sata0", "ide0", "virtio0"]:
                if key in config:
                    disk_val = config[key]
                    # Extract size from disk string like "local-lvm:vm-100-disk-0,size=64G"
                    if "size=" in disk_val:
                        size = disk_val.split("size=")[1].split(",")[0]
                        disk_parts.append(f"{key}: {size}")
            if disk_parts:
                vm.disk_info = ", ".join(disk_parts)

            # Get IP addresses from guest agent if running
            if vm.status == ResourceStatus.RUNNING:
                try:
                    agent_info = (
                        self.api.nodes(node_name)
                        .qemu(vm.vmid)
                        .agent("network-get-interfaces")
                        .get()
                    )
                    ips = []
                    for iface in agent_info.get("result", []):
                        for ip_info in iface.get("ip-addresses", []):
                            ip = ip_info.get("ip-address", "")
                            if ip and not ip.startswith("127.") and not ip.startswith("fe80"):
                                ips.append(ip)
                    vm.ip_addresses = ips
                except Exception:
                    pass
        except Exception:
            pass

        # Fetch snapshots
        vm.snapshots = self._get_snapshots(node_name, vm.vmid, "qemu")

        return vm

    def get_containers(
        self,
        node_filter: Optional[str] = None,
        include_backups: bool = False,
    ) -> list[ProxmoxContainer]:
        """
        Fetch all LXC containers across all nodes.

        Args:
            node_filter: Optional node name to filter by.
            include_backups: Whether to fetch backup information.

        Returns:
            List of ProxmoxContainer instances.
        """
        containers = []
        nodes = self.get_nodes()

        for node in nodes:
            if node_filter and node.name != node_filter:
                continue

            try:
                ct_list = self.api.nodes(node.name).lxc.get()
                for ct_data in ct_list:
                    container = self._parse_container(ct_data, node.name)
                    container = self._enrich_container(container, node.name)
                    if include_backups:
                        container.backup_info = self.get_backup_info(node.name, container.vmid)
                    containers.append(container)
            except Exception:
                continue

        return containers

    def _parse_container(self, ct_data: dict[str, Any], node_name: str) -> ProxmoxContainer:
        """
        Parse container data from Proxmox API response.
        """
        return ProxmoxContainer(
            vmid=ct_data.get("vmid", 0),
            name=ct_data.get("name", ""),
            node=node_name,
            status=self._parse_status(ct_data.get("status", "unknown")),
            resource_type=ResourceType.LXC,
            cpu_cores=ct_data.get("cpus"),
            memory_mb=self._bytes_to_mb(ct_data.get("maxmem")),
            disk_gb=self._bytes_to_gb(ct_data.get("maxdisk")),
            tags=self._parse_tags(ct_data.get("tags")),
            template=ct_data.get("template", 0) == 1,
            uptime=ct_data.get("uptime"),
            cpu_usage=ct_data.get("cpu"),
            memory_usage=(
                ct_data.get("mem", 0) / ct_data.get("maxmem", 1)
                if ct_data.get("maxmem")
                else None
            ),
        )

    def _enrich_container(
        self, container: ProxmoxContainer, node_name: str
    ) -> ProxmoxContainer:
        """
        Enrich container with additional configuration details.
        """
        try:
            config = self.api.nodes(node_name).lxc(container.vmid).config.get()
            container.description = config.get("description")
            container.hostname = config.get("hostname")
            container.os_template = config.get("ostemplate")

            # Parse rootfs size
            rootfs = config.get("rootfs", "")
            if "size=" in rootfs:
                container.rootfs_size = rootfs.split("size=")[1].split(",")[0]

            # Parse network interfaces and extract IPs
            network_interfaces = []
            ip_addresses = []
            for i in range(10):  # Check net0 through net9
                net_key = f"net{i}"
                if net_key in config:
                    net_string = config[net_key]
                    iface = self._parse_network_config(net_string, net_key)
                    network_interfaces.append(iface)

                    # Extract IP for the main ip_addresses list
                    if iface.ip_address and iface.ip_address != "dhcp":
                        ip_addresses.append(iface.ip_address)

            container.network_interfaces = network_interfaces
            if ip_addresses:
                container.ip_addresses = ip_addresses
        except Exception:
            pass

        # Fetch snapshots
        container.snapshots = self._get_snapshots(node_name, container.vmid, "lxc")

        return container

    def get_cluster(
        self,
        node_filter: Optional[str] = None,
        include_templates: bool = False,
        include_stopped: bool = True,
        tag_filter: Optional[str] = None,
        include_storage: bool = False,
        include_backups: bool = False,
    ) -> ProxmoxCluster:
        """
        Fetch the complete cluster state.

        Args:
            node_filter: Optional node name to filter by.
            include_templates: Whether to include templates.
            include_stopped: Whether to include stopped resources.
            tag_filter: Optional tag to filter resources by.
            include_storage: Whether to include storage pool information.
            include_backups: Whether to include backup information.

        Returns:
            ProxmoxCluster instance with all data.
        """
        from datetime import datetime

        nodes = self.get_nodes(include_storage=include_storage)
        vms = self.get_vms(node_filter, include_backups=include_backups)
        containers = self.get_containers(node_filter, include_backups=include_backups)

        if not include_templates:
            vms = [vm for vm in vms if not vm.template]
            containers = [ct for ct in containers if not ct.template]

        if not include_stopped:
            vms = [vm for vm in vms if vm.status == ResourceStatus.RUNNING]
            containers = [ct for ct in containers if ct.status == ResourceStatus.RUNNING]

        if tag_filter:
            vms = [vm for vm in vms if tag_filter in vm.tags]
            containers = [ct for ct in containers if tag_filter in ct.tags]

        cluster_name = None
        try:
            cluster_status = self.api.cluster.status.get()
            for item in cluster_status:
                if item.get("type") == "cluster":
                    cluster_name = item.get("name")
                    break
        except Exception:
            pass

        return ProxmoxCluster(
            name=cluster_name,
            nodes=nodes,
            vms=vms,
            containers=containers,
            last_sync=datetime.now(),
        )

    def test_connection(self) -> bool:
        """
        Test the connection to the Proxmox API.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self.api.version.get()
            return True
        except Exception:
            return False
