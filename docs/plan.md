# LogicMonitor Platform MCP Server — Implementation Plan

## Document Info
- **Version:** 1.0
- **Created:** 2024-12-12
- **Spec:** mcp_spec.md
- **State:** todo.md

---

## Phase Overview

| Phase | Description | Steps |
|-------|-------------|-------|
| 1 | Project Foundation | 1.1 - 1.4 |
| 2 | Authentication | 2.1 - 2.4 |
| 3 | API Client | 3.1 - 3.4 |
| 4 | MCP Server Shell | 4.1 - 4.3 |
| 5 | Alert Tools (Read) | 5.1 - 5.3 |
| 6 | Alert Tools (Write) | 6.1 - 6.3 |
| 7 | SDT Tools | 7.1 - 7.3 |
| 8 | Device Tools | 8.1 - 8.2 |
| 9 | Collector Tools | 9.1 - 9.2 |
| 10 | Integration & Polish | 10.1 - 10.3 |

---

## Phase 1: Project Foundation

### Step 1.1 — Initialize Project Structure

**Goal:** Create the Python project with uv, basic structure, and dependencies.

**Prompt:**

```text
Create a new Python project for a LogicMonitor MCP server called "logicmonitor-mcp".

Requirements:
1. Use `uv` for package management
2. Python 3.11+ required
3. Create pyproject.toml with these dependencies:
   - mcp>=1.0.0 (MCP SDK)
   - httpx>=0.27.0 (HTTP client)
   - pydantic>=2.0.0 (validation)
   - python-dotenv>=1.0.0 (env loading)
   
4. Dev dependencies:
   - pytest>=8.0.0
   - pytest-asyncio>=0.23.0
   - respx>=0.21.0 (httpx mocking)
   - ruff>=0.4.0 (linting)

5. Create this directory structure:
   ```
   logicmonitor-mcp/
   ├── pyproject.toml
   ├── README.md
   ├── .env.example
   ├── src/
   │   └── lm_mcp/
   │       └── __init__.py
   └── tests/
       └── __init__.py
   ```

6. In pyproject.toml, configure:
   - Package name: lm-mcp
   - Entry point script: lm-mcp = "lm_mcp.server:main"
   - pytest-asyncio mode = "auto"
   - ruff rules: E, F, I, W

7. Create .env.example with placeholder variables:
   - LM_PORTAL
   - LM_AUTH_METHOD
   - LM_ACCESS_ID
   - LM_ACCESS_KEY
   - LM_BEARER_TOKEN

8. Initialize with `uv sync` to verify it works.

Do not create any application code yet, just the project skeleton.
```

---

### Step 1.2 — Configuration Module

**Goal:** Create configuration loading with validation.

**Prompt:**

```text
In the logicmonitor-mcp project, create the configuration module.

Create src/lm_mcp/config.py with:

1. A Pydantic Settings class `LMConfig` that loads from environment:
   - portal: str (required) - The LogicMonitor portal hostname
   - auth_method: Literal["lmv1", "bearer"] (default "lmv1")
   - access_id: str | None (required if auth_method is lmv1)
   - access_key: str | None (required if auth_method is lmv1)
   - bearer_token: str | None (required if auth_method is bearer)
   - api_version: int (default 3)
   - timeout: int (default 30)

2. Add a validator that:
   - Raises ValueError if auth_method is "lmv1" but access_id or access_key is missing
   - Raises ValueError if auth_method is "bearer" but bearer_token is missing
   - Strips "https://" and trailing slashes from portal if present

3. Add a property `base_url` that returns: f"https://{self.portal}/santaba/rest"

4. Use model_config to set env_prefix = "LM_"

Create tests/test_config.py with tests for:
- Loading valid lmv1 config from env
- Loading valid bearer config from env
- Validation error when lmv1 missing credentials
- Validation error when bearer missing token
- Portal URL normalization

Use pytest fixtures and monkeypatch for env vars. Run tests to verify.
```

---

### Step 1.3 — Exception Classes

**Goal:** Define custom exceptions for error handling.

**Prompt:**

```text
In the logicmonitor-mcp project, create the exceptions module.

Create src/lm_mcp/exceptions.py with these exception classes:

1. Base exception:
   ```python
   class LMError(Exception):
       """Base exception for LogicMonitor MCP errors."""
       def __init__(self, message: str, code: str = "LM_ERROR", suggestion: str = None):
           self.message = message
           self.code = code
           self.suggestion = suggestion
           super().__init__(message)
       
       def to_dict(self) -> dict:
           """Return error as dict for tool responses."""
           result = {"error": True, "code": self.code, "message": self.message}
           if self.suggestion:
               result["suggestion"] = self.suggestion
           return result
   ```

2. Specific exceptions inheriting from LMError:
   - ConfigurationError (code: "CONFIG_ERROR")
   - AuthenticationError (code: "AUTH_FAILED") 
   - PermissionError (code: "PERMISSION_DENIED")
   - NotFoundError (code: "NOT_FOUND")
   - RateLimitError (code: "RATE_LIMITED") - add retry_after: int attribute
   - ServerError (code: "SERVER_ERROR")
   - ConnectionError (code: "CONNECTION_FAILED")

3. Each should have a sensible default suggestion message.

Create tests/test_exceptions.py with tests for:
- Each exception can be raised and caught
- to_dict() returns expected structure
- RateLimitError includes retry_after in dict

Run tests to verify.
```

---

### Step 1.4 — Verify Foundation

**Goal:** Ensure all foundation pieces work together.

**Prompt:**

```text
Verify the logicmonitor-mcp foundation is solid.

1. Update src/lm_mcp/__init__.py to export:
   - LMConfig from config
   - All exceptions from exceptions

2. Create a simple test in tests/test_foundation.py that:
   - Imports LMConfig and all exceptions
   - Verifies LMConfig can be instantiated with mock env vars
   - Verifies exceptions can be raised and converted to dict

3. Run the full test suite with `uv run pytest -v`

4. Run ruff check with `uv run ruff check src tests`

5. Fix any issues found.

The foundation is complete when all tests pass and ruff reports no issues.
```

---

## Phase 2: Authentication

### Step 2.1 — Auth Provider Interface

**Goal:** Define the abstract interface for auth providers.

**Prompt:**

```text
In the logicmonitor-mcp project, create the authentication provider interface.

Create src/lm_mcp/auth/__init__.py with:

1. An abstract base class `AuthProvider`:
   ```python
   from abc import ABC, abstractmethod
   
   class AuthProvider(ABC):
       @abstractmethod
       def get_auth_headers(
           self, 
           method: str, 
           resource_path: str, 
           body: str = ""
       ) -> dict[str, str]:
           """
           Generate authentication headers for a request.
           
           Args:
               method: HTTP method (GET, POST, etc.)
               resource_path: API path (e.g., /alert/alerts)
               body: Request body as string (for POST/PUT)
           
           Returns:
               Dict of headers to add to the request
           """
           pass
   ```

2. Export AuthProvider from the module.

No tests needed for abstract class - we'll test the implementations.
```

---

### Step 2.2 — Bearer Token Authentication

**Goal:** Implement the simpler bearer auth first.

