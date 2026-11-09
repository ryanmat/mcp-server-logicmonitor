# LogicMonitor MCP Server: Tool Reference

<!-- GENERATED FILE. Do not edit by hand. Regenerate: uv run python tests/test_tools_doc.py -->

Reference for all 256 tools the LogicMonitor MCP server can advertise. The **Write** column marks the tools that change the portal; the server lists them only when `LM_ENABLE_WRITE_OPERATIONS=true`.

This file is generated from the tool registry (`src/lm_mcp/registry.py`) and the domain index (`lm://guide/tool-categories`), and kept in sync by `tests/test_tools_doc.py`. At runtime, discover tools with the `search_tools` tool.

Back to the [README](../README.md).

## Composite Workflows

Composite workflow tools -- recommended starting point

| Tool | Description | Write |
|------|-------------|-------|
| `triage` | Composite triage: correlates alerts, clusters by device/time, scores noise, assesses blast radius, and checks recent changes. Returns a prioritized incident report. | No |
| `health_check` | Composite health check: resolves a device, reads the first instance of up to five datasources through analyze_metric (summary and anomalies over 24 hours), checks alerts, and calculates availability. Returns a single device health report. | No |
| `capacity_plan` | Composite capacity planning: reads each instance once through analyze_metric to classify its trend, detect seasonality and change points, and forecast when it crosses 90. Returns per-datasource capacity projections. | No |
| `portal_overview` | Composite portal overview: aggregates alert statistics, collector health, maintenance windows, noise scores, and dead devices into a shift-handoff report. | No |
| `diagnose` | Composite diagnosis: given an alert or device, gathers alert details, device context, correlated alerts, recent changes, blast radius, and health score. Returns a diagnosis report with probable root cause and recommendations. | No |
| `update_logicmodule` | Update a LogicModule definition (configsource, datasource, diagnosticsource, eventsource, logsource, propertysource, remediationsource, topologysource). Reads the current full definition, deep-merges your `changes` onto it, validates required fields, and either returns a dry-run diff (mode='preview', default) or applies the merged definition (mode='apply'). The LogicMonitor update is full-replace, so the merged full definition is sent and fields you do not change are kept. | Yes |
| `detect_site_outage` | Composite workflow for site outage detection. Chains CollectorDown detection, mass-interface-down burst analysis, UPS on-battery events, and downstream device silence into a single site-outage verdict with confidence score, scope, and affected device list. Designed to catch the class of site-outage that generic AIOps correlation misses. Pass a device group ID representing the site. | No |
| `audit_network_monitoring_coverage` | Portal audit that counts UPS/PDU devices onboarded, interface DataSources applied, SNMP credentials configured, and NetFlow exporters set up. Returns a prioritized gap list with onboarding recommendations — turns 'you can't detect X' into 'here's how to enable detection of X.' | No |

## Universal Reference

Resource mirror exposed as a Tool for clients without that primitive

| Tool | Description | Write |
|------|-------------|-------|
| `get_reference` | Get LogicMonitor reference content (schemas, enums, filter syntax, guides). Mirrors content from MCP Resources for clients without full Resource support (Copilot cloud agent, OpenAI Codex, Cline). Categories: schema, enums, filters, syntax, guide. Pass list=true (or omit both category and name) to discover all available (category, name) pairs. | No |

## Discovery

Tool search and discovery

| Tool | Description | Write |
|------|-------------|-------|
| `search_tools` | Search available MCP tools by keyword or category. Use this to discover which tools are available for a task. | No |

## Devices

Device/resource management

| Tool | Description | Write |
|------|-------------|-------|
| `get_devices` | List devices (resources) from LogicMonitor with optional filtering | No |
| `get_device` | Get detailed information about a specific device (resource) | No |
| `get_device_groups` | List device/resource groups from LogicMonitor | No |
| `get_device_group` | Get detailed information about a specific device/resource group, including appliesTo expression and parent ID | No |
| `create_device` | Create a new device/resource (requires write permission) | Yes |
| `update_device` | Update an existing device/resource (requires write permission). Custom properties are merged with existing properties (not replaced). | Yes |
| `delete_device` | Delete a device/resource (requires write permission). Soft delete by default. | Yes |
| `recover_device` | Recover a soft-deleted device/resource (requires write permission). Only works within the recovery window. | Yes |
| `bulk_delete_devices` | Delete multiple devices/resources in one operation (max 100, requires write permission). Soft delete by default. | Yes |
| `create_device_group` | Create a new device/resource group (requires write permission) | Yes |
| `update_device_group` | Update a device/resource group (requires write permission). Custom properties are merged with existing. | Yes |
| `delete_device_group` | Delete a device/resource group (requires write permission). Shows impact. | Yes |
| `get_device_properties` | Get all properties of a device (resource) | No |
| `get_device_property` | Get a specific property of a device (resource) | No |
| `update_device_property` | Update or create a device/resource property (requires write permission) | Yes |

