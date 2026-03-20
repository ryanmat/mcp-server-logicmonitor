# Contributing to LogicMonitor MCP Server

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

### Prerequisites
- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) for dependency management

### Setup

```bash
# Clone the repository
git clone https://github.com/ryanmat/mcp-server-logicmonitor.git
cd mcp-server-logicmonitor

# Install dependencies
uv sync --dev

# Run tests
uv run python -m pytest -v
```

## Development Workflow

### Running Tests
```bash
# Run all tests
uv run python -m pytest -v

# Run specific test file
uv run python -m pytest tests/test_tools/test_alerts.py -v

# Run with coverage
uv run python -m pytest --cov=src/lm_mcp
```

### Code Quality
```bash
# Run linter
uv run ruff check src tests

# Auto-fix issues
uv run ruff check --fix src tests

# Format code
uv run ruff format src tests
```

## Architecture Overview

The server follows a layered architecture:

- **`server.py`** -- Entry point and MCP protocol handler. Registers tools, prompts, resources, and completions with the MCP SDK. Contains shared middleware for tool execution (field validation, write audit logging, session recording, tool filtering).
- **`registry.py`** -- Tool catalog. Defines every tool's MCP schema (name, description, parameters) and maps each to its handler function. Single source of truth for what the server exposes.
- **`tools/`** -- Handler implementations organized by domain (alerts, devices, dashboards, etc.). Each file exports async functions that take a `LogicMonitorClient` and typed parameters, returning `list[TextContent]`.
- **`client/`** -- HTTP client layer for the LogicMonitor REST API. Handles authentication (Bearer and LMv1 HMAC), retry logic, rate limit backoff, and error mapping.
- **`resources/`** -- MCP resource definitions (schema references, enum lookups, guide documents). Read-only reference data served via `resources/read`.
- **`prompts/`** -- MCP prompt templates for guided workflows (triage, health check, capacity planning). Each prompt returns a sequence of messages that walk through a multi-step analysis.
- **`completions/`** -- Auto-complete providers for tool arguments (severity levels, SDT types, device statuses).
- **`config.py`** -- Pydantic-based configuration loaded from environment variables with `LM_` prefix.
- **`session.py`** -- Session context tracking for conversational workflows (variable storage, tool call history).
- **`validation.py`** -- Field validation against known LM API schemas. Catches typos in parameter names before they hit the API.

## Adding a New Tool (Detailed)

### 1. Write the handler

Create or update the appropriate file in `src/lm_mcp/tools/`. Follow the existing async function pattern:

```python
async def get_thing(
    client: "LogicMonitorClient",
    thing_id: int,
    limit: int = 50,
) -> list[TextContent]:
    """One-line description of what this tool does.

    Args:
        client: LogicMonitor API client.
        thing_id: The thing to fetch.
        limit: Maximum results to return.
    """
    try:
        result = await client.get(f"/things/{thing_id}", params={"size": limit})
        return format_response(result)
    except Exception as e:
        return handle_error(e)
```

For write operations, add the `@require_write_permission` decorator.

### 2. Register the schema

Add a tool entry to the `TOOLS` list in `src/lm_mcp/registry.py`:

```python
{
    "name": "get_thing",
    "description": "Get a thing by ID.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "thing_id": {"type": "integer", "description": "Thing ID"},
            "limit": {"type": "integer", "description": "Max results", "default": 50},
        },
        "required": ["thing_id"],
    },
    "handler": "lm_mcp.tools.things:get_thing",
},
```

Schema property names must match the handler function parameter names exactly (excluding `client`).

### 3. Write tests

Add a test file in `tests/test_tools/` that mocks the API response and verifies the handler returns expected results:

```python
async def test_get_thing(mock_client):
    mock_client.get.return_value = {"id": 1, "name": "Test"}
    result = await get_thing(mock_client, thing_id=1)
    assert len(result) == 1
    assert "Test" in result[0].text
```

### 4. Update documentation

Add the tool to the README tool table and update tool counts in CHANGELOG.

## Transport Modes

The server supports two transport modes controlled by `LM_TRANSPORT`:

- **stdio** (default) -- Communicates via stdin/stdout using the MCP stdio protocol. Used by Claude Code, Claude Desktop, and other local MCP clients. No network listener, no authentication needed.
- **http** -- Runs a Starlette HTTP server with SSE transport. Used for remote deployments, shared team servers, and containerized setups. Configurable via `LM_HTTP_HOST`, `LM_HTTP_PORT`, and `LM_CORS_ORIGINS`.

Both transports use the same tool execution middleware, so behavior is identical regardless of mode.

## Authentication

The server supports two authentication methods for the LogicMonitor API:

- **Bearer Token** (recommended) -- Set `LM_BEARER_TOKEN` to an API Bearer token from your LogicMonitor portal (Settings > Users > API Tokens). Sufficient for all read/write REST API operations.
- **LMv1 HMAC** -- Set both `LM_ACCESS_ID` and `LM_ACCESS_KEY`. Required for ingestion APIs (`ingest_logs`, `push_metrics`). Can be used alongside Bearer token -- the server uses Bearer for REST and LMv1 for ingestion when both are configured.

Write operations (create, update, delete) are disabled by default. Set `LM_ENABLE_WRITE_OPERATIONS=true` to enable them.

## Pull Request Guidelines

1. **Fork and branch** - Create a feature branch from `main`
2. **Write tests** - All new code should have tests
3. **Pass CI** - Ensure linting and tests pass
4. **Keep it focused** - One feature or fix per PR
5. **Update docs** - Update README and CHANGELOG as needed

## Code Style

- Follow existing code patterns
- Use type hints
- Keep functions focused and small
- Write clear docstrings for public functions

## Reporting Issues

- Search existing issues before creating new ones
- Include steps to reproduce bugs
- For feature requests, explain the use case

## Questions?

Open a [GitHub Discussion](https://github.com/ryanmat/mcp-server-logicmonitor/discussions) for questions or ideas.