**Prompt:**

```text
In the logicmonitor-mcp project, implement Bearer token authentication.

Create src/lm_mcp/auth/bearer.py with:

1. A class `BearerAuth` that implements `AuthProvider`:
   ```python
   class BearerAuth(AuthProvider):
       def __init__(self, token: str):
           if not token:
               raise ConfigurationError("Bearer token is required")
           self.token = token
       
       def get_auth_headers(self, method: str, resource_path: str, body: str = "") -> dict[str, str]:
           # Return the Authorization header with Bearer token
           pass
   ```

2. The header format should be: `{"Authorization": "Bearer {token}"}`

Create tests/test_auth/test_bearer.py with tests for:
- BearerAuth raises ConfigurationError if token is empty/None
- get_auth_headers returns correct Authorization header
- Method, path, body parameters don't affect the output (bearer is static)

Run tests to verify.
```

---

### Step 2.3 — LMv1 HMAC Authentication

**Goal:** Implement the more complex LMv1 signature-based auth.

**Prompt:**

```text
In the logicmonitor-mcp project, implement LMv1 HMAC authentication.

Create src/lm_mcp/auth/lmv1.py with:

1. A class `LMv1Auth` that implements `AuthProvider`:
   ```python
   import hmac
   import hashlib
   import base64
   import time
   
   class LMv1Auth(AuthProvider):
       def __init__(self, access_id: str, access_key: str):
           if not access_id or not access_key:
               raise ConfigurationError("Access ID and Key are required for LMv1 auth")
           self.access_id = access_id
           self.access_key = access_key
       
       def _get_timestamp(self) -> int:
           """Return current time in epoch milliseconds."""
           return int(time.time() * 1000)
       
       def _build_signature_string(
           self, 
           method: str, 
           timestamp: int, 
           resource_path: str, 
           body: str
       ) -> str:
           """Build the string to sign: METHOD + TIMESTAMP + BODY + PATH"""
           return f"{method}{timestamp}{body}{resource_path}"
       
       def _calculate_signature(self, string_to_sign: str) -> str:
           """Calculate HMAC-SHA256 signature, base64 encoded."""
           signature = hmac.new(
               self.access_key.encode('utf-8'),
               string_to_sign.encode('utf-8'),
               hashlib.sha256
           ).digest()
           return base64.b64encode(signature).decode('utf-8')
       
       def get_auth_headers(self, method: str, resource_path: str, body: str = "") -> dict[str, str]:
           """Generate LMv1 auth header."""
           timestamp = self._get_timestamp()
           string_to_sign = self._build_signature_string(method, timestamp, resource_path, body)
           signature = self._calculate_signature(string_to_sign)
           
           auth_value = f"LMv1 {self.access_id}:{signature}:{timestamp}"
           return {"Authorization": auth_value}
   ```

2. Make _get_timestamp injectable for testing (or use a factory pattern).

Create tests/test_auth/test_lmv1.py with tests for:
- LMv1Auth raises ConfigurationError if access_id or access_key missing
- _build_signature_string concatenates correctly
- _calculate_signature produces valid base64 HMAC-SHA256
- get_auth_headers returns properly formatted LMv1 header
- Use a fixed timestamp in tests to verify exact signature output

Example test with known values:
- access_id: "test_id"
- access_key: "test_key"
- method: "GET"
- timestamp: 1700000000000
- path: "/alert/alerts"
- body: ""
- Verify the exact signature matches expected output

Run tests to verify.
```

---

### Step 2.4 — Auth Factory

**Goal:** Create factory function to instantiate correct auth provider from config.

**Prompt:**

```text
In the logicmonitor-mcp project, create an auth factory.

Update src/lm_mcp/auth/__init__.py to add:

1. A factory function:
   ```python
   def create_auth_provider(config: LMConfig) -> AuthProvider:
       """Create the appropriate auth provider based on config."""
       if config.auth_method == "bearer":
           return BearerAuth(config.bearer_token)
       elif config.auth_method == "lmv1":
           return LMv1Auth(config.access_id, config.access_key)
       else:
           raise ConfigurationError(f"Unknown auth method: {config.auth_method}")
   ```

2. Export BearerAuth, LMv1Auth, and create_auth_provider.

Create tests/test_auth/test_factory.py with tests for:
- create_auth_provider returns BearerAuth when config.auth_method is "bearer"
- create_auth_provider returns LMv1Auth when config.auth_method is "lmv1"
- Factory-created providers work correctly (call get_auth_headers)

Run full test suite: `uv run pytest -v tests/test_auth/`
```

---

## Phase 3: API Client

### Step 3.1 — Basic HTTP Client

**Goal:** Create the base API client with request/response handling.

**Prompt:**

```text
In the logicmonitor-mcp project, create the LogicMonitor API client.

Create src/lm_mcp/client/__init__.py and src/lm_mcp/client/api.py with:

1. An async client class:
   ```python
   import httpx
   from lm_mcp.auth import AuthProvider
   from lm_mcp.exceptions import (
       AuthenticationError, PermissionError, NotFoundError,
       RateLimitError, ServerError, ConnectionError as LMConnectionError
   )
   
   class LogicMonitorClient:
       def __init__(
           self, 
           base_url: str, 
           auth: AuthProvider,
           timeout: int = 30,
           api_version: int = 3
       ):
           self.base_url = base_url.rstrip('/')
           self.auth = auth
           self.api_version = api_version
           self._client = httpx.AsyncClient(timeout=timeout)
       
       async def close(self):
           """Close the HTTP client."""
           await self._client.aclose()
       
       async def __aenter__(self):
           return self
       
       async def __aexit__(self, *args):
           await self.close()
       
       def _get_headers(self, method: str, path: str, body: str = "") -> dict:
           """Build request headers including auth."""
           headers = {
               "Content-Type": "application/json",
               "X-Version": str(self.api_version)
           }
           headers.update(self.auth.get_auth_headers(method, path, body))
           return headers
       
       def _handle_error_response(self, response: httpx.Response) -> None:
           """Raise appropriate exception for error responses."""
           # Implement based on status code
           pass
       
       async def request(
           self,
           method: str,
           path: str,
           params: dict = None,
           json_body: dict = None
       ) -> dict:
           """Make an authenticated request to the LM API."""
           pass
   ```

2. Implement _handle_error_response to map status codes:
   - 401 -> AuthenticationError
   - 403 -> PermissionError  
   - 404 -> NotFoundError
   - 429 -> RateLimitError (parse Retry-After header if present)
   - 5xx -> ServerError

3. Implement request() method:
   - Build full URL
   - Get headers with auth
   - Handle httpx.ConnectError -> LMConnectionError
   - Call _handle_error_response for non-2xx
   - Return parsed JSON

4. Add convenience methods: get(), post(), put(), patch(), delete()

Create tests/test_client/test_api.py with:
- Use respx to mock HTTP responses
- Test successful GET request
- Test successful POST request  
- Test each error status code maps to correct exception
- Test connection error handling
- Test auth headers are included

Run tests: `uv run pytest -v tests/test_client/`
```

---

### Step 3.2 — Response Parsing

**Goal:** Add structured response parsing for LM API responses.

