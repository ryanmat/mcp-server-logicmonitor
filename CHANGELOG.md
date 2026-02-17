# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.1] - 2026-02-17

### Fixed

- **Import tools send wrong Content-Type** — All 8 `import_*` tools now use `multipart/form-data` file upload via `post_multipart()` instead of `application/json` POST. The LM import endpoints require multipart upload; the previous JSON body approach silently failed.
- **Unhandled 4xx status codes returned as success** — `_raise_for_status()` now has a catch-all for 400-499 status codes (400, 405, 409, 415, etc.) that raises `LMError` with code `HTTP_{status}`. Previously these fell through and returned error response bodies as if they were successful results.
- **Export/import format mismatch documented** — Updated docstrings on all export and import functions to clarify that REST API export format differs from LM Exchange format required by import endpoints.

### Added

- **`create_dashboard` template and widget token support** — `create_dashboard` now accepts `widget_tokens` (list of token overrides) and `template` (full dashboard definition from `export_dashboard` to clone from). When using a template, the exported definition is used as the base payload with name overridden and id stripped.
- **`create_dashboard_group`** — Create dashboard groups with optional parent_id and description. Follows the same pattern as `create_website_group`.
- **`delete_dashboard_group`** — Delete dashboard groups by ID. Follows the same pattern as `delete_website_group`.
- **`post_multipart()` client method** — Handles multipart/form-data file uploads for LM import endpoints with proper auth headers and retry logic.

Tool count: 175 -> 177.

## [1.6.0] - 2026-02-16

### Added

8 APM trace tools for service discovery and RED metrics via the v3 API. APM services are stored as `deviceType:6` devices with `LogicMonitor_APM_Services` and `LogicMonitor_APM_Operations` datasources.

- **`get_trace_services`** — Lists all APM trace services by filtering for deviceType:6. Entry point for discovering which services are instrumented. Supports namespace filtering for substring matching on service names.
- **`get_trace_service`** — Gets full device detail for a specific APM service, including status, groups, and configuration.
- **`get_trace_service_alerts`** — Gets active alerts for an APM service with optional severity filtering (critical, error, warning, info). Bridges traces and alerting.
- **`get_trace_service_datasources`** — Lists datasources applied to an APM service (LogicMonitor_APM_Services, LogicMonitor_APM_Operations, etc.). Required step before querying instances or metric data.
- **`get_trace_operations`** — Lists operation instances (endpoints/routes) for an APM service datasource. Each operation has its own RED metrics.
- **`get_trace_service_metrics`** — Gets service-level time-series data for Duration, ErrorOperationCount, OperationCount, and UniqueOperationCount. Supports time range and datapoint filtering.
- **`get_trace_operation_metrics`** — Gets per-operation RED metrics for a specific endpoint/route. Same API shape as service metrics but scoped to an individual operation instance.
- **`get_trace_service_properties`** — Gets device properties for an APM service including OTel attributes, namespace info, and auto-discovered metadata. Supports name filtering.

Tool count: 167 -> 175. Added "traces" category to tool-categories guide resource.

## [1.5.1] - 2026-02-14

### Added
- ML tool usage guide with detailed examples for capacity forecasting, metric correlation, change point detection, noise scoring, health scoring, and availability calculation
- ML Analysis & Forecasting example prompts section (10 natural language examples)
- Updated project structure with new tool files

## [1.5.0] - 2026-02-14

### Added

10 ML/statistical analysis tools using pure-Python implementations (no numpy/scipy dependencies).

