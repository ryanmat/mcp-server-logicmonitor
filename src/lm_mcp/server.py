# Description: MCP server entry point for LogicMonitor platform.
# Description: Provides stdio transport for AI assistant integration.

import asyncio

from mcp.server import Server
from mcp.types import CompleteResult, GetPromptResult, TextContent

from lm_mcp.client import LogicMonitorClient
from lm_mcp.completions import get_completions
from lm_mcp.prompts import PROMPTS, get_prompt_messages
from lm_mcp.registry import TOOLS, get_tool_handler
from lm_mcp.resources import RESOURCES, get_resource_content

# Create server instance
server = Server("logicmonitor-platform")

# Global client (initialized on startup)
_client: LogicMonitorClient | None = None


def get_client() -> LogicMonitorClient:
    """Get the initialized LogicMonitor client.

    Returns:
        The LogicMonitor API client instance.

    Raises:
        RuntimeError: If called before server initialization.
    """
    if _client is None:
        raise RuntimeError("Client not initialized")
    return _client


@server.list_tools()
async def list_tools():
    """Return all available LogicMonitor tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a LogicMonitor tool.

    Args:
        name: Tool name to execute.
        arguments: Tool arguments.

    Returns:
        List of TextContent with the tool result.
    """
    try:
        handler = get_tool_handler(name)
        client = get_client()
        result = await handler(client, **arguments)
        return result
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error executing {name}: {e}")]


@server.list_resources()
async def list_resources():
    """Return all available LogicMonitor schema resources.

    Resources expose API field definitions, valid enum values, and filter
    syntax to help AI agents construct valid API queries.
    """
    return RESOURCES


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read the content of a LogicMonitor schema resource.

    Args:
        uri: Resource URI (e.g., 'lm://schema/alerts').

    Returns:
        JSON string containing the resource content.
    """
    try:
        content = get_resource_content(uri)
        return content
    except ValueError as e:
        raise ValueError(f"Resource not found: {uri}") from e


@server.completion()
async def complete(ref, argument) -> CompleteResult:
    """Provide auto-complete suggestions for argument values.

    Supports completions for common LogicMonitor argument names like
    severity, status, and sdt_type.

    Args:
        ref: Reference to the prompt or resource template.
        argument: The argument being completed (name and partial value).

    Returns:
        CompleteResult with matching completion values.
    """
    completion = get_completions(argument.name, argument.value)
    return CompleteResult(completion=completion)


@server.list_prompts()
async def list_prompts():
    """Return all available LogicMonitor workflow prompts.

    Prompts provide pre-built templates for common monitoring operations
    like incident triage, capacity review, and health checks.
    """
    return PROMPTS


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
    """Get the messages for a LogicMonitor workflow prompt.

    Args:
        name: Prompt name (e.g., 'incident_triage', 'health_check').
        arguments: Optional prompt arguments.

    Returns:
        GetPromptResult with workflow messages.
    """
    return get_prompt_messages(name, arguments or {})


async def run_server() -> None:
    """Run the MCP server with stdio transport."""
    global _client

    from mcp import stdio_server

    from lm_mcp.auth import create_auth_provider
    from lm_mcp.config import LMConfig

    # Load config and create client
    config = LMConfig()
    auth = create_auth_provider(config)
    _client = LogicMonitorClient(
        base_url=config.base_url,
        auth=auth,
        timeout=config.timeout,
        api_version=config.api_version,
    )

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        if _client:
            await _client.close()


def main() -> None:
    """Entry point for the MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
