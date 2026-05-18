# LogicMonitor MCP Server

[![PyPI version](https://img.shields.io/pypi/v/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<!-- mcp-name: io.github.ryanmat/logicmonitor -->

Model Context Protocol (MCP) server for LogicMonitor REST API v3 integration. Enables AI assistants to interact with LogicMonitor monitoring data through 280+ structured tools, 15 workflow prompts, and 26 resources. Optional integrations: IBM watsonx.ai for Granite TTM forecasting and NL summaries, Terraform IaC for any provider, and HuggingFace local Granite model fallback.

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

With **IBM watsonx.ai integration** (optional -- adds Granite TTM forecasting and NL summaries):
```bash
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=your-bearer-token \
  -e WATSONX_API_KEY=your-ibm-cloud-api-key \
  -e WATSONX_URL=https://us-south.ml.cloud.ibm.com \
  -e WATSONX_PROJECT_ID=your-watsonx-project-id \
  -- uvx --from "lm-mcp[ibm]" lm-mcp-server
```

With **Terraform IaC** (optional -- adds terraform plan/apply/generate tools):
```bash
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=your-bearer-token \
  -e TF_WORKSPACE_DIR=/path/to/terraform/workspaces \
  -- uvx --from lm-mcp lm-mcp-server
```

With **HuggingFace local models** (optional -- local Granite TTM + NL summaries, no cloud API needed):
```bash
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=your-bearer-token \
  -- uvx --from "lm-mcp[huggingface]" lm-mcp-server
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

## What's New in v3.8.3

**Patch.** Bug-class sweep across the tool surface. Fixes the diagnosticsource and remediationsource readers (HTTP 415 against the wrong path), an LMv1 HMAC signature mismatch on empty-body requests, a `JSONDecodeError` crash in `calculate_error_budget`, a wrong-math silent failure in `calculate_availability` when the device lookup 404s, missing `@require_write_permission` on `ingest_logs`/`push_metrics`, and bare error-string returns in `baselines.py`. Introduces `call_sub_tool` and `validation_error` as shared helpers in `lm_mcp.tools` so the v3.8.2 hardening pattern is usable outside `workflows.py`. CHANGELOG lists tracked follow-ups for the rest of the audit (pagination, naming, parity).

### v3.8.2 — composite dispatch helper hardening

Patches the composite dispatch helper and `detect_site_outage` collector enumeration. `_call_sub_tool` now handles sub-tool error responses cleanly (was crashing with `JSONDecodeError` when a sub-tool returned the human-readable `"Error: ..."` shape). `detect_site_outage` now probes each collector independently so a single orphaned collector reference no longer truncates the CollectorDown signal. Surfaced during the v3.8.1 portal smoke test.

### v3.8.1 — detect_site_outage collector enumeration

Fixes the v3.8.0 composite looking for raw-API field names (`currentCollectorId`) that the formatted `get_devices` response renames to `collector_id`; the CollectorDown signal was always zero. Also counts `hostStatus=2` (dead-collector) as dead alongside `hostStatus=1`.

### v3.8.0 — Networking intelligence

Eight read-only tools for interface metrics, NetFlow top talkers, alert burst detection, link flaps, UPS/PDU events, enriched collector health, and two composite workflows (`detect_site_outage`, `audit_network_monitoring_coverage`) that close the correlation gap generic AIOps misses.

See [documentation/networking-intelligence.md](documentation/networking-intelligence.md) for the full tool reference, scoring model, and prerequisites. Full release history in [CHANGELOG.md](CHANGELOG.md).

## Features

**280+ Tools** across comprehensive LogicMonitor API coverage (251 LM + 18 AAP + 10 Terraform + 1 watsonx):

### Core Monitoring
- **Alert Management**: Query, acknowledge, bulk acknowledge, add notes, view rules
- **Device Management**: Full CRUD - list, create, update, delete devices and groups
- **Metrics & Data**: Query datasources, instances, metric data, and graphs. Instance CRUD for manual datasource instances.
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

### AI Analysis Tools

Server-side intelligence that transforms raw monitoring data into actionable insights:

- **Alert Correlation**: Automatically clusters related alerts by device, datasource, and temporal proximity — replaces dozens of manual API calls with a single aggregated view
- **Alert Statistics**: Aggregated alert counts by severity, top-10 devices and datasources, time-bucketed distributions for trend analysis
- **Metric Anomaly Detection**: Multi-method anomaly detection (z-score, IQR, MAD) with auto-selection based on data distribution
- **Metric Baselines**: Save baseline snapshots of metric behavior, then compare current performance against the baseline to detect drift
- **Scheduled Analysis**: HTTP API endpoints for triggering analysis workflows (alert correlation, RCA, top talkers, health checks) from external schedulers and webhooks

### ML/Statistical Analysis Tools

Pure-Python statistical methods for capacity planning, trend analysis, and operational scoring:

- **Metric Forecasting**: Linear regression, Holt-Winters triple exponential smoothing, and IBM Granite TTM (via watsonx.ai, optional) with auto-selection, confidence intervals, and threshold breach prediction
- **Metric Correlation**: Pearson correlation matrix across multiple metric series with strong-correlation highlighting
- **Error Budget Tracking**: SLO-based error budget calculation with burn rate, projected exhaustion, and status classification
- **Change Point Detection**: CUSUM algorithm for identifying regime shifts and mean-level changes
- **Alert Noise Scoring**: Shannon entropy and flap detection to quantify alert noise (0-100) with tuning recommendations
- **Seasonality Detection**: Autocorrelation-based periodicity detection at standard intervals with peak-hour identification
- **Availability Calculation**: SLA-style uptime percentage from alert history with MTTR, incident counts, and per-device breakdown
- **Blast Radius Analysis**: Topology-based downstream impact scoring for device failure scenarios
- **Change Correlation**: Cross-references alert spikes with audit/change logs to identify change-induced incidents
- **Trend Classification**: Categorizes metrics as stable, increasing, decreasing, cyclic, or volatile
- **Device Health Scoring**: Multi-metric composite health score (0-100) using z-score analysis with configurable weights

### Composite Workflow Tools

Multi-step analysis tools that combine several sub-tools into a single call. Each supports `detail_level` ("summary" or "full"), optional `summarize=true` for plain-English NL summaries via IBM Granite (requires watsonx.ai), and handles sub-tool failures gracefully with partial results.

- **Triage**: Correlates active alerts, scores noise, analyzes blast radius, and cross-references recent changes
- **Health Check**: Device health score, monitoring coverage, anomaly detection, active alerts, and 30-day availability
- **Capacity Plan**: Per-datasource forecasting, trend classification, seasonality detection, and change point analysis
- **Portal Overview**: Alert statistics, collector health, active SDTs, alert clusters, noise assessment, and down devices
- **Diagnose**: Alert details, device context, correlation, blast radius, health scoring, and root cause analysis
- **Update LogicModule (Safe Partial Updates)**: `update_logicmodule(type, id, changes, mode)` exports the current full definition, deep-merges your `changes`, validates required fields, and returns a dry-run diff (default) or applies the merge. Prevents the full-replace blanking that wiped production Groovy scripts in two prior incidents. Supports configsource, datasource, eventsource, logsource, propertysource, topologysource.
- **Search Tools**: Keyword search across all tools by name and description with category filtering

### APM Trace Tools

Service discovery and RED metrics for LogicMonitor APM (Application Performance Monitoring):

- **Service Discovery**: List all traced services, inspect individual service details and properties
- **Operation Listing**: Discover endpoints/routes monitored within each service
- **RED Metrics**: Duration, error count, and operation count at both service and per-operation level
- **Alert Integration**: View active alerts for any traced service
- **Property Inspection**: OTel attributes, namespace info, and auto-discovered metadata

### Ansible Automation Platform Integration

18 tools for observability-driven remediation via Ansible Automation Platform (AAP). Connects LogicMonitor alerts to automated remediation playbooks.

- **Job Templates**: List, inspect, and launch job templates with extra variables and host limits
- **Job Execution**: Launch jobs, check status, view output, cancel or relaunch runs
- **Workflows**: Launch workflow templates, monitor multi-step automation sequences
- **Inventories & Hosts**: List inventories, inspect hosts for targeted remediation
- **Projects & Credentials**: Browse available projects and credentials (secrets never exposed)
- **Write Protection**: launch_job, launch_workflow, cancel_job, relaunch_job require `LM_ENABLE_WRITE_OPERATIONS=true`
- **Jinja2 Safety**: All extra_vars inputs are validated to prevent template injection

AAP tools are optional — they only appear when `AWX_URL` and `AWX_TOKEN` are configured. See [Example Playbooks](examples/playbooks/) for remediation templates.

### IBM watsonx.ai Integration

Optional AI-powered enhancements using IBM Granite foundation models via watsonx.ai. Requires an IBM Cloud account with a watsonx.ai project (Lite/free tier supported).

- **Granite TTM Forecasting**: ML-powered time series forecasting using IBM Granite Tiny Time Mixer (TTM). Use `method="ttm"` on `forecast_metric` for 96-step predictions that detect seasonality and non-linear patterns. Requires 512+ data points. Gracefully falls back to statistical methods when data is insufficient.
- **Granite NL Summaries**: Plain-English shift-handoff summaries on composite workflow tools (`triage`, `diagnose`, `health_check`, `capacity_plan`, `portal_overview`). Pass `summarize=true` to append an IBM Granite-generated analysis summary to the structured output.
- **watsonx_summarize**: Standalone tool that takes any JSON data and generates a concise NL summary via Granite 4.0. Useful for summarizing output from any MCP tool.

watsonx tools are optional — they only appear when `WATSONX_API_KEY` and `WATSONX_PROJECT_ID` are configured. Install with `lm-mcp[ibm]` to include the IBM SDK dependencies.

**Setup:**
1. Create a free IBM Cloud account at [cloud.ibm.com](https://cloud.ibm.com)
2. Provision **watsonx.ai Runtime** (Lite plan, free) from the IBM Cloud catalog
3. Create a watsonx.ai project and associate the Runtime instance
4. Generate an IBM Cloud API key at [cloud.ibm.com/iam/apikeys](https://cloud.ibm.com/iam/apikeys)
5. Configure the MCP server with `WATSONX_API_KEY`, `WATSONX_URL`, and `WATSONX_PROJECT_ID`

### Terraform Integration

11 tools for Infrastructure as Code workflows with any Terraform provider. AI agents can author HCL, use pre-made scripts, or reverse-engineer existing LM resources.

- **terraform_init**: Initialize workspace and download providers
- **terraform_validate**: Syntax-check HCL configuration
- **terraform_plan**: Preview changes with structured JSON output
- **terraform_apply**: Apply changes (triple-gated: write perms + config flag + confirm param)
- **terraform_destroy**: Destroy infrastructure (same triple gate)
- **terraform_import**: Import existing resources into Terraform state
- **terraform_state_list / terraform_state_show**: Inspect current state
- **terraform_output**: View Terraform outputs
- **terraform_write_config**: Write HCL files to workspace directories
- **terraform_generate**: Export existing LM portal resources as HCL using the `logicmonitor/logicmonitor` provider

Terraform tools are optional -- they only appear when `TF_WORKSPACE_DIR` is configured. Requires the `terraform` CLI installed separately.

**Three entry points:**
1. **Agent-authored**: AI generates HCL from natural language, writes to workspace, plans, applies
2. **Pre-made scripts**: Point `TF_WORKSPACE_DIR` at existing `.tf` files, agent operates on them
3. **Reverse-engineer**: `terraform_generate` exports LM resources as HCL, then import into state

### HuggingFace Local Fallback

When watsonx.ai API credentials are not configured, TTM forecasting and NL summaries automatically fall back to local Granite models via HuggingFace transformers. Install with `lm-mcp[huggingface]`.

**Priority chain:** watsonx.ai API (remote) > HuggingFace local > statistical/linear

- **TTM Model**: `ibm-granite/granite-timeseries-ttm-r2` (512 context, 96 forecast)
- **LLM Model**: `ibm-granite/granite-3.3-2b-instruct` (2B params, runs on CPU)
- Models lazy-load on first inference call (initial download: ~500MB TTM, ~4GB LLM)
- Same interface as WatsonxClient -- all existing watsonx tools work with either backend

### LogicModules
- **DataSources**: Query and export datasource definitions
- **ConfigSources**: Query definitions, retrieve device config data from the Config Archive, view diffs, trigger on-demand collection, and audit change history
- **EventSources**: Query and export event detection modules
- **PropertySources**: Query, create, and export property collection modules
- **TopologySources**: Query and export topology mapping modules
- **LogSources**: Query and export log collection modules
- **Import Support**: Import LogicModules from JSON definitions

### Advanced Capabilities
- **Cost Optimization**: Cloud cost analysis, recommendations, idle resources (LM Envision)
- **Network Topology**: Device neighbors, interfaces, flows, connections
- **Batch Jobs**: View and manage batch job execution history
- **Log/Metric Ingestion**: Push logs and metrics via LMv1 authentication

### MCP Protocol Features
- **Resources**: 26 schema/enum/filter/guide resources for API reference
- **Prompts**: 15 workflow templates (incident triage, RCA, capacity forecasting, remediation execution, etc.)
- **Completions**: Auto-complete for tool arguments

### Claude Code Skills

Pre-built slash-command workflows for Claude Code that orchestrate multiple tools into guided operational runbooks:

| Skill | Command | Description |
|-------|---------|-------------|
| Alert Triage | `/lm-triage` | Investigate active alerts, score noise, correlate clusters, assess blast radius, take action |
| Device Health | `/lm-health <device>` | Comprehensive health check — metrics, anomalies, health score, availability, topology |
| Portal Overview | `/lm-portal` | Portal-wide snapshot for shift handoff — alerts, collectors, SDTs, down devices |
| Capacity Planning | `/lm-capacity <device>` | Trend analysis, seasonality detection, breach forecasting, right-sizing |
| APM Investigation | `/lm-apm [service]` | Service discovery, operation-level RED metrics, alert correlation |
| Remediation | `/lm-remediate` | Diagnose alert, find/generate playbook, launch AAP job, verify fix |

Skills ship with the repo — clone it and invoke `/lm-triage` in Claude Code to get started.

### Operational Features
- **Security-First**: Read-only by default, write operations require explicit opt-in
- **Rate Limit Handling**: Automatic retry with exponential backoff and jitter
- **Server Error Recovery**: Automatic retry on 5xx server errors
- **Pagination Support**: Handle large result sets with offset-based pagination
- **Session Persistence**: Optional file-backed session variables that survive restarts

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

### Docker Deployment

For remote/shared deployments using HTTP transport:

```bash
cd deploy
cp .env.example .env
# Edit .env with your credentials

# Run with docker-compose
docker compose up -d

# With TLS via Caddy
docker compose --profile tls up -d
```

The server exposes health endpoints for container orchestration:
- `GET /health` - Detailed health check with all component statuses
- `GET /healthz` - Liveness probe (200 OK or 503)
- `GET /readyz` - Readiness probe (includes connectivity check if enabled)

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
| `LM_TRANSPORT` | No | `stdio` | Transport mode: `stdio` (local) or `http` (remote) |
| `LM_HTTP_HOST` | No | `0.0.0.0` | HTTP server bind address |
| `LM_HTTP_PORT` | No | `8080` | HTTP server port |
| `LM_CORS_ORIGINS` | No | `*` | Comma-separated CORS origins |
| `LM_SESSION_ENABLED` | No | `true` | Enable session context tracking |
| `LM_SESSION_HISTORY_SIZE` | No | `50` | Number of tool calls to keep in history |
| `LM_LOG_LEVEL` | No | `warning` | Logging level: `debug`, `info`, `warning`, or `error` |
| `LM_FIELD_VALIDATION` | No | `warn` | Field validation: `off`, `warn`, or `error` |
| `LM_ENABLED_TOOLS` | No | - | Comma-separated tool names or glob patterns to enable (e.g., `get_*,triage`). Mutually exclusive with `LM_DISABLED_TOOLS`. |
| `LM_DISABLED_TOOLS` | No | - | Comma-separated tool names or glob patterns to disable (e.g., `delete_*`). Mutually exclusive with `LM_ENABLED_TOOLS`. |
| `LM_MCP_CATEGORIES` | No | - | Comma-separated category names to include: `read`, `write`, `delete`, `export`, `import`, `session`, `workflow`. Composes by intersection with `LM_ENABLED_TOOLS`/`LM_DISABLED_TOOLS` -- only narrows, never expands. Useful for clients with tool-count limits (e.g., Cursor's 40-tool cap). |
| `LM_HEALTH_CHECK_CONNECTIVITY` | No | `false` | Include LM API ping in health checks |
| `LM_SESSION_PERSIST_PATH` | No | - | File path for persistent session variables (survives restarts) |
| `LM_ANALYSIS_TTL_MINUTES` | No | `60` | TTL for scheduled analysis results (1-1440 minutes) |
| `AWX_URL` | No | - | Ansible Automation Platform controller URL (e.g., `https://aap.example.com`) |
| `AWX_TOKEN` | No | - | AAP personal access token |
| `AWX_VERIFY_SSL` | No | `true` | Verify SSL certificates for AAP connections |
| `AWX_TIMEOUT` | No | `30` | Request timeout in seconds for AAP API calls |
| `AWX_MAX_RETRIES` | No | `3` | Max retries for failed AAP API requests |
| `WATSONX_API_KEY` | No | - | IBM Cloud API key for watsonx.ai (enables Granite TTM + NL summaries) |
| `WATSONX_URL` | No | `https://us-south.ml.cloud.ibm.com` | IBM watsonx.ai endpoint URL |
| `WATSONX_PROJECT_ID` | No | - | IBM watsonx.ai project ID |
| `WATSONX_TIMEOUT` | No | `60` | Request timeout in seconds for watsonx.ai API calls |
| `TF_WORKSPACE_DIR` | No | - | Root directory for Terraform workspaces (enables Terraform tools) |
| `TF_TERRAFORM_BINARY` | No | `terraform` | Path to the terraform binary |
| `TF_TIMEOUT` | No | `300` | Terraform command timeout in seconds |
| `TF_AUTO_APPROVE_ENABLED` | No | `false` | Enable terraform apply/destroy operations |
| `HF_TTM_MODEL` | No | `ibm-granite/granite-timeseries-ttm-r2` | HuggingFace TTM model name or path |
| `HF_LLM_MODEL` | No | `ibm-granite/granite-3.3-2b-instruct` | HuggingFace LLM model name or path |
| `HF_DEVICE` | No | `auto` | Torch device for inference (cpu, cuda, mps, auto) |
| `HF_CACHE_DIR` | No | - | HuggingFace model cache directory |

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

### Claude Code

```bash
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=your-bearer-token \
  -e LM_ENABLE_WRITE_OPERATIONS=true \
  -- uvx --from lm-mcp lm-mcp-server
```

> **Note:** Remove `-e LM_ENABLE_WRITE_OPERATIONS=true` if you want read-only access.
>
> **IBM watsonx.ai:** To enable Granite TTM forecasting and NL summaries, add `-e WATSONX_API_KEY=... -e WATSONX_URL=... -e WATSONX_PROJECT_ID=...` and change `--from lm-mcp` to `--from "lm-mcp[ibm]"`.

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

**Cursor's 40-tool cap (recommended for v3.6.0+):** Cursor only loads the first 40 MCP tools — the remaining ~225 are invisible to the agent. Use `LM_MCP_CATEGORIES` to fit a curated subset under the cap. The `workflow` category alone (`triage`, `diagnose`, `health_check`, `portal_overview`, `capacity_plan`, scoring/correlation tools, plus `update_logicmodule`) is roughly 21 tools and covers the 80% case:

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uvx",
      "args": ["--from", "lm-mcp", "lm-mcp-server"],
      "env": {
        "LM_PORTAL": "yourcompany.logicmonitor.com",
        "LM_BEARER_TOKEN": "your-bearer-token",
        "LM_MCP_CATEGORIES": "workflow"
      }
    }
  }
}
```

For surgical control, combine with `LM_ENABLED_TOOLS`:

```json
"env": {
  "LM_PORTAL": "yourcompany.logicmonitor.com",
  "LM_BEARER_TOKEN": "your-bearer-token",
  "LM_ENABLED_TOOLS": "triage,diagnose,health_check,portal_overview,get_alerts,get_devices,get_alert_details,acknowledge_alert,search_tools",
  "LM_MCP_CATEGORIES": "read,workflow"
}
```

The two filters compose by intersection: `LM_MCP_CATEGORIES` only narrows further, never expands. Default behavior (env var unset) returns all 272 tools — backwards compatible.

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
| `get_alerts` | List alerts with optional severity/status/group/device filters | No |
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
| `update_device_group` | Update a device group (name, properties, AppliesTo, alerting) | Yes |
| `delete_device_group` | Delete a device group | Yes |

### Metrics Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_device_datasources` | List DataSources applied to a device | No |
| `get_device_instances` | List instances for a DataSource on a device | No |
| `get_device_data` | Get metric data for a specific instance | No |
| `get_graph_data` | Get graph data for visualization | No |

