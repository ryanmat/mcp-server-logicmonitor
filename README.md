# LogicMonitor MCP Server

[![PyPI version](https://img.shields.io/pypi/v/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<!-- mcp-name: io.github.ryanmat/logicmonitor -->

Model Context Protocol (MCP) server for LogicMonitor REST API v3 integration. Enables AI assistants to interact with LogicMonitor monitoring data through structured tools.

Works with any MCP-compatible client: Claude Desktop, Claude Code, Cursor, Continue, Cline, and more.

## Quick Start

**1. Get your LogicMonitor Bearer Token:**
- Log into your LogicMonitor portal
- Go to **Settings** → **Users and Roles** → **API Tokens**
- Create a new API-only user or add a token to an existing user
- Copy the Bearer token

**2. Configure your MCP client:**

For **Claude Code** (CLI):
```bash
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=your-bearer-token \
  -- uvx --from lm-mcp lm-mcp-server
```

For **Claude Desktop**, add to your config file (see [MCP Client Configuration](#mcp-client-configuration) below).

**3. Verify it's working:**
```
claude mcp list
```

You should see: `logicmonitor: uvx --from lm-mcp lm-mcp-server - ✓ Connected`

**4. Test with a prompt:**
```
"Show me all critical alerts in LogicMonitor"
```

## Features

**146 Tools** across comprehensive LogicMonitor API coverage:

### Core Monitoring
- **Alert Management**: Query, acknowledge, bulk acknowledge, add notes, view rules
- **Device Management**: Full CRUD - list, create, update, delete devices and groups
- **Metrics & Data**: Query datasources, instances, metric data, and graphs
- **Dashboard Management**: Full CRUD for dashboards, widgets, and groups
- **SDT Management**: Create, list, bulk create/delete Scheduled Downtime
- **Collector Management**: List collectors and collector groups

### Extended Features
- **Website Monitoring**: Full CRUD for synthetic checks and website groups
- **Report Management**: List, view, run reports, manage schedules
- **Escalation Management**: Full CRUD for escalation chains and recipient groups
- **Alert Rules**: Full CRUD for alert routing rules
- **User & Role Management**: View users, roles, access groups, API tokens
- **Ops Management**: Audit logs, ops notes, login/change audits

### LogicModules
- **DataSources**: Query and export datasource definitions
- **ConfigSources**: Query and export configuration collection modules
- **EventSources**: Query and export event detection modules
- **PropertySources**: Query and export property collection modules
- **TopologySources**: Query and export topology mapping modules
- **LogSources**: Query and export log collection modules
- **Import Support**: Import LogicModules from JSON definitions

### Advanced Capabilities
- **Cost Optimization**: Cloud cost analysis, recommendations, idle resources (LM Envision)
- **Network Topology**: Device neighbors, interfaces, flows, connections
- **Batch Jobs**: View and manage batch job execution history
- **Log/Metric Ingestion**: Push logs and metrics via LMv1 authentication

### MCP Protocol Features
- **Resources**: 15 schema/enum/filter resources for API reference
- **Prompts**: 5 workflow templates (incident triage, health check, etc.)
- **Completions**: Auto-complete for tool arguments

### Operational Features
- **Security-First**: Read-only by default, write operations require explicit opt-in
- **Rate Limit Handling**: Automatic retry with exponential backoff and jitter
- **Server Error Recovery**: Automatic retry on 5xx server errors
- **Pagination Support**: Handle large result sets with offset-based pagination

## Installation

### Via PyPI (Recommended)

```bash
# Using uvx (no install needed)
uvx --from lm-mcp lm-mcp-server

# Using pip
pip install lm-mcp
```

### From Source

```bash
git clone https://github.com/ryanmat/mcp-server-logicmonitor.git
cd mcp-server-logicmonitor
uv sync
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LM_PORTAL` | Yes | - | LogicMonitor portal hostname (e.g., `company.logicmonitor.com`) |
| `LM_BEARER_TOKEN` | Yes* | - | API Bearer token (min 10 characters) |
| `LM_ACCESS_ID` | No | - | LMv1 API access ID (for ingestion APIs) |
| `LM_ACCESS_KEY` | No | - | LMv1 API access key (for ingestion APIs) |
| `LM_ENABLE_WRITE_OPERATIONS` | No | `false` | Enable write operations (create, update, delete) |
| `LM_API_VERSION` | No | `3` | API version |
| `LM_TIMEOUT` | No | `30` | Request timeout in seconds (range: 5-300) |
| `LM_MAX_RETRIES` | No | `3` | Max retries for rate-limited/server error requests (range: 0-10) |

*Either `LM_BEARER_TOKEN` or both `LM_ACCESS_ID` and `LM_ACCESS_KEY` are required.

### Authentication Methods

**Bearer Token (Recommended):**
- Simpler setup, works for most operations
- Set `LM_BEARER_TOKEN`

**LMv1 HMAC (Required for Ingestion):**
- Required for `ingest_logs` and `push_metrics` tools
- Set both `LM_ACCESS_ID` and `LM_ACCESS_KEY`
- Can be used alongside Bearer token

### Getting API Credentials

**Bearer Token:**
1. Log into your LogicMonitor portal
2. Go to **Settings** → **Users and Roles** → **API Tokens**
3. Create a new API-only user or add a token to an existing user
4. Copy the Bearer token

**LMv1 Credentials:**
1. Go to **Settings** → **Users and Roles** → **Users**
2. Select a user → **API Tokens** tab
3. Create or view the Access ID and Access Key

## MCP Client Configuration

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uvx",
      "args": ["--from", "lm-mcp", "lm-mcp-server"],
      "env": {
        "LM_PORTAL": "yourcompany.logicmonitor.com",
        "LM_BEARER_TOKEN": "your-bearer-token"
      }
    }
  }
}
```

To enable write operations and ingestion APIs:

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uvx",
      "args": ["--from", "lm-mcp", "lm-mcp-server"],
      "env": {
        "LM_PORTAL": "yourcompany.logicmonitor.com",
        "LM_BEARER_TOKEN": "your-bearer-token",
        "LM_ACCESS_ID": "your-access-id",
        "LM_ACCESS_KEY": "your-access-key",
        "LM_ENABLE_WRITE_OPERATIONS": "true"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=your-bearer-token \
  -e LM_ENABLE_WRITE_OPERATIONS=true \
  -- uvx --from lm-mcp lm-mcp-server
```

> **Note:** Remove `-e LM_ENABLE_WRITE_OPERATIONS=true` if you want read-only access.

Verify the connection:
```bash
claude mcp list
```

To update an existing configuration, remove and re-add:
```bash
claude mcp remove logicmonitor
claude mcp add logicmonitor -e LM_PORTAL=... -e LM_BEARER_TOKEN=... -- uvx --from lm-mcp lm-mcp-server
```

### Cursor

Add to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project):

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uvx",
      "args": ["--from", "lm-mcp", "lm-mcp-server"],
      "env": {
        "LM_PORTAL": "yourcompany.logicmonitor.com",
        "LM_BEARER_TOKEN": "your-bearer-token"
      }
    }
  }
}
```

To enable write operations and ingestion APIs:

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uvx",
      "args": ["--from", "lm-mcp", "lm-mcp-server"],
      "env": {
        "LM_PORTAL": "yourcompany.logicmonitor.com",
        "LM_BEARER_TOKEN": "your-bearer-token",
        "LM_ACCESS_ID": "your-access-id",
        "LM_ACCESS_KEY": "your-access-key",
        "LM_ENABLE_WRITE_OPERATIONS": "true"
      }
    }
  }
}
```