## Alerts

Alert monitoring and management

| Tool | Description | Write |
|------|-------------|-------|
| `get_alerts` | Get alerts from LogicMonitor with optional filtering For Kubernetes clusters, use group_id (from get_device_groups) instead of device — the device name filter does not work reliably for K8s resources. Common mistakes: startEpoch/endEpoch use SECONDS not milliseconds. String filter values need double quotes (e.g., monitorObjectName:"hostname"). | No |
| `get_alert_details` | Get detailed information about a specific alert | No |
| `acknowledge_alert` | Acknowledge an alert (requires write permission) Common mistakes: alert_id works with or without the LMA prefix. | Yes |
| `add_alert_note` | Add a note to an alert without acknowledging (requires write permission) | Yes |
| `bulk_acknowledge_alerts` | Acknowledge multiple alerts at once (max 100, requires write permission) | Yes |

## Alert Rules

Alert rule configuration

| Tool | Description | Write |
|------|-------------|-------|
| `get_alert_rules` | List alert rules | No |
| `get_alert_rule` | Get details about a specific alert rule | No |
| `create_alert_rule` | Create an alert rule in LogicMonitor (requires write permission) | Yes |
| `update_alert_rule` | Update an alert rule in LogicMonitor (requires write permission) | Yes |
| `delete_alert_rule` | Delete an alert rule from LogicMonitor (requires write permission) | Yes |

## Scheduled Downtime (SDT)

Scheduled downtime management

| Tool | Description | Write |
|------|-------------|-------|
| `list_sdts` | List scheduled downtimes from LogicMonitor | No |
| `create_sdt` | Create a scheduled downtime (requires write permission) Common mistakes: duration_minutes is MINUTES not hours/seconds. DeviceSDT needs device_id, DeviceGroupSDT needs device_group_id. DeviceDataSourceSDT needs device_id + datasource_id. Cloud resources (collector_id=-2) may not support DeviceSDT; use DeviceGroupSDT on their parent group instead. | Yes |
| `update_sdt` | Update a scheduled downtime (requires write permission). Uses fetch-modify-PUT to preserve unmodified fields. | Yes |
| `delete_sdt` | Delete a scheduled downtime (requires write permission) | Yes |
| `bulk_create_device_sdt` | Create SDT for multiple devices/resources (max 100, requires write permission) | Yes |
| `bulk_delete_sdt` | Delete multiple SDTs at once (max 100, requires write permission) | Yes |
| `get_active_sdts` | Get currently active SDTs | No |
| `get_upcoming_sdts` | Get SDTs scheduled to start within a time window | No |

## Collectors

Collector status and management

| Tool | Description | Write |
|------|-------------|-------|
| `get_collectors` | List collectors from LogicMonitor | No |
| `get_collector` | Get detailed information about a specific collector | No |
| `get_collector_groups` | List collector groups | No |
| `get_collector_group` | Get details about a specific collector group | No |
| `update_collector` | Update a collector (requires write permission). Change group, description, failback, or escalation chain. | Yes |
| `delete_collector` | Delete a collector (requires write permission). Blocks if devices are still assigned. | Yes |
| `create_collector_group` | Create a collector group (requires write permission) | Yes |
| `update_collector_group` | Update a collector group (requires write permission) | Yes |
| `delete_collector_group` | Delete a collector group (requires write permission). Blocks if collectors are still assigned. | Yes |
| `get_collector_health` | Enriched collector status: whether each collector is down, downstream device count, uptime, and optional alert history. Leading indicator for site-level events. Prefer this over `get_collectors` when investigating potential outages. | No |

## Networking

Network intelligence primitives: interface metrics, NetFlow top talkers, link flap identification, power event filtering (UPS/PDU)

| Tool | Description | Write |
|------|-------------|-------|
| `get_interface_metrics` | Pull interface-level metrics (in/out bytes, errors, discards, utilization, status) for a device's interface over a time window. Answers 'how is this port performing?' Resolves the Interface-family DataSource and the instance matching the interface name before fetching datapoints. | No |
| `get_top_talkers` | Rank NetFlow flows on an exporter by bandwidth, packets, or flow count. Group by source IP, destination IP, protocol, application, or source->destination pair. Answers 'what is consuming my WAN?' | No |
| `get_link_flaps` | Identify interfaces with repeated up/down transitions in a time window. Answers 'which ports are unstable?' Common causes: bad cable, duplex mismatch, bad SFP, PoE power cycling, WAN instability. | No |
| `get_power_events` | Filter alerts for UPS/PDU power-event signatures across APC, Liebert, and Eaton DataSources ('on battery', 'runtime remaining', 'input voltage lost') over a time window. Returns events matched by DataSource or alert name substring with counts per pattern. | No |

