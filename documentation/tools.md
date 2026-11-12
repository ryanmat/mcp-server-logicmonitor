# LogicMonitor MCP Server: Tool Reference

<!-- GENERATED FILE. Do not edit by hand. Regenerate: uv run python tests/test_tools_doc.py -->

Reference for all 256 tools the LogicMonitor MCP server can advertise. The **Write** column marks the tools that change the portal; the server lists them only when `LM_ENABLE_WRITE_OPERATIONS=true`.

This file is generated from the tool registry (`src/lm_mcp/registry.py`) and the domain index (`lm://guide/tool-categories`), and kept in sync by `tests/test_tools_doc.py`. At runtime, discover tools with the `search_tools` tool.

Back to the [README](../README.md).

## Composite Workflows

Composite workflow tools -- recommended starting point

| Tool | Description | Write |
|------|-------------|-------|
| `triage` | Triage the alerts of the last hours_back hours in one call. Reads the alert window once through analyze_alerts for its statistics, clusters (by device, datasource and signature), noise and changes, then counts the blast radius of up to three device clusters, largest first. Each count row gives the devices reached as neighbors and as dependents, how many of them have a critical alert open, and how many devices' neighbors could not be read; a website cluster gets none. detail_level=full adds the devices each blast radius reached. Use analyze_alerts for bursts or a single section, and analyze_blast_radius for one device. | No |
| `health_check` | Composite health check: resolves a device, picks up to five of its datasources whose names mention CPU, memory or disk (drive, volume, filesystem), reads the first instance of each through analyze_metric (summary and anomalies over 24 hours), checks open alerts, and calculates 30-day availability. A device with none of those datasources gets an empty metrics list and a warning. | No |
| `capacity_plan` | Composite capacity planning: reads each instance once through analyze_metric to classify its trend, detect seasonality and change points, and forecast when it crosses threshold (default 90). Summary rows carry each forecast method's breach_eta (epoch seconds) and hours_until_breach per datapoint. | No |
| `portal_overview` | Shift-handoff overview of the portal: reads the alert window of the last hours_back hours once for statistics, clusters and noise, and lists the collectors and the active SDTs. detail_level=full adds up to 20 open critical and 20 open error alerts from across the portal, not only the window, and up to 20 dead devices; summary does not read them. | No |
| `diagnose` | Composite diagnosis: given an alert, or a device's latest open critical alert, gathers the alert details, device context, alerts clustered and audit changes in the last four hours, blast radius, and the device's assigned DiagnosticSources with the latest results of the alert's diagnostic runs. It reads those results and never runs a DiagnosticSource. It computes no health score or root cause; health_check reports each metric's z-score. | No |
| `update_logicmodule` | Update a LogicModule definition (configsource, datasource, diagnosticsource, eventsource, logsource, propertysource, remediationsource, topologysource). Reads the current full definition, deep-merges your `changes` onto it, validates required fields, and either returns a dry-run diff (mode='preview', default) or applies the merged definition (mode='apply'). The LogicMonitor update is full-replace, so the merged full definition is sent and fields you do not change are kept. | Yes |
| `detect_site_outage` | Composite workflow for site outage detection. Chains CollectorDown detection, mass-interface-down burst analysis, UPS on-battery events, and downstream device silence into a single site-outage verdict with confidence score, scope, and affected device list. Designed to catch the class of site-outage that generic AIOps correlation misses. Pass a device group ID representing the site. | No |
| `audit_network_monitoring_coverage` | Portal audit that counts UPS/PDU devices onboarded, interface DataSources applied, SNMP credentials configured, and NetFlow exporters set up. Returns a prioritized gap list, each gap with the onboarding step that would let the portal detect what it cannot detect today. | No |

## Universal Reference

Resource mirror exposed as a Tool for clients without that primitive

| Tool | Description | Write |
|------|-------------|-------|
| `get_reference` | Get LogicMonitor reference content (schemas, enums, filter syntax, guides). Mirrors content from MCP Resources for clients without full Resource support (Copilot cloud agent, OpenAI Codex, Cline). Categories: schema, enums, filters, syntax, guide. Pass list=true (or omit both category and name) to discover all available (category, name) pairs. | No |

## Discovery

Tool search and discovery