Then restart Cursor or enable the server in **Cursor Settings** → **MCP**.

### OpenAI Codex CLI

```bash
codex mcp add logicmonitor \
  --env LM_PORTAL=yourcompany.logicmonitor.com \
  --env LM_BEARER_TOKEN=your-bearer-token \
  -- uvx --from lm-mcp lm-mcp-server
```

Or add directly to `~/.codex/config.toml`:

```toml
[mcp_servers.logicmonitor]
command = "uvx"
args = ["--from", "lm-mcp", "lm-mcp-server"]

[mcp_servers.logicmonitor.env]
LM_PORTAL = "yourcompany.logicmonitor.com"
LM_BEARER_TOKEN = "your-bearer-token"
```

### Cline (VS Code Extension)

Add to Cline's MCP settings file:

**macOS**: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

**Windows**: `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`

**Linux**: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uvx",
      "args": ["--from", "lm-mcp", "lm-mcp-server"],
      "env": {
        "LM_PORTAL": "yourcompany.logicmonitor.com",
        "LM_BEARER_TOKEN": "your-bearer-token"
      }
    }
  }
}
```

### GitHub Copilot (VS Code 1.99+)

Add to your VS Code settings (`settings.json`) or project-level `.vscode/mcp.json`:

```json
{
  "mcp": {
    "servers": {
      "logicmonitor": {
        "command": "uvx",
        "args": ["--from", "lm-mcp", "lm-mcp-server"],
        "env": {
          "LM_PORTAL": "yourcompany.logicmonitor.com",
          "LM_BEARER_TOKEN": "your-bearer-token"
        }
      }
    }
  }
}
```

Enable MCP in VS Code settings: `"chat.mcp.enabled": true`

### Gemini CLI

Gemini CLI supports MCP servers. Configure in `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uvx",
      "args": ["--from", "lm-mcp", "lm-mcp-server"],
      "env": {
        "LM_PORTAL": "yourcompany.logicmonitor.com",
        "LM_BEARER_TOKEN": "your-bearer-token"
      }
    }
  }
}
```

### Other Clients

**Aider**: Does not currently have native MCP support. Track progress at [aider issue #3314](https://github.com/Aider-AI/aider/issues/3314).

**Continue**: Uses similar JSON configuration. See [Continue MCP docs](https://docs.continue.dev/customize/model-providers/mcp).

### Enabling Write Operations

For any JSON-based configuration, add `LM_ENABLE_WRITE_OPERATIONS` to the `env` section:

```json
"env": {
  "LM_PORTAL": "yourcompany.logicmonitor.com",
  "LM_BEARER_TOKEN": "your-bearer-token",
  "LM_ENABLE_WRITE_OPERATIONS": "true"
}
```

This enables tools like `acknowledge_alert`, `create_sdt`, `create_device`, etc.

## Available Tools

### Alert Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_alerts` | List alerts with optional severity/status filters | No |
| `get_alert_details` | Get detailed information about a specific alert | No |
| `acknowledge_alert` | Acknowledge an alert with optional note | Yes |
| `add_alert_note` | Add a note to an alert | Yes |
| `bulk_acknowledge_alerts` | Acknowledge multiple alerts at once (max 100) | Yes |

