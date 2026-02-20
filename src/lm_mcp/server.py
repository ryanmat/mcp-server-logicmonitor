# Description: MCP server entry point for LogicMonitor platform.
# Description: Provides shared tool execution middleware and stdio transport.

import asyncio
import json
import logging
from fnmatch import fnmatch

from mcp.server import Server
from mcp.types import CompleteResult, GetPromptResult, TextContent

from lm_mcp.client import LogicMonitorClient
from lm_mcp.completions import get_completions
from lm_mcp.config import get_config
from lm_mcp.logging import is_write_tool, log_write_operation
from lm_mcp.prompts import PROMPTS, get_prompt_messages
from lm_mcp.registry import AWX_TOOLS, EDA_TOOLS, TOOLS, get_tool_handler
from lm_mcp.resources import RESOURCES, get_resource_content
from lm_mcp.session import get_session
from lm_mcp.validation import infer_resource_type, validate_fields, validate_filter_fields

logger = logging.getLogger(__name__)

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


def _set_client(client: LogicMonitorClient) -> None:
    """Set the global LogicMonitor client.

    Called by transport runners during initialization.

    Args:
        client: The LogicMonitor API client instance.
    """
    global _client
    _client = client


# Global AWX client (initialized when AWX_URL and AWX_TOKEN are set)
_awx_client = None

# Set of AWX tool names for dispatch routing
AWX_TOOL_NAMES = {t.name for t in AWX_TOOLS}


def get_awx_client():
    """Get the initialized AWX client.

    Returns:
        The AWX client instance, or None if not configured.
    """
    return _awx_client


def _set_awx_client(client) -> None:
    """Set the global AWX client.

    Called by transport runners during initialization when AWX
    credentials are available.

    Args:
        client: The AwxClient instance, or None to clear.
    """
    global _awx_client
    _awx_client = client


# Global EDA client (initialized when EDA_URL and EDA_TOKEN are set)
_eda_client = None

# Set of EDA tool names for dispatch routing
EDA_TOOL_NAMES = {t.name for t in EDA_TOOLS}


def get_eda_client():
    """Get the initialized EDA client.

    Returns:
        The EDA client instance, or None if not configured.
    """
    return _eda_client


def _set_eda_client(client) -> None:
    """Set the global EDA client.

    Called by transport runners during initialization when EDA
    credentials are available.

    Args:
        client: The EdaClient instance, or None to clear.
    """
    global _eda_client
    _eda_client = client


def _filter_tools(tools: list, config) -> list:
    """Filter tools based on LM_ENABLED_TOOLS or LM_DISABLED_TOOLS config.

    Supports comma-separated tool names and glob patterns (e.g., "get_*", "delete_*").

    Args:
        tools: Full list of Tool objects.
        config: LMConfig instance with enabled_tools/disabled_tools.

    Returns:
        Filtered list of Tool objects.
    """
    if config.enabled_tools:
        patterns = [p.strip() for p in config.enabled_tools.split(",") if p.strip()]
        return [t for t in tools if any(fnmatch(t.name, pat) for pat in patterns)]

    if config.disabled_tools:
        patterns = [p.strip() for p in config.disabled_tools.split(",") if p.strip()]
        return [t for t in tools if not any(fnmatch(t.name, pat) for pat in patterns)]

    return tools


@server.list_tools()
async def list_tools():
    """Return available tools, filtered by config.

    Includes AWX tools only when the AWX client is configured.
    Includes EDA tools only when the EDA client is configured.
    """
    config = get_config()
    tools = list(TOOLS)
    if _awx_client is not None:
        tools.extend(AWX_TOOLS)
    if _eda_client is not None:
        tools.extend(EDA_TOOLS)
    return _filter_tools(tools, config)


# Session tools that don't require the LM client
SESSION_TOOLS = {
    "get_session_context",
    "set_session_variable",
    "get_session_variable",
    "delete_session_variable",
    "clear_session_context",
    "list_session_history",
}