**Prompt:**

```text
In the logicmonitor-mcp project, enhance the API client with response parsing.

Update src/lm_mcp/client/api.py to add:

1. A response parsing method:
   ```python
   def _parse_response(self, response: httpx.Response) -> dict:
       """Parse LM API response, handling pagination info."""
       data = response.json()
       
       # v3 API returns data directly at root level (not wrapped in 'data')
       # But list endpoints include pagination: total, searchId, items
       
       return {
           "data": data.get("items", data),  # items for lists, or whole response
           "total": data.get("total"),
           "search_id": data.get("searchId"),
           "raw": data
       }
   ```

2. Update request() to use _parse_response and return just the data by default,
   but allow returning full response with a parameter.

3. Add a paginated request helper:
   ```python
   async def get_all(
       self, 
       path: str, 
       params: dict = None,
       max_items: int = None
   ) -> list:
       """Fetch all items from a paginated endpoint."""
       # Implement pagination using offset/size
       pass
   ```

Update tests to verify:
- Response parsing extracts items correctly
- Pagination info is captured
- get_all fetches multiple pages (mock paginated responses)

Run tests to verify.
```

---

### Step 3.3 — Client Factory

**Goal:** Create factory to build client from config.

**Prompt:**

```text
In the logicmonitor-mcp project, create a client factory.

Update src/lm_mcp/client/__init__.py to add:

1. A factory function:
   ```python
   from lm_mcp.config import LMConfig
   from lm_mcp.auth import create_auth_provider
   from lm_mcp.client.api import LogicMonitorClient
   
   def create_client(config: LMConfig) -> LogicMonitorClient:
       """Create a LogicMonitor client from config."""
       auth = create_auth_provider(config)
       return LogicMonitorClient(
           base_url=config.base_url,
           auth=auth,
           timeout=config.timeout,
           api_version=config.api_version
       )
   ```

2. Export create_client and LogicMonitorClient.

Create tests/test_client/test_factory.py with tests for:
- create_client returns LogicMonitorClient with correct base_url
- Client has working auth provider (verify headers are set)

Run tests to verify.
```

---

### Step 3.4 — Integration Test for Client

**Goal:** Verify full client works end-to-end with mocked API.

**Prompt:**

```text
In the logicmonitor-mcp project, create integration tests for the client.

Create tests/test_client/test_integration.py with:

1. A pytest fixture that:
   - Sets up mock env vars for LMv1 config
   - Creates a client via create_client()
   - Sets up respx mocking for the portal

2. Integration tests that:
   - Mock a successful /alert/alerts response with sample alert data
   - Verify client.get("/alert/alerts") returns parsed alerts
   - Mock a 403 response and verify PermissionError is raised
   - Mock a paginated response (2 pages) and verify get_all() returns all items

3. Sample alert response to mock:
   ```json
   {
     "items": [
       {
         "id": "LMA123",
         "severity": 3,
         "type": "dataSourceAlert",
         "monitorObjectName": "server01",
         "resourceId": 42,
         "alertValue": "95",
         "threshold": "> 90",
         "startEpoch": 1700000000
       }
     ],
     "total": 1,
     "searchId": "abc123"
   }
   ```

Run full client test suite: `uv run pytest -v tests/test_client/`
```

---

## Phase 4: MCP Server Shell

### Step 4.1 — Basic MCP Server

**Goal:** Create the minimal MCP server that starts and responds.

**Prompt:**

```text
In the logicmonitor-mcp project, create the MCP server shell.

Create src/lm_mcp/server.py with:

1. Basic MCP server setup using the mcp library:
   ```python
   import asyncio
   from mcp.server import Server
   from mcp.server.stdio import stdio_server
   
   from lm_mcp.config import LMConfig
   from lm_mcp.client import create_client, LogicMonitorClient
   
   # Create server instance
   server = Server("logicmonitor-platform")
   
   # Global client (initialized on startup)
   _client: LogicMonitorClient | None = None
   
   def get_client() -> LogicMonitorClient:
       """Get the initialized client."""
       if _client is None:
           raise RuntimeError("Client not initialized")
       return _client
   
   @server.list_tools()
   async def list_tools():
       """Return list of available tools."""
       return []  # We'll add tools in later steps
   
   async def run_server():
       """Run the MCP server."""
       global _client
       
       # Load config and create client
       config = LMConfig()
       _client = create_client(config)
       
       try:
           async with stdio_server() as (read_stream, write_stream):
               await server.run(
                   read_stream,
                   write_stream,
                   server.create_initialization_options()
               )
       finally:
           if _client:
               await _client.close()
   
   def main():
       """Entry point."""
       asyncio.run(run_server())
   
   if __name__ == "__main__":
       main()
   ```

2. Verify entry point in pyproject.toml: lm-mcp = "lm_mcp.server:main"

3. Test that the server can be imported without errors:
   ```python
   # tests/test_server.py
   def test_server_import():
       from lm_mcp.server import server, main
       assert server.name == "logicmonitor-platform"
   ```

Run: `uv run pytest -v tests/test_server.py`
```

---

### Step 4.2 — Tool Registration Pattern

**Goal:** Establish the pattern for registering tools.

**Prompt:**

```text
In the logicmonitor-mcp project, create the tool registration pattern.

Create src/lm_mcp/tools/__init__.py with:

1. A base function for formatting tool responses:
   ```python
   from mcp.types import TextContent
   import json
   
   def format_response(data: any) -> list[TextContent]:
       """Format data as MCP TextContent response."""
       if isinstance(data, dict) and data.get("error"):
           # Error response
           text = f"Error: {data['message']}"
           if data.get("suggestion"):
               text += f"\nSuggestion: {data['suggestion']}"
           return [TextContent(type="text", text=text)]
       
       # Success response
       if isinstance(data, (dict, list)):
           text = json.dumps(data, indent=2, default=str)
       else:
           text = str(data)
       
       return [TextContent(type="text", text=text)]
   
   def handle_error(e: Exception) -> list[TextContent]:
       """Convert exception to MCP response."""
       from lm_mcp.exceptions import LMError
       
       if isinstance(e, LMError):
           return format_response(e.to_dict())
       else:
           return format_response({
               "error": True,
               "code": "UNEXPECTED_ERROR",
               "message": str(e)
           })
   ```

2. Create a simple test tool to verify the pattern works.

Update src/lm_mcp/server.py to:
1. Import the tools module
2. Register a test tool (we'll replace it later):
   ```python
   @server.tool()
   async def ping() -> list[TextContent]:
       """Test tool that returns pong."""
       return format_response({"status": "pong"})
   ```

Create tests/test_tools/__init__.py and tests/test_tools/test_base.py:
- Test format_response with dict data
- Test format_response with list data
- Test format_response with error dict
- Test handle_error with LMError
- Test handle_error with generic Exception

Run: `uv run pytest -v tests/test_tools/`
```

---

### Step 4.3 — Server Startup Test

**Goal:** Verify server can start and list tools.

**Prompt:**