### Alert Rule Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_alert_rules` | List alert rules | No |
| `get_alert_rule` | Get detailed alert rule information | No |
| `create_alert_rule` | Create a new alert rule | Yes |
| `update_alert_rule` | Update an existing alert rule | Yes |
| `delete_alert_rule` | Delete an alert rule | Yes |
| `export_alert_rule` | Export alert rule as JSON | No |

### Device Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_devices` | List devices with optional group/name filters | No |
| `get_device` | Get detailed information about a specific device | No |
| `get_device_groups` | List device groups | No |
| `create_device` | Create a new device | Yes |
| `update_device` | Update an existing device | Yes |
| `delete_device` | Delete a device | Yes |
| `create_device_group` | Create a new device group | Yes |
| `delete_device_group` | Delete a device group | Yes |

### Metrics Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_device_datasources` | List DataSources applied to a device | No |
| `get_device_instances` | List instances for a DataSource on a device | No |
| `get_device_data` | Get metric data for a specific instance | No |
| `get_graph_data` | Get graph data for visualization | No |

### Dashboard Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_dashboards` | List dashboards with optional filters | No |
| `get_dashboard` | Get detailed dashboard information | No |
| `get_dashboard_widgets` | Get widgets for a specific dashboard | No |
| `get_widget` | Get detailed widget information | No |
| `get_dashboard_groups` | List dashboard groups | No |
| `get_dashboard_group` | Get dashboard group details | No |
| `create_dashboard` | Create a new dashboard | Yes |
| `update_dashboard` | Update an existing dashboard | Yes |
| `delete_dashboard` | Delete a dashboard | Yes |
| `add_widget` | Add a widget to a dashboard | Yes |
| `update_widget` | Update a widget | Yes |
| `delete_widget` | Delete a widget from a dashboard | Yes |
| `export_dashboard` | Export dashboard as JSON | No |