### APM Trace Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_trace_services` | List APM trace services (deviceType:6) | No |
| `get_trace_service` | Get detailed APM service information | No |
| `get_trace_service_alerts` | Get alerts for an APM service | No |
| `get_trace_service_datasources` | List datasources applied to an APM service | No |
| `get_trace_operations` | List operations (endpoints/routes) for an APM service | No |
| `get_trace_service_metrics` | Get service-level RED metrics (Duration, ErrorOperationCount, OperationCount) | No |
| `get_trace_operation_metrics` | Get per-operation RED metrics | No |
| `get_trace_service_properties` | Get APM service properties (OTel attributes, metadata) | No |

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
| `create_dashboard_group` | Create a dashboard group | Yes |
| `update_dashboard_group` | Update a dashboard group | Yes |
| `delete_dashboard_group` | Delete a dashboard group | Yes |

### SDT Tools

| Tool | Description | Write |
|------|-------------|-------|
| `list_sdts` | List Scheduled Downtime entries | No |
| `get_active_sdts` | Get currently active SDTs | No |
| `get_upcoming_sdts` | Get SDTs scheduled within a time window | No |
| `create_sdt` | Create a new SDT for a device or group | Yes |
| `update_sdt` | Update an existing SDT (fetch-modify-PUT) | Yes |
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
| `create_collector_group` | Create a collector group | Yes |
| `update_collector_group` | Update a collector group | Yes |
| `delete_collector_group` | Delete a collector group (blocks if collectors assigned) | Yes |

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
| `create_datasource` | Create DataSource via REST API format (supports overwrite) | Yes |
| `update_datasource` | Update existing DataSource definition | Yes |
| `delete_datasource` | Delete a DataSource definition | Yes |