```text
In the logicmonitor-mcp project, verify the server starts correctly.

Create tests/test_server_startup.py with:

1. A test that verifies the server can be initialized:
   ```python
   import pytest
   from unittest.mock import patch, AsyncMock
   
   @pytest.fixture
   def mock_config(monkeypatch):
       """Set up mock config env vars."""
       monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
       monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
       monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
   
   def test_server_has_name(mock_config):
       from lm_mcp.server import server
       assert server.name == "logicmonitor-platform"
   
   @pytest.mark.asyncio
   async def test_list_tools_returns_ping(mock_config):
       from lm_mcp.server import server
       tools = await server.list_tools()
       tool_names = [t.name for t in tools]
       assert "ping" in tool_names
   ```

2. Run the tests and verify they pass.

3. Manually test the server can start (will fail without stdin, but shouldn't crash on import):
   ```bash
   uv run python -c "from lm_mcp.server import server; print(server.name)"
   ```

Run: `uv run pytest -v tests/test_server_startup.py`
```

---

## Phase 5: Alert Tools (Read)

### Step 5.1 — Get Alerts Tool

**Goal:** Implement the first real tool - get_alerts.

**Prompt:**

```text
In the logicmonitor-mcp project, implement the get_alerts tool.

Create src/lm_mcp/tools/alerts.py with:

1. The get_alerts tool:
   ```python
   from mcp.server import Server
   from mcp.types import TextContent
   from lm_mcp.tools import format_response, handle_error
   from lm_mcp.server import get_client
   
   def register_alert_tools(server: Server):
       """Register alert-related tools with the server."""
       
       @server.tool()
       async def get_alerts(
           severity: str = None,
           status: str = None,
           limit: int = 50
       ) -> list[TextContent]:
           """
           Get alerts from LogicMonitor.
           
           Args:
               severity: Filter by severity - "critical", "error", "warning", or "all"
               status: Filter by acknowledgement status - "active", "acknowledged", or "all"  
               limit: Maximum number of alerts to return (default 50, max 1000)
           
           Returns:
               List of alerts with id, severity, device, message, and timestamp
           """
           try:
               client = get_client()
               
               # Build filter parameters
               params = {"size": min(limit, 1000)}
               filters = []
               
               if severity and severity != "all":
                   severity_map = {"critical": 4, "error": 3, "warning": 2}
                   if severity in severity_map:
                       filters.append(f"severity:{severity_map[severity]}")
               
               if status == "active":
                   filters.append("acked:false")
               elif status == "acknowledged":
                   filters.append("acked:true")
               
               if filters:
                   params["filter"] = ",".join(filters)
               
               response = await client.get("/alert/alerts", params=params)
               
               # Format alerts for readability
               alerts = []
               for alert in response.get("data", []):
                   alerts.append({
                       "id": alert.get("id"),
                       "severity": _severity_name(alert.get("severity")),
                       "device": alert.get("monitorObjectName"),
                       "datapoint": alert.get("dataPointName"),
                       "message": alert.get("alertValue"),
                       "threshold": alert.get("threshold"),
                       "started": alert.get("startEpoch"),
                       "acked": alert.get("acked", False)
                   })
               
               return format_response({
                   "count": len(alerts),
                   "total_matching": response.get("total", len(alerts)),
                   "alerts": alerts
               })
               
           except Exception as e:
               return handle_error(e)
       
   def _severity_name(severity: int) -> str:
       """Convert severity int to name."""
       return {4: "critical", 3: "error", 2: "warning", 1: "info"}.get(severity, "unknown")
   ```

2. Update src/lm_mcp/server.py to import and register:
   ```python
   from lm_mcp.tools.alerts import register_alert_tools
   
   # After server = Server(...)
   register_alert_tools(server)
   ```

Create tests/test_tools/test_alerts.py with:
- Mock the client.get() method using respx
- Test get_alerts with no filters
- Test get_alerts with severity filter
- Test get_alerts with status filter
- Test error handling when API fails
- Verify response format is correct

Run: `uv run pytest -v tests/test_tools/test_alerts.py`
```

---

### Step 5.2 — Get Alert Details Tool

**Goal:** Add tool to get a single alert's details.

**Prompt:**

```text
In the logicmonitor-mcp project, add the get_alert_details tool.

Update src/lm_mcp/tools/alerts.py to add within register_alert_tools():

```python
@server.tool()
async def get_alert_details(alert_id: str) -> list[TextContent]:
    """
    Get detailed information about a specific alert.
    
    Args:
        alert_id: The alert ID (e.g., "LMA12345" or just "12345")
    
    Returns:
        Full alert details including device info, thresholds, and history
    """
    try:
        client = get_client()
        
        # Normalize alert ID (remove LMA prefix if present)
        clean_id = alert_id.replace("LMA", "").replace("lma", "")
        
        response = await client.get(f"/alert/alerts/{clean_id}")
        alert = response.get("data", response)
        
        # Format detailed response
        details = {
            "id": alert.get("id"),
            "internal_id": alert.get("internalId"),
            "severity": _severity_name(alert.get("severity")),
            "type": alert.get("type"),
            "device": {
                "name": alert.get("monitorObjectName"),
                "id": alert.get("resourceId"),
                "groups": alert.get("resourceTemplateName")
            },
            "datasource": {
                "name": alert.get("dataSourceName"),
                "instance": alert.get("instanceName"),
                "datapoint": alert.get("dataPointName")
            },
            "alert_info": {
                "value": alert.get("alertValue"),
                "threshold": alert.get("threshold"),
                "started": alert.get("startEpoch"),
                "cleared": alert.get("endEpoch"),
                "duration_seconds": alert.get("alertDuration")
            },
            "acknowledgement": {
                "acked": alert.get("acked", False),
                "acked_by": alert.get("ackedBy"),
                "acked_epoch": alert.get("ackedEpoch"),
                "notes": alert.get("alertNotes", [])
            }
        }
        
        return format_response(details)
        
    except Exception as e:
        return handle_error(e)
```

Update tests/test_tools/test_alerts.py to add:
- Test get_alert_details with valid ID
- Test get_alert_details with "LMA" prefixed ID
- Test get_alert_details with non-existent ID (404 response)
- Verify response includes all expected fields

Run: `uv run pytest -v tests/test_tools/test_alerts.py`
```

---

### Step 5.3 — Alert Tools Integration Test

**Goal:** Verify alert tools work with full mock server.

**Prompt:**

```text
In the logicmonitor-mcp project, create integration tests for alert tools.

Create tests/test_tools/test_alerts_integration.py with:

1. Fixtures that set up:
   - Mock environment variables
   - respx mock routes for /alert/alerts and /alert/alerts/{id}
   - Sample alert data matching real LM API responses

2. Sample response data:
   ```python
   SAMPLE_ALERTS_RESPONSE = {
       "items": [
           {
               "id": "LMA111",
               "internalId": "111",
               "severity": 4,
               "type": "dataSourceAlert",
               "monitorObjectName": "prod-server-01",
               "resourceId": 42,
               "dataSourceName": "CPU",
               "instanceName": "CPU-0",
               "dataPointName": "CPUBusyPercent",
               "alertValue": "98.5",
               "threshold": "> 95",
               "startEpoch": 1700000000,
               "acked": False
           },
           {
               "id": "LMA222",
               "internalId": "222", 
               "severity": 3,
               "type": "dataSourceAlert",
               "monitorObjectName": "prod-server-02",
               "resourceId": 43,
               "dataSourceName": "Memory",
               "instanceName": "Memory",
               "dataPointName": "MemoryUsedPercent",
               "alertValue": "91.2",
               "threshold": "> 90",
               "startEpoch": 1700001000,
               "acked": True,
               "ackedBy": "admin"
           }
       ],
       "total": 2,
       "searchId": "search123"
   }
   ```

3. Integration tests:
   - Test full flow: config -> client -> get_alerts
   - Verify correct number of alerts returned
   - Verify severity filtering works
   - Verify status filtering works
   - Test get_alert_details returns complete info

Run: `uv run pytest -v tests/test_tools/test_alerts_integration.py`

Then run full test suite: `uv run pytest -v`
```

