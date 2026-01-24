# Description: Transport abstraction layer for MCP server.
# Description: Supports stdio (default) and HTTP transports.

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Coroutine

if TYPE_CHECKING:
    from lm_mcp.config import LMConfig

__all__ = ["get_transport_runner", "run_stdio", "run_http"]


async def run_stdio() -> None:
    """Run the MCP server with stdio transport.

    This is the default transport for local AI assistant integration.
    The server communicates via stdin/stdout using JSON-RPC messages.
    """
    from mcp import stdio_server

    from lm_mcp.auth import create_auth_provider
    from lm_mcp.client import LogicMonitorClient
    from lm_mcp.config import LMConfig
    from lm_mcp.server import _set_client, server
    from lm_mcp.session import get_session

    # Load config and create client
    config = LMConfig()
    auth = create_auth_provider(config)
    client = LogicMonitorClient(
        base_url=config.base_url,
        auth=auth,
        timeout=config.timeout,
        api_version=config.api_version,
        ingest_url=config.ingest_url,
    )
    _set_client(client)

    # Initialize session with config settings
    if config.session_enabled:
        session = get_session()
        session.max_history_size = config.session_history_size

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        await client.close()


async def run_http() -> None:
    """Run the MCP server with HTTP transport.

    This transport is for remote deployments and shared access.
    Requires the 'http' optional dependencies: starlette, uvicorn.
    """
    try:
        from lm_mcp.transport.http import create_http_server
    except ImportError as e:
        raise ImportError(
            "HTTP transport requires additional dependencies. "
            "Install with: pip install lm-mcp[http]"
        ) from e

    await create_http_server()


def get_transport_runner(config: LMConfig) -> Callable[[], Coroutine]:
    """Get the transport runner based on configuration.

    Args:
        config: Server configuration with transport setting.

    Returns:
        Async function to run the server with selected transport.

    Raises:
        ValueError: If transport type is not supported.
    """
    if config.transport == "stdio":
        return run_stdio
    elif config.transport == "http":
        return run_http
    else:
        raise ValueError(f"Unsupported transport: {config.transport}")
