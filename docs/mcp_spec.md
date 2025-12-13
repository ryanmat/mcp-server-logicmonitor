# LogicMonitor Platform MCP Server — Technical Specification

## Document Info
- **Version:** 1.0
- **Created:** 2024-12-12
- **Author:** Ryan (CTA) + Claude
- **Status:** Draft

---

## 1. Overview

### 1.1 Purpose
Build an MCP (Model Context Protocol) server that enables AI applications (Claude, ChatGPT, etc.) to interact with LogicMonitor portals via the REST API v3.

### 1.2 Goals
- Enable natural language management of LogicMonitor resources
- Support both internal (CTA team) and customer-facing use
- Provide read operations + low-risk write operations in MVP
- Add LogicModule development capabilities in Phase 2

### 1.3 Non-Goals
- Documentation search (separate server, deprioritized)
- Observability/predictive analytics (future PROPHET project)
- Replacing LogicMonitor UI for complex operations

---

## 2. Architecture

### 2.1 High-Level Design

```
┌─────────────────────────────────────┐
│         MCP Client                  │
│  (Claude Desktop, ChatGPT, etc.)   │
└─────────────────┬───────────────────┘
                  │ JSON-RPC 2.0 (stdio)
                  ▼
┌─────────────────────────────────────┐
│   logicmonitor-platform MCP Server  │
├─────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  │
│  │ Tool Layer  │  │  Resources   │  │
│  │             │  │              │  │
│  │ - Alerts    │  │ - API Schema │  │
│  │ - Devices   │  │ - Patterns   │  │
│  │ - SDTs      │  │              │  │
│  │ - Modules   │  │              │  │
│  └──────┬──────┘  └──────────────┘  │
│         │                           │
│  ┌──────▼──────────────────────┐    │
│  │     LM API Client           │    │
│  │  - LMv1 Auth                │    │
│  │  - Bearer Auth              │    │
│  │  - Request/Response         │    │
│  │  - Rate Limit Handling      │    │
│  └──────┬──────────────────────┘    │
└─────────┼───────────────────────────┘
          │ HTTPS
          ▼
┌─────────────────────────────────────┐
│   LogicMonitor REST API v3          │
│   https://{portal}.logicmonitor.com │
└─────────────────────────────────────┘
```

### 2.2 Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | MCP SDK available, LM SDK available |
| MCP SDK | `mcp` (official Python SDK) | Anthropic-maintained, well-documented |
| HTTP Client | `httpx` | Async support, modern API |
| Testing | `pytest` + `pytest-asyncio` | Standard, async support |
| Mocking | `respx` | Mock httpx requests |
| Package Mgmt | `uv` | Fast, per user preference |

### 2.3 Project Structure

```
logicmonitor-mcp/
├── pyproject.toml
├── README.md
├── LICENSE
├── .env.example
├── src/
│   └── lm_mcp/
│       ├── __init__.py
│       ├── server.py          # MCP server entry point
│       ├── config.py          # Configuration management
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── lmv1.py        # LMv1 HMAC authentication
│       │   └── bearer.py      # Bearer token authentication
│       ├── client/
│       │   ├── __init__.py
│       │   └── api.py         # LogicMonitor API client
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── alerts.py      # Alert tools
│       │   ├── devices.py     # Device tools
│       │   ├── sdts.py        # SDT tools
│       │   ├── collectors.py  # Collector tools
│       │   ├── dashboards.py  # Dashboard tools
│       │   └── modules.py     # LogicModule tools (Phase 2)
│       └── resources/
│           ├── __init__.py
│           └── schemas.py     # API schema resources
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Pytest fixtures
│   ├── test_auth/
│   │   ├── test_lmv1.py
│   │   └── test_bearer.py
│   ├── test_client/
│   │   └── test_api.py
│   └── test_tools/
│       ├── test_alerts.py
│       ├── test_devices.py
│       └── test_sdts.py
└── docs/
    ├── plan.md
    └── todo.md
```

---

## 3. Authentication

### 3.1 Configuration

Users configure credentials via environment variables:

```bash
# Required
LM_PORTAL=company.logicmonitor.com
LM_AUTH_METHOD=lmv1  # or "bearer"

# For LMv1 auth
LM_ACCESS_ID=your_access_id
LM_ACCESS_KEY=your_access_key

# For Bearer auth
LM_BEARER_TOKEN=your_bearer_token
```

### 3.2 LMv1 Authentication

Per LogicMonitor docs, each request requires:

