# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.5.1...v1.0.0
[0.5.1]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ryanmat/mcp-server-logicmonitor/releases/tag/v0.1.0
