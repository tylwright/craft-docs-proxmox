"""
Command-line interface for craft-proxmox.

Provides commands for configuring, testing, and running syncs
between Proxmox and Craft Docs.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from . import __version__
from .config import AppConfig, CraftConfig, ProxmoxConfig, SyncConfig, load_config, save_config
from .craft_client import CraftClient
from .proxmox_client import ProxmoxClient
from .sync import create_sync_engine

app = typer.Typer(
    name="craft-proxmox",
    help="Sync Proxmox VMs and containers to Craft Docs",
    add_completion=False,
)
console = Console()

CONFIG_DIR = Path.home() / ".config" / "craft-proxmox"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_config() -> AppConfig:
    """
    Load configuration from file or environment.
    """
    return load_config(CONFIG_FILE if CONFIG_FILE.exists() else None)


@app.command()
def version() -> None:
    """
    Show version information.
    """
    console.print(f"craft-proxmox version {__version__}")


@app.command()
def debug() -> None:
    """
    Debug Proxmox API connection and permissions.
    """
    config = get_config()

    console.print("\n[bold]Debugging Proxmox API...[/bold]\n")

    try:
        from proxmoxer import ProxmoxAPI

        console.print(f"Connecting to: [cyan]{config.proxmox.host}:{config.proxmox.port}[/cyan]")
        console.print(f"User: [cyan]{config.proxmox.user}[/cyan]")

        if config.proxmox.use_token_auth:
            console.print(f"Auth: [cyan]API Token ({config.proxmox.token_name})[/cyan]")
            api = ProxmoxAPI(
                config.proxmox.host,
                port=config.proxmox.port,
                user=config.proxmox.user,
                token_name=config.proxmox.token_name,
                token_value=config.proxmox.token_value.get_secret_value(),
                verify_ssl=config.proxmox.verify_ssl,
            )
        else:
            console.print("Auth: [cyan]Password[/cyan]")
            api = ProxmoxAPI(
                config.proxmox.host,
                port=config.proxmox.port,
                user=config.proxmox.user,
                password=config.proxmox.password.get_secret_value(),
                verify_ssl=config.proxmox.verify_ssl,
            )

        console.print("\n[green]Connected![/green]\n")

        # Get version
        version_info = api.version.get()
        console.print(f"Proxmox Version: [cyan]{version_info.get('version', 'unknown')}[/cyan]")

        # Get nodes
        console.print("\n[bold]Nodes:[/bold]")
        nodes = api.nodes.get()
        for node in nodes:
            console.print(f"  - {node.get('node')} ({node.get('status')})")

        # Try to get VMs from each node
        for node in nodes:
            node_name = node.get("node")
            console.print(f"\n[bold]VMs on {node_name}:[/bold]")
            try:
                vms = api.nodes(node_name).qemu.get()
                if vms:
                    for vm in vms:
                        console.print(f"  - VMID {vm.get('vmid')}: {vm.get('name', 'unnamed')} ({vm.get('status')})")
                else:
                    console.print("  [dim]No VMs found[/dim]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")

            console.print(f"\n[bold]Containers on {node_name}:[/bold]")
            try:
                cts = api.nodes(node_name).lxc.get()
                if cts:
                    for ct in cts:
                        console.print(f"  - CTID {ct.get('vmid')}: {ct.get('name', 'unnamed')} ({ct.get('status')})")
                else:
                    console.print("  [dim]No containers found[/dim]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")

    except Exception as e:
        console.print(f"\n[red]Connection Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def init(
    proxmox_host: str = typer.Option(
        ...,
        "--proxmox-host",
        "-ph",
        prompt="Proxmox host address",
        help="Proxmox server address (IP or hostname)",
    ),
    proxmox_user: str = typer.Option(
        "root@pam",
        "--proxmox-user",
        "-pu",
        prompt="Proxmox user",
        help="Proxmox user (e.g., root@pam)",
    ),
    proxmox_token_name: Optional[str] = typer.Option(
        None,
        "--proxmox-token-name",
        "-ptn",
        help="Proxmox API token name (optional)",
    ),
    proxmox_token_value: Optional[str] = typer.Option(
        None,
        "--proxmox-token-value",
        "-ptv",
        help="Proxmox API token value (optional)",
    ),
    craft_api_url: str = typer.Option(
        ...,
        "--craft-api-url",
        "-cu",
        prompt="Craft API URL",
        help="Craft Docs API endpoint URL",
    ),
) -> None:
    """
    Initialize configuration interactively.
    """
    console.print("\n[bold blue]Initializing craft-proxmox configuration[/bold blue]\n")

    proxmox_config = ProxmoxConfig(
        host=proxmox_host,
        user=proxmox_user,
        token_name=proxmox_token_name,
        token_value=proxmox_token_value,
    )

    craft_config = CraftConfig(api_url=craft_api_url)

    sync_config = SyncConfig()

    config = AppConfig(
        proxmox=proxmox_config,
        craft=craft_config,
        sync=sync_config,
    )

    save_config(config, CONFIG_FILE)
    console.print(f"\n[green]Configuration saved to {CONFIG_FILE}[/green]")
    console.print("\n[dim]Tip: Set PROXMOX_TOKEN_VALUE or PROXMOX_PASSWORD in .env for auth[/dim]")


@app.command()
def test() -> None:
    """
    Test connections to Proxmox and Craft.
    """
    config = get_config()

    console.print("\n[bold]Testing connections...[/bold]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        proxmox_task = progress.add_task("Testing Proxmox connection...", total=1)

        try:
            proxmox = ProxmoxClient(config.proxmox)
            if proxmox.test_connection():
                progress.update(proxmox_task, completed=1)
                console.print("[green]  Proxmox: Connected[/green]")

                nodes = proxmox.get_nodes()
                console.print(f"    Found {len(nodes)} node(s)")
            else:
                progress.update(proxmox_task, completed=1)
                console.print("[red]  Proxmox: Connection failed[/red]")
        except Exception as e:
            progress.update(proxmox_task, completed=1)
            console.print(f"[red]  Proxmox: Error - {e}[/red]")

        craft_task = progress.add_task("Testing Craft connection...", total=1)

        try:
            craft = CraftClient(config.craft)
            if craft.test_connection():
                progress.update(craft_task, completed=1)
                console.print("[green]  Craft: Connected[/green]")
            else:
                progress.update(craft_task, completed=1)
                console.print("[red]  Craft: Connection failed[/red]")
        except Exception as e:
            progress.update(craft_task, completed=1)
            console.print(f"[red]  Craft: Error - {e}[/red]")

    console.print()


@app.command()
def status() -> None:
    """
    Show current Proxmox cluster status.
    """
    config = get_config()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching cluster status...", total=1)

        try:
            proxmox = ProxmoxClient(config.proxmox)
            cluster = proxmox.get_cluster(
                node_filter=config.sync.node_filter,
                include_templates=config.sync.include_templates,
                include_stopped=config.sync.include_stopped,
                tag_filter=config.sync.tag_filter,
            )
            progress.update(task, completed=1)
        except Exception as e:
            progress.update(task, completed=1)
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

    console.print()

    if cluster.name:
        console.print(Panel(f"[bold]{cluster.name}[/bold]", title="Cluster"))

    node_table = Table(title="Nodes")
    node_table.add_column("Name", style="cyan")
    node_table.add_column("Status")
    node_table.add_column("CPU")
    node_table.add_column("Memory")

    for node in cluster.nodes:
        status_style = "green" if node.status == "online" else "red"
        cpu = f"{node.cpu_usage * 100:.1f}%" if node.cpu_usage else "-"
        mem = f"{node.memory_usage_percent:.1f}%" if node.memory_usage_percent else "-"
        node_table.add_row(
            node.name,
            f"[{status_style}]{node.status}[/{status_style}]",
            cpu,
            mem,
        )

    console.print(node_table)
    console.print()

    if cluster.vms:
        vm_table = Table(title="Virtual Machines")
        vm_table.add_column("VMID", style="cyan")
        vm_table.add_column("Name")
        vm_table.add_column("Node")
        vm_table.add_column("Status")
        vm_table.add_column("CPU")
        vm_table.add_column("Memory")

        for vm in sorted(cluster.vms, key=lambda v: v.vmid):
            status_style = "green" if vm.status.value == "running" else "red"
            vm_table.add_row(
                str(vm.vmid),
                vm.display_name,
                vm.node,
                f"[{status_style}]{vm.status.value}[/{status_style}]",
                str(vm.cpu_cores or "-"),
                f"{vm.memory_mb} MB" if vm.memory_mb else "-",
            )

        console.print(vm_table)
        console.print()

    if cluster.containers:
        ct_table = Table(title="Containers")
        ct_table.add_column("CTID", style="cyan")
        ct_table.add_column("Name")
        ct_table.add_column("Node")
        ct_table.add_column("Status")
        ct_table.add_column("CPU")
        ct_table.add_column("Memory")

        for ct in sorted(cluster.containers, key=lambda c: c.vmid):
            status_style = "green" if ct.status.value == "running" else "red"
            ct_table.add_row(
                str(ct.vmid),
                ct.display_name,
                ct.node,
                f"[{status_style}]{ct.status.value}[/{status_style}]",
                str(ct.cpu_cores or "-"),
                f"{ct.memory_mb} MB" if ct.memory_mb else "-",
            )

        console.print(ct_table)

    console.print()
    console.print(
        f"[dim]Total: {cluster.total_vms} VMs ({cluster.running_vms} running), "
        f"{cluster.total_containers} containers ({cluster.running_containers} running)[/dim]"
    )


@app.command()
def sync(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be synced without making changes",
    ),
    incremental: bool = typer.Option(
        False,
        "--incremental",
        "-i",
        help="Incremental sync that preserves user-added notes",
    ),
    node: Optional[str] = typer.Option(
        None,
        "--node",
        "-N",
        help="Only sync resources from this node",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        "-t",
        help="Only sync resources with this tag",
    ),
    group_by: str = typer.Option(
        "node",
        "--group-by",
        "-g",
        help="Group resources by: node, tag, status, or none",
    ),
    include_storage: bool = typer.Option(
        False,
        "--include-storage",
        "-s",
        help="Include storage pool information",
    ),
    include_backups: bool = typer.Option(
        False,
        "--include-backups",
        "-b",
        help="Include backup status per resource",
    ),
    alerts: bool = typer.Option(
        True,
        "--alerts/--no-alerts",
        help="Show/hide alert indicators (default: show)",
    ),
) -> None:
    """
    Sync Proxmox data to Craft Docs.

    Use --incremental to preserve any notes you've added to VM/container subpages.
    Use --group-by to organize resources by node (default), tag, or status.
    Use --include-storage to add storage pool info to node sections.
    Use --include-backups to show backup status on each resource.
    """
    config = get_config()

    # Apply CLI overrides
    if node:
        config.sync.node_filter = node
    if tag:
        config.sync.tag_filter = tag
    if group_by:
        config.sync.group_by = group_by
    config.sync.include_storage = include_storage
    config.sync.include_backups = include_backups
    config.sync.show_alerts = alerts

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be made[/yellow]\n")

        try:
            proxmox = ProxmoxClient(config.proxmox)
            cluster = proxmox.get_cluster(
                node_filter=config.sync.node_filter,
                include_templates=config.sync.include_templates,
                include_stopped=config.sync.include_stopped,
                tag_filter=config.sync.tag_filter,
                include_storage=include_storage,
                include_backups=include_backups,
            )

            console.print("[bold]Would sync to Craft document:[/bold]")
            console.print(f"  - Dashboard overview section")
            console.print(f"  - Group by: [cyan]{group_by}[/cyan]")
            console.print(f"  - {len(cluster.nodes)} node(s)")
            console.print(f"  - {len(cluster.vms)} VM entries")
            console.print(f"  - {len(cluster.containers)} container entries")
            if include_storage:
                storage_count = sum(len(n.storage_pools) for n in cluster.nodes)
                console.print(f"  - {storage_count} storage pool(s)")
            if include_backups:
                console.print(f"  - Backup info: [cyan]enabled[/cyan]")
            console.print(f"  - Alerts: [cyan]{'enabled' if alerts else 'disabled'}[/cyan]")
            console.print(f"  - Quick reference tables")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

        return

    sync_type = "incremental" if incremental else "full"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_desc = f"Syncing to Craft Docs ({sync_type})..."
        task = progress.add_task(task_desc, total=1)

        try:
            engine = create_sync_engine(config)
            if incremental:
                result = engine.sync_incremental()
            else:
                result = engine.sync()
            progress.update(task, completed=1)
        except Exception as e:
            progress.update(task, completed=1)
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

    console.print()

    if result["success"]:
        console.print("[green]Sync completed successfully![/green]")
    else:
        console.print("[yellow]Sync completed with errors[/yellow]")

    console.print(f"\n[bold]Summary:[/bold]")
    if incremental:
        console.print(f"  Blocks updated: {result.get('blocks_updated', 0)}")
        console.print(f"  Notes preserved: {result.get('notes_preserved', 0)}")
        flagged = result.get('resources_flagged_deleted', 0)
        if flagged > 0:
            console.print(f"  [yellow]Resources flagged as deleted: {flagged}[/yellow]")
    console.print(f"  Blocks inserted: {result.get('blocks_inserted', 0)}")
    console.print(f"  Subpages created: {result.get('subpages_created', 0)}")

    # Show alerts summary
    if alerts:
        critical = result.get('alerts_critical', 0)
        warning = result.get('alerts_warning', 0)
        if critical > 0 or warning > 0:
            alert_parts = []
            if critical > 0:
                alert_parts.append(f"[red]🚨 {critical} critical[/red]")
            if warning > 0:
                alert_parts.append(f"[yellow]⚠️ {warning} warnings[/yellow]")
            console.print(f"  Alerts: {', '.join(alert_parts)}")
        else:
            console.print(f"  Alerts: [green]✅ All healthy[/green]")

    if result["errors"]:
        console.print(f"\n[red]Errors ({len(result['errors'])}):[/red]")
        for error in result["errors"]:
            console.print(f"  - {error}")


@app.command()
def export_markdown(
    output: Path = typer.Option(
        Path("proxmox-export.md"),
        "--output",
        "-o",
        help="Output file path",
    ),
) -> None:
    """
    Export Proxmox data as Markdown (useful for manual import).
    """
    config = get_config()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching Proxmox data...", total=1)

        try:
            proxmox = ProxmoxClient(config.proxmox)
            cluster = proxmox.get_cluster(
                node_filter=config.sync.node_filter,
                include_templates=config.sync.include_templates,
                include_stopped=config.sync.include_stopped,
                tag_filter=config.sync.tag_filter,
            )
            progress.update(task, completed=1)
        except Exception as e:
            progress.update(task, completed=1)
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

    md_content = _generate_markdown(cluster)

    output.write_text(md_content)
    console.print(f"[green]Exported to {output}[/green]")


def _generate_markdown(cluster) -> str:
    """
    Generate Markdown content from cluster data.
    """
    from datetime import datetime

    lines = [
        "# Proxmox Infrastructure Dashboard",
        "",
        f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
    ]

    if cluster.name:
        lines.append(f"**Cluster:** {cluster.name}")
        lines.append("")

    lines.extend([
        "## Overview",
        "",
        f"- **Nodes:** {len(cluster.nodes)}",
        f"- **Virtual Machines:** {cluster.total_vms} ({cluster.running_vms} running)",
        f"- **Containers:** {cluster.total_containers} ({cluster.running_containers} running)",
        "",
        "---",
        "",
    ])

    for node in cluster.nodes:
        status_icon = "🟢" if node.status == "online" else "🔴"
        lines.extend([
            f"## {status_icon} Node: {node.name}",
            "",
            f"- **Status:** {node.status}",
        ])

        if node.cpu_usage is not None:
            lines.append(f"- **CPU Usage:** {node.cpu_usage * 100:.1f}%")
        if node.memory_usage_percent is not None:
            lines.append(f"- **Memory Usage:** {node.memory_usage_percent:.1f}%")

        lines.append("")

        node_vms = [vm for vm in cluster.vms if vm.node == node.name]
        node_cts = [ct for ct in cluster.containers if ct.node == node.name]

        if node_vms:
            lines.append("### Virtual Machines")
            lines.append("")
            for vm in sorted(node_vms, key=lambda v: v.vmid):
                status_icon = "🟢" if vm.status.value == "running" else "🔴"
                lines.append(f"#### {status_icon} {vm.display_name} (VMID: {vm.vmid})")
                lines.append("")
                if vm.cpu_cores:
                    lines.append(f"- **CPU:** {vm.cpu_cores} cores")
                if vm.memory_mb:
                    lines.append(f"- **Memory:** {vm.memory_mb} MB")
                if vm.ip_addresses:
                    lines.append(f"- **IP:** {', '.join(vm.ip_addresses)}")
                if vm.tags:
                    lines.append(f"- **Tags:** {', '.join(vm.tags)}")
                lines.append("")
                lines.append("**Notes:**")
                lines.append("")
                lines.append("*Add your notes here*")
                lines.append("")

        if node_cts:
            lines.append("### Containers")
            lines.append("")
            for ct in sorted(node_cts, key=lambda c: c.vmid):
                status_icon = "🟢" if ct.status.value == "running" else "🔴"
                lines.append(f"#### {status_icon} {ct.display_name} (CTID: {ct.vmid})")
                lines.append("")
                if ct.cpu_cores:
                    lines.append(f"- **CPU:** {ct.cpu_cores} cores")
                if ct.memory_mb:
                    lines.append(f"- **Memory:** {ct.memory_mb} MB")
                if ct.ip_addresses:
                    lines.append(f"- **IP:** {', '.join(ct.ip_addresses)}")
                if ct.tags:
                    lines.append(f"- **Tags:** {', '.join(ct.tags)}")
                lines.append("")
                lines.append("**Notes:**")
                lines.append("")
                lines.append("*Add your notes here*")
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    app()