### LogicModule Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_configsources` | List ConfigSources | No |
| `get_configsource` | Get ConfigSource details | No |
| `get_configsource_update_reasons` | Get ConfigSource change audit trail | No |
| `get_device_config` | List config versions for a device instance | No |
| `get_device_config_version` | Get config content with diffs and alerts | No |
| `collect_device_config` | Trigger on-demand config collection | Yes |
| `delete_configsource` | Delete a ConfigSource definition | Yes |
| `export_configsource` | Export ConfigSource as JSON | No |
| `import_configsource` | Import ConfigSource from JSON | Yes |
| `get_eventsources` | List EventSources | No |
| `get_eventsource` | Get EventSource details | No |
| `export_eventsource` | Export EventSource as JSON | No |
| `import_eventsource` | Import EventSource from JSON | Yes |
| `delete_eventsource` | Delete an EventSource definition | Yes |
| `get_propertysources` | List PropertySources | No |
| `get_propertysource` | Get PropertySource details | No |
| `create_propertysource` | Create PropertySource via REST API | Yes |
| `export_propertysource` | Export PropertySource as JSON | No |
| `import_propertysource` | Import PropertySource from JSON | Yes |
| `delete_propertysource` | Delete a PropertySource definition | Yes |
| `get_topologysources` | List TopologySources | No |
| `get_topologysource` | Get TopologySource details | No |
| `import_topologysource` | Import TopologySource from JSON | Yes |
| `delete_topologysource` | Delete a TopologySource definition | Yes |
| `get_logsources` | List LogSources | No |
| `get_logsource` | Get LogSource details | No |
| `get_device_logsources` | Get LogSources applied to a device | No |
| `export_logsource` | Export LogSource as JSON | No |
| `import_logsource` | Import LogSource from JSON | Yes |
| `delete_logsource` | Delete a LogSource definition | Yes |
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
| `update_ops_note` | Update an existing ops note | Yes |
| `delete_ops_note` | Delete an ops note | Yes |