```
Authorization: LMv1 {AccessId}:{Signature}:{Timestamp}
```

Where:
- `Timestamp` = Current epoch milliseconds
- `Signature` = Base64(HMAC-SHA256(AccessKey, RequestString))
- `RequestString` = `{HTTPVerb}{Timestamp}{RequestBody}{ResourcePath}`

### 3.3 Bearer Authentication

Simple header injection:

```
Authorization: Bearer {Token}
```

### 3.4 Auth Interface

```python
from abc import ABC, abstractmethod

class AuthProvider(ABC):
    @abstractmethod
    def get_headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """Return authorization headers for the request."""
        pass
```

---

## 4. API Client

### 4.1 Base Client

```python
class LogicMonitorClient:
    def __init__(self, portal: str, auth: AuthProvider):
        self.base_url = f"https://{portal}/santaba/rest"
        self.auth = auth
        self.http = httpx.AsyncClient()
    
    async def request(
        self,
        method: str,
        path: str,
        params: dict = None,
        json: dict = None
    ) -> dict:
        """Make authenticated request to LM API."""
        pass
    
    async def get(self, path: str, params: dict = None) -> dict:
        return await self.request("GET", path, params=params)
    
    async def post(self, path: str, json: dict) -> dict:
        return await self.request("POST", path, json=json)
    
    async def delete(self, path: str) -> dict:
        return await self.request("DELETE", path)
```

### 4.2 Error Handling

Map LM API errors to meaningful exceptions:

| HTTP Status | LM Error | Exception |
|-------------|----------|-----------|
| 401 | Auth failed | `AuthenticationError` |
| 403 | Permission denied | `PermissionError` |
| 404 | Not found | `NotFoundError` |
| 429 | Rate limited | `RateLimitError` |
| 5xx | Server error | `ServerError` |

### 4.3 Rate Limit Handling

- Parse `X-Rate-Limit-*` headers from responses
- Implement exponential backoff on 429
- Surface rate limit info to tools for user feedback

---

## 5. MCP Tools

### 5.1 Tool Definition Pattern

Each tool follows this pattern:

```python
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("logicmonitor-platform")

@server.tool()
async def get_alerts(
    severity: str = None,
    status: str = None,
    limit: int = 50
) -> list[TextContent]:
    """
    Get alerts from LogicMonitor.
    
    Args:
        severity: Filter by severity (critical, error, warning)
        status: Filter by status (active, acknowledged, cleared)
        limit: Maximum number of alerts to return (default 50)
    
    Returns:
        List of alerts with id, severity, message, device, timestamp
    """
    # Implementation
    pass
```

### 5.2 MVP Tools (Phase 1)

#### Alerts

| Tool | Method | Endpoint | Risk |
|------|--------|----------|------|
| `get_alerts` | GET | `/alert/alerts` | Read |
| `get_alert_details` | GET | `/alert/alerts/{id}` | Read |
| `acknowledge_alert` | POST | `/alert/alerts/{id}/ack` | Low |
| `add_alert_note` | POST | `/alert/alerts/{id}/note` | Low |

#### SDTs

| Tool | Method | Endpoint | Risk |
|------|--------|----------|------|
| `list_sdts` | GET | `/sdt/sdts` | Read |
| `get_sdt` | GET | `/sdt/sdts/{id}` | Read |
| `create_sdt` | POST | `/sdt/sdts` | Low |
| `delete_sdt` | DELETE | `/sdt/sdts/{id}` | Low |

#### Devices

| Tool | Method | Endpoint | Risk |
|------|--------|----------|------|
| `get_devices` | GET | `/device/devices` | Read |
| `get_device` | GET | `/device/devices/{id}` | Read |
| `get_device_groups` | GET | `/device/groups` | Read |
| `get_device_data` | GET | `/device/devices/{id}/data` | Read |

#### Collectors

| Tool | Method | Endpoint | Risk |
|------|--------|----------|------|
| `get_collectors` | GET | `/setting/collector/collectors` | Read |
| `get_collector` | GET | `/setting/collector/collectors/{id}` | Read |

#### Dashboards

| Tool | Method | Endpoint | Risk |
|------|--------|----------|------|
| `get_dashboards` | GET | `/dashboard/dashboards` | Read |
| `get_dashboard` | GET | `/dashboard/dashboards/{id}` | Read |

### 5.3 Phase 2 Tools (LogicModule Development)

#### DataSources

