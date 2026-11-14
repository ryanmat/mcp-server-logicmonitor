# LogicMonitor MCP Server

[![PyPI version](https://img.shields.io/pypi/v/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/lm-mcp.svg)](https://pypi.org/project/lm-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<!-- mcp-name: io.github.ryanmat/logicmonitor -->

A Model Context Protocol (MCP) server that gives AI assistants the LogicMonitor REST API v3 through 273 tools, 3 workflow prompts and 25 resources.

## Upgrading from 4.x

5.0.0 is a breaking release. Check a setup that worked on 4.3.0 against these before it moves to 5.x. The CHANGELOG has the rest under [Upgrading from 4.3.0](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/CHANGELOG.md#upgrading-from-430).

- 82 of the 306 tool names in 4.3.0 no longer answer: 7 are renamed and 75 removed. The CHANGELOG's table gives each one's 5.0 name or what to call instead.
- A tool that changes the portal is listed only with `LM_ENABLE_WRITE_OPERATIONS=true`. 4.3.0 listed its write tools and refused the call.
- A failed call returns one JSON envelope, `{"error": {"code", "message", ...}}`, in place of the `Error:` and `Suggestion:` lines.
- `uvx --from lm-mcp lm-mcp-server` takes the newest release the first time it runs on a machine and uv's cached one after that, so a setup moves to 5.x when that cache is cleared or refreshed. `uv tool install lm-mcp` stays on its version until `uv tool upgrade lm-mcp`. To hold a setup on 4.3.0, start it with `uvx --from lm-mcp==4.3.0 lm-mcp-server`.

## Overview

Your MCP client starts the server as a subprocess and talks to it over stdio; the server calls your portal with your API token. It can also run as an HTTP service that serves MCP at `/mcp`.

Of the 273 tools, 261 are there with one portal. Multi-portal mode adds four portal tools, and Edwin AI credentials add eight Edwin tools. The server lists a tool that changes the portal only when you set `LM_ENABLE_WRITE_OPERATIONS=true`, and refuses it by name until then, so by default a client sees 150 of them (154 in multi-portal mode, 7 more with Edwin credentials).

Before one of the 36 destructive tools runs, the server asks you to confirm when the client supports MCP elicitation. Where it cannot ask, as over the stateless HTTP transport, the write setting is the only check.

## Setup

You need [uv](https://docs.astral.sh/uv/) for `uvx`, and a LogicMonitor API token: a Bearer token, or an LMv1 access ID and key.

### Claude Code

1. In your portal, go to **Settings** > **Users and Roles** > **API Tokens**.
2. Create an API-only user or add a token to an existing user, then copy the Bearer token.
3. Add the server:

   ```bash
   claude mcp add logicmonitor \
     -e LM_PORTAL=yourcompany.logicmonitor.com \
     -e LM_BEARER_TOKEN=<your-bearer-token> \
     -- uvx --from lm-mcp lm-mcp-server
   ```

4. Run `claude mcp list`. It lists `logicmonitor` as connected.
5. Ask your assistant to "List the first 5 devices in LogicMonitor".

### Other clients

Claude Desktop, Cursor and Gemini CLI read the same block:

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

[documentation/client-setup.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/documentation/client-setup.md) has each client's config file and steps, including VS Code and OpenAI Codex CLI, whose formats differ. If your Cursor release still sends only the first 40 MCP tools to the agent, that page shows how to narrow the list with `LM_MCP_CATEGORIES`.

### Container

The image on GitHub Container Registry runs the HTTP transport on port 8080:

```bash
docker run --rm -p 8080:8080 \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=<your-bearer-token> \
  -e LM_HTTP_AUTH_TOKEN=<a-secret-of-16-characters-or-more> \
  ghcr.io/ryanmat/mcp-server-logicmonitor:latest
```

Point a Streamable HTTP client at `http://127.0.0.1:8080/mcp` with the header `Authorization: Bearer <LM_HTTP_AUTH_TOKEN>`. [Deployment](#deployment) covers compose, TLS and Kubernetes.

### Other install methods

```bash
# pip
pip install lm-mcp

# a persistent install; uv tool upgrade lm-mcp picks up a new release
uv tool install lm-mcp

# from source
git clone https://github.com/ryanmat/mcp-server-logicmonitor.git
cd mcp-server-logicmonitor
uv sync
uv run lm-mcp-server
```

Restart your MCP client after an upgrade.

## Usage

Ask your assistant in plain language:

- "Triage the critical alerts from the last 4 hours"
- "Run a health check on device 123"
- "Give me a portal overview for shift handoff"
- "Forecast when memory on device 123 reaches 90 percent"
- "What is the blast radius if device 789 goes down?"
- "Acknowledge alert LMA12345 with the note 'Investigating disk issue'"
- "Create a 2-hour SDT for device 123"

The tools also take LogicMonitor filter syntax, for example `displayName~"prod",hostStatus:"normal"`. String values, `hostStatus` words included, are quoted.

### Find a tool

Start with `search_tools`. It searches the tools your settings list by keyword, so with writes off it names no write tool, and `category` narrows it to one group. The `lm://guide/tool-categories` resource groups all 273 tools by domain, and [documentation/tools.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/documentation/tools.md) lists every tool with its parameters and whether it writes, generated from the registry.

### Tool families

| Family | What the tools cover |
|--------|----------------------|
| Alerts | Query, acknowledge, bulk acknowledge, escalate and annotate alerts; alert rules; datapoint thresholds, read at instance, device or group level with the level each comes from, and set or cleared at instance or group level |
| Devices | Devices and groups, their properties and manual instances; Active Discovery scheduling; the device delta, to follow what changed; the unmonitored devices a NetScan found |
| Metrics | Datasources and the devices each applies to, instances, metric data and graphs |
| Dashboards | Dashboards, widgets and dashboard groups |
| SDT | Scheduled downtime, one at a time or in bulk |
| Collectors | Collectors and collector groups, with the operations below |
| Websites | Synthetic checks, website groups and checkpoint locations |
| Reports | List, view, run and schedule reports |
| Escalations | Escalation chains and recipient groups |
| Users and audit | Users, roles, access groups, API tokens, audit logs and ops notes |
| LogicModules | Data, config, event, property, topology, log, diagnostic and remediation sources: query, create, update, delete and import, and read any as its full REST object with `raw=true`; Config Archive versions, diffs and on-demand collection |
| Diagnostics and remediation | Assigned sources, execution results with script output, manual runs, action chains and action rules |
| Services | Service Insights services, service groups and rules |
| APM | Traced services and their alerts; a service's operations, metrics and properties through the device tools |
| Network | Neighbors, interfaces, flows, connections, top talkers and link flaps. See [networking intelligence](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/documentation/networking-intelligence.md) |
| Usage and cost | The contract's entitlements per feature, current resource counts (not billing figures), cost recommendations and idle resources |
| Ingestion | `ingest_logs` and `push_metrics`, with a Bearer or an LMv1 token |
| Batch jobs | Batch jobs and the BatchJob datasources on a device |

`update_logicmodule(type, id, changes, mode)` is the safe way to change a LogicModule: it reads the definition, deep-merges `changes`, checks required fields, and returns a dry-run diff unless you ask it to apply.

`get_device_flows` and `get_device_top_talkers` answer `FEATURE_DISABLED` when the portal has NetFlow off, as the only portal tested does, so their row shapes are unverified against NetFlow data.

### Analytics and composites

The analytics run in the server, so an assistant gets an answer in one call:

- `analyze_metric` reads one series once for its summary, trend, seasonality, change points, anomalies and a forecast to a threshold, and can compare it with an earlier window.
- `analyze_alerts` clusters a window's alerts and reports statistics, noise, flapping and bursts.
- `correlate_metrics`, `calculate_availability` (with MTTR and an SLO error budget) and `analyze_blast_radius` cover the rest.

The composites combine several reads to answer a common investigation: `triage`, `diagnose`, `health_check`, `portal_overview`, `capacity_plan` and `detect_site_outage`. Each takes `detail_level` (`summary` or `full`) and returns what it could read when a sub-call fails. `triage`, `portal_overview`, `capacity_plan` and `detect_site_outage` send a progress notification per phase when the request carries a progress token. These eleven tools declare an output schema and return structured content beside the JSON text.

### Edwin AI

Set `EDWIN_CLIENT_ID` and `EDWIN_CLIENT_TOKEN` to an Edwin AI API credential and the server lists eight more tools:

- `get_edwin_insights` and `get_edwin_insight` read the incidents Edwin built from correlated alerts, with its root cause and remediation analysis when it has one.
- `get_edwin_records`, `get_edwin_alert_volume` and `get_edwin_metadata` read Edwin's copy of alerts and events and its data model.
- `get_edwin_tools` lists Edwin's agent tools, and `edwin_run_tool` runs one. It needs writes on, every run is audited, and multi-portal mode leaves it out, since one Edwin tenant serves every portal there.
- `ask_edwin` asks Edwin a question and waits up to two minutes for the answer.

The server calls `https://<portal name>.dexda.ai` unless `EDWIN_HOST` names another host; multi-portal mode has no portal name to derive it from, so set `EDWIN_HOST` there. A credential that lacks a scope a tool needs gets `SCOPE_MISSING` naming the scope.

### Logs

`get_log_pipelines`, `get_tracked_log_queries`, `get_log_query_groups`, `get_log_partitions` and `get_log_usage` read LM Logs configuration and usage, and `ingest_logs` sends log lines. There is no log search: the v3 search endpoint applied neither the query nor the time range when probed.

### OpenTelemetry metrics

`get_otlp_metric_names`, `get_otlp_metric_labels` and `get_otlp_label_values` explore the OTLP metrics your portal holds, and `query_otlp_metrics` runs a PromQL instant or range query. `analyze_metric(source="otlp")` analyzes a PromQL series, and `add_widget` and `update_widget` take an OTLP query for an advanced metrics widget. Alert rules cannot hold one: the v3 alert rule has no query field.

### Collector operations

`get_collectors` marks each collector `is_down`, and `get_collector_health` adds the latest status check and five latest events for the collector you name and for each one not known to be up. The events, uploaded log files and upgrade history are readable too. With writes on, `run_collector_status_check`, `restart_collector`, `acknowledge_collector_down` and `collector_debug` act on a collector; `collector_debug` runs one debug command from a fixed list, and the portal records each session in its audit log. OpenTelemetry (lmotel) collectors are not listed: the v3 API does not return them.

### Terraform imports

`get_terraform_imports` lists one resource type's objects as import blocks for the `logicmonitor/logicmonitor` provider, one per object:

```hcl
import {
  to = logicmonitor_device_group.linux_servers_18
  id = "18"
}
```

It covers 15 of the 16 types whose provider docs (2.1.7) import by ID: `alert_rule`, `collector`, `collector_group`, `dashboard`, `dashboard_group`, `datasource`, `device`, `device_group`, `escalation_chain`, `report_group`, `role`, `sdt`, `website`, `website_group` and `widget`. It refuses `device_group_cluster_alert_conf`, whose importer reads a conf by ID without its device group, a read the API answers with 404. Each address ends with the object's ID, so objects that share a name get distinct addresses.

Save the blocks in a `.tf` file beside the provider configuration:

```hcl
terraform {
  required_providers {
    logicmonitor = {
      source = "logicmonitor/logicmonitor"
    }
  }
}

provider "logicmonitor" {}
```

Then run `terraform init` and `terraform plan -generate-config-out=generated.tf` (Terraform 1.5 or later), and review `generated.tf` before `terraform apply`.

The provider authenticates only with an LMv1 token, `api_id` and `api_key` (`LM_API_ID`, `LM_API_KEY`), plus `company` (`LM_COMPANY`). It takes no Bearer token, so a server set up with `LM_BEARER_TOKEN` alone needs an LMv1 token for Terraform.

### What the server does not do

The server does not run Terraform or launch Ansible jobs. Run Terraform with the `terraform` CLI, or HashiCorp's [Terraform MCP server](https://github.com/hashicorp/terraform-mcp-server), which drives runs in HCP Terraform and Terraform Enterprise. Launch Ansible jobs with `ansible-playbook`, or Red Hat's [MCP server for Ansible Automation Platform](https://www.redhat.com/en/blog/it-automation-agentic-ai-introducing-mcp-server-red-hat-ansible-automation-platform), a Technology Preview in AAP 2.6.4.

The portal refuses API tokens on API version 4 ("External calls are not supported for API Version 4"), so trace and span search, service maps, Resource Explorer, Cloud Operations billing and the lmotel collector list are out of the server's reach.

### Multi-portal mode

One server entry can serve many portals. Set `LM_MULTI_PORTAL=true` and point the server at a credential vault: an age-encrypted file, or a plaintext JSON file for testing. `get_portals`, `use_portal`, `get_current_portal` and `run_portal_reload` manage the active portal, and every LogicMonitor tool takes an optional `portal` argument that runs one call against another portal. Each portal is read-only unless its record marks it writable. The mode is stdio-only. See [MULTIPORTAL.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/MULTIPORTAL.md).

### Claude Code skills

The repository ships slash-command runbooks. Clone it and run `/lm-triage` in Claude Code.

| Command | What it does |
|---------|--------------|
| `/lm-triage` | Triage alerts: one `triage` call, then bursts, the worst clusters, and acknowledgements or notes you confirm |
| `/lm-health <device>` | A device health check: CPU, memory and disk, anomalies, open alerts, availability and topology neighbors |
| `/lm-portal` | A portal-wide overview: alert volume, clusters, noise, collectors, active SDTs, open critical and error alerts, and dead devices |
| `/lm-capacity <device>` | Capacity planning: level, trend, daily and weekly cycles, level shifts and threshold-breach forecasts |
| `/lm-apm [service]` | APM: services, operation-level RED metrics and alert correlation |
| `/lm-remediate <alert_id or device>` | Diagnose an alert, then run an assigned RemediationSource or an Edwin AI agent tool after a checklist and your confirmation |
| `/lm-edwin [insight]` | Check an Edwin AI insight's root cause against the causal CI's metric and the alert window |
| `/lm-logs [partition]` | Review LM Logs partitions and their contracts, the pipelines that name them, usage, and saved and tracked queries |

### Resources and prompts

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
| `lm://guide/tool-categories` | All 273 tools organized by domain category |
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

## Layout

| Path | Contents |
|------|----------|
| `src/lm_mcp/server.py` | Entry point (`lm-mcp-server`) and tool dispatch |
| `src/lm_mcp/registry.py` | Tool definitions and the handler map |
| `src/lm_mcp/tools/` | Tool handlers, one module per domain |
| `src/lm_mcp/client/` | Async HTTP clients for the LogicMonitor and Edwin AI APIs |
| `src/lm_mcp/auth/` | Bearer and LMv1 authentication |
| `src/lm_mcp/transport/` | Stdio and HTTP transports |
| `src/lm_mcp/prompts/`, `resources/` | MCP prompts and reference resources |
| `.claude/skills/` | Claude Code skills |
| `documentation/` | Tool reference (generated), client setup, networking intelligence |
| `deploy/` | Dockerfile, compose file, Caddyfile, Kubernetes manifest |
| `server.json` | MCP Registry manifest |
| `tests/` | pytest suite and contract fixtures |

## Configuration

Set these as environment variables, through your client's `env` block or `-e` flags. The server does not read a `.env` file; to use one from a clone, run `uv run --env-file .env lm-mcp-server`. [server.json](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/server.json) lists the same variables for registry clients.

### Authentication

Set `LM_BEARER_TOKEN`, or `LM_ACCESS_ID` and `LM_ACCESS_KEY` for an LMv1 token. Either works for every tool, `ingest_logs` and `push_metrics` included; with both set, the server uses the Bearer token. To create an LMv1 token, go to **Settings** > **Users and Roles** > **Users**, select a user, open the **API Tokens** tab, and create the access ID and key.

### Portal, tools and requests

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LM_PORTAL` | Yes, one portal | - | Portal hostname, such as `company.logicmonitor.com`. Multi-portal mode takes hosts from the vault instead |
| `LM_BEARER_TOKEN` | Yes, or LMv1 | - | API Bearer token (10 characters or more) |
| `LM_ACCESS_ID` | For LMv1 | - | LMv1 access ID; with `LM_ACCESS_KEY` it stands in for `LM_BEARER_TOKEN` |
| `LM_ACCESS_KEY` | For LMv1 | - | LMv1 access key |
| `LM_ENABLE_WRITE_OPERATIONS` | No | `false` | List and allow the tools that change the portal |
| `LM_ENABLED_TOOLS` | No | - | Comma-separated tool names or glob patterns to enable, such as `get_*,triage`. Not with `LM_DISABLED_TOOLS` |
| `LM_DISABLED_TOOLS` | No | - | Comma-separated tool names or glob patterns to disable, such as `delete_*`. Not with `LM_ENABLED_TOOLS` |
| `LM_MCP_CATEGORIES` | No | - | Comma-separated categories to list: `read`, `write`, `delete`, `export`, `import`, `session`, `workflow`. It narrows the two settings above, never widens them; useful under a client's tool cap |
| `LM_TIMEOUT` | No | `30` | Request timeout in seconds, 5 to 300 |
| `LM_MAX_RETRIES` | No | `3` | Resends of a rate-limited request, and of a 5xx on an idempotent request (GET, PUT, DELETE); a POST or PATCH that gets a 5xx is not resent. 0 to 10 |
| `LM_RETRY_AFTER_CAP_SECONDS` | No | `120` | Longest wait between retries. A `Retry-After` header can lengthen the backoff up to this cap, never shorten it |
| `LM_SESSION_HISTORY_SIZE` | No | `50` | Tool calls kept in the session history, 0 to 1000 |
| `LM_LOG_LEVEL` | No | `warning` | `debug`, `info`, `warning` or `error`, for the server and, under the HTTP transport, uvicorn. The server logs to stderr. Write audit lines (`info` for a success, `warning` for a failure) appear at every level, with argument values under credential-shaped keys such as `password`, `token`, `api_key` and `extra_vars`, LogicMonitor credential properties such as `ssh.pass` and `snmp.community`, and a `property_value` whose `property_name` is one, redacted |


### Multi-portal and Edwin AI

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LM_MULTI_PORTAL` | No | `false` | Serve several portals from one server, chosen with `use_portal` or a call's `portal` argument. Stdio only |
| `LM_VAULT_FILE` | No | - | Age-encrypted portal vault |
| `LM_AGE_KEY` | No | - | Age identity file that decrypts the vault |
| `LM_PORTALS_FILE` | No | - | Plaintext JSON portal map, for testing; the vault wins when both are set |
| `EDWIN_CLIENT_ID` | No | - | Edwin AI API credential client ID. With `EDWIN_CLIENT_TOKEN` it turns on the eight Edwin tools; one without the other leaves them off and logs a warning |
| `EDWIN_CLIENT_TOKEN` | No | - | Secret of that Edwin AI credential |
| `EDWIN_HOST` | No | `https://<portal name>.dexda.ai` | Edwin AI base URL, https only. Required in multi-portal mode |

### HTTP transport

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LM_TRANSPORT` | No | `stdio` | `stdio` for MCP clients, or `http` (see [Deployment](#deployment)) |
| `LM_HTTP_HOST` | No | `0.0.0.0` | Bind address. Any address but `127.0.0.1`, `::1` or `localhost` needs `LM_HTTP_AUTH_TOKEN` or `LM_HTTP_ALLOW_UNAUTHENTICATED=true`, or the server refuses to start |
| `LM_HTTP_PORT` | No | `8080` | Port |
| `LM_HTTP_AUTH_TOKEN` | No | - | Bearer token required on every path except `/` and the health endpoints; 16 characters or more |
| `LM_HTTP_ALLOW_UNAUTHENTICATED` | No | `false` | Start on a non-loopback bind with no `LM_HTTP_AUTH_TOKEN`, for a listener protected another way |
| `LM_HTTP_ALLOWED_HOSTS` | No | - | Comma-separated `Host` names accepted on every route except `/healthz` and `/readyz`, besides the loopback names and a non-wildcard `LM_HTTP_HOST`, such as the name a reverse proxy forwards |
| `LM_HTTP_SSL_CERTFILE` | No | - | TLS certificate; with `LM_HTTP_SSL_KEYFILE` the server speaks HTTPS |
| `LM_HTTP_SSL_KEYFILE` | No | - | TLS private key |
| `LM_HTTP_SSL_KEYFILE_PASSWORD` | No | - | Password of an encrypted TLS private key |
| `LM_HEALTH_CHECK_CONNECTIVITY` | No | `false` | Add a LogicMonitor API call to `/health` for callers that pass the bearer check; `/readyz` never makes one |

## Deployment

Stdio needs no deployment: your client starts the server. The HTTP transport serves MCP at `/mcp` through the MCP SDK's Streamable HTTP, stateless and answering with JSON, beside the health and info routes. With `LM_HTTP_AUTH_TOKEN` set, `/mcp` requires it like every route outside `/` and the health endpoints. `/mcp` refuses a body that is not `application/json` with 415, and one over 4 MiB with 413.

```bash
cd deploy
cp .env.example .env
# Edit .env with your credentials, including LM_HTTP_AUTH_TOKEN (required)

docker compose up -d                  # HTTP on port 8080
docker compose --profile tls up -d    # behind Caddy with TLS
```

Health endpoints for orchestration:

- `GET /health`: every component's status, plus the API connectivity check when `LM_HEALTH_CHECK_CONNECTIVITY` is on and the caller passes the bearer check
- `GET /healthz`: liveness, 200 or 503
- `GET /readyz`: readiness from local checks only; never calls the LogicMonitor API

Every route except `/healthz` and `/readyz` answers only the `Host` names the server expects (the loopback names, a non-wildcard `LM_HTTP_HOST` and `LM_HTTP_ALLOWED_HOSTS`) and refuses others with 400; the two probes accept any `Host`, so probes by pod IP work. The compose file requires `LM_HTTP_AUTH_TOKEN` in every profile and passes `DOMAIN` through as an allowed host for the `tls` profile.

`deploy/k8s/deployment.yaml` is a Deployment and Service for the published image that runs on AKS, EKS, GKE, OpenShift or plain Kubernetes. It reads credentials from a secret you create, documented at the top of the file, and wires the liveness and readiness probes to the endpoints above. Apply it with `kubectl apply -f deploy/k8s/deployment.yaml`.

[SECURITY.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/SECURITY.md) describes the exposure model.

## Troubleshooting

The server logs to stderr. Set `LM_LOG_LEVEL=debug` to add the httpx and MCP SDK lines.

### "Failed to connect" in Claude Code

The server is missing environment variables. Claude Code starts it with its own environment, so variables in your shell or a `.env` file do not reach it; pass them with `-e`:

```bash
claude mcp remove logicmonitor
claude mcp add logicmonitor \
  -e LM_PORTAL=yourcompany.logicmonitor.com \
  -e LM_BEARER_TOKEN=<your-bearer-token> \
  -- uvx --from lm-mcp lm-mcp-server
```

### "Write operations are disabled"

The tools that change the portal are off by default: the server does not list them, and a call to one by name returns this error. Set `LM_ENABLE_WRITE_OPERATIONS=true`.

### "spawn uvx ENOENT" in Claude Desktop

Claude Desktop cannot find `uvx`. Find its path with `which uvx` and use the full path:

```json
{
  "command": "/Users/yourname/.local/bin/uvx",
  "args": ["--from", "lm-mcp", "lm-mcp-server"]
}
```

### The server refuses to start with `LM_TRANSPORT=http`

The default bind is `0.0.0.0`, which needs `LM_HTTP_AUTH_TOKEN`. Set the token, bind to `127.0.0.1`, or set `LM_HTTP_ALLOW_UNAUTHENTICATED=true` for a listener protected another way.

### Authentication errors

Check that the token is active and that its user's role grants the access the tool needs. Manage tokens under **Settings** > **Users and Roles** > **API Tokens**.

### Rate limits

The server retries a rate-limited request with exponential backoff, waiting at least what `Retry-After` asks up to `LM_RETRY_AFTER_CAP_SECONDS`. If you keep hitting limits, make fewer calls.

## Development

```bash
uv sync --extra http
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
```

[CONTRIBUTING.md](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/CONTRIBUTING.md) has the workflow, the type-check ratchet, and what to regenerate after a tool change.

## License

MIT License. See [LICENSE](https://github.com/ryanmat/mcp-server-logicmonitor/blob/main/LICENSE).