---

## Phase 6: Alert Tools (Write)

### Step 6.1 — Acknowledge Alert Tool

**Goal:** Implement first write operation - acknowledging alerts.

**Prompt:**

```text
In the logicmonitor-mcp project, add the acknowledge_alert tool.

Update src/lm_mcp/tools/alerts.py to add within register_alert_tools():

```python
@server.tool()
async def acknowledge_alert(
    alert_id: str,
    note: str = ""
) -> list[TextContent]:
    """
    Acknowledge an alert in LogicMonitor.
    
    Args:
        alert_id: The alert ID to acknowledge (e.g., "LMA12345" or "12345")
        note: Optional note to add when acknowledging
    
    Returns:
        Confirmation of acknowledgement with alert details
    """
    try:
        client = get_client()
        
        # Normalize alert ID
        clean_id = alert_id.replace("LMA", "").replace("lma", "")
        
        # Build ack payload
        payload = {"ackComment": note} if note else {}
        
        # POST to ack endpoint
        response = await client.post(
            f"/alert/alerts/{clean_id}/ack",
            json_body=payload
        )
        
        return format_response({
            "success": True,
            "alert_id": alert_id,
            "message": f"Alert {alert_id} acknowledged successfully",
            "note_added": bool(note)
        })
        
    except Exception as e:
        return handle_error(e)
```

Update tests/test_tools/test_alerts.py to add:
- Test acknowledge_alert with just ID
- Test acknowledge_alert with ID and note
- Test acknowledge_alert with already-acked alert (should still succeed)
- Test acknowledge_alert with invalid ID (404)
- Test acknowledge_alert with permission error (403)
- Verify POST payload is correct

Run: `uv run pytest -v tests/test_tools/test_alerts.py`
```

---

### Step 6.2 — Add Alert Note Tool

**Goal:** Add tool to add notes to alerts without acknowledging.

**Prompt:**

```text
In the logicmonitor-mcp project, add the add_alert_note tool.

Update src/lm_mcp/tools/alerts.py to add within register_alert_tools():

```python
@server.tool()
async def add_alert_note(
    alert_id: str,
    note: str
) -> list[TextContent]:
    """
    Add a note to an alert without acknowledging it.
    
    Args:
        alert_id: The alert ID (e.g., "LMA12345" or "12345")
        note: The note text to add (required)
    
    Returns:
        Confirmation that the note was added
    """
    try:
        if not note or not note.strip():
            return format_response({
                "error": True,
                "code": "INVALID_INPUT",
                "message": "Note text is required",
                "suggestion": "Provide a non-empty note parameter"
            })
        
        client = get_client()
        
        # Normalize alert ID
        clean_id = alert_id.replace("LMA", "").replace("lma", "")
        
        # POST to note endpoint
        response = await client.post(
            f"/alert/alerts/{clean_id}/note",
            json_body={"ackComment": note.strip()}
        )
        
        return format_response({
            "success": True,
            "alert_id": alert_id,
            "message": f"Note added to alert {alert_id}",
            "note": note.strip()
        })
        
    except Exception as e:
        return handle_error(e)
```

Update tests/test_tools/test_alerts.py to add:
- Test add_alert_note with valid note
- Test add_alert_note with empty note (validation error)
- Test add_alert_note with whitespace-only note (validation error)
- Test add_alert_note with invalid ID (404)
- Verify POST payload is correct

Run: `uv run pytest -v tests/test_tools/test_alerts.py`
```

---

### Step 6.3 — Alert Write Tools Integration

**Goal:** Integration test for alert write operations.

**Prompt:**

```text
In the logicmonitor-mcp project, add integration tests for alert write tools.

Update tests/test_tools/test_alerts_integration.py to add:

1. Mock routes for:
   - POST /alert/alerts/{id}/ack
   - POST /alert/alerts/{id}/note

2. Tests:
   - Test acknowledge_alert flow with mock API
   - Test add_alert_note flow with mock API
   - Test error handling when API returns 403 (permission denied)
   - Verify correct HTTP method and payload sent

3. Add a combined scenario test:
   - Get alerts -> Find critical unacked -> Acknowledge with note
   - Verify each step works correctly

Run: `uv run pytest -v tests/test_tools/test_alerts_integration.py`

Then full test suite: `uv run pytest -v`
```

---

## Phase 7: SDT Tools

### Step 7.1 — List SDTs Tool

**Goal:** Implement SDT listing.

**Prompt:**

```text
In the logicmonitor-mcp project, create the SDT tools module.

Create src/lm_mcp/tools/sdts.py with:

```python
from mcp.server import Server
from mcp.types import TextContent
from lm_mcp.tools import format_response, handle_error
from lm_mcp.server import get_client
from datetime import datetime

def register_sdt_tools(server: Server):
    """Register SDT-related tools with the server."""
    
    @server.tool()
    async def list_sdts(
        active_only: bool = True,
        limit: int = 50
    ) -> list[TextContent]:
        """
        List scheduled downtime (SDT) entries.
        
        Args:
            active_only: If true, only show currently active SDTs (default true)
            limit: Maximum number of SDTs to return (default 50)
        
        Returns:
            List of SDT entries with type, target, start/end times
        """
        try:
            client = get_client()
            
            params = {"size": min(limit, 1000)}
            if active_only:
                # Filter for SDTs that are currently in effect
                now = int(datetime.now().timestamp() * 1000)
                params["filter"] = f"startDateTime<{now},endDateTime>{now}"
            
            response = await client.get("/sdt/sdts", params=params)
            
            sdts = []
            for sdt in response.get("data", []):
                sdts.append({
                    "id": sdt.get("id"),
                    "type": sdt.get("type"),
                    "target": _get_sdt_target(sdt),
                    "comment": sdt.get("comment"),
                    "start": _epoch_to_iso(sdt.get("startDateTime")),
                    "end": _epoch_to_iso(sdt.get("endDateTime")),
                    "is_effective": sdt.get("isEffective", False),
                    "created_by": sdt.get("admin")
                })
            
            return format_response({
                "count": len(sdts),
                "sdts": sdts
            })
            
        except Exception as e:
            return handle_error(e)

