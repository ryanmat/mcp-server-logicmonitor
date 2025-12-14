# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.5.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ryanmat/mcp-server-logicmonitor/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ryanmat/mcp-server-logicmonitor/releases/tag/v0.1.0