### User & Access Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_users` | List users | No |
| `get_user` | Get detailed user information | No |
| `create_user` | Create a new user | Yes |
| `update_user` | Update an existing user | Yes |
| `delete_user` | Delete a user | Yes |
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

### Session Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_session_context` | Get current session state (last results, variables, history) | No |
| `set_session_variable` | Store a named variable in the session | No |
| `get_session_variable` | Retrieve a session variable | No |
| `delete_session_variable` | Delete a session variable | No |
| `clear_session_context` | Reset all session state | No |
| `list_session_history` | List recent tool call history | No |

### Correlation & Analysis Tools

| Tool | Description | Write |
|------|-------------|-------|
| `correlate_alerts` | Cluster related alerts by device, datasource, and temporal proximity | No |
| `get_alert_statistics` | Aggregated alert counts by severity, top devices/datasources, time buckets | No |
| `get_metric_anomalies` | Multi-method anomaly detection (z-score/IQR/MAD/auto) on metric datapoints | No |

### Baseline Tools

| Tool | Description | Write |
|------|-------------|-------|
| `save_baseline` | Save a metric baseline snapshot to session for later comparison | No |
| `compare_to_baseline` | Compare current metrics against a saved baseline | No |

### ML/Statistical Analysis Tools

| Tool | Description | Write |
|------|-------------|-------|
| `forecast_metric` | Multi-method forecasting (linear/Holt-Winters/auto) with confidence intervals | No |
| `correlate_metrics` | Pearson correlation matrix across multiple metric series (max 10) | No |
| `detect_change_points` | CUSUM-based regime shift detection with configurable sensitivity | No |
| `score_alert_noise` | Shannon entropy + flap detection to score alert noise (0-100) | No |
| `detect_seasonality` | Autocorrelation-based periodicity detection at standard intervals | No |
| `calculate_availability` | SLA-style uptime % from alert history with MTTR and incident counts | No |
| `analyze_blast_radius` | Topology-based downstream impact scoring for device failures | No |
| `correlate_changes` | Cross-reference alert spikes with audit/change logs | No |
| `classify_trend` | Categorize metric behavior: stable, increasing, decreasing, cyclic, volatile | No |
| `score_device_health` | Composite health score (0-100) from multi-metric z-score analysis | No |