def _get_sdt_target(sdt: dict) -> str:
    """Extract the target name from SDT based on type."""
    sdt_type = sdt.get("type", "")
    if "Device" in sdt_type:
        return sdt.get("deviceDisplayName", "Unknown Device")
    elif "Group" in sdt_type:
        return sdt.get("deviceGroupFullPath", "Unknown Group")
    elif "DataSource" in sdt_type:
        return f"{sdt.get('deviceDisplayName', '?')}/{sdt.get('dataSourceName', '?')}"
    elif "Instance" in sdt_type:
        return f"{sdt.get('deviceDisplayName', '?')}/{sdt.get('dataSourceName', '?')}/{sdt.get('dataSourceInstanceName', '?')}"
    elif "Collector" in sdt_type:
        return sdt.get("collectorDescription", "Unknown Collector")
    else:
        return sdt.get("comment", "Unknown")

def _epoch_to_iso(epoch_ms: int) -> str:
    """Convert epoch milliseconds to ISO format string."""
    if not epoch_ms:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000).isoformat()
```

Update src/lm_mcp/server.py to register SDT tools:
```python
from lm_mcp.tools.sdts import register_sdt_tools
register_sdt_tools(server)
```

Create tests/test_tools/test_sdts.py with:
- Test list_sdts with no filters
- Test list_sdts with active_only=False
- Test _get_sdt_target for different SDT types
- Test _epoch_to_iso conversion

Run: `uv run pytest -v tests/test_tools/test_sdts.py`
```

---

### Step 7.2 — Create SDT Tool

**Goal:** Implement SDT creation.

**Prompt:**

```text
In the logicmonitor-mcp project, add the create_sdt tool.

Update src/lm_mcp/tools/sdts.py to add within register_sdt_tools():

```python
@server.tool()
async def create_sdt(
    target_type: str,
    target_id: int,
    start_time: str = None,
    end_time: str = None,
    duration_minutes: int = None,
    comment: str = ""
) -> list[TextContent]:
    """
    Create a scheduled downtime (SDT) entry.
    
    Args:
        target_type: Type of target - "device", "device_group", "datasource", "collector"
        target_id: ID of the target (device ID, group ID, etc.)
        start_time: Start time in ISO format (default: now)
        end_time: End time in ISO format (required if duration_minutes not set)
        duration_minutes: Duration in minutes (alternative to end_time)
        comment: Comment explaining the SDT
    
    Returns:
        Created SDT details including ID
    """
    try:
        client = get_client()
        
        # Validate inputs
        if not end_time and not duration_minutes:
            return format_response({
                "error": True,
                "code": "INVALID_INPUT",
                "message": "Either end_time or duration_minutes is required",
                "suggestion": "Specify how long the SDT should last"
            })
        
        # Calculate times
        if start_time:
            start_epoch = int(datetime.fromisoformat(start_time.replace('Z', '+00:00')).timestamp() * 1000)
        else:
            start_epoch = int(datetime.now().timestamp() * 1000)
        
        if end_time:
            end_epoch = int(datetime.fromisoformat(end_time.replace('Z', '+00:00')).timestamp() * 1000)
        else:
            end_epoch = start_epoch + (duration_minutes * 60 * 1000)
        
        # Map target type to SDT type
        type_map = {
            "device": "DeviceSDT",
            "device_group": "DeviceGroupSDT",
            "datasource": "DeviceDataSourceSDT",
            "collector": "CollectorSDT"
        }
        
        if target_type not in type_map:
            return format_response({
                "error": True,
                "code": "INVALID_INPUT",
                "message": f"Invalid target_type: {target_type}",
                "suggestion": f"Use one of: {', '.join(type_map.keys())}"
            })
        
        sdt_type = type_map[target_type]
        
        # Build payload
        payload = {
            "type": sdt_type,
            "startDateTime": start_epoch,
            "endDateTime": end_epoch,
            "comment": comment or "Created via MCP"
        }
        
        # Add target-specific field
        if target_type == "device":
            payload["deviceId"] = target_id
        elif target_type == "device_group":
            payload["deviceGroupId"] = target_id
        elif target_type == "datasource":
            payload["deviceDataSourceId"] = target_id
        elif target_type == "collector":
            payload["collectorId"] = target_id
        
        response = await client.post("/sdt/sdts", json_body=payload)
        sdt = response.get("data", response)
        
        return format_response({
            "success": True,
            "sdt_id": sdt.get("id"),
            "message": f"SDT created for {target_type} {target_id}",
            "start": _epoch_to_iso(start_epoch),
            "end": _epoch_to_iso(end_epoch)
        })
        
    except Exception as e:
        return handle_error(e)
```

Update tests/test_tools/test_sdts.py to add:
- Test create_sdt with duration_minutes
- Test create_sdt with end_time
- Test create_sdt with explicit start_time
- Test create_sdt with missing end/duration (validation error)
- Test create_sdt with invalid target_type
- Test create_sdt with different target types
- Verify correct payload structure for each type

Run: `uv run pytest -v tests/test_tools/test_sdts.py`
```

---

### Step 7.3 — Delete SDT Tool

**Goal:** Implement SDT deletion.

**Prompt:**

```text
In the logicmonitor-mcp project, add the delete_sdt tool.

Update src/lm_mcp/tools/sdts.py to add within register_sdt_tools():

```python
@server.tool()
async def delete_sdt(sdt_id: int) -> list[TextContent]:
    """
    Delete a scheduled downtime (SDT) entry.
    
    Args:
        sdt_id: The ID of the SDT to delete
    
    Returns:
        Confirmation of deletion
    """
    try:
        client = get_client()
        
        # First get the SDT to confirm it exists and get details
        try:
            sdt_response = await client.get(f"/sdt/sdts/{sdt_id}")
            sdt = sdt_response.get("data", sdt_response)
            target_info = _get_sdt_target(sdt)
        except Exception:
            target_info = "unknown target"
        
        # Delete the SDT
        await client.delete(f"/sdt/sdts/{sdt_id}")
        
        return format_response({
            "success": True,
            "sdt_id": sdt_id,
            "message": f"SDT {sdt_id} deleted successfully",
            "was_for": target_info
        })
        
    except Exception as e:
        return handle_error(e)
```

Update tests/test_tools/test_sdts.py to add:
- Test delete_sdt with valid ID
- Test delete_sdt with non-existent ID (404)
- Test delete_sdt with permission error (403)
- Verify DELETE request is sent to correct endpoint

Create tests/test_tools/test_sdts_integration.py with:
- Full integration test: list SDTs -> create SDT -> verify in list -> delete -> verify gone
- Use mock responses throughout

Run: `uv run pytest -v tests/test_tools/`
```

---

## Phase 8: Device Tools

### Step 8.1 — Get Devices Tool

**Goal:** Implement device listing and details.

**Prompt:**

```text
In the logicmonitor-mcp project, create the device tools module.

Create src/lm_mcp/tools/devices.py with:

```python
from mcp.server import Server
from mcp.types import TextContent
from lm_mcp.tools import format_response, handle_error
from lm_mcp.server import get_client