## DataSources

DataSource and instance monitoring

| Tool | Description | Write |
|------|-------------|-------|
| `get_device_datasources` | Get datasources applied to a device (resource) Common mistakes: Returns device-datasource associations not definitions. The ID returned here is device_datasource_id for use with get_device_data. | No |
| `get_device_instances` | Get instances of a datasource on a device (resource) | No |
| `add_device_instance` | Add a monitored instance to a datasource on a device (requires write permission). Used for datasources without Active Discovery (e.g. ServiceStatus). | Yes |
| `update_device_instance` | Update a monitored instance on a device (requires write permission) | Yes |
| `delete_device_instance` | Delete a monitored instance from a datasource on a device (requires write permission) | Yes |
| `get_device_data` | Get metric data for a device/resource datasource instance Common mistakes: Returns most recent data unless period/start/end specified. Requires device_datasource_id (from get_device_datasources) not the datasource definition ID. | No |
| `get_graph_data` | Get graph image data for visualization | No |
| `get_datasources` | List datasources from LogicMonitor | No |
| `get_datasource` | Get details about a specific datasource | No |
| `create_datasource` | Create a DataSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as export_datasource output). Use for round-tripping exports or building definitions from scratch. For LM Exchange format, use import_datasource. Script DataSource datapoints require appropriate type values. | Yes |
| `delete_datasource` | Delete a DataSource definition (requires write permission). Existing collected data is retained. | Yes |

## Dashboards

Dashboard and widget management

| Tool | Description | Write |
|------|-------------|-------|
| `get_dashboards` | List dashboards from LogicMonitor | No |
| `get_dashboard` | Get detailed information about a specific dashboard | No |
| `get_dashboard_widgets` | Get widgets configured on a dashboard | No |
| `get_widget` | Get details about a specific widget | No |
| `create_dashboard` | Create a dashboard, optionally from template (requires write permission) | Yes |
| `update_dashboard` | Update an existing dashboard (requires write permission) | Yes |
| `delete_dashboard` | Delete a dashboard (requires write permission) | Yes |
| `add_widget` | Add a widget to a dashboard (requires write permission). For text widgets: use 'content' (not 'html') as the config key. For bigNumber widgets: dataPoints need 'name' field, include 'bigNumberItems' array, colorThresholds use 'relation'/'threshold', aggregateFunction is lowercase (e.g., 'average'). For cgraph widgets: deviceDisplayName/deviceGroupFullPath/instanceName must be GlobMatchToggle objects {'value': '...', 'isGlob': true}, dataPoints need 'display' object, graphInfo needs 'aggregate': false when using topX. For deviceSLA widgets: required config fields are 'groupName' (not deviceGroupFullPath), 'deviceName', 'dataSourceFullName', 'metric', 'threshold'. Also required: 'daysInWeek' (e.g., '1,2,3,4,5,6,7'), 'periodInOneDay' (e.g., '0:00-23:59'), 'displayType' (0=availability, 1=timeline), 'calculationMethod' (0=percent, 1=actual), 'unmonitoredTimeAlertStatus' (0=ignore, 1=warning, 2=error, 3=critical). | Yes |
| `update_widget` | Update a widget (requires write permission) | Yes |
| `delete_widget` | Delete a widget from a dashboard (requires write permission) | Yes |
| `get_dashboard_groups` | List dashboard groups | No |
| `get_dashboard_group` | Get details about a specific dashboard group | No |
| `create_dashboard_group` | Create a dashboard group in LogicMonitor (requires write permission) | Yes |
| `update_dashboard_group` | Update a dashboard group (requires write permission) | Yes |
| `delete_dashboard_group` | Delete a dashboard group from LogicMonitor (requires write permission) | Yes |

## Websites

Website monitoring

| Tool | Description | Write |
|------|-------------|-------|
| `get_websites` | List websites from LogicMonitor | No |
| `get_website` | Get detailed information about a specific website | No |
| `get_website_groups` | List website groups | No |
| `get_website_data` | Get synthetic check data for a website | No |
| `create_website` | Create a website check in LogicMonitor (requires write permission) | Yes |
| `update_website` | Update a website check in LogicMonitor (requires write permission) | Yes |
| `delete_website` | Delete a website check from LogicMonitor (requires write permission) | Yes |
| `create_website_group` | Create a website group in LogicMonitor (requires write permission) | Yes |
| `delete_website_group` | Delete a website group from LogicMonitor (requires write permission) | Yes |

## Reports

Report management and execution