### Ansible Automation Platform Tools

These tools are only available when `AWX_URL` and `AWX_TOKEN` are configured.

| Tool | Description | Write |
|------|-------------|-------|
| `test_awx_connection` | Test connectivity to Ansible Automation Platform controller | No |
| `get_job_templates` | List job templates with optional name/project filters | No |
| `get_job_template` | Get details of a specific job template | No |
| `launch_job` | Launch a job template with extra variables, host limits, and check mode | Yes |
| `get_job_status` | Get the status of a running or completed job | No |
| `get_job_output` | Get the stdout output of a job | No |
| `cancel_job` | Cancel a running job | Yes |
| `relaunch_job` | Relaunch a previously run job with optional variable overrides | Yes |
| `get_inventories` | List inventories with optional name filter | No |
| `get_inventory_hosts` | List hosts in a specific inventory | No |
| `launch_workflow` | Launch a workflow job template | Yes |
| `get_workflow_status` | Get the status of a workflow job | No |
| `get_workflow_templates` | List workflow job templates | No |
| `get_projects` | List projects from Ansible Automation Platform | No |
| `get_credentials` | List credentials (secrets not exposed) | No |
| `get_organizations` | List organizations from Ansible Automation Platform | No |
| `get_job_events` | Get events from a specific job run | No |
| `get_hosts` | List hosts with optional name/inventory filters | No |