### SDT Tools

| Tool | Description | Write |
|------|-------------|-------|
| `list_sdts` | List Scheduled Downtime entries | No |
| `get_active_sdts` | Get currently active SDTs | No |
| `get_upcoming_sdts` | Get SDTs scheduled within a time window | No |
| `create_sdt` | Create a new SDT for a device or group | Yes |
| `delete_sdt` | Delete an existing SDT | Yes |
| `bulk_create_device_sdt` | Create SDT for multiple devices (max 100) | Yes |
| `bulk_delete_sdt` | Delete multiple SDTs at once (max 100) | Yes |

### Collector Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_collectors` | List all collectors | No |
| `get_collector` | Get detailed information about a specific collector | No |
| `get_collector_groups` | List collector groups | No |
| `get_collector_group` | Get detailed collector group info | No |

### Website Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_websites` | List websites/synthetic checks | No |
| `get_website` | Get detailed website information | No |
| `get_website_groups` | List website groups | No |
| `get_website_data` | Get monitoring data for a website | No |
| `create_website` | Create a new website check | Yes |
| `update_website` | Update a website check | Yes |
| `delete_website` | Delete a website check | Yes |
| `create_website_group` | Create a website group | Yes |
| `delete_website_group` | Delete a website group | Yes |

### Escalation Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_escalation_chains` | List escalation chains | No |
| `get_escalation_chain` | Get detailed escalation chain info | No |
| `create_escalation_chain` | Create a new escalation chain | Yes |
| `update_escalation_chain` | Update an escalation chain | Yes |
| `delete_escalation_chain` | Delete an escalation chain | Yes |
| `export_escalation_chain` | Export escalation chain as JSON | No |
| `get_recipient_groups` | List recipient groups | No |
| `get_recipient_group` | Get detailed recipient group info | No |
| `create_recipient_group` | Create a new recipient group | Yes |
| `update_recipient_group` | Update a recipient group | Yes |
| `delete_recipient_group` | Delete a recipient group | Yes |

### Resource Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_device_properties` | List all properties for a device | No |
| `get_device_property` | Get a specific device property | No |
| `update_device_property` | Update or create a custom device property | Yes |

### Report Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_reports` | List reports with optional filters | No |
| `get_report` | Get detailed report information | No |
| `get_report_groups` | List report groups | No |
| `get_scheduled_reports` | Get reports with schedules configured | No |
| `run_report` | Execute/run a report | Yes |
| `create_report` | Create a new report | Yes |
| `update_report_schedule` | Update a report's schedule | Yes |
| `delete_report` | Delete a report | Yes |

### DataSource Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_datasources` | List all DataSources | No |
| `get_datasource` | Get DataSource details | No |
| `export_datasource` | Export DataSource as JSON | No |
| `import_datasource` | Import DataSource from JSON | Yes |