| Tool | Description | Write |
|------|-------------|-------|
| `get_reports` | List reports from LogicMonitor | No |
| `get_report` | Get detailed information about a specific report | No |
| `get_report_groups` | List report groups | No |
| `get_scheduled_reports` | Get reports with schedules configured | No |
| `run_report` | Run/execute a report (requires write permission) | Yes |
| `get_report_execution` | Poll the status of a report generation task started by run_report (returns status and result URL when finished) | No |
| `create_report` | Create a new report (requires write permission) | Yes |
| `update_report_schedule` | Update a report's schedule (requires write permission) | Yes |
| `delete_report` | Delete a report (requires write permission) | Yes |

## Escalations

Escalation chain and recipient management

| Tool | Description | Write |
|------|-------------|-------|
| `get_escalation_chains` | List escalation chains | No |
| `get_escalation_chain` | Get details about a specific escalation chain | No |
| `get_recipient_groups` | List recipient groups | No |
| `get_recipient_group` | Get details about a specific recipient group | No |
| `create_escalation_chain` | Create an escalation chain (requires write permission) | Yes |
| `update_escalation_chain` | Update an escalation chain (requires write permission) | Yes |
| `delete_escalation_chain` | Delete an escalation chain (requires write permission) | Yes |
| `create_recipient_group` | Create a recipient group (requires write permission) | Yes |
| `update_recipient_group` | Update a recipient group (requires write permission) | Yes |
| `delete_recipient_group` | Delete a recipient group (requires write permission) | Yes |

## Integrations

Alert delivery integrations (Custom HTTP Delivery / webhooks). CRUD on /setting/integrations. Pair with escalation chains and alert rules to route alerts to Azure Sentinel, PagerDuty, ServiceNow, etc.

| Tool | Description | Write |
|------|-------------|-------|
| `get_integrations` | List LogicMonitor integrations (Custom HTTP Delivery, Slack, PagerDuty, etc.). Returns a short summary per integration. | No |
| `get_integration` | Get a specific integration's full definition. Field set depends on integration type; password/OAuth secret fields are masked. | No |
| `create_http_integration` | Create a Custom HTTP Delivery integration (type=http). Required fields: name, url. Use extra_fields for OAuth, actionNotes*, updateData*, or the 'extra' UI metadata blob. (requires write permission) | Yes |
| `update_http_integration` | Update a Custom HTTP Delivery integration via PATCH. Only fields explicitly provided are sent; omitted fields keep their current server values. (requires write permission) | Yes |
| `delete_integration` | Delete an integration by ID. Works for any integration type (http, slack-2, pagerduty, etc.). (requires write permission) | Yes |

## Users and Access

User, role, and access management

| Tool | Description | Write |
|------|-------------|-------|
| `get_users` | List users from LogicMonitor | No |
| `get_user` | Get details about a specific user | No |
| `create_user` | Create a user in LogicMonitor (requires write permission) | Yes |
| `update_user` | Update a user in LogicMonitor (requires write permission) | Yes |
| `delete_user` | Delete a user from LogicMonitor (requires write permission) | Yes |
| `get_roles` | List roles | No |
| `get_role` | Get details about a specific role | No |
| `get_access_groups` | List access groups | No |
| `get_access_group` | Get details about a specific access group | No |
| `get_api_tokens` | List API tokens | No |
| `get_api_token` | Get details about a specific API token | No |

## Topology

Network topology and connectivity

| Tool | Description | Write |
|------|-------------|-------|
| `get_topology_map` | Get network topology map data | No |
| `get_device_neighbors` | Get neighboring devices/resources based on topology | No |
| `get_device_interfaces` | Get network interfaces for a device (resource) | No |
| `get_network_flows` | Get network flow data (NetFlow/sFlow) | No |
| `get_device_connections` | Get device/resource relationships and connections | No |

## Audit

Audit logs and activity tracking

| Tool | Description | Write |
|------|-------------|-------|
| `get_audit_logs` | Get audit logs from LogicMonitor | No |
| `get_api_token_audit` | Get API token usage audit logs | No |
| `get_login_audit` | Get login/authentication audit logs | No |
| `get_change_audit` | Get configuration change audit logs | No |

## Cost Optimization

Cloud cost analysis and optimization

| Tool | Description | Write |
|------|-------------|-------|
| `get_cost_recommendations` | Get cost optimization recommendations. Category filter takes the category description string from get_cost_recommendation_categories | No |
| `get_cost_recommendation_categories` | Get cost recommendation categories with counts and savings | No |
| `get_cost_recommendation` | Get a specific cost recommendation by ID (v224 API) | No |

## LogicModules

LogicModule definitions (ConfigSource, EventSource, etc.)