### Remediation Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_diagnosticsources` | List diagnostic sources from Exchange Toolbox | No |
| `get_diagnosticsource` | Get diagnostic source details | No |
| `get_remediationsources` | List remediation sources from Exchange Toolbox | No |
| `get_remediationsource` | Get remediation source details | No |
| `execute_remediation` | Execute a remediation source on a device with safety checks | Yes |
| `get_remediation_status` | Get current status of a remediation source on a device | No |
| `get_remediation_history` | Get past remediation executions from audit logs | No |

### Composite Workflow Tools

| Tool | Description | Write |
|------|-------------|-------|
| `triage` | Multi-step alert triage: correlation, noise scoring, blast radius, change correlation | No |
| `health_check` | Device health: score, anomalies, alerts, availability, monitoring coverage | No |
| `capacity_plan` | Capacity planning: forecasting, trends, seasonality per datasource | No |
| `portal_overview` | Portal snapshot: alert stats, collectors, SDTs, clusters, down devices | No |
| `diagnose` | Alert diagnosis: details, device context, correlation, blast radius, root cause | No |
| `search_tools` | Keyword search across all tools by name and description | No |

### Error Budget Tool

| Tool | Description | Write |
|------|-------------|-------|
| `calculate_error_budget` | SLO error budget tracking with burn rate and projected exhaustion | No |

