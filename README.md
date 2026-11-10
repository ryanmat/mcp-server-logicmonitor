# LogicMonitor MCP Server

[![PyPI version](https://img.shields.io/pypi/v/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<!-- mcp-name: io.github.ryanmat/logicmonitor -->

Model Context Protocol (MCP) server that gives AI assistants structured access to the LogicMonitor REST API v3 through 236 tools, 3 workflow prompts, and 25 resources.

## Overview

The server runs as a local subprocess of your MCP client and calls your portal with your API token. It works with any MCP client that launches a stdio server, including Claude Desktop, Claude Code, Cursor, Continue, and Cline.

Until you set `LM_ENABLE_WRITE_OPERATIONS=true`, the server does not list the tools that change your portal. Composite tools such as `triage`, `diagnose`, `health_check`, `portal_overview`, `capacity_plan`, and `detect_site_outage` answer common investigations in one call, and `search_tools` finds the right tool when your client cannot load them all.

The 236 counts every tool the server can advertise; four of them appear only in multi-portal mode; see [Integrations](#integrations).

## What's new in v4.3.0

A hardening release: mostly fixes to HTTP exposure, Terraform gating, and analytics that returned wrong or partial answers without saying so.

Check these before you upgrade:

- `LM_TRANSPORT=http` with no `LM_HTTP_AUTH_TOKEN` refuses to start on the default bind, and HTTP routes check `Host` and `Content-Type`.
- `terraform_init` and `terraform_plan` need writes enabled, the `terraform` subprocess no longer inherits cloud credentials, and `backend_config` is an object.
- `get_topology_map` no longer takes `device_group_id`.
- `get_collector_health` reads each collector's `isDown` field and no longer returns `active_collector_down_alerts`, so `detect_site_outage` verdicts change where a collector is down.
- `calculate_availability` and `score_alert_noise` read cleared alerts, so availability falls and flap counts rise where cleared incidents exist.

The [CHANGELOG](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/CHANGELOG.md) has every change and what to do about it.

<details>
<summary>Earlier releases</summary>

- v4.2.1: LMv1 portals authenticate again, tool errors reach the client with `isError: true`, every tool is callable per its own schema, and the container installs from `uv.lock`.
- v4.2.0: Multi-portal mode serves many customer portals from one server, with credentials in an age-encrypted vault.
- v4.1.0: Native OTLP metrics tools, for discovery and PromQL range queries.
- v4.0.0: Tools that called nonexistent API paths are gone, the cost and Service Insight tools move to working APIs, and the Automated Diagnostics and Remediation surface arrives.

</details>

## Setup

You need [uv](https://docs.astral.sh/uv/) for `uvx`, and a LogicMonitor API token.

To connect Claude Code:

1. In your portal, go to **Settings** > **Users and Roles** > **API Tokens**.
2. Create an API-only user or add a token to an existing user, then copy the bearer token.
3. Add the server:

   ```bash
   claude mcp add logicmonitor \
     -e LM_PORTAL=yourcompany.logicmonitor.com \
     -e LM_BEARER_TOKEN=<your-bearer-token> \
     -- uvx --from lm-mcp lm-mcp-server
   ```

4. Run `claude mcp list`. The output lists `logicmonitor` as connected.
5. Ask your assistant to "List the first 5 devices in LogicMonitor".

Cursor, Claude Desktop, Cline, and Gemini CLI run the same server with the same block:

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

[documentation/client-setup.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/documentation/client-setup.md) has each client's config file location and exact steps, including OpenAI Codex and GitHub Copilot, whose formats differ. Cursor loads only the first 40 MCP tools, and that page shows how to fit a curated set under the cap with `LM_MCP_CATEGORIES`.

### Other install methods

```bash
# pip
pip install lm-mcp

# From source
git clone https://github.com/ryanmat/mcp-server-logicmonitor.git
cd mcp-server-logicmonitor
uv sync
```

A `uv tool install` does not update itself: run `uv tool upgrade lm-mcp`, then restart your MCP client.

## Usage

Ask your assistant in natural language:

- "Show me all critical alerts from the last hour"
- "Acknowledge alert LMA12345 with note 'Investigating disk issue'"
- "What datasources are applied to device 123, and get CPU metrics for the last hour"
- "Create a dashboard called 'API Health' and add a graph widget"
- "Create a 2-hour maintenance window (SDT) for device 123"
- "Triage all critical alerts from the last 4 hours"
- "Run a health check on device 123, then give me a portal overview for shift handoff"
- "Forecast when memory on device 123 will hit 90%"
- "What's the blast radius if device 789 goes down?"
- "What diagnostics ran on device 123 today, and what did the scripts output?"

The server also takes LogicMonitor filter syntax directly, for example "Get devices where filter is 'displayName~"prod",hostStatus:"normal"'". String values, `hostStatus` words included, are quoted.

### Find a tool

- `search_tools`: keyword search by name and description over the tools your settings list, so with writes off it names no write tool; an optional `category` narrows it to one group
- the `lm://guide/tool-categories` resource: all 236 tools grouped by domain
- [documentation/tools.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/documentation/tools.md): every tool, its parameters, and its read/write classification, generated from the tool registry

### What the tools cover

| Area | Tools |
|------|-------|
| Alerts | Query, acknowledge, bulk acknowledge, add notes, and full CRUD for alert rules |
| Devices | Full CRUD for devices and groups, properties, and manual datasource instances |
| Metrics | Datasources, instances, metric data, graphs, and native OTLP metrics (preview) through PromQL range queries |
| Dashboards | Full CRUD for dashboards, widgets, and groups |
| SDT | Create, list, bulk create, and bulk delete scheduled downtime |
| Collectors | Collectors and collector groups |
| Websites | Full CRUD for synthetic checks and website groups |
| Reports | List, view, run, and schedule reports |
| Escalations | Full CRUD for escalation chains and recipient groups |
| Users and audit | Users, roles, access groups, API tokens, audit logs, ops notes, login and change audits |
| LogicModules | Query, create, update, delete, and import data, config, event, property, topology, log, diagnostic, and remediation sources, and read any of them as its full REST object with `raw=true` (remediation sources have no import), plus Config Archive retrieval, diffs, and on-demand collection |
| Diagnostics and remediation | Assigned-source resolution, structured execution results with script output, manual execution, action chains and rules |
| APM traces | Service discovery, per-operation RED metrics, service alerts, and OTel properties |
| Network | Neighbors, interfaces, flows, connections, top talkers, link flaps, and outage detection. See [networking intelligence](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/documentation/networking-intelligence.md) |
| Cost | Cost recommendations, recommendation categories, and idle resources (LM Envision) |
| Ingestion | Push logs and metrics through LMv1 authentication |
| Batch jobs | List batch jobs and the BatchJob datasources on a device; per-run output comes from `get_device_data` |

`get_network_flows` and `get_top_talkers` read `/netflow/flows`, which answered 404 on the only portal tested, one with no NetFlow-enabled device. Treat both as unverified until you have tried them on a portal with NetFlow data.

`update_logicmodule(type, id, changes, mode)` is the safe way to change a LogicModule: it reads the full definition, deep-merges your `changes`, validates required fields, and returns a dry-run diff by default, so a partial change cannot blank a script.

### Analysis tools

These run server-side in pure Python, so an assistant gets the result in one call.

- Alert correlation clusters, statistics by severity and device, noise scoring with flap detection, and burst detection
- `analyze_metric` reads a series once for its summary, trend, seasonality, change points, anomalies (z-score, IQR, MAD) and linear and Holt-Winters forecast to a threshold, and with one more read compares it with an earlier window; metric correlation across series
- Availability with MTTR from active and cleared alerts, and SLO error budgets
- Topology-based blast radius, and change correlation against audit logs

Composite tools (`triage`, `diagnose`, `health_check`, `capacity_plan`, `portal_overview`) combine these. Each takes `detail_level` (`summary` or `full`) and returns partial results when a sub-tool fails.

### Claude Code skills

Slash-command runbooks that ship with the repo. Clone it and invoke `/lm-triage` in Claude Code.

| Skill | Command | Description |
|-------|---------|-------------|
| Alert Triage | `/lm-triage` | Investigate active alerts, score noise, correlate clusters, assess blast radius, take action |
| Device Health | `/lm-health <device>` | Health check: metrics, anomalies, availability, topology |
| Portal Overview | `/lm-portal` | Portal-wide snapshot for shift handoff: alerts, collectors, SDTs, down devices |
| Capacity Planning | `/lm-capacity <device>` | Trend analysis, seasonality detection, breach forecasting, right-sizing |
| APM Investigation | `/lm-apm [service]` | Service discovery, operation-level RED metrics, alert correlation |

## Integrations

`terraform_generate` needs no settings. Multi-portal mode is optional; add its variables to the `env` block or `claude mcp add` command from [Setup](#setup).

### Terraform

`terraform_generate` exports an existing LM portal resource as HCL for the `logicmonitor/logicmonitor` provider. It is part of the core tool set and needs no settings of its own.

### Multi-portal mode

Serves many customer portals from a single server entry. Set `LM_MULTI_PORTAL=true` and point the server at a credential vault; the full tool set loads once, and four tools (`get_portals`, `use_portal`, `get_current_portal`, `run_portal_reload`) switch the active portal at runtime. Credentials come from an age-encrypted vault (or a plaintext JSON file for testing), and each portal is read-only unless its record marks it writable. The mode is stdio-only. See [MULTIPORTAL.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/MULTIPORTAL.md).

## Deployment

Stdio is the default transport and the one MCP clients use. It needs no deployment: your client launches the server.

### HTTP transport

The HTTP transport serves health, readiness and info routes only; it exposes no tool and no MCP endpoint, so `/mcp` and `/api/v1/*` have no route (`404` once past the bearer check). Use stdio for MCP clients.

```bash
cd deploy
cp .env.example .env
# Edit .env with your credentials, including LM_HTTP_AUTH_TOKEN (required)

# Run with docker-compose
docker compose up -d

# With TLS via Caddy
docker compose --profile tls up -d
```

The server exposes health endpoints for container orchestration:
- `GET /health` - Detailed health check with all component statuses (adds the LM API connectivity check when enabled, for callers presenting `LM_HTTP_AUTH_TOKEN` or when no token is set)
- `GET /healthz` - Liveness probe (200 OK or 503)
- `GET /readyz` - Readiness probe (local checks only; never calls the LM API)

Every route except `/healthz` and `/readyz`, `/health` included, answers only the `Host` names the server expects (the loopback names, a non-wildcard `LM_HTTP_HOST`, and `LM_HTTP_ALLOWED_HOSTS`) and refuses others with `400`; those two probes accept any `Host` so probes by pod IP keep working. The compose file requires `LM_HTTP_AUTH_TOKEN` for every profile and passes `DOMAIN` through as an allowed host for the Caddy `tls` profile.

See [SECURITY.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/SECURITY.md) for the exposure model.

### Kubernetes

`deploy/k8s/deployment.yaml` is a vendor-neutral Deployment and Service running
the published `ghcr.io` image. It works on AKS, EKS, GKE, OpenShift, or vanilla
Kubernetes, reads credentials from a Kubernetes secret you create, and wires the
liveness and readiness probes to the endpoints above. Apply it with
`kubectl apply -f deploy/k8s/deployment.yaml` after creating the secret
documented at the top of the file.

## Configuration

Set these as environment variables, through your client's `env` block or `-e` flags. The server does not read a `.env` file itself; to use one when you run it from a clone, run `uv run --env-file .env lm-mcp-server`.

### Authentication

Set `LM_BEARER_TOKEN` for most operations. Set `LM_ACCESS_ID` and `LM_ACCESS_KEY` as well for `ingest_logs` and `push_metrics`, which require LMv1 authentication.

To get LMv1 credentials:

1. Go to **Settings** > **Users and Roles** > **Users**.
2. Select a user, then open the **API Tokens** tab.
3. Create or view the Access ID and Access Key.

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LM_PORTAL` | Yes | - | LogicMonitor portal hostname (e.g., `company.logicmonitor.com`) |
| `LM_BEARER_TOKEN` | Yes* | - | API Bearer token (min 10 characters) |
| `LM_ACCESS_ID` | No | - | LMv1 API access ID (for ingestion APIs) |
| `LM_ACCESS_KEY` | No | - | LMv1 API access key (for ingestion APIs) |
| `LM_ENABLE_WRITE_OPERATIONS` | No | `false` | Enable write operations (create, update, delete) |
| `LM_TIMEOUT` | No | `30` | Request timeout in seconds (range: 5-300) |
| `LM_MAX_RETRIES` | No | `3` | Max retries for rate-limited requests, and for server errors on idempotent requests (GET, PUT, DELETE); a POST or PATCH that gets a 5xx is not resent (range: 0-10) |
| `LM_RETRY_AFTER_CAP_SECONDS` | No | `120` | Longest wait between retries. A server's `Retry-After` can lengthen the backoff up to this cap, never shorten it |
| `LM_TRANSPORT` | No | `stdio` | Transport mode: `stdio` (MCP clients) or `http` (see [HTTP transport](#http-transport)) |
| `LM_MULTI_PORTAL` | No | `false` | Serve many customer portals from one server, selected at runtime via `use_portal`. Stdio-only. |
| `LM_VAULT_FILE` | No | - | Path to the age-encrypted portal vault (multi-portal) |
| `LM_AGE_KEY` | No | - | Path to the age identity that decrypts the vault (multi-portal) |
| `LM_PORTALS_FILE` | No | - | Plaintext JSON portal map (multi-portal, testing only; the encrypted vault wins when both are set) |
| `LM_HTTP_HOST` | No | `0.0.0.0` | HTTP server bind address. With `LM_TRANSPORT=http`, an address other than `127.0.0.1`, `::1` or `localhost` needs `LM_HTTP_AUTH_TOKEN` or `LM_HTTP_ALLOW_UNAUTHENTICATED=true`, or the server refuses to start. |
| `LM_HTTP_PORT` | No | `8080` | HTTP server port |
| `LM_HTTP_AUTH_TOKEN` | No | - | Require this bearer token on every path outside `/` and the health endpoints (min 16 chars). Needed to start on a non-loopback `LM_HTTP_HOST`, the default `0.0.0.0` included, unless `LM_HTTP_ALLOW_UNAUTHENTICATED=true`. Health endpoints and `/` stay open for probes. HTTP transport only. |
| `LM_HTTP_ALLOWED_HOSTS` | No | - | Comma-separated `Host` names the server accepts on every route except `/healthz` and `/readyz`, besides `127.0.0.1`, `::1`, `localhost` and a non-wildcard `LM_HTTP_HOST` (for example the public name a reverse proxy forwards). HTTP transport only. |
| `LM_HTTP_ALLOW_UNAUTHENTICATED` | No | `false` | Start on a non-loopback `LM_HTTP_HOST` with no `LM_HTTP_AUTH_TOKEN`, for a listener protected another way (an authenticating proxy, a private network). HTTP transport only. |
| `LM_HTTP_SSL_CERTFILE` | No | - | TLS certificate path. Set with `LM_HTTP_SSL_KEYFILE` to serve HTTPS. HTTP transport only. |
| `LM_HTTP_SSL_KEYFILE` | No | - | TLS private key path. HTTP transport only. |
| `LM_HTTP_SSL_KEYFILE_PASSWORD` | No | - | Password for an encrypted TLS private key. HTTP transport only. |
| `LM_SESSION_HISTORY_SIZE` | No | `50` | Number of tool calls to keep in history |
| `LM_LOG_LEVEL` | No | `warning` | Logging level: `debug`, `info`, `warning`, or `error`. Records go to stderr; write audit lines (`info` for a success, `warning` for a failure) redact argument values under credential-shaped keys such as `password`, `token`, `api_key` and `extra_vars`, LogicMonitor credential properties such as `ssh.pass` and `snmp.community`, and a `property_value` whose `property_name` is one |
| `LM_ENABLED_TOOLS` | No | - | Comma-separated tool names or glob patterns to enable (e.g., `get_*,triage`). Mutually exclusive with `LM_DISABLED_TOOLS`. |
| `LM_DISABLED_TOOLS` | No | - | Comma-separated tool names or glob patterns to disable (e.g., `delete_*`). Mutually exclusive with `LM_ENABLED_TOOLS`. |
| `LM_MCP_CATEGORIES` | No | - | Comma-separated category names to include: `read`, `write`, `delete`, `export`, `import`, `session`, `workflow`. Composes by intersection with `LM_ENABLED_TOOLS`/`LM_DISABLED_TOOLS` -- only narrows, never expands. Useful for clients with tool-count limits (e.g., Cursor's 40-tool cap). |
| `LM_HEALTH_CHECK_CONNECTIVITY` | No | `false` | Include an LM API ping in `/health` for authenticated callers (never in `/readyz`) |

*Either `LM_BEARER_TOKEN` or both `LM_ACCESS_ID` and `LM_ACCESS_KEY` are required.

## MCP resources and prompts

Clients read these through the standard MCP resource and prompt calls.

<details>
<summary>25 reference resources</summary>

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
| `lm://enums/severity` | Alert severity levels: critical(4), error(3), warning(2), info(1) |
| `lm://enums/device-status` | Device status words: normal, dead, dead-collector, unmonitored, disabled |
| `lm://enums/sdt-type` | SDT types: DeviceSDT, DeviceGroupSDT, etc. |
| `lm://enums/alert-cleared` | Alert cleared status: true, false |
| `lm://enums/alert-acked` | Alert acknowledgment status: true, false |
| `lm://enums/collector-build` | Collector build types: EA, GD, MGD |
| `lm://filters/alerts` | Filter fields and operators for alert queries |
| `lm://filters/devices` | Filter fields and operators for device queries |
| `lm://filters/sdts` | Filter fields and operators for SDT queries |
| `lm://syntax/operators` | Filter operators: `:`, `~`, `>`, `<`, `!:`, `!~`, `>:`, `<:` |
| `lm://guide/tool-categories` | All 236 tools organized by domain category |
| `lm://guide/examples` | Common filter patterns and query examples |
| `lm://guide/mcp-orchestration` | Patterns for combining LogicMonitor with other MCP servers |
| `lm://guide/best-practices` | Scenario-based best practices with recommendations and anti-patterns |

</details>

<details>
<summary>3 workflow prompts</summary>

| Prompt | Description | Arguments |
|--------|-------------|-----------|
| `incident_triage` | Analyze active alerts, identify patterns, suggest root cause | `severity`, `time_window_hours` |
| `capacity_review` | Review resource utilization and identify capacity concerns | `group_id`, `threshold_percent` |
| `remediation` | Execute a LogicMonitor remediation source with pre-execution safety checks | `host_id`, `remediation_source_id`, `alert_id` |

</details>

## Troubleshooting

The server logs to stderr. Set `LM_LOG_LEVEL=debug` to add httpx and MCP SDK lines.

### "Failed to connect" in Claude Code

`claude mcp list` shows this when the server is missing environment variables. Claude Code spawns the server as a subprocess with its own environment, so variables in your shell or a `.env` file do not reach it, and the `-e` flags are required:

```bash
# Remove the broken config
claude mcp remove logicmonitor

# Re-add with environment variables
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=<your-bearer-token> \
  -- uvx --from lm-mcp lm-mcp-server
```

### "Write operations are disabled"

Write operations (acknowledge, create SDT, etc.) are disabled by default: the server does not list those tools, and a call to one by name returns this error. Set `LM_ENABLE_WRITE_OPERATIONS=true` in your environment.

### "spawn uvx ENOENT" in Claude Desktop

Claude Desktop cannot find `uvx`. Find its path with `which uvx`, then use the full path:

```json
{
  "command": "/Users/yourname/.local/bin/uvx",
  "args": ["--from", "lm-mcp", "lm-mcp-server"]
}
```

### The server refuses to start with `LM_TRANSPORT=http`

The default bind is `0.0.0.0`, which needs `LM_HTTP_AUTH_TOKEN`. Set the token, bind to `127.0.0.1`, or set `LM_HTTP_ALLOW_UNAUTHENTICATED=true` for a listener protected another way.

### Ingestion API errors

The `ingest_logs` and `push_metrics` tools require LMv1 authentication, and bearer tokens do not work with ingestion APIs. Add `LM_ACCESS_ID` and `LM_ACCESS_KEY` to your configuration.

### Rate limit errors

The server retries rate-limited requests with exponential backoff. If you consistently hit limits, reduce request frequency or contact LogicMonitor support.

### Authentication errors

Verify your bearer token is correct and has appropriate permissions. Manage API tokens in LogicMonitor under **Settings** > **Users and Roles** > **API Tokens**.

## Development

```bash
uv sync --extra http
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
```

[CONTRIBUTING.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/CONTRIBUTING.md) has the workflow, the type-check ratchet, and what to regenerate after a tool change.

### Layout

| Path | Contents |
|------|----------|
| `src/lm_mcp/server.py` | MCP server entry point (`lm-mcp-server`) and tool dispatch |
| `src/lm_mcp/registry.py` | Tool definitions and the handler map |
| `src/lm_mcp/tools/` | Tool handlers, one module per domain |
| `src/lm_mcp/client/` | Async HTTP client for the LogicMonitor API |
| `src/lm_mcp/auth/` | Bearer and LMv1 authentication |
| `src/lm_mcp/transport/` | Stdio and HTTP transports |
| `src/lm_mcp/prompts/`, `resources/` | MCP prompts and reference resources |
| `.claude/skills/` | Claude Code skills |
| `documentation/` | Tool reference (generated), client setup, networking intelligence |
| `deploy/` | Dockerfile, compose file, Caddyfile, Kubernetes manifest |
| `tests/` | pytest suite and contract fixtures |

## License

MIT License. See the [LICENSE](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/LICENSE) file.