| Tool | Description | Write |
|------|-------------|-------|
| `get_configsources` | List ConfigSources | No |
| `get_configsource` | Get details about a specific ConfigSource | No |
| `create_configsource` | Create a ConfigSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as export_configsource output). For LM Exchange format, use import_configsource. | Yes |
| `delete_configsource` | Delete a ConfigSource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_configsource_update_reasons` | Get update history and audit trail for a ConfigSource | No |
| `get_device_config` | List config versions collected for a device instance | No |
| `get_device_config_version` | Get a specific config version with full content and diffs | No |
| `collect_device_config` | Trigger an on-demand config collection for a device instance | Yes |
| `get_eventsources` | List EventSources | No |
| `get_eventsource` | Get details about a specific EventSource | No |
| `create_eventsource` | Create an EventSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as export_eventsource output). For LM Exchange format, use import_eventsource. | Yes |
| `delete_eventsource` | Delete an EventSource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_device_eventsources` | Get EventSources applied to a device (resource). Returns device-level EventSource associations. | No |
| `update_device_eventsource` | Update a device-level EventSource association (requires write permission). Use to enable or disable alerting for an EventSource on a specific device. | Yes |
| `get_propertysources` | List PropertySources | No |
| `get_propertysource` | Get details about a specific PropertySource | No |
| `create_propertysource` | Create a PropertySource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as export_propertysource output). Use for round-tripping exports or building definitions from scratch. For LM Exchange format, use import_propertysource. | Yes |
| `delete_propertysource` | Delete a PropertySource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_topologysources` | List TopologySources | No |
| `get_topologysource` | Get details about a specific TopologySource | No |
| `create_topologysource` | Create a TopologySource via REST API from a full definition dict (requires write permission). Accepts REST API format. For LM Exchange format, use import_topologysource. | Yes |
| `delete_topologysource` | Delete a TopologySource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_logsources` | List LogSources | No |
| `get_logsource` | Get details about a specific LogSource | No |
| `create_logsource` | Create a LogSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as export_logsource output). For LM Exchange format, use import_logsource. | Yes |
| `delete_logsource` | Delete a LogSource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_device_logsources` | Get LogSources applied to a device (resource) | No |

## Netscans

Network scan management

| Tool | Description | Write |
|------|-------------|-------|
| `get_netscans` | List network scans | No |
| `get_netscan` | Get details about a specific network scan | No |
| `run_netscan` | Execute a network scan (requires write permission) | Yes |

## Ops, OIDs, and Services

Operations notes, OIDs, and services

| Tool | Description | Write |
|------|-------------|-------|
| `get_oids` | List OID definitions | No |
| `get_oid` | Get details about a specific OID | No |
| `get_services` | List Service Insight business services (deviceType 6 devices, including APM trace services) | No |
| `get_service` | Get details about a specific Service Insight service | No |
| `get_service_groups` | List Service Insight service groups (BizService device groups) | No |
| `get_ops_notes` | List ops notes | No |
| `get_ops_note` | Get details about a specific ops note | No |
| `add_ops_note` | Add an ops note (requires write permission) | Yes |
| `update_ops_note` | Update an ops note (requires write permission) | Yes |
| `delete_ops_note` | Delete an ops note (requires write permission) | Yes |

## Batch Jobs

Batch job monitoring

| Tool | Description | Write |
|------|-------------|-------|
| `get_batchjobs` | List batch jobs | No |
| `get_batchjob` | Get details about a specific batch job | No |
| `get_device_batchjobs` | List BatchJob datasources applied to a device (resource); per-run output lives in instance data via get_device_data | No |
| `get_scheduled_downtime_jobs` | Get batch jobs related to SDT automation | No |

## Exports

Export LogicModule definitions as JSON

| Tool | Description | Write |
|------|-------------|-------|
| `export_datasource` | Export a datasource definition (REST API format). Output can be used with create_datasource. | No |
| `export_dashboard` | Export a dashboard definition | No |
| `export_alert_rule` | Export an alert rule definition | No |
| `export_escalation_chain` | Export an escalation chain definition | No |
| `export_configsource` | Export a ConfigSource definition (REST API format). Output can be used with create_configsource. | No |
| `export_eventsource` | Export an EventSource definition (REST API format). Output can be used with create_eventsource. | No |
| `export_propertysource` | Export a PropertySource definition (REST API format). Output can be used with create_propertysource. | No |
| `export_logsource` | Export a LogSource definition (REST API format). Output can be used with create_logsource. | No |
| `export_diagnosticsource` | Export a DiagnosticSource definition (REST API format). Output can be used with create_diagnosticsource. | No |
| `export_remediationsource` | Export a RemediationSource definition (REST API format). Output can be used with create_remediationsource. | No |

## Imports

Import LogicModule definitions from JSON

| Tool | Description | Write |
|------|-------------|-------|
| `import_datasource` | Import a DataSource from LM Exchange JSON format via multipart upload (requires write permission). This expects LM Exchange format, not REST API format. For REST API format definitions (e.g., from export_datasource), use create_datasource instead. | Yes |
| `import_configsource` | Import a ConfigSource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from export_configsource), use create_configsource instead. | Yes |
| `import_eventsource` | Import an EventSource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from export_eventsource), use create_eventsource instead. | Yes |
| `import_propertysource` | Import a PropertySource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from export_propertysource), use create_propertysource instead. | Yes |
| `import_logsource` | Import a LogSource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from export_logsource), use create_logsource instead. | Yes |
| `import_topologysource` | Import a TopologySource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions, use create_topologysource instead. | Yes |
| `import_diagnosticsource` | Import a DiagnosticSource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from export_diagnosticsource), use create_diagnosticsource instead. | Yes |
| `import_jobmonitor` | Import a JobMonitor from JSON (requires write permission) | Yes |
| `import_appliesto_function` | Import an AppliesTo function from JSON (requires write permission) | Yes |

## Ingestion

Push custom logs and metrics

| Tool | Description | Write |
|------|-------------|-------|
| `ingest_logs` | Ingest log entries into LogicMonitor (requires LMv1 auth) | Yes |
| `push_metrics` | Push custom metrics into LogicMonitor (requires LMv1 auth) | Yes |

## OTLP Metrics

Native OTLP metrics: PromQL range queries and metric/label discovery (feature-flag gated, [PREVIEW])

| Tool | Description | Write |
|------|-------------|-------|
| `get_otlp_metric_names` | [PREVIEW] List metric names ingested via native OpenTelemetry (OTLP). Requires the OTLP Metrics feature flag; returns a friendly notice when unavailable | No |
| `get_otlp_metric_labels` | [PREVIEW] List label names on native OTLP metrics, optionally narrowed to one metric | No |
| `get_otlp_label_values` | [PREVIEW] List values observed for one native OTLP metric label (e.g. all service_name values) | No |
| `query_otlp_metrics` | [PREVIEW] Run a PromQL range query against native OTLP metrics. Returns a time-series matrix | No |

## Correlation

Alert-window analysis: statistics, clusters, noise, bursts and changes

| Tool | Description | Write |
|------|-------------|-------|
| `analyze_alerts` | Analyze one alert window: call this for how many alerts fired and when, which alerts belong together, how noisy alerting is, which datasources burst, or which portal changes preceded a spike over the last hours. One read of the window's active and cleared alerts, under the severity, device, group and datasource filters, feeds every section; 'statistics' gives active and cleared totals, counts by severity, the ten busiest devices and datasources, and the volume of each hour, cleared alerts included; 'clusters' groups two or more alerts by device, by datasource and by signature (datasource and datapoint), with their alert ids and first and last start times; 'noise' gives a 0 to 100 score from the entropy of alerts over datasource and datapoint (weight 40), flaps, an alert on the same device and datapoint that re-fires within 30 minutes of clearing (30), and repeats, a combination with three or more alerts (30), with the first ten flap pairs and tuning recommendations; 'bursts' gives the windows of window_seconds on one datasource that hold at least min_alerts alerts on min_devices devices; 'changes' reads the audit log once and pairs each write action (create, add, update, delete, remove or modify) with the first 5-minute alert spike, a bucket above the mean by one standard deviation, within correlation_window_minutes after it, with a confidence from 1.0 to 0.5. truncated says when the 5000-alert cap cut either read short. Use get_alerts to list or page through the alerts themselves. | No |

## APM Traces

APM trace service discovery, metrics, and properties

| Tool | Description | Write |
|------|-------------|-------|
| `get_trace_services` | List APM trace services (deviceType:6). Entry point for discovering traced services. | No |
| `get_trace_service` | Get detailed information about a specific APM trace service | No |
| `get_trace_service_alerts` | Get alerts for an APM trace service | No |
| `get_trace_service_datasources` | List datasources applied to an APM service (e.g. LogicMonitor_APM_Services, _Operations) | No |
| `get_trace_operations` | List operations (endpoints/routes) for an APM service datasource | No |
| `get_trace_service_metrics` | Get APM service-level RED metrics (Duration, ErrorOperationCount, OperationCount) | No |
| `get_trace_operation_metrics` | Get per-operation RED metrics (Duration, ErrorOperationCount, OperationCount) | No |
| `get_trace_service_properties` | Get properties for an APM service (OTel attributes, namespace, metadata) | No |

## ML and Statistical Analysis

ML/statistical analysis and forecasting

| Tool | Description | Write |
|------|-------------|-------|
| `correlate_metrics` | Compute Pearson correlation between multiple metric series. Builds an NxN correlation matrix and highlights strong correlations (\|r\| > 0.7). Maximum 10 sources. | No |
| `calculate_availability` | Calculate availability percentage from alert history. Computes SLA-style uptime metrics, MTTR, and per-device breakdown from the window's cleared and active alerts, read as two lists; truncated says when the 5000-alert cap cut either read short. Common mistakes: hours_back defaults to 720 (30 days). Narrow scope with device_id/group_id for performance. | No |
| `analyze_blast_radius` | Analyze the blast radius of a device failure using topology data. Traverses neighbors to identify downstream impact and scores overall blast radius (0-100). | No |
| `analyze_metric` | Analyze one device instance's metric series: call this for statistics on a datapoint's recent history, such as its current level against the window, whether it is rising, its daily cycle, when it shifted, or which samples stand out. One paged read of the window feeds every section; 'summary' gives latest, mean, standard deviation, min, max and the latest sample's signed z-score; 'trend' gives least-squares and Theil-Sen slopes per hour, r-squared, coefficient of variation, the detrended 24-hour autocorrelation and a label (volatile, cyclic, increasing, decreasing or stable); 'seasonality' gives detrended autocorrelation at 1, 4, 12, 24 and 168 hours, the dominant period and the peak hours in UTC; 'change_points' gives level shifts, where the mean of the next 30 samples leaves the mean of the previous 30 by five times the noise in that comparison (measured with any steady trend and autocorrelation the noise has), with the daily cycle removed first when the window holds three days or more and that leaves less noise; each shift has its timestamp and the levels before and after it, less the daily cycle when that was removed. A change in the last 30 samples is not reported yet, small shifts in strongly autocorrelated noise go unfound, on a window under a day a change inflates the noise and smaller shifts go unfound, and changes about a day apart in a few days leave the cycle in and go unfound; 'anomalies' gives z-score, IQR and MAD hits, each method's 20 most extreme; 'forecast' gives the least-squares and Holt-Winters (daily season, two days of samples needed) slopes per hour and, with threshold, when each crosses it, within 30 days; 'baseline' compares the window with one as long ending baseline_hours_ago hours ago (one more read): both windows' statistics, the mean's percent deviation and a status (normal within 20 percent, elevated or reduced within 50, anomalous past it). The baseline runs only with baseline_hours_ago. Use get_device_data for the raw samples. | No |
| `calculate_error_budget` | Calculate SLO error budget consumption and projected exhaustion date. Computes remaining budget, burn rate, and status (healthy/warning/critical/exhausted) based on actual availability vs target SLO. | No |

## Session

Session context, variable management, and history

| Tool | Description | Write |
|------|-------------|-------|
| `get_session_context` | Get current session context (variables and history) | No |
| `set_session_variable` | Set a user-defined session variable for use across tool calls | No |
| `get_session_variable` | Get a user-defined session variable | No |
| `delete_session_variable` | Delete a user-defined session variable | No |
| `clear_session_context` | Clear all session context (variables and history) | No |
| `list_session_history` | List recent tool call history | No |

## Portals

Multi-portal switching: one server, many customer portals

| Tool | Description | Write |
|------|-------------|-------|
| `list_portals` | List the customer portals available in this multi-portal server. | No |
| `use_portal` | Switch the active customer portal for subsequent tool calls. | No |
| `current_portal` | Show which customer portal is currently active. | No |
| `reload_portals` | Re-read the vault so portals added or removed since startup take effect without restarting the client. | No |

## Terraform

Export LogicMonitor resources as Terraform HCL

| Tool | Description | Write |
|------|-------------|-------|
| `terraform_generate` | Export an existing LogicMonitor resource as Terraform HCL configuration using the logicmonitor/logicmonitor provider. Supports device, device_group, collector, alert_rule, escalation_chain, dashboard, datasource, sdt, website, role, and report_group resource types. | No |

## Remediation

Diagnostic sources, remediation sources, and remediation execution.

| Tool | Description | Write |
|------|-------------|-------|
| `get_diagnosticsources` | List DiagnosticSources from LogicMonitor | No |
| `get_diagnosticsource` | Get details about a specific DiagnosticSource including datapoints | No |
| `get_remediationsources` | List RemediationSources from LogicMonitor | No |
| `get_remediationsource` | Get details about a specific RemediationSource including the Groovy script | No |
| `get_diagnostic_remediation_assignments` | List the diagnostic and remediation sources assigned to a specific resource or alert (Automated Diagnostics & Remediation). Unlike get_diagnosticsources/get_remediationsources, this resolves which modules actually apply to the target. | No |
| `get_diagnostic_remediation_results` | Get structured execution results for diagnostic and remediation source runs: status, trigger type, executor, script output, and timing. Provide exactly one of alert_id or host_id. Time window params are epoch milliseconds; result timestamps are epoch seconds. | No |
| `execute_remediation` | Execute a RemediationSource script on a target device. Performs pre-execution checks (collector version, device status, script review) before triggering manual execution. Requires write permission. | Yes |
| `execute_diagnostic` | Execute a DiagnosticSource script on a target device. Performs pre-execution checks (collector version, device status, script review) before triggering manual execution. Poll get_diagnostic_remediation_results for status and output. Requires write permission. | Yes |
| `create_diagnosticsource` | Create a DiagnosticSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as export_diagnosticsource output). For LM Exchange format, use import_diagnosticsource. | Yes |
| `delete_diagnosticsource` | Delete a DiagnosticSource definition (requires write permission). Action chains referencing it lose that stage. | Yes |
| `create_remediationsource` | Create a RemediationSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as export_remediationsource output). RemediationSources have no LM Exchange import endpoint. | Yes |
| `delete_remediationsource` | Delete a RemediationSource definition (requires write permission). Action chains referencing it lose that stage. | Yes |

## Actions

ADR automation: action chains (ordered diagnostic/remediation stages) and the rules that bind them to alerts.

| Tool | Description | Write |
|------|-------------|-------|
| `get_action_chains` | List action chains: ordered DiagnosticSource/RemediationSource stages that action rules trigger on alerts (Automated Diagnostics & Remediation) | No |
| `get_action_chain` | Get details about a specific action chain including its stages | No |
| `create_action_chain` | Create an action chain from ordered diagnostic/remediation stages (requires write permission). Each stage references a DiagnosticSource or RemediationSource by ID. | Yes |
| `update_action_chain` | Update an action chain via PATCH; only provided fields are sent (requires write permission) | Yes |
| `delete_action_chain` | Delete an action chain (requires write permission). Action rules referencing it stop triggering. | Yes |
| `get_action_rules` | List action rules: alert conditions (severity, device groups, datasource matchers) that trigger action chains | No |
| `get_action_rule` | Get details about a specific action rule | No |
| `create_action_rule` | Create an action rule binding an action chain to alert conditions (requires write permission) | Yes |
| `update_action_rule` | Update an action rule via PATCH; only provided fields are sent (requires write permission) | Yes |
| `delete_action_rule` | Delete an action rule (requires write permission) | Yes |
| `set_action_rule_status` | Enable or disable an action rule without touching its matchers (requires write permission) | Yes |

## Usage examples for the ML and statistical tools

These tools use pure-Python statistical methods (no external ML libraries). They all operate on data fetched from the LM API at query time. Most metric-based tools share the same core parameters: `device_id`, `device_datasource_id`, `instance_id` (find these using `get_device_datasources` and `get_device_instances`).

**Capacity forecasting** -- predict when a metric will breach a threshold:
```
"Forecast when memory usage on device 150098 will exceed 90%"
```
Uses `analyze_metric` with `analyses=["forecast"]` and `threshold=90`. Returns the least-squares and Holt-Winters slopes per hour and, for each method, when it crosses the threshold within 30 days (`breach_eta` in epoch seconds, `hours_until_breach`, `direction`), or the reason it does not. Holt-Winters fits a daily season and needs two days of samples; `hours` defaults to 168 (one week).

**Metric correlation** -- find relationships between metrics across devices:
```
"Correlate CPU usage on server A with memory usage on server B over the last 24 hours"
```
Uses `correlate_metrics` with a `sources` array. Each source requires `device_id`, `device_datasource_id`, `instance_id`, and `datapoint` name. Returns an NxN Pearson correlation matrix and highlights strong correlations (|r| > 0.7). Maximum 10 sources per call.

**Change point detection** -- find when metric behavior shifted:
```
"Detect any level shifts in CPU metrics on device 150098 over the last week"
```
Uses `analyze_metric` with `analyses=["change_points"]`. A shift is reported where the mean of the next 30 samples leaves the mean of the previous 30 by five times the noise in that comparison, with the daily cycle removed first when the window holds three days or more and that leaves less noise. Returns each shift's timestamp and the levels before and after it. A change in the last 30 samples is not reported yet.

**Alert noise scoring** -- identify tuning opportunities:
```
"Score the alert noise across all devices over the last 24 hours"
```
Uses `analyze_alerts` with `analyses=["noise"]`. Returns a 0-100 noise score combining Shannon entropy, flap detection (alerts that clear and re-fire within 30 minutes), and repeat ratio. Includes top noisy devices/datasources and tuning recommendations.

**Metric status and anomalies** -- how far the latest samples sit from the window:
```
"How far from normal are the stress-demo pod's metrics right now?"
```
Uses `analyze_metric` with `analyses=["summary", "anomalies"]`. The summary gives each datapoint's latest value, mean, standard deviation, min, max and the latest sample's signed z-score; the anomalies section gives z-score, IQR and MAD hits, each method's 20 most extreme. `health_check` runs both sections on the first instance of up to five datasources.

**Availability calculation** -- SLA reporting from alert data:
```
"Calculate 30-day availability across all devices at error severity or above"
```
Uses `calculate_availability` with `hours_back=720` and `severity_threshold="error"`. Merges overlapping alert windows and returns availability %, MTTR, incident count, longest incident, and per-device breakdown.