def register_device_tools(server: Server):
    """Register device-related tools with the server."""
    
    @server.tool()
    async def get_devices(
        group_id: int = None,
        name_filter: str = None,
        limit: int = 50
    ) -> list[TextContent]:
        """
        Get devices from LogicMonitor.
        
        Args:
            group_id: Filter to devices in this group (optional)
            name_filter: Filter devices by display name (partial match)
            limit: Maximum number of devices to return (default 50)
        
        Returns:
            List of devices with id, name, type, and status
        """
        try:
            client = get_client()
            
            params = {"size": min(limit, 1000)}
            filters = []
            
            if group_id:
                filters.append(f"hostGroupIds~{group_id}")
            
            if name_filter:
                filters.append(f"displayName~*{name_filter}*")
            
            if filters:
                params["filter"] = ",".join(filters)
            
            response = await client.get("/device/devices", params=params)
            
            devices = []
            for device in response.get("data", []):
                devices.append({
                    "id": device.get("id"),
                    "name": device.get("displayName"),
                    "hostname": device.get("name"),
                    "type": device.get("deviceType"),
                    "collector_id": device.get("preferredCollectorId"),
                    "status": _device_status(device),
                    "groups": [g.get("fullPath") for g in device.get("hostGroupIds", []) if isinstance(g, dict)]
                })
            
            return format_response({
                "count": len(devices),
                "total_matching": response.get("total", len(devices)),
                "devices": devices
            })
            
        except Exception as e:
            return handle_error(e)
    
    @server.tool()
    async def get_device(device_id: int) -> list[TextContent]:
        """
        Get detailed information about a specific device.
        
        Args:
            device_id: The device ID
        
        Returns:
            Full device details including properties and monitoring info
        """
        try:
            client = get_client()
            
            response = await client.get(f"/device/devices/{device_id}")
            device = response.get("data", response)
            
            # Get custom properties
            custom_props = {
                p.get("name"): p.get("value")
                for p in device.get("customProperties", [])
            }
            
            details = {
                "id": device.get("id"),
                "name": device.get("displayName"),
                "hostname": device.get("name"),
                "description": device.get("description"),
                "type": device.get("deviceType"),
                "collector": {
                    "id": device.get("preferredCollectorId"),
                    "description": device.get("preferredCollectorDescription")
                },
                "status": _device_status(device),
                "monitoring": {
                    "disable_alerting": device.get("disableAlerting", False),
                    "sdt_status": device.get("sdtStatus"),
                    "alert_status": device.get("alertStatus")
                },
                "groups": device.get("hostGroupIds", []),
                "properties": custom_props,
                "created": device.get("createdOn"),
                "updated": device.get("updatedOn")
            }
            
            return format_response(details)
            
        except Exception as e:
            return handle_error(e)

def _device_status(device: dict) -> str:
    """Determine device status from various fields."""
    if device.get("disableAlerting"):
        return "alerting_disabled"
    elif device.get("sdtStatus") == "SDT":
        return "in_sdt"
    elif device.get("alertStatus") == "alert":
        return "alerting"
    else:
        return "normal"
```

Update src/lm_mcp/server.py to register device tools:
```python
from lm_mcp.tools.devices import register_device_tools
register_device_tools(server)
```

Create tests/test_tools/test_devices.py with:
- Test get_devices with no filters
- Test get_devices with group_id filter
- Test get_devices with name_filter
- Test get_device with valid ID
- Test get_device with invalid ID (404)
- Test _device_status returns correct status

Run: `uv run pytest -v tests/test_tools/test_devices.py`
```

---

### Step 8.2 — Get Device Groups Tool

**Goal:** Add device group listing.

**Prompt:**

```text
In the logicmonitor-mcp project, add the get_device_groups tool.

Update src/lm_mcp/tools/devices.py to add within register_device_tools():

```python
@server.tool()
async def get_device_groups(
    parent_id: int = None,
    name_filter: str = None,
    limit: int = 50
) -> list[TextContent]:
    """
    Get device groups from LogicMonitor.
    
    Args:
        parent_id: Filter to subgroups of this group (optional, omit for root groups)
        name_filter: Filter groups by name (partial match)
        limit: Maximum number of groups to return (default 50)
    
    Returns:
        List of device groups with id, name, path, and device count
    """
    try:
        client = get_client()
        
        params = {"size": min(limit, 1000)}
        filters = []
        
        if parent_id is not None:
            filters.append(f"parentId:{parent_id}")
        
        if name_filter:
            filters.append(f"name~*{name_filter}*")
        
        if filters:
            params["filter"] = ",".join(filters)
        
        response = await client.get("/device/groups", params=params)
        
        groups = []
        for group in response.get("data", []):
            groups.append({
                "id": group.get("id"),
                "name": group.get("name"),
                "full_path": group.get("fullPath"),
                "parent_id": group.get("parentId"),
                "device_count": group.get("numOfHosts", 0),
                "subgroup_count": group.get("numOfDirectSubGroups", 0),
                "description": group.get("description")
            })
        
        return format_response({
            "count": len(groups),
            "groups": groups
        })
        
    except Exception as e:
        return handle_error(e)
```

Update tests/test_tools/test_devices.py to add:
- Test get_device_groups with no filters
- Test get_device_groups with parent_id
- Test get_device_groups with name_filter
- Verify response structure

Run: `uv run pytest -v tests/test_tools/test_devices.py`
```

---

## Phase 9: Collector Tools

### Step 9.1 — Get Collectors Tool

**Goal:** Implement collector listing.

**Prompt:**

```text
In the logicmonitor-mcp project, create the collector tools module.

Create src/lm_mcp/tools/collectors.py with:

```python
from mcp.server import Server
from mcp.types import TextContent
from lm_mcp.tools import format_response, handle_error
from lm_mcp.server import get_client

def register_collector_tools(server: Server):
    """Register collector-related tools with the server."""
    
    @server.tool()
    async def get_collectors(
        limit: int = 50
    ) -> list[TextContent]:
        """
        Get collectors from LogicMonitor.
        
        Args:
            limit: Maximum number of collectors to return (default 50)
        
        Returns:
            List of collectors with id, hostname, status, and version
        """
        try:
            client = get_client()
            
            params = {"size": min(limit, 1000)}
            response = await client.get("/setting/collector/collectors", params=params)
            
            collectors = []
            for collector in response.get("data", []):
                collectors.append({
                    "id": collector.get("id"),
                    "description": collector.get("description"),
                    "hostname": collector.get("hostname"),
                    "status": _collector_status(collector),
                    "version": collector.get("build"),
                    "platform": collector.get("platform"),
                    "device_count": collector.get("numberOfHosts", 0),
                    "group": collector.get("collectorGroupName"),
                    "uptime": collector.get("upTime")
                })
            
            return format_response({
                "count": len(collectors),
                "collectors": collectors
            })
            
        except Exception as e:
            return handle_error(e)
    
    @server.tool()
    async def get_collector(collector_id: int) -> list[TextContent]:
        """
        Get detailed information about a specific collector.
        
        Args:
            collector_id: The collector ID
        
        Returns:
            Full collector details including configuration and status
        """
        try:
            client = get_client()
            
            response = await client.get(f"/setting/collector/collectors/{collector_id}")
            collector = response.get("data", response)
            
            details = {
                "id": collector.get("id"),
                "description": collector.get("description"),
                "hostname": collector.get("hostname"),
                "status": _collector_status(collector),
                "version": {
                    "build": collector.get("build"),
                    "platform": collector.get("platform"),
                    "arch": collector.get("arch")
                },
                "configuration": {
                    "escalating_chain_id": collector.get("escalatingChainId"),
                    "backup_collector_id": collector.get("backupAgentId"),
                    "resend_interval": collector.get("resendIval"),
                    "suppress_alert_clear": collector.get("suppressAlertClear")
                },
                "statistics": {
                    "device_count": collector.get("numberOfHosts", 0),
                    "instance_count": collector.get("numberOfInstances", 0),
                    "uptime_seconds": collector.get("upTime")
                },
                "group": {
                    "id": collector.get("collectorGroupId"),
                    "name": collector.get("collectorGroupName")
                },
                "last_seen": collector.get("lastSentNotificationOn")
            }
            
            return format_response(details)
            
        except Exception as e:
            return handle_error(e)