| Tool | Method | Endpoint | Risk |
|------|--------|----------|------|
| `list_datasources` | GET | `/setting/datasources` | Read |
| `get_datasource` | GET | `/setting/datasources/{id}` | Read |
| `export_datasource_xml` | GET | `/setting/datasources/{id}?format=xml` | Read |
| `import_datasource_xml` | POST | `/setting/datasources` | Medium |
| `update_datasource` | PUT | `/setting/datasources/{id}` | Medium |

#### Validation (Local)

| Tool | Method | Description |
|------|--------|-------------|
| `validate_groovy_syntax` | Local | Check Groovy syntax validity |
| `lint_groovy_code` | Local | Check against monitoring-recipes standards |

---

## 6. MCP Resources

### 6.1 Static Resources

```python
@server.resource("lm://api-schema")
async def get_api_schema() -> str:
    """LogicMonitor REST API v3 schema reference."""
    return API_SCHEMA_JSON

@server.resource("lm://groovy-patterns")
async def get_groovy_patterns() -> str:
    """Common Groovy patterns for LogicModule development."""
    return GROOVY_PATTERNS_MD
```

---

## 7. Error Handling Strategy

### 7.1 Tool Error Response

Tools return structured errors that the AI can interpret:

```python
{
    "error": True,
    "code": "PERMISSION_DENIED",
    "message": "Your API token lacks 'manage' permission for alerts",
    "suggestion": "Ask your LogicMonitor admin to grant acknowledge permission"
}
```

### 7.2 Connection Errors

```python
{
    "error": True,
    "code": "CONNECTION_FAILED",
    "message": "Could not connect to company.logicmonitor.com",
    "suggestion": "Verify LM_PORTAL is correct and portal is accessible"
}
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

- Auth signature calculation (LMv1)
- Request building
- Response parsing
- Error mapping

### 8.2 Integration Tests (Mocked)

- Full tool execution with mocked API responses
- Error handling paths
- Rate limit handling

### 8.3 Live Tests (Optional, Manual)

- Marked with `@pytest.mark.live`
- Skipped by default
- Run with `pytest --live` against real portal

---

## 9. Configuration Schema

### 9.1 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LM_PORTAL` | Yes | — | Portal hostname (e.g., `company.logicmonitor.com`) |
| `LM_AUTH_METHOD` | No | `lmv1` | Auth method: `lmv1` or `bearer` |
| `LM_ACCESS_ID` | If LMv1 | — | LMv1 Access ID |
| `LM_ACCESS_KEY` | If LMv1 | — | LMv1 Access Key |
| `LM_BEARER_TOKEN` | If Bearer | — | Bearer token |
| `LM_API_VERSION` | No | `3` | API version |
| `LM_TIMEOUT` | No | `30` | Request timeout in seconds |

### 9.2 MCP Client Configuration

Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "uv",
      "args": ["run", "lm-mcp"],
      "env": {
        "LM_PORTAL": "company.logicmonitor.com",
        "LM_AUTH_METHOD": "bearer",
        "LM_BEARER_TOKEN": "your-token-here"
      }
    }
  }
}
```

---

## 10. Release Phases

### Phase 1: MVP (Read + Low-Risk Writes)
- Project setup
- LMv1 + Bearer authentication
- Alert tools (get, acknowledge, note)
- SDT tools (list, create, delete)
- Device tools (get, list)
- Collector tools (get, list)

### Phase 2: Extended Operations
- Dashboard tools
- Report tools
- Device data queries
- Threshold updates

### Phase 3: LogicModule Development
- DataSource CRUD
- Groovy validation
- Script generation helpers

---

## 11. Success Criteria

### MVP Complete When:
1. User can configure portal + credentials
2. User can query alerts via natural language
3. User can acknowledge alerts
4. User can create/delete SDTs
5. User can query devices and collectors
6. All operations have test coverage
7. Errors provide actionable feedback

### Phase 2 Complete When:
1. User can manage LogicModules
2. User can validate Groovy scripts
3. User can export/import DataSources

---

## Appendix A: LogicMonitor API Reference

- Swagger: `https://{portal}.logicmonitor.com/santaba/rest/swagger.json`
- Docs: https://www.logicmonitor.com/support/rest-api-v3-swagger-documentation
- Auth: https://www.logicmonitor.com/support/rest-api-authentication

## Appendix B: MCP Protocol Reference

- Spec: https://spec.modelcontextprotocol.io/
- Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Getting Started: https://modelcontextprotocol.io/docs/getting-started/intro