### LogicModule Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_configsources` | List ConfigSources | No |
| `get_configsource` | Get ConfigSource details | No |
| `export_configsource` | Export ConfigSource as JSON | No |
| `import_configsource` | Import ConfigSource from JSON | Yes |
| `get_eventsources` | List EventSources | No |
| `get_eventsource` | Get EventSource details | No |
| `export_eventsource` | Export EventSource as JSON | No |
| `import_eventsource` | Import EventSource from JSON | Yes |
| `get_propertysources` | List PropertySources | No |
| `get_propertysource` | Get PropertySource details | No |
| `export_propertysource` | Export PropertySource as JSON | No |
| `import_propertysource` | Import PropertySource from JSON | Yes |
| `get_topologysources` | List TopologySources | No |
| `get_topologysource` | Get TopologySource details | No |
| `import_topologysource` | Import TopologySource from JSON | Yes |
| `get_logsources` | List LogSources | No |
| `get_logsource` | Get LogSource details | No |
| `get_device_logsources` | Get LogSources applied to a device | No |
| `export_logsource` | Export LogSource as JSON | No |
| `import_logsource` | Import LogSource from JSON | Yes |
| `import_jobmonitor` | Import JobMonitor from JSON | Yes |
| `import_appliesto_function` | Import AppliesTo function from JSON | Yes |

### Cost Optimization Tools (LM Envision)

| Tool | Description | Write |
|------|-------------|-------|
| `get_cost_summary` | Get cloud cost summary | No |
| `get_resource_cost` | Get cost data for a specific resource | No |
| `get_cost_recommendations` | Get cost optimization recommendations | No |
| `get_cost_recommendation_categories` | Get recommendation categories with counts | No |
| `get_cost_recommendation` | Get specific recommendation by ID | No |
| `get_idle_resources` | Get idle/underutilized resources | No |
| `get_cloud_cost_accounts` | Get cloud accounts with cost data | No |

### Ingestion Tools (Requires LMv1 Auth)

| Tool | Description | Write |
|------|-------------|-------|
| `ingest_logs` | Push log entries to LogicMonitor | Yes |
| `push_metrics` | Push custom metrics to LogicMonitor | Yes |

### Network & Topology Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_topology_map` | Get network topology map data | No |
| `get_device_neighbors` | Get neighboring devices based on topology | No |
| `get_device_interfaces` | Get network interfaces for a device | No |
| `get_network_flows` | Get network flow data (NetFlow/sFlow) | No |
| `get_device_connections` | Get device relationships/connections | No |

### Batch Job Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_batchjobs` | List batch jobs | No |
| `get_batchjob` | Get batch job details | No |
| `get_batchjob_history` | Get execution history for a batch job | No |
| `get_device_batchjobs` | Get batch jobs for a specific device | No |
| `get_scheduled_downtime_jobs` | Get batch jobs related to SDT automation | No |

### Ops & Audit Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_audit_logs` | Get audit log entries | No |
| `get_api_token_audit` | Get API token usage audit logs | No |
| `get_login_audit` | Get login/authentication audit logs | No |
| `get_change_audit` | Get configuration change audit logs | No |
| `get_ops_notes` | List ops notes | No |
| `get_ops_note` | Get detailed ops note information | No |
| `add_ops_note` | Add a new ops note | Yes |

### User & Access Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_users` | List users | No |
| `get_user` | Get detailed user information | No |
| `get_roles` | List roles | No |
| `get_role` | Get detailed role information | No |
| `get_access_groups` | List access groups (RBAC) | No |
| `get_access_group` | Get access group details | No |
| `get_api_tokens` | List API tokens | No |
| `get_api_token` | Get API token details | No |

### Service Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_services` | List services (LM Service Insight) | No |
| `get_service` | Get detailed service information | No |
| `get_service_groups` | List service groups | No |

### Netscan Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_netscans` | List network discovery scans | No |
| `get_netscan` | Get detailed netscan information | No |
| `run_netscan` | Execute a netscan immediately | Yes |

### OID Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_oids` | List SNMP OIDs | No |
| `get_oid` | Get detailed OID information | No |

## MCP Resources

The server exposes 15 resources for API reference:

### Schema Resources
| URI | Description |
|-----|-------------|
| `lm://schema/alerts` | Alert object fields, types, and descriptions |
| `lm://schema/devices` | Device object fields and types |
| `lm://schema/sdts` | SDT (Scheduled Downtime) object fields |
| `lm://schema/dashboards` | Dashboard object fields |
| `lm://schema/collectors` | Collector object fields |

