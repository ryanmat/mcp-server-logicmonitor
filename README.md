# LogicMonitor MCP Server

Model Context Protocol (MCP) server for LogicMonitor REST API v3 integration. Enables AI assistants like Claude to interact with LogicMonitor monitoring data through structured tools.

## Features

- **Alert Management**: Get alerts, view details, acknowledge alerts, add notes
- **Device Management**: List devices, get device details, browse device groups
- **Metrics & Data**: Query device datasources, instances, and metric data
- **Dashboard Management**: List dashboards, view widgets, create dashboards
- **SDT Management**: List, create, and delete Scheduled Downtime
- **Collector Management**: List and view collector details
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

## Available Tools

### Alert Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_alerts` | List alerts with optional severity/status filters | No |
| `get_alert_details` | Get detailed information about a specific alert | No |
| `acknowledge_alert` | Acknowledge an alert with optional note | Yes |
| `add_alert_note` | Add a note to an alert | Yes |

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

## Example Usage

Once configured, you can ask Claude:

- "Show me all critical alerts"
- "What devices are in the Production group?"
- "Acknowledge alert LMA12345 with note 'Investigating'"
- "Create a 1-hour maintenance window for device ID 100"
- "List all collectors and their status"
- "Show me the CPU metrics for device ID 100"
- "What datasources are monitoring server prod-web-01?"
- "List all dashboards"
- "Show me the widgets on the Production Overview dashboard"

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
    ├── collectors.py  # Collector tools
    ├── dashboards.py  # Dashboard tools
    ├── datasources.py # DataSource tools
    ├── devices.py     # Device management tools
    ├── metrics.py     # Metrics and data tools
    └── sdts.py        # SDT management tools
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
