# LogicMonitor MCP Server

[![PyPI version](https://img.shields.io/pypi/v/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<!-- mcp-name: io.github.ryanmat/logicmonitor -->

Model Context Protocol (MCP) server that gives AI assistants structured access to the LogicMonitor REST API v3 through 305 tools, 15 workflow prompts, and 26 resources.

## Overview

The server runs as a local subprocess of your MCP client and calls your portal with your API token. It works with any MCP client that launches a stdio server, including Claude Desktop, Claude Code, Cursor, Continue, and Cline.

Tools are read-only until you set `LM_ENABLE_WRITE_OPERATIONS=true`. Composite tools such as `triage`, `diagnose`, `health_check`, `portal_overview`, `capacity_plan`, and `detect_site_outage` answer common investigations in one call, and `search_tools` finds the right tool when your client cannot load them all.

The 305 counts every tool the server can advertise (277 LM + 18 AAP + 10 Terraform). The AAP and Terraform tools appear only when their settings are present, and four of the LM tools only in multi-portal mode; see [Integrations](#integrations).

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

- `search_tools`: keyword search across every tool by name and description, with an optional `category` filter
- the `lm://guide/tool-categories` resource: all 305 tools grouped by domain
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
| LogicModules | Query, create, update, delete, export, and import data, config, event, property, topology, log, diagnostic, and remediation sources (topology sources have no export, and remediation sources have no import), plus Config Archive retrieval, diffs, and on-demand collection |
| Diagnostics and remediation | Assigned-source resolution, structured execution results with script output, manual execution, action chains and rules |
| APM traces | Service discovery, per-operation RED metrics, service alerts, and OTel properties |
| Network | Neighbors, interfaces, flows, connections, top talkers, link flaps, and outage detection. See [networking intelligence](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/documentation/networking-intelligence.md) |
| Cost | Cost recommendations, recommendation categories, and idle resources (LM Envision) |
| Ingestion | Push logs and metrics through LMv1 authentication |
| Batch jobs | List batch jobs and the BatchJob datasources on a device; per-run output comes from `get_device_data` |

`get_network_flows` and `get_top_talkers` read `/netflow/flows`, which answered 404 on the only portal tested, one with no NetFlow-enabled device. Treat both as unverified until you have tried them on a portal with NetFlow data.

`update_logicmodule(type, id, changes, mode)` is the safe way to change a LogicModule: it exports the full definition, deep-merges your `changes`, validates required fields, and returns a dry-run diff by default, so a partial change cannot blank a script. It does not work on topology sources, which have no export tool.

### Analysis tools

These run server-side in pure Python, so an assistant gets the result in one call.

- Alert correlation clusters, statistics by severity and device, noise scoring with flap detection, and burst detection
- Metric anomaly detection (z-score, IQR, MAD), saved baselines and drift, correlation, change points, trend classification, and seasonality
- Forecasting with linear regression, Holt-Winters, or IBM Granite TTM (optional), with confidence intervals and breach prediction. The response names the method that ran and why it fell back
- Availability with MTTR from active and cleared alerts, SLO error budgets, and device health scoring
- Topology-based blast radius, and change correlation against audit logs

Composite tools (`triage`, `diagnose`, `health_check`, `capacity_plan`, `portal_overview`) combine these. Each takes `detail_level` (`summary` or `full`) and `summarize=true` for a plain-English summary from IBM Granite, and returns partial results when a sub-tool fails.

### Claude Code skills

Slash-command runbooks that ship with the repo. Clone it and invoke `/lm-triage` in Claude Code.

| Skill | Command | Description |
|-------|---------|-------------|
| Alert Triage | `/lm-triage` | Investigate active alerts, score noise, correlate clusters, assess blast radius, take action |
| Device Health | `/lm-health <device>` | Health check: metrics, anomalies, health score, availability, topology |
| Portal Overview | `/lm-portal` | Portal-wide snapshot for shift handoff: alerts, collectors, SDTs, down devices |
| Capacity Planning | `/lm-capacity <device>` | Trend analysis, seasonality detection, breach forecasting, right-sizing |
| APM Investigation | `/lm-apm [service]` | Service discovery, operation-level RED metrics, alert correlation |
| Remediation | `/lm-remediate` | Diagnose alert, find or generate playbook, launch AAP job, verify fix |

## Integrations

Each integration is optional. Add its variables to the `env` block or `claude mcp add` command from [Setup](#setup), and change the package to the extra it names.

### Ansible Automation Platform

18 tools that connect LogicMonitor alerts to remediation playbooks. They appear when `AWX_URL` and `AWX_TOKEN` are set.

They list, inspect, and launch job templates with extra variables and host limits, check status, view output, cancel or relaunch a job, launch workflow templates and monitor multi-step sequences, and browse inventories, projects, and credentials for targeted remediation. Secrets are never exposed.

`launch_job`, `launch_workflow`, `cancel_job`, and `relaunch_job` require `LM_ENABLE_WRITE_OPERATIONS=true`. All `extra_vars` inputs are validated to prevent Jinja2 template injection.

See [Example Playbooks](https://github.com/ryanmat/mcp-server-logicmonitor/tree/main/examples/playbooks) for remediation templates.

### IBM watsonx.ai

IBM Granite models through watsonx.ai. The tools appear when `WATSONX_API_KEY` and `WATSONX_PROJECT_ID` are set, and the package is `lm-mcp[ibm]`:

```bash
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=<your-bearer-token> \
  -e WATSONX_API_KEY=<your-ibm-cloud-api-key> \
  -e WATSONX_URL=https://us-south.ml.cloud.ibm.com \
  -e WATSONX_PROJECT_ID=your-watsonx-project-id \
  -- uvx --from "lm-mcp[ibm]" lm-mcp-server
```

`method="ttm"` on `forecast_metric` gives 96-step Granite TTM predictions that detect seasonality and non-linear patterns. It requires 512+ data points and falls back to statistical methods when data is insufficient. `summarize=true` on `triage`, `diagnose`, `health_check`, `capacity_plan`, and `portal_overview` appends a plain-English Granite summary to the structured output, and `watsonx_summarize` generates a concise summary of any JSON data.

To set up watsonx.ai (the Lite plan is free):

1. Create an IBM Cloud account at [cloud.ibm.com](https://cloud.ibm.com).
2. Provision **watsonx.ai Runtime** from the IBM Cloud catalog.
3. Create a watsonx.ai project and associate the Runtime instance.
4. Generate an IBM Cloud API key at [cloud.ibm.com/iam/apikeys](https://cloud.ibm.com/iam/apikeys).

### HuggingFace local models

Install `lm-mcp[huggingface]` to run TTM forecasting and NL summaries locally when watsonx.ai credentials are not configured. The server tries watsonx.ai first, then HuggingFace, then statistical methods.

The TTM model is `ibm-granite/granite-timeseries-ttm-r2` (512 context, 96 forecast) and the LLM model is `ibm-granite/granite-3.3-2b-instruct` (2B params, runs on CPU). Models load on the first inference call (initial download: ~500MB TTM, ~4GB LLM).

### Terraform

11 tools for Infrastructure as Code with any Terraform provider. `terraform_generate` exports existing LM portal resources as HCL using the `logicmonitor/logicmonitor` provider. The other ten appear when `TF_WORKSPACE_DIR` is set, and they need the `terraform` CLI installed separately.

- `terraform_init` and `terraform_plan` require write permission, since providers and data sources call live APIs, and `terraform_import` and `terraform_write_config` require it too
- `terraform_apply` and `terraform_destroy` are triple-gated: write permission, `TF_AUTO_APPROVE_ENABLED`, and a confirm parameter
- `terraform_validate`, `terraform_state_list`, `terraform_state_show`, and `terraform_output` need no write permission

An agent can author HCL from natural language, operate on existing `.tf` files under `TF_WORKSPACE_DIR`, or export LM resources with `terraform_generate` and import them into state.

The `terraform` subprocess inherits only `PATH`, `HOME`, `TMPDIR`, `TF_*`, the proxy settings (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and their lowercase forms) and the CA settings (`SSL_CERT_FILE`, `SSL_CERT_DIR`) from the server's environment, so server and cloud credentials such as `LM_BEARER_TOKEN` or `AWS_SECRET_ACCESS_KEY` never reach provider or data-source code. The `logicmonitor` provider gets `LM_API_ID`, `LM_API_KEY` and `LM_COMPANY` (and their `TF_VAR_lm_*` forms) from the server's LMv1 configuration. Other providers take credentials as `TF_VAR_*` variables that the HCL passes to them, or from files under `HOME` such as `~/.aws/credentials`. A backend block cannot read variables, so backend credentials come from files under `HOME` or from `terraform_init`'s `backend_config` keys (`profile`, `access_key`, `sas_token` and the like).

`var_file` and a local backend `path` must resolve inside the workspace, symlinks included. `terraform_init`'s `backend_config` takes an object of local, s3 or azurerm backend keys and refuses endpoint and proxy overrides by name. A command that exceeds `TF_TIMEOUT` gets SIGINT and 30 seconds to persist state and release its lock before it is killed; a timed-out `apply` or `destroy` reports that the lock may still be held and state may be incomplete.

### Multi-portal mode

Serves many customer portals from a single server entry. Set `LM_MULTI_PORTAL=true` and point the server at a credential vault; the full tool set loads once, and four tools (`list_portals`, `use_portal`, `current_portal`, `reload_portals`) switch the active portal at runtime. Credentials come from an age-encrypted vault (or a plaintext JSON file for testing), and each portal is read-only unless its record marks it writable. The mode is stdio-only, and the ten Terraform workspace tools are unavailable in it. See [MULTIPORTAL.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/MULTIPORTAL.md).

## Deployment

Stdio is the default transport and the one MCP clients use. It needs no deployment: your client launches the server.

### HTTP transport

The HTTP transport serves the `/api/v1` analysis API, for triggering workflows such as alert correlation, RCA, top talkers, and health checks from schedulers and webhooks. It also serves a minimal JSON-RPC route at `/mcp` that answers `tools/list` (names and descriptions, no input schemas), `tools/call`, `resources/list`, and `prompts/list`. `/mcp` has no `initialize`, so standard MCP clients cannot connect to it.

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

POST requests to `/mcp` and `/api/v1/*` must send `Content-Type: application/json`; any other body type gets `415`. Every route except `/healthz` and `/readyz`, `/health` included, answers only the `Host` names the server expects (the loopback names, a non-wildcard `LM_HTTP_HOST`, and `LM_HTTP_ALLOWED_HOSTS`) and refuses others with `400`; those two probes accept any `Host` so probes by pod IP keep working. The compose file requires `LM_HTTP_AUTH_TOKEN` for every profile and passes `DOMAIN` through as an allowed host for the Caddy `tls` profile.

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
| `LM_API_VERSION` | No | `3` | API version |
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
| `LM_CORS_ORIGINS` | No | - | Comma-separated CORS origins (default: none) |
| `LM_HTTP_AUTH_TOKEN` | No | - | Require this bearer token on `/mcp` and `/api/v1/*` (min 16 chars). Needed to start on a non-loopback `LM_HTTP_HOST`, the default `0.0.0.0` included, unless `LM_HTTP_ALLOW_UNAUTHENTICATED=true`. Health endpoints and `/` stay open for probes. HTTP transport only. |
| `LM_HTTP_ALLOWED_HOSTS` | No | - | Comma-separated `Host` names the server accepts on every route except `/healthz` and `/readyz`, besides `127.0.0.1`, `::1`, `localhost` and a non-wildcard `LM_HTTP_HOST` (for example the public name a reverse proxy forwards). HTTP transport only. |
| `LM_HTTP_ALLOW_UNAUTHENTICATED` | No | `false` | Start on a non-loopback `LM_HTTP_HOST` with no `LM_HTTP_AUTH_TOKEN`, for a listener protected another way (an authenticating proxy, a private network). HTTP transport only. |
| `LM_HTTP_SSL_CERTFILE` | No | - | TLS certificate path. Set with `LM_HTTP_SSL_KEYFILE` to serve HTTPS. HTTP transport only. |
| `LM_HTTP_SSL_KEYFILE` | No | - | TLS private key path. HTTP transport only. |
| `LM_HTTP_SSL_KEYFILE_PASSWORD` | No | - | Password for an encrypted TLS private key. HTTP transport only. |
| `LM_SESSION_ENABLED` | No | `true` | Enable session context tracking |
| `LM_SESSION_HISTORY_SIZE` | No | `50` | Number of tool calls to keep in history |
| `LM_LOG_LEVEL` | No | `warning` | Logging level: `debug`, `info`, `warning`, or `error`. Records go to stderr; write audit lines (`info` for a success, `warning` for a failure) redact argument values under credential-shaped keys such as `password`, `token`, `api_key` and `extra_vars`, LogicMonitor credential properties such as `ssh.pass` and `snmp.community`, and a `property_value` whose `property_name` is one |
| `LM_FIELD_VALIDATION` | No | `warn` | Field validation: `off`, `warn`, or `error` |
| `LM_ENABLED_TOOLS` | No | - | Comma-separated tool names or glob patterns to enable (e.g., `get_*,triage`). Mutually exclusive with `LM_DISABLED_TOOLS`. |
| `LM_DISABLED_TOOLS` | No | - | Comma-separated tool names or glob patterns to disable (e.g., `delete_*`). Mutually exclusive with `LM_ENABLED_TOOLS`. |
| `LM_MCP_CATEGORIES` | No | - | Comma-separated category names to include: `read`, `write`, `delete`, `export`, `import`, `session`, `workflow`. Composes by intersection with `LM_ENABLED_TOOLS`/`LM_DISABLED_TOOLS` -- only narrows, never expands. Useful for clients with tool-count limits (e.g., Cursor's 40-tool cap). |
| `LM_HEALTH_CHECK_CONNECTIVITY` | No | `false` | Include an LM API ping in `/health` for authenticated callers (never in `/readyz`) |
| `LM_SESSION_PERSIST_PATH` | No | - | File path for persistent session variables (survives restarts) |
| `LM_ANALYSIS_MAX_CONCURRENCY` | No | `4` | Analysis workflows (`/api/v1/analyze` and the alert webhook) that run at once; later submissions are accepted and wait as `pending`. At least 1. HTTP transport only. |
| `AWX_URL` | No | - | Ansible Automation Platform controller URL (e.g., `https://aap.example.com`) |
| `AWX_TOKEN` | No | - | AAP personal access token |
| `AWX_VERIFY_SSL` | No | `true` | Verify SSL certificates for AAP connections |
| `AWX_TIMEOUT` | No | `30` | Request timeout in seconds for AAP API calls |
| `AWX_MAX_RETRIES` | No | `3` | Max retries for rate-limited AAP requests, and for server errors on idempotent ones; a job launch that gets a 5xx is not resent. A `Retry-After` lengthens the backoff up to 120 seconds |
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

## MCP resources and prompts

Clients read these through the standard MCP resource and prompt calls. Prompt and resource-template arguments also offer auto-complete through MCP completions.

<details>
<summary>26 reference resources</summary>

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
| `lm://guide/tool-categories` | All 305 tools organized by domain category |
| `lm://guide/examples` | Common filter patterns and query examples |
| `lm://guide/mcp-orchestration` | Patterns for combining LogicMonitor with other MCP servers |
| `lm://guide/best-practices` | Scenario-based best practices with recommendations and anti-patterns |
| `lm://guide/example-responses` | Example output for key tools to help understand response formats |

</details>

<details>
<summary>15 workflow prompts</summary>

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

Write operations (acknowledge, create SDT, etc.) are disabled by default. Set `LM_ENABLE_WRITE_OPERATIONS=true` in your environment.

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
| `src/lm_mcp/client/` | Async HTTP clients for the LogicMonitor and AAP APIs |
| `src/lm_mcp/auth/` | Bearer and LMv1 authentication |
| `src/lm_mcp/transport/` | HTTP transport and analysis API |
| `src/lm_mcp/prompts/`, `resources/`, `completions/` | MCP prompts, reference resources, and argument completions |
| `.claude/skills/` | Claude Code skills |
| `documentation/` | Tool reference (generated), client setup, networking intelligence |
| `examples/playbooks/` | Sample AAP remediation playbooks |
| `deploy/` | Dockerfile, compose file, Caddyfile, Kubernetes manifest |
| `tests/` | pytest suite and contract fixtures |

## License

MIT License. See the [LICENSE](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/LICENSE) file.