### Enum Resources
| URI | Description |
|-----|-------------|
| `lm://enums/severity` | Alert severity levels: critical(4), error(3), warning(2), info(1) |
| `lm://enums/device-status` | Device status values: normal(0), dead(1), etc. |
| `lm://enums/sdt-type` | SDT types: DeviceSDT, DeviceGroupSDT, etc. |
| `lm://enums/alert-cleared` | Alert cleared status: true, false |
| `lm://enums/alert-acked` | Alert acknowledgment status: true, false |
| `lm://enums/collector-build` | Collector build types: EA, GD, MGD |

### Filter Resources
| URI | Description |
|-----|-------------|
| `lm://filters/alerts` | Filter fields and operators for alert queries |
| `lm://filters/devices` | Filter fields and operators for device queries |
| `lm://filters/sdts` | Filter fields and operators for SDT queries |
| `lm://syntax/operators` | Filter operators: `:`, `~`, `>`, `<`, `!:`, `!~`, `>:`, `<:` |

## MCP Prompts

Pre-built workflow templates for common tasks:

| Prompt | Description | Arguments |
|--------|-------------|-----------|
| `incident_triage` | Analyze active alerts, identify patterns, suggest root cause | `severity`, `time_window_hours` |
| `capacity_review` | Review resource utilization and identify capacity concerns | `group_id`, `threshold_percent` |
| `health_check` | Generate environment health summary with key metrics | `include_collectors` |
| `alert_summary` | Generate alert digest grouped by severity or resource | `group_by`, `hours_back` |
| `sdt_planning` | Plan scheduled downtime for maintenance windows | `device_ids`, `group_id` |

## Example Usage

Once configured, you can ask your AI assistant natural language questions. Here are prompts to test different capabilities:

### Quick Verification Prompts
Start with these to verify the connection is working:
- "List the first 5 devices in LogicMonitor"
- "How many collectors do I have?"
- "Show me active alerts"

### Alert Management
- "Show me all critical alerts"
- "What alerts fired in the last hour?"
- "Get details on alert LMA12345"
- "Acknowledge alert LMA12345 with note 'Investigating disk issue'"
- "Bulk acknowledge all warning alerts from the last hour"
- "Add a note to alert LMA67890: 'Escalated to storage team'"
- "What alert rules route to the Primary On-Call escalation chain?"

### Device Operations
- "What devices are in the Production group?"
- "Find all devices with 'web' in the name"
- "Show me details for device ID 123"
- "Add device 10.0.0.1 called 'web-server-03' to group ID 5 using collector 2"
- "Create a device group called 'Staging' under the Production group"
- "Update the description on device 456 to 'Primary web server'"

### Monitoring & Metrics
- "What datasources are applied to device 123?"
- "Show me the instances for datasource 456 on device 123"
- "Get CPU metrics for the last hour on device 123"
- "List all collectors and their status"

### Dashboards & Visualization
- "List all dashboards"
- "Show me dashboards with 'NOC' in the name"
- "What widgets are on dashboard 123?"
- "Create a new dashboard called 'API Health'"
- "Add a graph widget to dashboard 123"

### Scheduled Downtime (SDT)
- "List all active SDTs"
- "What SDTs are coming up in the next 24 hours?"
- "Create a 2-hour maintenance window for device 123"
- "Schedule downtime for devices 1, 2, and 3 for 1 hour"
- "Delete SDT abc123"

### Website Monitoring
- "List all website checks"
- "Create a ping check for example.com"
- "Show me details for website 123"
- "Update the polling interval on website 456 to 10 minutes"

### Cost Optimization (LM Envision)
- "Show me a cloud cost summary"
- "What are the cost optimization recommendations?"
- "List idle resources under 10% utilization"
- "What are the cost recommendation categories?"

### LogicModule Management
- "Export datasource ID 123 as JSON"
- "List all ConfigSources"
- "Show me EventSources that apply to Windows"
- "Import this datasource JSON definition"

### Log & Metric Ingestion
- "Push this log entry to LogicMonitor: 'Application started successfully'"
- "Send these metrics to device server1"