| Tool | Description | Write |
|------|-------------|-------|
| `search_tools` | Search the tools this server offers under its current settings by keyword, optionally within one category. Use it to find the tool for a task. It never names a tool the settings hide, so with writes off no write tool appears. Words such as 'the' and 'on' are ignored, plurals match singulars, and a query word that is a tool's full name ranks that tool first. | No |

## Devices

Device/resource management

| Tool | Description | Write |
|------|-------------|-------|
| `get_devices` | List devices (resources) from LogicMonitor, optionally filtered by name, hostname, status or device group | No |
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
| `get_alerts` | Get open or cleared alerts from LogicMonitor, optionally filtered by severity (critical, error, warning), device, group, datasource or time For Kubernetes clusters, use group_id (from get_device_groups) instead of device; the device name filter does not work reliably for K8s resources. Common mistakes: startEpoch/endEpoch use SECONDS not milliseconds. String filter values need double quotes (e.g., monitorObjectName:"hostname"). | No |
| `get_alert_details` | Get detailed information about a specific alert | No |
| `acknowledge_alert` | Acknowledge an alert (requires write permission) Common mistakes: alert_id works with or without the LMA prefix. | Yes |
| `add_alert_note` | Add a note to an alert without acknowledging (requires write permission) | Yes |
| `bulk_acknowledge_alerts` | Acknowledge multiple alerts at once (max 100, requires write permission) | Yes |

## Alert Rules

Alert rule configuration

| Tool | Description | Write |
|------|-------------|-------|
| `get_alert_rules` | List alert rules: each rule's priority and the escalation chain it routes matching alerts to | No |
| `get_alert_rule` | Get details about a specific alert rule | No |
| `create_alert_rule` | Create an alert rule in LogicMonitor (requires write permission) | Yes |
| `update_alert_rule` | Update an alert rule in LogicMonitor (requires write permission) | Yes |
| `delete_alert_rule` | Delete an alert rule from LogicMonitor (requires write permission) | Yes |

## Scheduled Downtime (SDT)

Scheduled downtime management

