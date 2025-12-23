# craft-docs-proxmox

**Self-documenting infrastructure for Proxmox** - Automatically generate and maintain living documentation for your VMs, containers, storage, and backups with real-time health monitoring.

Built for the [Craft Docs Winter Challenge 2025](https://www.craft.do/imagine).

## The Problem

Infrastructure documentation is always out of date. The moment you spin up a new VM, change an IP, or add storage, your docs are stale. Teams waste hours hunting for information that should be at their fingertips, and critical details about backups, resource usage, and system health live only in the heads of senior engineers.

Whether you're running a homelab or managing enterprise Proxmox clusters, the challenge is the same: **documentation that doesn't maintain itself becomes technical debt.**

## The Solution

**craft-proxmox** creates **self-documenting infrastructure** by automatically syncing your entire Proxmox environment to Craft Docs. Your infrastructure documents itself:

- **Always current** - Sync on-demand or schedule automatic updates
- **Health at a glance** - Visual alerts surface VMs needing attention before they become incidents
- **Team-ready** - Craft's collaboration features let teams annotate, discuss, and build runbooks together
- **Audit-friendly** - Timestamped syncs create a living record of your infrastructure state
- **Preserves tribal knowledge** - Incremental sync keeps your team's runbooks and notes intact while updating specs

## Features

### Core Sync
- **Automatic Discovery** - Fetches all nodes, VMs, and LXC containers
- **Rich Details** - Specs, status, IPs, tags, descriptions, snapshots, network interfaces
- **Subpage Structure** - Each resource gets its own detailed subpage
- **Direct Links** - Click to open any resource directly in Proxmox web UI

### Storage & Backups
- **Storage Pools** - See all storage with usage percentages and alerts
- **Backup Status** - Last backup date, age, scheduled jobs per resource
- **Backup Warnings** - Visual indicators for missing or outdated backups

### Smart Organization
- **Group by Node** (default) - Traditional infrastructure view
- **Group by Tag** - See resources by function (production, development, etc.)
- **Group by Status** - Quick view of running vs stopped resources

### Health Monitoring & Alerts
- **CPU Alerts** - Warning at 80%, critical at 95%
- **Memory Alerts** - Warning at 80%, critical at 95%
- **Storage Alerts** - Warning when <20% free, critical when <10% free
- **Backup Alerts** - Warning after 7 days, critical after 30 days without backup
- **Dashboard Summary** - Overall health status at the top

### Incremental Sync
- **Preserves Notes** - Your runbooks and documentation stay intact
- **Updates Only Changed Data** - Specs, status, and alerts refresh
- **Detects New Resources** - Automatically adds new VMs/containers

## Installation

### Requirements
- Python 3.10 or higher
- A Proxmox server with API access
- A Craft Docs account with API connection

### Install from PyPI
```bash
pip install craft-proxmox
```

### Install from Source
```bash
git clone https://github.com/tylwright/craft-docs-proxmox
cd craft-docs-proxmox
pip install -e .
```

## Quick Start

### 1. Set up Proxmox API Access

Create an API token in Proxmox:
1. Go to **Datacenter > Permissions > API Tokens > Add**
2. Select user (e.g., `root@pam`)
3. Create token with appropriate permissions (VM.Audit, Datastore.Audit for backups)
4. Save the token ID and secret

### 2. Set up Craft Docs API

1. Open Craft Docs
2. Go to the **Imagine** tab in the sidebar
3. Click **Add Your First API Connection**
4. Select which documents the API can access
5. Copy the API URL
6. Generate an API Key for secure authentication

### 3. Configure craft-proxmox

Create a `.env` file in your working directory:

```bash
# Proxmox Configuration
PROXMOX_HOST=192.168.1.100
PROXMOX_PORT=8006
PROXMOX_USER=root@pam
PROXMOX_TOKEN_NAME=craft-sync
PROXMOX_TOKEN_VALUE=your-token-secret-here
PROXMOX_VERIFY_SSL=false

# Craft Configuration
CRAFT_API_URL=https://your-craft-api-url.craft.me/api/...
CRAFT_API_KEY=your-api-key-here

# Optional: Specify a root document
# CRAFT_ROOT_DOCUMENT_ID=your-document-id
```

Or use the interactive setup:
```bash
craft-proxmox init
```

### 4. Test Your Connections

```bash
craft-proxmox test
```

### 5. Preview What Will Be Synced

```bash
craft-proxmox sync --dry-run
```

### 6. Sync to Craft Docs

```bash
# Full sync (replaces existing content)
craft-proxmox sync

# With storage pools and backup info
craft-proxmox sync --include-storage --include-backups

# Group by tags instead of nodes
craft-proxmox sync --group-by tag
```

## Automation

### Scheduled Sync (Recommended for Teams)

Set up automatic syncing to keep documentation current:

```bash
# Cron: Sync every hour, preserve notes
0 * * * * /usr/local/bin/craft-proxmox sync --incremental >> /var/log/craft-proxmox.log 2>&1

# Cron: Full sync daily at 2am with storage and backup info
0 2 * * * /usr/local/bin/craft-proxmox sync --include-storage --include-backups >> /var/log/craft-proxmox.log 2>&1
```

### CI/CD Integration

Trigger documentation updates as part of your infrastructure pipeline:

```yaml
# GitHub Actions example
- name: Update Infrastructure Docs
  run: craft-proxmox sync --incremental
  env:
    PROXMOX_HOST: ${{ secrets.PROXMOX_HOST }}
    PROXMOX_TOKEN_VALUE: ${{ secrets.PROXMOX_TOKEN }}
    CRAFT_API_URL: ${{ secrets.CRAFT_API_URL }}
    CRAFT_API_KEY: ${{ secrets.CRAFT_API_KEY }}
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Interactive configuration setup |
| `test` | Test connections to Proxmox and Craft |
| `status` | Show current Proxmox cluster status in terminal |
| `debug` | Debug Proxmox API connection and permissions |
| `sync` | Sync Proxmox data to Craft Docs |
| `export-markdown` | Export as Markdown file (for manual import) |
| `version` | Show version information |

## Sync Options

```bash
# Basic sync
craft-proxmox sync

# Incremental sync (preserves your notes)
craft-proxmox sync --incremental

# Include storage pool information
craft-proxmox sync --include-storage

# Include backup status per resource
craft-proxmox sync --include-backups

# Group by tag or status instead of node
craft-proxmox sync --group-by tag
craft-proxmox sync --group-by status

# Filter to specific node or tag
craft-proxmox sync --node pve1
craft-proxmox sync --tag production

# Disable alert indicators
craft-proxmox sync --no-alerts

# Combine options
craft-proxmox sync --include-storage --include-backups --group-by tag
```

## Document Structure

craft-proxmox creates a hierarchical structure in Craft:

```
Proxmox Infrastructure Dashboard
│
├── Overview
│   ├── Nodes: 2
│   ├── Virtual Machines: 10 (8 running)
│   ├── Containers: 25 (22 running)
│   └── Health: 2 critical, 5 warnings
│
├── Node: pve1
│   ├── Storage Pools (if enabled)
│   │   ├── local-lvm (45% used)
│   │   └── backup-nfs (82% used) ⚠️
│   │
│   ├── Virtual Machines
│   │   ├── webserver (subpage with full details)
│   │   └── database (subpage with full details)
│   │
│   └── Containers
│       ├── nginx-proxy (subpage)
│       └── redis-cache (subpage)
│
└── Node: pve2
    └── ...
```

Each resource subpage includes:
- Status badge with Proxmox web UI link
- Alerts section (if any issues)
- Specifications (CPU, memory, disk)
- Network interfaces and IPs
- Backup status (if enabled)
- Snapshots list
- Tags
- Description
- **Notes section** for your documentation

## Example Output

### Dashboard with Health Summary
```markdown
# Proxmox Infrastructure Dashboard
*Last synced: 2024-12-15 14:30:00*

## Overview
- **Nodes:** 2
- **Virtual Machines:** 10 (8 running)
- **Containers:** 25 (22 running)
- **Health:** 🚨 2 critical, ⚠️ 5 warnings
```

### Resource with Alerts
```markdown
# ⚠️ web-server

🟢 Running | VMID: 100 | Node: pve1

[Open in Proxmox](https://192.168.1.100:8006/...)

**Alerts:**
- ⚠️ Memory usage high: 82.5%
- ⚠️ Last backup 12 days ago

## Specifications
- **CPU:** 4 cores
- **Memory:** 8.0 GB
- **Disk:** 100.0 GB

## Backups
- **Last backup:** 2024-12-03 03:00 (12 days ago) ⚠️
- **Scheduled:** Yes (Job: daily-backup)
- **Total backups:** 14
```

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PROXMOX_HOST` | Proxmox server address | (required) |
| `PROXMOX_PORT` | API port | `8006` |
| `PROXMOX_USER` | Username (e.g., `root@pam`) | (required) |
| `PROXMOX_TOKEN_NAME` | API token name | (optional) |
| `PROXMOX_TOKEN_VALUE` | API token value | (optional) |
| `PROXMOX_PASSWORD` | Password (if not using token) | (optional) |
| `PROXMOX_VERIFY_SSL` | Verify SSL certificate | `false` |
| `CRAFT_API_URL` | Craft API endpoint URL | (required) |
| `CRAFT_API_KEY` | Craft API key | (recommended) |
| `CRAFT_ROOT_DOCUMENT_ID` | Target document for sync | (auto-detected) |

### Sync Options

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNC_INCLUDE_TEMPLATES` | Include template VMs/CTs | `false` |
| `SYNC_INCLUDE_STOPPED` | Include stopped resources | `true` |
| `SYNC_TAG_FILTER` | Only sync resources with tag | (none) |
| `SYNC_NODE_FILTER` | Only sync from this node | (none) |
| `SYNC_GROUP_BY` | Group by: node, tag, status | `node` |
| `SYNC_INCLUDE_STORAGE` | Include storage pools | `false` |
| `SYNC_INCLUDE_BACKUPS` | Include backup info | `false` |
| `SYNC_SHOW_ALERTS` | Show alert indicators | `true` |

### Alert Thresholds

| Variable | Description | Default |
|----------|-------------|---------|
| `ALERT_CPU_WARNING_THRESHOLD` | CPU warning % | `80.0` |
| `ALERT_CPU_CRITICAL_THRESHOLD` | CPU critical % | `95.0` |
| `ALERT_MEMORY_WARNING_THRESHOLD` | Memory warning % | `80.0` |
| `ALERT_MEMORY_CRITICAL_THRESHOLD` | Memory critical % | `95.0` |
| `ALERT_STORAGE_WARNING_THRESHOLD` | Storage free % warning | `20.0` |
| `ALERT_STORAGE_CRITICAL_THRESHOLD` | Storage free % critical | `10.0` |
| `ALERT_BACKUP_WARNING_DAYS` | Days without backup warning | `7` |
| `ALERT_BACKUP_CRITICAL_DAYS` | Days without backup critical | `30` |

## Use Cases

### For Homelabbers
- **Personal Infrastructure Wiki** - Every VM and container documented automatically
- **Project Notes** - Add setup guides, config notes, and lessons learned to each resource
- **Backup Peace of Mind** - Visual alerts when backups are overdue

### For Teams & Enterprise

#### Self-Documenting Infrastructure
Eliminate documentation drift. Schedule `craft-proxmox sync` via cron or CI/CD pipeline to keep docs current automatically:
```bash
# Cron example: sync every hour
0 * * * * cd /opt/craft-proxmox && craft-proxmox sync --incremental
```

#### Runbooks & Operational Procedures
Use the Notes section in each resource subpage to build living runbooks:
- Deployment procedures
- Maintenance checklists
- Incident response guides
- Change management history

#### Team Onboarding
New team members get instant visibility into:
- What's running and where
- System specifications and dependencies
- Who to contact (add to notes)
- Historical context and architecture decisions

#### Compliance & Audit
- Timestamped sync records show infrastructure state over time
- Document backup schedules and verify compliance
- Track resource allocation and capacity

#### Incident Response
During outages, teams can quickly:
- See all affected systems in one place
- Access runbooks directly from the resource page
- Click through to Proxmox console instantly
- Review recent changes documented in notes

### Health Dashboard
Proactive visibility into infrastructure health:
- Which VMs need backup attention?
- What's consuming too many resources?
- Which storage pools are filling up?
- What's stopped that should be running?

## Development

```bash
# Clone the repository
git clone https://github.com/yourusername/craft-proxmox
cd craft-proxmox

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/craft_proxmox

# Linting
ruff check src/craft_proxmox
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- Built for the [Craft Docs Winter Challenge 2024/2025](https://www.craft.do/imagine)
- Uses [proxmoxer](https://github.com/proxmoxer/proxmoxer) for Proxmox API access
- Uses [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/) for the beautiful CLI
- Uses [Pydantic](https://docs.pydantic.dev/) for data validation and settings management