- **`forecast_metric`** — Predicts when a metric will breach a threshold. Uses linear regression on historical data to calculate trend direction, slope, and estimated days until breach. Useful for capacity planning — point it at CPU, memory, or disk and set a threshold to get an early warning.
- **`correlate_metrics`** — Computes a Pearson correlation matrix across up to 10 metric series. Helps answer "are these metrics related?" — for example, does CPU spike when memory does? Highlights strong correlations (|r| > 0.7) automatically. Each source can be from a different device.
- **`detect_change_points`** — Finds moments where metric behavior shifted using the CUSUM algorithm. Instead of just looking at whether a value is high or low, it detects when the pattern changed — a sudden jump, a drop to a new baseline, or a regime shift. Sensitivity is configurable.
- **`score_alert_noise`** — Scores how noisy your alert environment is on a 0-100 scale. Combines Shannon entropy (how spread out alerts are across sources), flap detection (alerts that clear and re-fire within 30 minutes), and repeat ratio. Returns the top noisy devices and datasources with tuning recommendations.
- **`detect_seasonality`** — Checks whether a metric has a repeating pattern using autocorrelation. Tests standard intervals (1h, 4h, 6h, 8h, 12h, 24h, 7d) and reports which periods show strong periodicity. Useful for distinguishing "this spikes every day at 2pm" from "this is random."
- **`calculate_availability`** — Computes SLA-style uptime percentage from alert history. Merges overlapping alert windows and returns availability %, MTTR, incident count, longest incident duration, and a per-device breakdown. Filterable by severity threshold and time range.
- **`analyze_blast_radius`** — Scores the downstream impact if a device goes down. Walks the topology map to find dependent devices and produces an impact score. Useful for change management — check the blast radius before taking a device offline for maintenance.
- **`correlate_changes`** — Cross-references alert activity with audit/change logs to find correlations. Identifies config changes, device updates, or user actions that occurred within a configurable window before alert spikes. Each correlation gets a confidence score based on time proximity.
- **`classify_trend`** — Categorizes a metric's recent behavior into one of five patterns: stable, increasing, decreasing, cyclic, or volatile. A quick way to triage a metric without staring at a graph — run it across multiple datapoints to see what's moving.
- **`score_device_health`** — Produces a composite health score from 0-100 by computing z-scores for each datapoint's latest value against its historical window. Weights are configurable. Returns an overall status (healthy/degraded/critical) and identifies the top contributing factors dragging the score down.

2 analysis workflows:
- `capacity_forecast` — runs forecast_metric + classify_trend
- `device_health_assessment` — runs score_device_health + analyze_blast_radius + get_metric_anomalies

Shared statistical helpers module (`stats_helpers.py`) for reusable math utilities.

## [1.4.1] - 2026-02-14

### Fixed
- Metric data API returns values as list-of-lists, not dict

## [1.4.0] - 2026-02-14

### Added

5 AI analysis tools for server-side intelligence on monitoring data.

- **`correlate_alerts`** — Groups related alerts together by device, datasource, and time proximity. Instead of looking at alerts one by one, it clusters them to show which alerts are part of the same incident. Helps cut through a noisy alert storm to see "these 15 alerts are actually 3 distinct issues."
- **`get_alert_statistics`** — Aggregates alert counts across severity, device, datasource, and time buckets. Returns a statistical summary over a configurable time window — think of it as a quick dashboard view of alert volume and distribution without needing to open the portal.
- **`get_metric_anomalies`** — Detects datapoints that are deviating significantly from their historical mean using z-score analysis. Point it at a device and it flags which metrics are behaving abnormally right now. Useful for triage — instead of checking every graph, let it tell you what looks off.
- **`save_baseline`** — Snapshots a metric's historical behavior — mean, min, max, and standard deviation per datapoint — and stores it in the session. Use this to capture what "normal" looks like before a maintenance window, deployment, or any planned change.
- **`compare_to_baseline`** — Compares current metric values against a previously saved baseline. Reports deviation percentage and status (normal, elevated, critical) for each datapoint. The companion to `save_baseline` — run it after a change to see if anything drifted from where it was.

3 workflow prompts:
- `top_talkers` — Identify the noisiest devices and datasources generating the most alerts
- `rca_workflow` — Guided root cause analysis combining alert correlation, topology, and change history
- `capacity_forecast` — Forecast capacity trends and predict days-until-threshold-breach

