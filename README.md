# LogicMonitor MCP Server

Model Context Protocol (MCP) server for LogicMonitor REST API v3 integration. Enables AI assistants to interact with LogicMonitor monitoring data through structured tools.

Works with any MCP-compatible client: Claude Desktop, Cursor, Continue, Cline, and more.

## Features

- **Alert Management**: Get alerts, view details, acknowledge alerts, add notes, view alert rules
- **Device Management**: List devices, get device details, browse device groups
- **Metrics & Data**: Query device datasources, instances, and metric data
- **Dashboard Management**: List dashboards, view widgets, create dashboards
- **SDT Management**: List, create, and delete Scheduled Downtime
- **Collector Management**: List and view collector details
- **Website Monitoring**: List websites, get synthetic check details and data
- **Resource Management**: Get and update device properties
- **Report Management**: List, view, and run reports
- **Escalation Management**: View escalation chains and recipient groups
- **Ops Management**: Get audit logs and manage ops notes
- **Security-First**: Read-only by default, write operations require explicit opt-in
- **Rate Limit Handling**: Automatic retry with exponential backoff

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
| `LM_PORTAL` | Yes | - | LogicMonitor portal (e.g., `company.logicmonitor.com`) |
| `LM_BEARER_TOKEN` | Yes | - | API Bearer token |
| `LM_ENABLE_WRITE_OPERATIONS` | No | `false` | Enable write operations (ack alerts, create SDTs) |
| `LM_API_VERSION` | No | `3` | API version |
| `LM_TIMEOUT` | No | `30` | Request timeout in seconds |
| `LM_MAX_RETRIES` | No | `3` | Max retries for rate-limited requests |

### Getting a Bearer Token

1. Log into your LogicMonitor portal
2. Go to **Settings** → **Users and Roles** → **API Tokens**
3. Create a new API-only user or add a token to an existing user
4. Copy the Bearer token

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

To enable write operations (acknowledge alerts, create SDTs):

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uvx",
      "args": ["--from", "lm-mcp", "lm-mcp-server"],
      "env": {
        "LM_PORTAL": "yourcompany.logicmonitor.com",
        "LM_BEARER_TOKEN": "your-bearer-token",
        "LM_ENABLE_WRITE_OPERATIONS": "true"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add logicmonitor -- uvx --from lm-mcp lm-mcp-server
```

Then set environment variables in your shell or `.env` file.

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

Then enable the server in Cursor Settings > MCP.

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

## Available Tools

### Alert Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_alerts` | List alerts with optional severity/status filters | No |
| `get_alert_details` | Get detailed information about a specific alert | No |
| `acknowledge_alert` | Acknowledge an alert with optional note | Yes |
| `add_alert_note` | Add a note to an alert | Yes |

### Alert Rule Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_alert_rules` | List alert rules with optional name/priority filters | No |
| `get_alert_rule` | Get detailed information about a specific alert rule | No |

### Device Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_devices` | List devices with optional group/name filters | No |
| `get_device` | Get detailed information about a specific device | No |
| `get_device_groups` | List device groups | No |

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
| `create_dashboard` | Create a new dashboard | Yes |

### DataSource Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_datasources` | List all DataSources (LogicModules) | No |
| `get_datasource` | Get DataSource details with datapoints and graphs | No |

### SDT Tools

| Tool | Description | Write |
|------|-------------|-------|
| `list_sdts` | List Scheduled Downtime entries | No |
| `create_sdt` | Create a new SDT for a device or group | Yes |
| `delete_sdt` | Delete an existing SDT | Yes |

### Collector Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_collectors` | List all collectors | No |
| `get_collector` | Get detailed information about a specific collector | No |

### Website Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_websites` | List websites/synthetic checks with optional filters | No |
| `get_website` | Get detailed information about a specific website | No |
| `get_website_groups` | List website groups | No |
| `get_website_data` | Get monitoring data for a website checkpoint | No |

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
| `get_report` | Get detailed information about a specific report | No |
| `get_report_groups` | List report groups | No |
| `run_report` | Execute/run a report | Yes |

### Escalation Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_escalation_chains` | List escalation chains | No |
| `get_escalation_chain` | Get detailed escalation chain info with destinations | No |
| `get_recipient_groups` | List recipient groups | No |
| `get_recipient_group` | Get detailed recipient group info with members | No |

### Ops Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_audit_logs` | Get audit log entries with optional filters | No |
| `get_ops_notes` | List ops notes with optional tag filter | No |
| `get_ops_note` | Get detailed information about a specific ops note | No |
| `add_ops_note` | Add a new ops note with optional tags and scopes | Yes |

## Example Usage

Once configured, you can ask your AI assistant:

- "Show me all critical alerts"
- "What alert rules route to the Primary On-Call chain?"
- "What devices are in the Production group?"
- "Acknowledge alert LMA12345 with note 'Investigating'"
- "Create a 1-hour maintenance window for device ID 100"
- "List all collectors and their status"
- "Show me the CPU metrics for device ID 100"
- "What datasources are monitoring server prod-web-01?"
- "List all dashboards"
- "Show me the widgets on the Production Overview dashboard"
- "List all website checks"
- "Show me the response times for website ID 100"
- "What properties does device ID 100 have?"
- "Update the location property on device 100 to US-West"
- "List all reports"
- "Run the Daily Alert Summary report"
- "Show me the escalation chains"
- "Who is in the DevOps recipient group?"
- "Show me recent audit log entries"
- "List all ops notes with the maintenance tag"
- "Add an ops note for the deployment"

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
├── __init__.py       # Package exports
├── config.py         # Environment-based configuration
├── exceptions.py     # Exception hierarchy
├── server.py         # MCP server entry point
├── auth/
│   ├── __init__.py   # Auth provider factory
│   └── bearer.py     # Bearer token auth
├── client/
│   ├── __init__.py   # Client exports
│   └── api.py        # Async HTTP client
└── tools/
    ├── __init__.py    # Tool utilities
    ├── alerts.py      # Alert management tools
    ├── alert_rules.py # Alert rule tools
    ├── collectors.py  # Collector tools
    ├── dashboards.py  # Dashboard tools
    ├── datasources.py # DataSource tools
    ├── devices.py     # Device management tools
    ├── escalations.py # Escalation chain and recipient tools
    ├── metrics.py     # Metrics and data tools
    ├── ops.py         # Audit log and ops notes tools
    ├── reports.py     # Report management tools
    ├── resources.py   # Resource/property management tools
    ├── sdts.py        # SDT management tools
    └── websites.py    # Website/synthetic monitoring tools
```

## Troubleshooting

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

### Rate Limit Errors

The server automatically retries rate-limited requests with exponential backoff. If you're consistently hitting limits, reduce request frequency or contact LogicMonitor support.

### Authentication Errors

Verify your bearer token is correct and has appropriate permissions. API tokens can be managed in LogicMonitor under **Settings** → **Users and Roles** → **API Tokens**.

## License

MIT License - see LICENSE file.
