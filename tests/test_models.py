"""
Tests for data models.
"""

import pytest

from craft_proxmox.models import (
    ProxmoxCluster,
    ProxmoxContainer,
    ProxmoxNode,
    ProxmoxVM,
    ResourceStatus,
    ResourceType,
)


class TestProxmoxNode:
    def test_node_creation(self):
        node = ProxmoxNode(
            name="pve1",
            status="online",
            cpu_usage=0.25,
            memory_used=8 * 1024 * 1024 * 1024,
            memory_total=32 * 1024 * 1024 * 1024,
            uptime=86400,
        )
        assert node.name == "pve1"
        assert node.status == "online"
        assert node.cpu_usage == 0.25

    def test_memory_usage_percent(self):
        node = ProxmoxNode(
            name="pve1",
            status="online",
            memory_used=8 * 1024 * 1024 * 1024,
            memory_total=32 * 1024 * 1024 * 1024,
        )
        assert node.memory_usage_percent == 25.0

    def test_memory_usage_percent_none(self):
        node = ProxmoxNode(name="pve1", status="online")
        assert node.memory_usage_percent is None


class TestProxmoxVM:
    def test_vm_creation(self):
        vm = ProxmoxVM(
            vmid=100,
            name="webserver",
            node="pve1",
            status=ResourceStatus.RUNNING,
            cpu_cores=4,
            memory_mb=8192,
        )
        assert vm.vmid == 100
        assert vm.name == "webserver"
        assert vm.resource_type == ResourceType.VM

    def test_display_name_with_name(self):
        vm = ProxmoxVM(
            vmid=100,
            name="webserver",
            node="pve1",
            status=ResourceStatus.RUNNING,
        )
        assert vm.display_name == "webserver"

    def test_display_name_without_name(self):
        vm = ProxmoxVM(
            vmid=100,
            name="",
            node="pve1",
            status=ResourceStatus.RUNNING,
        )
        assert vm.display_name == "VM-100"

    def test_vm_with_tags(self):
        vm = ProxmoxVM(
            vmid=100,
            name="webserver",
            node="pve1",
            status=ResourceStatus.RUNNING,
            tags=["production", "web"],
        )
        assert "production" in vm.tags
        assert len(vm.tags) == 2


class TestProxmoxContainer:
    def test_container_creation(self):
        container = ProxmoxContainer(
            vmid=200,
            name="nginx-proxy",
            node="pve1",
            status=ResourceStatus.RUNNING,
            cpu_cores=2,
            memory_mb=2048,
        )
        assert container.vmid == 200
        assert container.name == "nginx-proxy"
        assert container.resource_type == ResourceType.LXC

    def test_display_name_hierarchy(self):
        ct1 = ProxmoxContainer(
            vmid=200,
            name="nginx-proxy",
            node="pve1",
            status=ResourceStatus.RUNNING,
        )
        assert ct1.display_name == "nginx-proxy"

        ct2 = ProxmoxContainer(
            vmid=201,
            name="",
            node="pve1",
            status=ResourceStatus.RUNNING,
            hostname="my-container",
        )
        assert ct2.display_name == "my-container"

        ct3 = ProxmoxContainer(
            vmid=202,
            name="",
            node="pve1",
            status=ResourceStatus.RUNNING,
        )
        assert ct3.display_name == "CT-202"


class TestProxmoxCluster:
    def test_cluster_stats(self):
        cluster = ProxmoxCluster(
            name="homelab",
            nodes=[
                ProxmoxNode(name="pve1", status="online"),
                ProxmoxNode(name="pve2", status="online"),
            ],
            vms=[
                ProxmoxVM(vmid=100, name="vm1", node="pve1", status=ResourceStatus.RUNNING),
                ProxmoxVM(vmid=101, name="vm2", node="pve1", status=ResourceStatus.STOPPED),
                ProxmoxVM(vmid=102, name="vm3", node="pve2", status=ResourceStatus.RUNNING),
            ],
            containers=[
                ProxmoxContainer(
                    vmid=200, name="ct1", node="pve1", status=ResourceStatus.RUNNING
                ),
                ProxmoxContainer(
                    vmid=201, name="ct2", node="pve2", status=ResourceStatus.STOPPED
                ),
            ],
        )

        assert cluster.total_vms == 3
        assert cluster.running_vms == 2
        assert cluster.total_containers == 2
        assert cluster.running_containers == 1


class TestResourceStatus:
    def test_status_values(self):
        assert ResourceStatus.RUNNING.value == "running"
        assert ResourceStatus.STOPPED.value == "stopped"
        assert ResourceStatus.PAUSED.value == "paused"