#### ML Tool Usage Guide

These tools use pure-Python statistical methods (no external ML libraries). They all operate on data fetched from the LM API at query time. Most metric-based tools share the same core parameters: `device_id`, `device_datasource_id`, `instance_id` (find these using `get_device_datasources` and `get_device_instances`).

**Capacity forecasting** — predict when a metric will breach a threshold:
```
"Forecast when memory usage on device 150098 will exceed 90%"
```
Uses `forecast_metric` with `threshold=90`. Supports `method` parameter: `"auto"` (default, selects based on data), `"linear"` (regression), or `"holt_winters"` (seasonal). Returns days until breach, trend direction, confidence interval, and method used. Use `hours_back=168` (1 week) for meaningful regression, or `hours_back=24` if the device has limited history.

**Metric correlation** — find relationships between metrics across devices:
```
"Correlate CPU usage on server A with memory usage on server B over the last 24 hours"
```
Uses `correlate_metrics` with a `sources` array. Each source requires `device_id`, `device_datasource_id`, `instance_id`, and `datapoint` name. Returns an NxN Pearson correlation matrix and highlights strong correlations (|r| > 0.7). Maximum 10 sources per call.

**Change point detection** — find when metric behavior shifted:
```
"Detect any regime shifts in CPU metrics on device 150098 in the last 24 hours"
```
Uses `detect_change_points` with CUSUM algorithm. The `sensitivity` parameter (default 1.0) controls detection threshold — lower values detect smaller shifts. Returns timestamps and direction of each detected change.

**Alert noise scoring** — identify tuning opportunities:
```
"Score the alert noise across all devices over the last 24 hours"
```
Uses `score_alert_noise`. Returns a 0-100 noise score combining Shannon entropy, flap detection (alerts that clear and re-fire within 30 minutes), and repeat ratio. Includes top noisy devices/datasources and tuning recommendations.

**Device health scoring** — aggregate health into a single number:
```
"Give me a health score for the stress-demo pod"
```
Uses `score_device_health`. Computes z-scores for each datapoint's latest value against its historical window, then produces a weighted composite score (0-100). Status: healthy (80+), degraded (50-79), critical (<50). Use the `weights` parameter to emphasize specific datapoints.

**Availability calculation** — SLA reporting from alert data:
```
"Calculate 30-day availability across all devices at error severity or above"
```
Uses `calculate_availability` with `hours_back=720` and `severity_threshold="error"`. Merges overlapping alert windows and returns availability %, MTTR, incident count, longest incident, and per-device breakdown.

## MCP Resources

The server exposes 26 resources for API reference:

### Schema Resources
| URI | Description |
|-----|-------------|
| `lm://schema/alerts` | Alert object fields, types, and descriptions |
| `lm://schema/devices` | Device object fields and types |
| `lm://schema/sdts` | SDT (Scheduled Downtime) object fields |
| `lm://schema/dashboards` | Dashboard object fields |
| `lm://schema/collectors` | Collector object fields |
| `lm://schema/escalations` | Escalation chain object fields |
| `lm://schema/reports` | Report object fields |
| `lm://schema/websites` | Website check object fields |
| `lm://schema/datasources` | DataSource definition fields |
| `lm://schema/users` | User object fields |
| `lm://schema/audit` | Audit log entry fields |

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

### Guide Resources
| URI | Description |
|-----|-------------|
| `lm://guide/tool-categories` | All 220 tools organized by domain category |
| `lm://guide/examples` | Common filter patterns and query examples |
| `lm://guide/mcp-orchestration` | Patterns for combining LogicMonitor with other MCP servers |
| `lm://guide/best-practices` | Scenario-based best practices with recommendations and anti-patterns |
| `lm://guide/example-responses` | Example output for key tools to help understand response formats |

## MCP Prompts

Pre-built workflow templates for common tasks:

| Prompt | Description | Arguments |
|--------|-------------|-----------|
| `incident_triage` | Analyze active alerts, identify patterns, suggest root cause | `severity`, `time_window_hours` |
| `capacity_review` | Review resource utilization and identify capacity concerns | `group_id`, `threshold_percent` |
| `health_check` | Generate environment health summary with key metrics | `include_collectors` |
| `alert_summary` | Generate alert digest grouped by severity or resource | `group_by`, `hours_back` |
| `sdt_planning` | Plan scheduled downtime for maintenance windows | `device_ids`, `group_id` |
| `cost_optimization` | Analyze cloud costs, find savings opportunities | `provider`, `threshold_percent` |
| `audit_review` | Review recent changes, logins, and security events | `hours_back`, `username` |
| `alert_correlation` | Correlate alerts across devices to find common root causes | `severity`, `hours_back`, `device_id`, `group_id` |
| `collector_health` | Assess collector load balancing, versions, and failover readiness | `group_id` |
| `troubleshoot_device` | Guided troubleshooting for a specific device | `device_id` |
| `top_talkers` | Identify noisiest devices and datasources generating the most alerts | `hours_back`, `limit`, `group_by` |
| `rca_workflow` | Guided root cause analysis combining alerts, topology, and change history | `device_id`, `alert_id`, `hours_back` |
| `capacity_forecast` | Forecast capacity trends and predict threshold breaches | `device_id`, `group_id`, `datasource`, `hours_back`, `threshold` |
| `remediate_workflow` | Diagnose a LogicMonitor alert and remediate via Ansible Automation Platform | `alert_id`, `device_id` |
| `remediation` | Execute a LogicMonitor remediation source with pre-execution safety checks | `host_id`, `remediation_source_id` |

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
- "Show me the running config for device 42"
- "What changed in the last config collection for this switch?"
- "Trigger a config collection on device 100"

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