Enhanced `alert_correlation` prompt with `device_id`/`group_id` scoping and correlation tool integration.

MCP orchestration guide resource (`lm://guide/mcp-orchestration`) documenting multi-MCP-server patterns.

Session persistence via `LM_SESSION_PERSIST_PATH` — session variables survive restarts.

HTTP analysis API: `POST /api/v1/analyze`, `GET /api/v1/analysis/{id}`, `POST /api/v1/webhooks/alert` for scheduled and webhook-triggered analysis workflows.

## [1.3.3] - 2026-02-13

### Fixed
- HTTP transport now applies the full middleware chain (tool filtering, field validation, write audit logging, session recording) — previously bypassed entirely
- HTTP `tools/list` now respects `LM_ENABLED_TOOLS` and `LM_DISABLED_TOOLS` filtering

### Changed
- Extracted shared `execute_tool()` middleware from `call_tool()` for transport-agnostic tool execution
- LMConfig cached as singleton to avoid redundant environment parsing on every tool call
- Removed dead logging infrastructure (LogLevel enum, LogEvent dataclass, 7 unused event factory functions)

## [1.3.2] - 2025-02-13

### Fixed
- Fixed 20 MCP tool schemas where parameter names did not match handler function signatures, causing "unexpected keyword argument" errors at runtime

### Added
- Registry test that validates all schema property names match handler function parameter names, preventing future mismatches

## [1.3.1] - 2025-02-12

### Fixed
- `get_change_audit` no longer crashes when the API returns `happenedOn` as an epoch integer

## [1.3.0] - 2025-02-10

### Added
- 5 MCP prompts: `cost_optimization`, `audit_review`, `alert_correlation`, `collector_health`, `troubleshoot_device`
- 6 resource schemas: escalations, reports, websites, datasources, users, audit
- 2 guide resources: tool categories index (all 152 tools) and common query examples
- `LM_LOG_LEVEL` configuration for controlling debug output (debug, info, warning, error)
- Write operation audit trail (INFO-level logging for create/update/delete actions)

### Fixed
- Wildcard sanitization applied to all 11 remaining string filter parameters across audit, cost, batchjobs, SDTs, and topology tools

## [1.2.1] - 2025-02-05

### Fixed
- Patch release with minor fixes

## [1.2.0] - 2025-02-01

### Added
- Tool filtering with `LM_ENABLED_TOOLS` and `LM_DISABLED_TOOLS` glob patterns
- Export/import support for all LogicModule types
- Cost optimization recommendation categories and detail endpoints

## [1.1.0] - 2025-01-20

### Added
- HTTP transport for remote deployments via Starlette/Uvicorn
- Session context tracking for conversational workflows
- 6 session management tools
- Health endpoints (`/health`, `/healthz`, `/readyz`) for Kubernetes
- Docker deployment with multi-stage build and Caddy reverse proxy
- CORS middleware configuration via `LM_CORS_ORIGINS`

## [1.0.1] - 2025-01-15

### Changed
- Comprehensive README update with all 146 tools documented
- Fixed installation command: `uvx --from lm-mcp lm-mcp-server`
- Added MCP Resources and Prompts documentation
- Added LMv1 authentication configuration instructions

## [1.0.0] - 2025-01-15

### Added
- **MCP Resources**: 15 schema/enum/filter resources for API reference
  - Schema resources: alerts, devices, sdts, dashboards, collectors
  - Enum resources: severity, device-status, sdt-type, alert-cleared, alert-acked, collector-build
  - Filter resources: alerts, devices, sdts, operators
- **MCP Prompts**: 5 workflow templates
  - incident_triage, capacity_review, health_check, alert_summary, sdt_planning