| Tool | Description | Write |
|------|-------------|-------|
| `get_sdts` | List scheduled downtimes from LogicMonitor | No |
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
| `get_collector_events` | List one collector's events, newest first: agent and sbproxy restarts, credential rotation, and reports that the collector is unreachable, each with its time and build. Use it for a collector's recent history; get_collector_health gives its current state. | No |
| `get_collector_log_files` | List the log files a collector has uploaded to the portal, as zip files with their size and upload time. A collector uploads them through Send Logs to LogicMonitor in the portal or the !uploadlog debug command, so an empty list means nothing was uploaded. Read one with get_collector_log_file. | No |
| `get_collector_log_file` | Read one uploaded collector log file, named as get_collector_log_files lists it, and return the end of its text: at most max_bytes bytes, starting on a whole line. truncated says whether earlier lines were left out. | No |
| `get_collector_upgrade_history` | List the portal's collector version upgrades, each row as the API returns it. | No |
| `run_collector_status_check` | Trigger a collector status check (requires write permission) and wait up to 45 seconds for its result: script counts and the checks that are not OK. An unreachable collector refuses the trigger. A check still running after the wait returns finished false; get_collector_health with the collector_id reads it later. | Yes |
| `restart_collector` | Restart a collector (requires write permission). It sends the collector's own size and config files back with the restart, so neither changes, and returns the async job id of the restart and the size it kept. | Yes |
| `acknowledge_collector_down` | Acknowledge a down collector's alert with a comment (requires write permission). The portal refuses it for a collector that is up. | Yes |
| `update_collector` | Update a collector (requires write permission). Change group, description, failback, or escalation chain. | Yes |
| `delete_collector` | Delete a collector (requires write permission). Blocks if devices are still assigned. | Yes |
| `create_collector_group` | Create a collector group (requires write permission) | Yes |
| `update_collector_group` | Update a collector group (requires write permission) | Yes |
| `delete_collector_group` | Delete a collector group (requires write permission). Blocks if collectors are still assigned. | Yes |
| `get_collector_health` | Enriched collector status: whether each collector is down, downstream device count, uptime, and optional alert history. Leading indicator for site-level events. Prefer this over `get_collectors` when investigating potential outages. The collector asked for by collector_id, and each collector not known to be up, carries evidence: its latest status check and its five latest events. | No |

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
| `get_device_data` | Get the raw metric values (samples) of a device/resource datasource instance, such as CPU, memory or disk usage Common mistakes: Returns the last hour unless start_time or end_time is given. Requires device_datasource_id (from get_device_datasources) not the datasource definition ID. | No |
| `get_graph_data` | Get graph image data for visualization | No |
| `get_datasources` | List datasources from LogicMonitor | No |
| `get_datasource` | Get details about a specific datasource | No |
| `create_datasource` | Create a DataSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as get_datasource with raw=true). Use for round-tripping exports or building definitions from scratch. For LM Exchange format, use import_datasource. Script DataSource datapoints require appropriate type values. | Yes |
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
| `get_audit_logs` | Read the portal audit log: call this for who did what and when. kind='all' returns one page of entries, newest first; kind='change' returns the configuration changes (create, update, delete or import, read from each entry's description) found in a pool of the newest entries, with scanned and has_more; kind='login' returns portal sign-ins, sign-outs and failed logins, one query per login wording (up to six calls), with status and method per row, success_only or failed_only, and total as a lower bound while has_more is true; kind='api_token' returns the rows naming an API token, given by access_id or token_id (read to its access ID), keeping only that exact access ID, with event (change, rejected, throttled), path and method per row. username is an exact name or a comma-separated list; action and resource_type (kinds all and change) are whole words the description holds (the portal applies one, the second is matched on the fetched page); start_time and end_time bound the entry time in epoch seconds. System and automation actors (System:*, LogicMonitor Internal, cloud auto-delete) are dropped after the fetch for kinds all and change unless exclude_system is false or a username is given; dropped counts them and paging follows the rows the portal returned. An argument another kind reads is refused. offset plus the rows read must stay within 10,000, and the filter within about 900 characters. | No |

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
| `create_configsource` | Create a ConfigSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as get_configsource with raw=true). For LM Exchange format, use import_configsource. | Yes |
| `delete_configsource` | Delete a ConfigSource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_configsource_update_reasons` | Get update history and audit trail for a ConfigSource | No |
| `get_device_config` | List config versions collected for a device instance | No |
| `get_device_config_version` | Get a specific config version with full content and diffs | No |
| `collect_device_config` | Trigger an on-demand config collection for a device instance | Yes |
| `get_eventsources` | List EventSources | No |
| `get_eventsource` | Get details about a specific EventSource | No |
| `create_eventsource` | Create an EventSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as get_eventsource with raw=true). For LM Exchange format, use import_eventsource. | Yes |
| `delete_eventsource` | Delete an EventSource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_device_eventsources` | Get EventSources applied to a device (resource). Returns device-level EventSource associations. | No |
| `update_device_eventsource` | Update a device-level EventSource association (requires write permission). Use to enable or disable alerting for an EventSource on a specific device. | Yes |
| `get_propertysources` | List PropertySources | No |
| `get_propertysource` | Get details about a specific PropertySource | No |
| `create_propertysource` | Create a PropertySource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as get_propertysource with raw=true). Use for round-tripping exports or building definitions from scratch. For LM Exchange format, use import_propertysource. | Yes |
| `delete_propertysource` | Delete a PropertySource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_topologysources` | List TopologySources | No |
| `get_topologysource` | Get details about a specific TopologySource | No |
| `create_topologysource` | Create a TopologySource via REST API from a full definition dict (requires write permission). Accepts REST API format. For LM Exchange format, use import_topologysource. | Yes |
| `delete_topologysource` | Delete a TopologySource definition (requires write permission). Existing collected data is retained. | Yes |
| `get_logsources` | List LogSources | No |
| `get_logsource` | Get details about a specific LogSource | No |
| `create_logsource` | Create a LogSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as get_logsource with raw=true). For LM Exchange format, use import_logsource. | Yes |
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

## Imports

Import LogicModule definitions from JSON

| Tool | Description | Write |
|------|-------------|-------|
| `import_datasource` | Import a DataSource from LM Exchange JSON format via multipart upload (requires write permission). This expects LM Exchange format, not REST API format. For REST API format definitions (e.g., from get_datasource with raw=true), use create_datasource instead. | Yes |
| `import_configsource` | Import a ConfigSource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from get_configsource with raw=true), use create_configsource instead. | Yes |
| `import_eventsource` | Import an EventSource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from get_eventsource with raw=true), use create_eventsource instead. | Yes |
| `import_propertysource` | Import a PropertySource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from get_propertysource with raw=true), use create_propertysource instead. | Yes |
| `import_logsource` | Import a LogSource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from get_logsource with raw=true), use create_logsource instead. | Yes |
| `import_topologysource` | Import a TopologySource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions, use create_topologysource instead. | Yes |
| `import_diagnosticsource` | Import a DiagnosticSource from LM Exchange JSON format via multipart upload (requires write permission). For REST API format definitions (e.g., from get_diagnosticsource with raw=true), use create_diagnosticsource instead. | Yes |
| `import_jobmonitor` | Import a JobMonitor from JSON (requires write permission) | Yes |
| `import_appliesto_function` | Import an AppliesTo function from JSON (requires write permission) | Yes |

## Ingestion

Push custom logs and metrics

| Tool | Description | Write |
|------|-------------|-------|
| `ingest_logs` | Ingest log entries into LogicMonitor (requires LMv1 auth) | Yes |
| `push_metrics` | Push custom metrics into LogicMonitor (requires LMv1 auth) | Yes |

## Logs

LM Logs configuration and usage: pipelines, tracked queries, query groups, partitions and the usage figure

| Tool | Description | Write |
|------|-------------|-------|
| `get_log_pipelines` | List every LM Logs pipeline with its log query and the partitions it names. It returns all pipelines at once and takes no arguments. It does not search log content. | No |
| `get_tracked_log_queries` | List the portal's tracked log queries, each row as the API returns it. Use it to see which log queries the portal tracks; it does not run them. | No |
| `get_log_query_groups` | List the saved LM Logs query groups (folders) with their type, owner, permission and the queries each holds. | No |
| `get_log_partitions` | List the LM Logs partitions with whether each is active or paused, its criteria, and its active contract (state, SKU, retention, usage limit, period). Use it to check partition state and contract limits. | No |
| `get_log_usage` | Read the portal's LM Logs usage figure from /log/usage: one number, as returned. The API states no unit or period for it. | No |

## OTLP Metrics

Native OTLP metrics: PromQL range and instant queries and metric/label discovery

| Tool | Description | Write |
|------|-------------|-------|
| `get_otlp_metric_names` | List the names of metrics ingested through native OpenTelemetry (OTLP), optionally those containing a substring, to find what to query with query_otlp_metrics or analyze_metric(source="otlp"). A portal without OTLP Metrics answers with available: false | No |
| `get_otlp_metric_labels` | List the label names on native OTLP metrics, optionally narrowed to one metric or to names containing a substring | No |
| `get_otlp_label_values` | List the values observed for one native OTLP metric label, such as every service_name, optionally narrowed to one metric | No |
| `query_otlp_metrics` | Run a PromQL query against native OTLP metrics. A range query (start and end in epoch seconds, optional step) returns each series' samples over the window; instant=true returns each series' value now and takes no window. Returns at most 20 series and 500 points a series, downsampled; for statistics on a series use analyze_metric(source="otlp") | No |

## Correlation

Alert-window analysis: statistics, clusters, noise, bursts and changes

| Tool | Description | Write |
|------|-------------|-------|
| `analyze_alerts` | Analyze one alert window: call this for how many alerts fired and when, which alerts belong together, how noisy alerting is, which datasources burst, or which portal changes preceded a spike over the last hours. One read of the window's active and cleared alerts, under the severity, device, group and datasource filters, feeds every section; 'statistics' gives active and cleared totals, counts by severity, the ten busiest devices and datasources, and the volume of each hour, cleared alerts included; 'clusters' groups two or more alerts by device, by datasource and by signature (datasource and datapoint), with their alert ids and first and last start times, and a device cluster names the device_id its alerts share, null for a website or two devices under one name; 'noise' gives a 0 to 100 score from the entropy of alerts over datasource and datapoint (weight 40), flaps, an alert on the same device and datapoint that re-fires within 30 minutes of clearing (30), and repeats, a combination with three or more alerts (30), with the first ten flap pairs and tuning recommendations; 'bursts' gives the windows of window_seconds on one datasource that hold at least min_alerts alerts on min_devices devices; 'changes' reads the audit log once and pairs each change (a create, update, delete or import, read from the entry's description) with the first 5-minute alert spike, a bucket above the mean by one standard deviation, within correlation_window_minutes after it, with a confidence from 1.0 to 0.5. truncated says when the 5000-alert cap cut either read short. Use get_alerts to list or page through the alerts themselves. | No |

## APM Traces

APM trace services (deviceType 6 devices) and their alerts; the device tools read their datasources, operations, metrics and properties

| Tool | Description | Write |
|------|-------------|-------|
| `get_apm_services` | List APM trace services, the deviceType 6 devices, one page at a time. Entry point for discovering traced services; read a service's datasources, operations (the instances of its operations datasource), metrics and properties with get_device_datasources, get_device_instances, get_device_data and get_device_properties, passing the service id as device_id. | No |
| `get_apm_service_alerts` | Get the alerts on one APM trace service, one page at a time | No |

## ML and Statistical Analysis

ML/statistical analysis and forecasting

| Tool | Description | Write |
|------|-------------|-------|
| `correlate_metrics` | Compute Pearson correlation between multiple metric series. Joins the series by timestamp bucket, as wide as the coarsest series' median sample interval with finer series averaged into it, and correlates over the buckets every series holds, reported as shared_samples. Builds an NxN correlation matrix and highlights strong correlations (\|r\| > 0.7). Maximum 10 sources. | No |
| `calculate_availability` | Calculate availability percentage from alert history. Computes SLA-style uptime metrics, MTTR, and per-device breakdown from the window's cleared and active alerts, read as two lists; truncated says when the 5000-alert cap cut either read short. With target_slo it adds error_budget for the window: budget, consumed and remaining minutes, percent consumed, burn rate, projected exhaustion in days and a status (healthy, warning past 50 percent, critical past 90, exhausted). Common mistakes: hours_back defaults to 720 (30 days). Narrow scope with device_id/group_id for performance. | No |
| `analyze_blast_radius` | Count the devices a device failure could reach through topology neighbors: neighbor_count at depth 1, dependent_count beyond it, each device's alert status, and critical path devices. A device whose neighbors neither topology path answers is listed under unreadable with a warning, never counted as zero; on a portal without those routes every read is unreadable. | No |
| `analyze_metric` | Analyze one device instance's metric series, such as CPU, memory or disk usage: call this for statistics on a datapoint's recent history, such as its current level against the window, whether it is rising, its daily cycle, when it shifted, or which samples stand out. One paged read of the window feeds every section; 'summary' gives latest, mean, standard deviation, min, max and the latest sample's signed z-score; 'trend' gives least-squares and Theil-Sen slopes per hour, r-squared, coefficient of variation, the detrended 24-hour autocorrelation and a label (volatile, cyclic, increasing, decreasing or stable); 'seasonality' gives detrended autocorrelation at 1, 4, 12, 24 and 168 hours, the dominant period and the peak hours in UTC; 'change_points' gives level shifts, where the mean of the next 30 samples leaves the mean of the previous 30 by five times the noise in that comparison (measured with any steady trend and autocorrelation the noise has), with the daily cycle removed first when the window holds three days or more and that leaves less noise; each shift has its timestamp and the levels before and after it, less the daily cycle when that was removed. A change in the last 30 samples is not reported yet, small shifts in strongly autocorrelated noise go unfound, on a window under a day a change inflates the noise and smaller shifts go unfound, and changes about a day apart in a few days leave the cycle in and go unfound; 'anomalies' gives z-score, IQR and MAD hits, each method's 20 most extreme; 'forecast' gives the least-squares and Holt-Winters (daily season, two days of samples needed) slopes per hour and, with threshold, when each crosses it, within 30 days; 'baseline' compares the window with one as long ending baseline_hours_ago hours ago (one more read): both windows' statistics, the mean's percent deviation and a status (normal within 20 percent, elevated or reduced within 50, anomalous past it). The baseline runs only with baseline_hours_ago. Use get_device_data for the raw samples. With source="otlp" it reads one PromQL range query (query, hours, step) in place of a device instance and runs the same sections on each series it returns, the first 20. | No |

## Session

Session context, variable management, and history

| Tool | Description | Write |
|------|-------------|-------|
| `get_session_context` | Get current session context (variables and history) | No |
| `set_session_variable` | Set a user-defined session variable for use across tool calls | No |
| `get_session_variable` | Get a user-defined session variable | No |
| `delete_session_variable` | Delete a user-defined session variable | No |
| `clear_session_context` | Clear all session context (variables and history) | No |
| `get_session_history` | List recent tool call history | No |

## Portals

Multi-portal switching: one server, many customer portals

| Tool | Description | Write |
|------|-------------|-------|
| `get_portals` | List the customer portals available in this multi-portal server. | No |
| `use_portal` | Switch the active customer portal for subsequent tool calls. | No |
| `get_current_portal` | Show which customer portal is currently active. | No |
| `run_portal_reload` | Re-read the vault so portals added or removed since startup take effect without restarting the client. | No |

## Edwin

Edwin AI: its insights, its copy of alerts and events, its data model, its agents' tools, and Ask Edwin; listed only with Edwin credentials

| Tool | Description | Write |
|------|-------------|-------|
| `get_edwin_insights` | List the insights Edwin AI created in the last `hours`, newest first. An insight is an incident Edwin built by correlating alerts. Each row has Edwin's id and display id, state, workflow state, severity, causal CI, impacted CIs, alert count and alert keys, a link into Edwin, and once Edwin has analyzed it, its title, summary, root cause, impact, timeline, remediation, evidence, contributing factors and similar incidents. Call this to find what Edwin concluded about an incident before reading raw alerts and metrics; get_edwin_insight reads one insight whole. `total` is Edwin's count of matches; it has read exactly 10000 for a window of all time, so treat 10000 as a lower bound. A cleared insight reads severity 0. | No |
| `get_edwin_insight` | Read one Edwin AI insight by its `_id` from get_edwin_insights, with every field Edwin holds for it, including the ones get_edwin_insights leaves out. Each epoch-millisecond timestamp comes with an ISO 8601 twin. | No |
| `get_edwin_records` | List Edwin AI's own copy of the alerts or events it received in the last `hours`, newest first unless `order` says otherwise. Use it to see what Edwin correlated; LogicMonitor's alerts are read with get_alerts and insights with get_edwin_insights. `filter` takes one Edwin filterCondition condition, ANDed with the window, such as {"EQUALS": [{"type": "string", "field": "cf.eventCI"}, "web01"]}; get_edwin_metadata lists the field names. Without `columns` every field comes back except extra.* (the CI's LogicMonitor properties) and raw.* (the source record). | No |
| `get_edwin_alert_volume` | Count the alerts Edwin AI received in the last `hours`, by hour or by alert state. Returns [key, count] buckets, hour keys in epoch milliseconds, and Edwin's total for the window. The Edwin credential needs the query_aggregate scope; without it the call fails with SCOPE_MISSING naming that scope. | No |
| `get_edwin_metadata` | List Edwin AI's record types with their field counts, or with `record_type` the fields of one type, so you can name fields in get_edwin_records filters and columns. The extra.* fields, the CI's LogicMonitor properties, are counted but not listed unless `prefix` asks for them. | No |
| `get_edwin_tools` | List Edwin AI's agents, or with `agent` (such as LMDiagnosticsAgent) that agent's MCP servers and the active tools on each. The mcp_name and tool name pairs are what edwin_run_tool takes. Edwin publishes no input schema for its tools, so a tool's short_description is the only guide to its parameter names. | No |
| `edwin_run_tool` | Run one tool on one of Edwin AI's MCP servers, sending `parameters` to Edwin unchanged. Requires write permission: an Edwin tool can change the systems it connects to, and this server cannot tell which tools do, so every run is gated and audited. Take mcp_name and tool_name from get_edwin_tools; the parameter names come from the tool's short_description, since Edwin publishes no input schema. A tool that reports failure returns REJECTED_BY_TOOL with Edwin's error. | Yes |
| `ask_edwin` | Ask Edwin AI a question in plain words and wait up to 120 seconds for its answer. Edwin investigates with its own tools and returns `answer`, `reasoning` (its tool-call narration), a `conversation_id` to pass back for a follow-up, and `truncated: true` when the answer stopped early. Slower than the get_edwin_* reads; use it when a question needs Edwin's judgment rather than one of its records. | No |

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
| `create_diagnosticsource` | Create a DiagnosticSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as get_diagnosticsource with raw=true). For LM Exchange format, use import_diagnosticsource. | Yes |
| `delete_diagnosticsource` | Delete a DiagnosticSource definition (requires write permission). Action chains referencing it lose that stage. | Yes |
| `create_remediationsource` | Create a RemediationSource via REST API from a full definition dict (requires write permission). Accepts REST API format (same as get_remediationsource with raw=true). RemediationSources have no LM Exchange import endpoint. | Yes |
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
