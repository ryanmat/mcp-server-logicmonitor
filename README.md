# LogicMonitor MCP Server

Model Context Protocol (MCP) server for LogicMonitor REST API v3 integration. Enables AI assistants to interact with LogicMonitor monitoring data through structured tools.

## Architecture

```
src/lm_mcp/
├── __init__.py      # Package exports
├── config.py        # Environment-based configuration (Pydantic)
├── exceptions.py    # Exception hierarchy with error codes
├── auth/
│   ├── __init__.py  # AuthProvider ABC and factory
│   └── bearer.py    # Bearer token implementation
└── client/
    ├── __init__.py  # Client exports
    └── api.py       # Async HTTP client (httpx)
```

## Installation

Requires Python 3.11+ and uv package manager.

```bash
# Clone repository
git clone https://github.com/ryanmat/mcp-server-logicmonitor.git
cd mcp-server-logicmonitor

# Install dependencies
uv sync
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
LM_PORTAL=yourcompany.logicmonitor.com
LM_BEARER_TOKEN=your_bearer_token_here
LM_API_VERSION=3
LM_TIMEOUT=30
```

Configuration is loaded via Pydantic settings. All `LM_` prefixed environment variables are automatically mapped.

## Usage

### API Client

```python
import asyncio
from lm_mcp.config import LMConfig
from lm_mcp.auth import create_auth_provider
from lm_mcp.client import LogicMonitorClient

async def main():
    config = LMConfig()
    auth = create_auth_provider(config)

    async with LogicMonitorClient(
        base_url=config.base_url,
        auth=auth,
        timeout=config.timeout,
        api_version=config.api_version,
    ) as client:
        # Get alerts
        alerts = await client.get("/alert/alerts", params={"size": 10})
        print(f"Total alerts: {alerts['total']}")

        # Get devices
        devices = await client.get("/device/devices", params={"size": 5})
        print(f"Total devices: {devices['total']}")

asyncio.run(main())
```

### Exception Handling

```python
from lm_mcp.exceptions import (
    AuthenticationError,
    RateLimitError,
    NotFoundError,
)

try:
    result = await client.get("/device/devices/999")
except NotFoundError as e:
    print(f"Device not found: {e}")
except RateLimitError as e:
    print(f"Rate limited. Retry after: {e.retry_after} seconds")
except AuthenticationError as e:
    print(f"Auth failed: {e}")
```

## Development

### Running Tests

```bash
uv run pytest -v
```

### Linting

```bash
uv run ruff check src tests
uv run ruff format src tests
```

### Project Structure

- `src/lm_mcp/` - Source code
- `tests/` - Unit and integration tests
- `docs/` - Implementation plans and specifications

## API Reference

### LogicMonitorClient

Async HTTP client supporting GET, POST, PUT, PATCH, DELETE methods.

| Method | Description |
|--------|-------------|
| `get(path, params)` | GET request with optional query params |
| `post(path, json_body)` | POST request with JSON body |
| `put(path, json_body)` | PUT request with JSON body |
| `patch(path, json_body)` | PATCH request with JSON body |
| `delete(path, params)` | DELETE request with optional params |

### Exception Hierarchy

| Exception | HTTP Status | Code |
|-----------|-------------|------|
| `LMError` | Base class | `LM_ERROR` |
| `ConfigurationError` | N/A | `CONFIGURATION_ERROR` |
| `AuthenticationError` | 401 | `AUTHENTICATION_ERROR` |
| `LMPermissionError` | 403 | `PERMISSION_ERROR` |
| `NotFoundError` | 404 | `NOT_FOUND_ERROR` |
| `RateLimitError` | 429 | `RATE_LIMIT_ERROR` |
| `ServerError` | 5xx | `SERVER_ERROR` |
| `LMConnectionError` | N/A | `CONNECTION_ERROR` |

## License

See LICENSE file.