def _collector_status(collector: dict) -> str:
    """Determine collector status."""
    # Status is typically in a 'status' field or derived from other fields
    status = collector.get("status")
    if status:
        return status.lower()
    
    # Fallback: check if recently active
    uptime = collector.get("upTime", 0)
    if uptime > 0:
        return "active"
    return "unknown"
```

Update src/lm_mcp/server.py to register collector tools:
```python
from lm_mcp.tools.collectors import register_collector_tools
register_collector_tools(server)
```

Create tests/test_tools/test_collectors.py with:
- Test get_collectors with default params
- Test get_collector with valid ID
- Test get_collector with invalid ID (404)
- Test _collector_status with various inputs

Run: `uv run pytest -v tests/test_tools/test_collectors.py`
```

---

### Step 9.2 — Collector Tools Integration

**Goal:** Integration test for collector tools.

**Prompt:**

```text
In the logicmonitor-mcp project, add integration tests for collector tools.

Create tests/test_tools/test_collectors_integration.py with:

1. Sample collector response data:
   ```python
   SAMPLE_COLLECTORS_RESPONSE = {
       "items": [
           {
               "id": 1,
               "description": "Primary Collector",
               "hostname": "collector01.example.com",
               "status": "ok",
               "build": "34.001",
               "platform": "linux",
               "arch": "64",
               "numberOfHosts": 150,
               "numberOfInstances": 3500,
               "upTime": 864000,
               "collectorGroupId": 1,
               "collectorGroupName": "Production"
           },
           {
               "id": 2,
               "description": "Backup Collector",
               "hostname": "collector02.example.com",
               "status": "ok",
               "build": "34.001",
               "platform": "windows",
               "arch": "64",
               "numberOfHosts": 0,
               "numberOfInstances": 0,
               "upTime": 432000,
               "collectorGroupId": 1,
               "collectorGroupName": "Production"
           }
       ],
       "total": 2
   }
   ```

2. Tests:
   - Test get_collectors returns formatted list
   - Test get_collector returns full details
   - Test collector status formatting
   - Verify response structure matches expected format

Run: `uv run pytest -v tests/test_tools/test_collectors_integration.py`
```

---

## Phase 10: Integration & Polish

### Step 10.1 — Full Tool Suite Test

**Goal:** Verify all tools work together.

**Prompt:**

```text
In the logicmonitor-mcp project, create a full integration test suite.

Create tests/test_integration/test_full_suite.py with:

1. A comprehensive fixture that mocks all LM API endpoints:
   - /alert/alerts
   - /alert/alerts/{id}
   - /alert/alerts/{id}/ack
   - /alert/alerts/{id}/note
   - /sdt/sdts
   - /sdt/sdts/{id}
   - /device/devices
   - /device/devices/{id}
   - /device/groups
   - /setting/collector/collectors
   - /setting/collector/collectors/{id}

2. Test scenarios:
   - "Incident response": get_alerts -> get_alert_details -> acknowledge_alert -> add_alert_note
   - "Maintenance window": get_devices -> create_sdt -> list_sdts -> delete_sdt
   - "Health check": get_collectors -> get_devices (filter by collector)

3. Each scenario should verify:
   - Tools execute without error
   - Responses are well-formatted
   - Data flows correctly between steps

Run: `uv run pytest -v tests/test_integration/`
```

---

### Step 10.2 — Error Handling Polish

**Goal:** Ensure all error paths are handled gracefully.

**Prompt:**

```text
In the logicmonitor-mcp project, polish error handling across all tools.

1. Review each tool and ensure:
   - All exceptions are caught and converted via handle_error()
   - Input validation errors return helpful messages
   - API errors include suggestions for resolution

2. Update src/lm_mcp/exceptions.py to add:
   - Default suggestions for each error type:
     - AuthenticationError: "Check your LM_ACCESS_ID/LM_ACCESS_KEY or LM_BEARER_TOKEN"
     - PermissionError: "Your API token may lack required permissions. Contact your LM admin."
     - NotFoundError: "The requested resource does not exist. Verify the ID is correct."
     - RateLimitError: "API rate limit reached. Wait {retry_after} seconds and retry."
     - ConnectionError: "Cannot connect to LogicMonitor. Check LM_PORTAL and network access."

3. Create tests/test_error_handling.py with:
   - Test each error type is handled gracefully in tools
   - Test error responses include helpful suggestions
   - Test network errors don't crash the server

Run: `uv run pytest -v tests/test_error_handling.py`
```

---

### Step 10.3 — Documentation and README

**Goal:** Finalize documentation for release.

**Prompt:**

```text
In the logicmonitor-mcp project, create comprehensive documentation.

Update README.md with:

1. Project overview and features
2. Installation instructions:
   ```bash
   # Using uv
   uv tool install logicmonitor-mcp
   
   # Or from source
   git clone https://github.com/yourorg/logicmonitor-mcp
   cd logicmonitor-mcp
   uv sync
   ```

3. Configuration section:
   - Environment variables (LM_PORTAL, LM_AUTH_METHOD, etc.)
   - How to create API tokens in LogicMonitor
   - Example .env file

4. MCP Client configuration:
   - Claude Desktop example
   - Generic MCP client example

5. Available tools reference:
   - List all tools with brief descriptions
   - Example usage for each

6. Development section:
   - How to run tests
   - How to contribute

7. Troubleshooting section:
   - Common errors and solutions

Run the full test suite one final time:
```bash
uv run pytest -v --tb=short
uv run ruff check src tests
```

Verify all tests pass and no linting errors.
```

---

## Completion Checklist

- [ ] Phase 1: Project Foundation (1.1-1.4)
- [ ] Phase 2: Authentication (2.1-2.4)
- [ ] Phase 3: API Client (3.1-3.4)
- [ ] Phase 4: MCP Server Shell (4.1-4.3)
- [ ] Phase 5: Alert Tools - Read (5.1-5.3)
- [ ] Phase 6: Alert Tools - Write (6.1-6.3)
- [ ] Phase 7: SDT Tools (7.1-7.3)
- [ ] Phase 8: Device Tools (8.1-8.2)
- [ ] Phase 9: Collector Tools (9.1-9.2)
- [ ] Phase 10: Integration & Polish (10.1-10.3)

**MVP Complete** when all phases are checked off.