### Escalations & Notifications
- "Show me all escalation chains"
- "Create an escalation chain called 'Critical Alerts'"
- "List recipient groups"
- "Who is in the 'DevOps On-Call' recipient group?"

### Operations & Audit
- "Show me recent audit log entries"
- "What configuration changes were made in the last 24 hours?"
- "Show me failed login attempts"
- "List ops notes tagged 'maintenance'"
- "Add an ops note: 'Starting v2.5 deployment' with tag 'deployment'"

### Advanced Filtering
The server supports LogicMonitor's filter syntax for power users:
- "Get devices where filter is 'displayName~prod,hostStatus:alive'"
- "List alerts with filter 'severity>2,cleared:false'"
- "Find datasources matching 'appliesTo~isWindows()'"

## Development

### Running Tests

```bash
uv run pytest -v
```

### Linting

```bash
uv run ruff check src tests
uv run ruff format src tests
```

### Project Structure

```
src/lm_mcp/
├── __init__.py           # Package exports
├── config.py             # Environment-based configuration
├── exceptions.py         # Exception hierarchy
├── logging.py            # Structured logging
├── server.py             # MCP server entry point
├── registry.py           # Tool definitions and handlers
├── auth/
│   ├── __init__.py       # Auth provider factory
│   ├── bearer.py         # Bearer token auth
│   └── lmv1.py           # LMv1 HMAC auth
├── client/
│   ├── __init__.py       # Client exports
│   └── api.py            # Async HTTP client
├── completions/
│   └── registry.py       # Auto-complete definitions
├── prompts/
│   └── registry.py       # Workflow templates
├── resources/
│   ├── registry.py       # Resource definitions
│   ├── schemas.py        # Schema content
│   ├── enums.py          # Enum content
│   └── filters.py        # Filter content
└── tools/
    ├── __init__.py       # Tool utilities
    ├── alerts.py         # Alert management
    ├── alert_rules.py    # Alert rule CRUD
    ├── collectors.py     # Collector tools
    ├── cost.py           # Cost optimization
    ├── dashboards.py     # Dashboard CRUD
    ├── devices.py        # Device CRUD
    ├── escalations.py    # Escalation/recipient CRUD
    ├── imports.py        # LogicModule import
    ├── ingestion.py      # Log/metric ingestion
    ├── metrics.py        # Metrics and data
    ├── sdts.py           # SDT management
    ├── websites.py       # Website CRUD
    └── ...               # Additional tool modules
```

## Troubleshooting

### "Failed to connect" in Claude Code

If `claude mcp list` shows `✗ Failed to connect`, the server is missing environment variables. The `-e` flags must be included when adding the server:

```bash
# Remove the broken config
claude mcp remove logicmonitor

# Re-add with environment variables
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=your-bearer-token \
  -- uvx --from lm-mcp lm-mcp-server
```

> **Note:** Setting environment variables in your shell or `.env` file won't work—Claude Code spawns the MCP server as a subprocess with its own environment.

### "Write operations are disabled"

Write operations (acknowledge, create SDT, etc.) are disabled by default. Set `LM_ENABLE_WRITE_OPERATIONS=true` in your environment.

### "spawn uvx ENOENT" in Claude Desktop

Claude Desktop can't find `uvx`. Use the full path:

```json
{
  "command": "/Users/yourname/.local/bin/uvx",
  "args": ["--from", "lm-mcp", "lm-mcp-server"]
}
```

Find your uvx path with: `which uvx`

### Ingestion API Errors

The `ingest_logs` and `push_metrics` tools require LMv1 authentication. Bearer tokens don't work with ingestion APIs. Add `LM_ACCESS_ID` and `LM_ACCESS_KEY` to your configuration.

### Rate Limit Errors

The server automatically retries rate-limited requests with exponential backoff. If you're consistently hitting limits, reduce request frequency or contact LogicMonitor support.

### Authentication Errors

Verify your bearer token is correct and has appropriate permissions. API tokens can be managed in LogicMonitor under **Settings** → **Users and Roles** → **API Tokens**.

## License

MIT License - see LICENSE file.