### Composite Workflows
- "Triage all critical alerts from the last 4 hours"
- "Run a health check on device 123"
- "Do a capacity plan for the database server over the last week"
- "Give me a portal overview for shift handoff"
- "Diagnose alert LMA12345"
- "Search for tools related to dashboards"

### ML Analysis & Forecasting
- "Forecast when memory on device 123 will hit 90%"
- "Score the alert noise level across all devices"
- "Classify the trend for CPU metrics on device 456"
- "Detect any change points in network throughput over the last 24 hours"
- "Check if there's a seasonal pattern in CPU usage over the past week"
- "Calculate 30-day availability for the Production group"
- "What's the blast radius if device 789 goes down?"
- "Correlate recent config changes with alert spikes"
- "Give me a health score for device 123"
- "Are CPU and memory correlated on my web servers?"
- "Calculate error budget for the Production group with a 99.9% SLO"

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
├── analysis.py           # Scheduled analysis workflows and store
├── awx_config.py         # AAP connection configuration
├── config.py             # Environment-based configuration
├── exceptions.py         # Exception hierarchy
├── health.py             # Health check endpoints
├── logging.py            # Structured logging
├── server.py             # MCP server entry point
├── session.py            # Session context with optional persistence
├── registry.py           # Tool definitions and handlers (TOOLS + AWX_TOOLS)
├── validation.py         # Field validation with suggestions
├── auth/
│   ├── __init__.py       # Auth provider factory
│   ├── bearer.py         # Bearer token auth
│   └── lmv1.py           # LMv1 HMAC auth
├── client/
│   ├── __init__.py       # Client exports
│   ├── api.py            # Async HTTP client for LogicMonitor API
│   └── awx.py            # Async HTTP client for AAP controller API
├── completions/
│   └── registry.py       # Auto-complete definitions
├── prompts/
│   ├── registry.py       # Prompt definitions
│   └── templates.py      # Workflow template content
├── resources/
│   ├── registry.py       # Resource definitions
│   ├── schemas.py        # Schema content
│   ├── enums.py          # Enum content
│   ├── filters.py        # Filter content
│   ├── guides.py         # Tool categories, query examples, orchestration guide
│   ├── best_practices.py # Scenario-based best practices and anti-patterns
│   └── examples.py       # Example responses for key tools
├── transport/
│   ├── __init__.py       # Transport abstraction
│   └── http.py           # HTTP/SSE transport with analysis endpoints
└── tools/
    ├── __init__.py       # Tool utilities
    ├── alerts.py         # Alert management
    ├── alert_rules.py    # Alert rule CRUD
    ├── ansible.py        # Ansible Automation Platform tool handlers
    ├── baselines.py      # Metric baseline save/compare
    ├── collectors.py     # Collector tools
    ├── correlation.py    # Alert correlation, anomaly detection, metric correlation
    ├── cost.py           # Cost optimization
    ├── dashboards.py     # Dashboard CRUD
    ├── devices.py        # Device CRUD
    ├── escalations.py    # Escalation/recipient CRUD
    ├── event_correlation.py  # Change-alert correlation
    ├── forecasting.py    # Forecast, trend, seasonality, change points
    ├── imports.py        # LogicModule import
    ├── ingestion.py      # Log/metric ingestion
    ├── metrics.py        # Metrics and data
    ├── scoring.py        # Alert noise, availability, device health
    ├── sdts.py           # SDT management
    ├── session.py        # Session management tools
    ├── stats_helpers.py  # Shared statistical math utilities (incl. Holt-Winters, IQR, MAD)
    ├── topology_analysis.py  # Blast radius analysis
    ├── websites.py       # Website CRUD
    ├── workflows.py      # Composite workflow tools (triage, health_check, etc.)
    ├── metric_presets.py # Metric-type presets for auto-configuration
    └── ...               # Additional tool modules

examples/playbooks/
├── lm-remediate-disk-cleanup.yml
├── lm-remediate-service-restart.yml
├── lm-remediate-log-rotate.yml
└── lm-remediate-memory-cache-clear.yml

deploy/
├── Dockerfile            # Production Docker image
├── docker-compose.yml    # Full stack deployment
├── Caddyfile             # TLS proxy configuration
└── .env.example          # Environment template
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