async def execute_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a LogicMonitor tool with full middleware chain.

    Applies tool filtering, field validation, write audit logging, and
    session recording. Used by both the MCP stdio handler and the HTTP
    transport endpoint to ensure consistent behavior across transports.

    Args:
        name: Tool name to execute.
        arguments: Tool arguments.

    Returns:
        List of TextContent with the tool result.
    """
    config = get_config()

    try:
        handler = get_tool_handler(name)

        # Reject calls to filtered-out tools
        if config.enabled_tools:
            patterns = [p.strip() for p in config.enabled_tools.split(",") if p.strip()]
            if not any(fnmatch(name, pat) for pat in patterns):
                return [
                    TextContent(
                        type="text",
                        text=f"Error: Tool '{name}' is not enabled. "
                        f"Enabled tools: {config.enabled_tools}",
                    )
                ]
        elif config.disabled_tools:
            patterns = [p.strip() for p in config.disabled_tools.split(",") if p.strip()]
            if any(fnmatch(name, pat) for pat in patterns):
                return [
                    TextContent(
                        type="text",
                        text=f"Error: Tool '{name}' is disabled. "
                        f"Disabled tools: {config.disabled_tools}",
                    )
                ]

        # Field validation (if enabled and not a session tool)
        if config.field_validation != "off" and name not in SESSION_TOOLS:
            resource_type = infer_resource_type(name)
            if resource_type:
                # Validate 'fields' argument if present
                if "fields" in arguments and arguments["fields"]:
                    validation = validate_fields(resource_type, arguments["fields"])
                    if not validation.valid:
                        msg = f"Invalid fields: {validation.invalid_fields}"
                        if validation.suggestions:
                            suggestions = ", ".join(
                                f"{k} -> {v}" for k, v in validation.suggestions.items()
                            )
                            msg += f". Did you mean: {suggestions}?"

                        if config.field_validation == "error":
                            return [
                                TextContent(
                                    type="text",
                                    text=json.dumps(
                                        {
                                            "error": True,
                                            "code": "INVALID_FIELDS",
                                            "message": msg,
                                            "invalid_fields": validation.invalid_fields,
                                            "suggestions": validation.suggestions,
                                            "valid_fields": validation.valid_field_names[:20],
                                        },
                                        indent=2,
                                    ),
                                )
                            ]
                        else:
                            logger.warning(f"Field validation warning for {name}: {msg}")

                # Validate 'filter' argument if present
                if "filter" in arguments and arguments["filter"]:
                    validation = validate_filter_fields(resource_type, arguments["filter"])
                    if not validation.valid:
                        msg = f"Invalid filter fields: {validation.invalid_fields}"
                        if validation.suggestions:
                            suggestions = ", ".join(
                                f"{k} -> {v}" for k, v in validation.suggestions.items()
                            )
                            msg += f". Did you mean: {suggestions}?"

                        if config.field_validation == "error":
                            return [
                                TextContent(
                                    type="text",
                                    text=json.dumps(
                                        {
                                            "error": True,
                                            "code": "INVALID_FILTER_FIELDS",
                                            "message": msg,
                                            "invalid_fields": validation.invalid_fields,
                                            "suggestions": validation.suggestions,
                                        },
                                        indent=2,
                                    ),
                                )
                            ]
                        else:
                            logger.warning(f"Filter validation warning for {name}: {msg}")

        # Session tools don't need any client
        if name in SESSION_TOOLS:
            result = await handler(**arguments)
        elif name in EDA_TOOL_NAMES:
            # EDA tools use the EDA client
            if _eda_client is None:
                return [
                    TextContent(
                        type="text",
                        text="Error: EDA Controller not configured. "
                        "Set EDA_URL and EDA_TOKEN environment variables.",
                    )
                ]
            result = await handler(_eda_client, **arguments)
        elif name in AWX_TOOL_NAMES:
            # AWX tools use the AWX client
            if _awx_client is None:
                return [
                    TextContent(
                        type="text",
                        text="Error: Ansible Automation Platform not configured. "
                        "Set AWX_URL and AWX_TOKEN environment variables.",
                    )
                ]
            result = await handler(_awx_client, **arguments)
        else:
            client = get_client()
            result = await handler(client, **arguments)

        # Audit trail for write operations
        if is_write_tool(name):
            log_write_operation(name, arguments, success=True)

        # Record result in session if enabled
        if config.session_enabled and name not in SESSION_TOOLS:
            session = get_session()
            # Try to parse the result for session storage
            if result and len(result) > 0:
                try:
                    text = result[0].text
                    data = json.loads(text)
                    session.record_result(name, arguments, data, success=True)
                except (json.JSONDecodeError, AttributeError):
                    # Non-JSON result, just record with minimal info
                    session.record_result(name, arguments, {}, success=True)

        return result
    except ValueError as e:
        if is_write_tool(name):
            log_write_operation(name, arguments, success=False)
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        if is_write_tool(name):
            log_write_operation(name, arguments, success=False)
        return [TextContent(type="text", text=f"Error executing {name}: {e}")]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """MCP call_tool handler that delegates to execute_tool.

    Args:
        name: Tool name to execute.
        arguments: Tool arguments.

    Returns:
        List of TextContent with the tool result.
    """
    return await execute_tool(name, arguments)


@server.list_resources()
async def list_resources():
    """Return all available LogicMonitor schema resources.

    Resources expose API field definitions, valid enum values, and filter
    syntax to help AI agents construct valid API queries.
    """
    return RESOURCES


@server.read_resource()
async def read_resource(uri) -> str:
    """Read the content of a LogicMonitor schema resource.

    Args:
        uri: Resource URI (e.g., 'lm://schema/alerts'). May be AnyUrl or str.

    Returns:
        JSON string containing the resource content.
    """
    try:
        # Convert AnyUrl to string if needed
        uri_str = str(uri)
        content = get_resource_content(uri_str)
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
    """Run the MCP server with configured transport.

    The transport is selected based on the LM_TRANSPORT environment variable:
    - "stdio" (default): Standard input/output for local AI assistants
    - "http": HTTP transport for remote/shared deployments
    """
    from lm_mcp.transport import get_transport_runner

    config = get_config()
    runner = get_transport_runner(config)
    await runner()


def main() -> None:
    """Entry point for the MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