- **MCP Completions**: Auto-complete for tool arguments (severity, status, sdt_type, etc.)
- **LMv1 HMAC Authentication**: Support for Access ID/Key authentication
- **Ingestion APIs**: ingest_logs and push_metrics tools (requires LMv1 auth)
- **Cost Optimization Tools**: 7 tools for LM Envision cost analysis
  - get_cost_summary, get_resource_cost, get_cost_recommendations
  - get_cost_recommendation_categories, get_cost_recommendation
  - get_idle_resources, get_cloud_cost_accounts
- **LogicModule Import Tools**: 8 import tools for JSON definitions
  - import_datasource, import_configsource, import_eventsource
  - import_propertysource, import_logsource, import_topologysource
  - import_jobmonitor, import_appliesto_function
- **Website CRUD**: create_website, update_website, delete_website, create_website_group, delete_website_group
- **Alert Rule CRUD**: create_alert_rule, update_alert_rule, delete_alert_rule
- **Escalation CRUD**: create_escalation_chain, update_escalation_chain, delete_escalation_chain
- **Recipient Group CRUD**: create_recipient_group, update_recipient_group, delete_recipient_group
- **Structured Logging**: Event-based logging for API operations

### Changed
- Total tool count increased from ~120 to 146
- Development status changed to Production/Stable
- Improved metrics ingestion endpoint (changed to /rest/metric/ingest with create=true)

### Fixed
- MCP resource reading: Convert AnyUrl to string in read handler

## [0.5.1] - 2024-12-14

### Added
- MCP Registry server name in README for registry ownership validation

## [0.5.0] - 2024-12-14

### Added
- Comprehensive API filter support for all list tools
- Raw `filter` parameter for power users (LogicMonitor filter syntax)
- Named filter parameters for convenience (e.g., `name_filter`, `severity`)
- `offset` parameter for pagination on all list endpoints
- `has_more` indicator in responses for easier pagination
- Expanded README with Quick Start section and 50+ example prompts

### Changed
- All list tools now support both named parameters and raw filter expressions
- Improved pagination support across all endpoints

## [0.4.0] - 2024-12-13

### Added
- MCP tool registration with 120 tools
- Bulk operations: bulk_acknowledge_alerts, bulk_create_device_sdt, bulk_delete_sdt
- Export tools for datasources, dashboards, alert rules, escalation chains
- Active and upcoming SDT queries
- Network topology and flow tools
- Batch job management tools
- Cloud cost analysis tools
- Comprehensive LogicModule support (ConfigSources, EventSources, PropertySources, TopologySources, LogSources)

### Changed
- Improved tool descriptions for better AI understanding
- Enhanced error messages with actionable guidance

## [0.3.0] - 2024-12-13

### Added
- Dashboard management (create, update, delete dashboards and widgets)
- Report management (list, view, run, schedule reports)
- User and role management
- Access group tools
- API token tools
- Service and service group tools
- OID management tools
- Netscan execution

### Changed
- Reorganized tool modules for better maintainability
- Improved response formatting consistency

## [0.2.0] - 2024-12-12

### Added
- Alert rules tools
- Escalation chain and recipient group tools
- Ops notes and audit log tools
- Website/synthetic monitoring tools
- Collector group tools
- Device property management

### Changed
- Enhanced alert filtering options
- Improved error handling with retry logic

## [0.1.0] - 2024-12-12

### Added
- Initial release
- Bearer token authentication
- Core device management (list, create, update, delete)
- Alert management (list, view, acknowledge, add notes)
- SDT management (list, create, delete)
- Collector listing
- Basic metrics and datasource queries
- Rate limit handling with exponential backoff
- Write operation protection (disabled by default)

[1.6.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.5.1...v1.6.0
[1.5.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.3.3...v1.4.0
[1.3.3]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.3.2...v1.3.3
[1.3.2]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.5.1...v1.0.0
[0.5.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ryanmat/mcp-server-logicmonitor/releases/tag/v0.1.0
