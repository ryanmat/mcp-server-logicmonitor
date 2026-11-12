# Description: MCP server entry point for LogicMonitor platform.
# Description: Provides shared tool execution middleware and stdio transport.

import asyncio
import dataclasses
import json
import logging
from typing import TYPE_CHECKING

from mcp.server import Server
from mcp.types import CallToolResult, GetPromptResult, TextContent, Tool

from lm_mcp import __version__, portals
from lm_mcp.categories import passes_name_filter, writes_to_portal
from lm_mcp.client import LogicMonitorClient
from lm_mcp.config import LMConfig, get_config
from lm_mcp.context import CallBinding, bind, current_binding, missing_client_message
from lm_mcp.logging import (
    configure_logging,
    is_write_tool,
    log_write_operation,
    redact_arguments,
)
from lm_mcp.prompts import PROMPTS, get_prompt_messages
from lm_mcp.registry import TOOLS, get_tool_handler
from lm_mcp.resources import RESOURCES, get_resource_content
from lm_mcp.session import get_session
from lm_mcp.tools import (
    error_content,
    error_from_exception,
    is_error_result,
    stamp_portal,
    write_disabled_response,
)

if TYPE_CHECKING:
    from lm_mcp.client.edwin import EdwinClient

logger = logging.getLogger(__name__)

# Create server instance
SERVER_INSTRUCTIONS = (
    "This server exposes up to 256 LogicMonitor tools, more than most clients load at once. "
    "To find the right tool for a task, call `search_tools` with relevant keywords (or a "
    "`category`) first instead of enumerating the full list. The composite workflow tools "
    "(`triage`, `diagnose`, `health_check`, `portal_overview`, `capacity_plan` and "
    "`detect_site_outage`) answer common multi-step investigations in a single call. "
    "Tools that change the portal (create, update, delete, acknowledge, run) are listed "
    "only when the operator sets `LM_ENABLE_WRITE_OPERATIONS=true`."
)
server = Server("logicmonitor-platform", version=__version__, instructions=SERVER_INSTRUCTIONS)

# Global client (initialized on startup)
_client: LogicMonitorClient | None = None

# The Edwin AI client the transport bootstrap built, or None when Edwin is not configured
_edwin_client: "EdwinClient | None" = None


def get_client() -> LogicMonitorClient:
    """Get the default LogicMonitor client.

    The client built at startup, or in multi-portal mode the one use_portal selected.
    A tool call takes its client from its own binding (:mod:`lm_mcp.context`); this
    serves callers outside a call, such as the health check.

    Returns:
        The LogicMonitor API client instance.

    Raises:
        RuntimeError: If no client is built yet, or no portal is selected.
    """
    if _client is not None:
        return _client
    # Only surface the multi-portal hint when we can confirm multi-portal mode.
    # If the config can't be built yet (e.g. no env in a unit test), fall back to
    # the plain "not initialized" message rather than leaking a config error.
    multi = False
    try:
        multi = get_config().multi_portal
    except Exception:
        logger.debug("config unavailable; reporting the client as not initialized", exc_info=True)
    client = portals.call_binding(writes_enabled=False).client if multi else None
    if client is None:
        raise RuntimeError(missing_client_message(multi))
    return client


def _set_client(client: LogicMonitorClient) -> None:
    """Set the global LogicMonitor client.

    Called by transport runners during initialization.

    Args:
        client: The LogicMonitor API client instance.
    """
    global _client
    _client = client


def _set_edwin_client(client: "EdwinClient | None") -> None:
    """Set the Edwin AI client the Edwin tools call, or None to withdraw them.

    Called by the transport bootstrap at startup and when it closes its backends.
    """
    global _edwin_client
    _edwin_client = client


def _filter_tools(tools: list, config) -> list:
    """Filter tools on the write gate, LM_ENABLED_TOOLS, LM_DISABLED_TOOLS and LM_MCP_CATEGORIES.

    With LM_ENABLE_WRITE_OPERATIONS false, tools whose annotations say they change the
    portal are left out. The Edwin tools are left out unless the bootstrap built an
    Edwin client, which it does only when both Edwin credentials are set, and in
    multi-portal mode the Edwin tools that change state are left out (see _edwin_write).

    Supports comma-separated tool names and glob patterns (e.g., "get_*", "delete_*").
    LM_MCP_CATEGORIES composes by intersection — it narrows the result of the
    enabled/disabled pass but never expands it.

    Args:
        tools: Full list of Tool objects.
        config: LMConfig instance with enable_write_operations, enabled_tools,
            disabled_tools and mcp_categories.

    Returns:
        Filtered list of Tool objects.
    """
    if not config.multi_portal:
        tools = [t for t in tools if t.name not in PORTAL_TOOLS]

    if _edwin_client is None:
        tools = [t for t in tools if t.name not in EDWIN_TOOLS]
    elif config.multi_portal:
        tools = [t for t in tools if not _edwin_write(t.name)]

    if not config.enable_write_operations:
        tools = [t for t in tools if not writes_to_portal(t)]

    tools = [t for t in tools if passes_name_filter(t.name, config)]

    if config.mcp_categories:
        from lm_mcp.categories import filter_by_categories

        # In multi-portal mode the portal tools are the control plane: filtering
        # them out would leave every data tool stuck at "No portal selected".
        exempt = [t for t in tools if config.multi_portal and t.name in PORTAL_TOOLS]
        candidates = [t for t in tools if t not in exempt]
        tools, unknown = filter_by_categories(candidates, config.mcp_categories)
        tools.extend(exempt)
        if unknown:
            logger.warning(
                "LM_MCP_CATEGORIES contains unknown tokens %s — ignored. "
                "Known categories: read, write, delete, export, import, session, workflow",
                unknown,
            )

    return tools


@server.list_tools()
async def list_tools():
    """Return available tools, filtered by config."""
    return _filter_tools(collect_tools(), get_config())


def collect_tools() -> list[Tool]:
    """The tools this server can dispatch, before operator filters.

    The MCP list_tools handler, which the stdio transport serves, builds its list from this.
    """
    return list(TOOLS)


# Session tools that don't require the LM client
SESSION_TOOLS = {
    "get_session_context",
    "set_session_variable",
    "get_session_variable",
    "delete_session_variable",
    "clear_session_context",
    "get_session_history",
}

PORTAL_TOOLS = {
    "get_portals",
    "use_portal",
    "get_current_portal",
    "run_portal_reload",
}

# Edwin AI tools: served only with an Edwin client, which their handlers take in place
# of the LogicMonitor client
EDWIN_TOOLS = {
    "get_edwin_insights",
    "get_edwin_insight",
    "get_edwin_records",
    "get_edwin_alert_volume",
    "get_edwin_metadata",
    "get_edwin_tools",
    "edwin_run_tool",
    "ask_edwin",
}

# Discovery tools that take the client argument by convention but never use it,
# so they must work before a portal is selected in multi-portal mode.
CLIENT_OPTIONAL_TOOLS = {
    "search_tools",
    "get_reference",
}


def _edwin_write(name: str) -> bool:
    """Whether a tool is an Edwin tool that changes state. Edwin AI is one tenant for every
    portal in multi-portal mode, so no portal's vault write flag vouches for such a call."""
    return name in EDWIN_TOOLS and is_write_tool(name)


def _call_binding(config: LMConfig) -> CallBinding:
    """The clients, write flag and portal name a call runs against, read once at its start."""
    if config.multi_portal:
        binding = portals.call_binding(writes_enabled=config.enable_write_operations)
        return dataclasses.replace(binding, edwin=_edwin_client)
    return CallBinding(
        client=_client, writable=config.enable_write_operations, portal=None, edwin=_edwin_client
    )


async def execute_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a LogicMonitor tool with full middleware chain.

    Binds the call's LogicMonitor and Edwin clients, write flag and portal name for
    its duration (spec R2.12), then applies tool filtering, the write gate, write
    audit logging and session recording. In multi-portal mode every result except a
    portal tool's carries the bound portal name. The MCP call_tool handler delegates
    to it.

    Args:
        name: Tool name to execute.
        arguments: Tool arguments.

    Returns:
        List of TextContent with the tool result.
    """
    config = get_config()
    binding = _call_binding(config)
    with bind(binding):
        result = await _execute_bound(name, arguments, config)
    if config.multi_portal and name not in PORTAL_TOOLS:
        return stamp_portal(result, binding.portal)
    return result


async def _execute_bound(name: str, arguments: dict, config: LMConfig) -> list[TextContent]:
    """Run one tool call inside its binding: the filters, the gate, the handler, the audit."""
    try:
        handler = get_tool_handler(name)

        # Portal tools exist only in multi-portal mode
        if name in PORTAL_TOOLS and not config.multi_portal:
            return error_content(
                "FEATURE_DISABLED",
                f"Tool '{name}' is only available in multi-portal mode (set LM_MULTI_PORTAL=true).",
            )

        # Edwin tools exist only with the Edwin client the bootstrap built
        if name in EDWIN_TOOLS and current_binding().edwin is None:
            if is_write_tool(name):
                log_write_operation(name, arguments, success=False)
            return error_content(
                "FEATURE_DISABLED",
                f"Tool '{name}' needs Edwin AI: set EDWIN_CLIENT_ID and EDWIN_CLIENT_TOKEN.",
            )
        if config.multi_portal and _edwin_write(name):
            log_write_operation(name, arguments, success=False)
            return error_content(
                "FEATURE_DISABLED",
                f"Tool '{name}' is off in multi-portal mode: Edwin AI is one tenant for every "
                "portal, so no portal's write permission can cover the change.",
            )

        # Reject calls to filtered-out tools
        if not passes_name_filter(name, config):
            if config.enabled_tools:
                message = f"Tool '{name}' is not enabled. Enabled tools: {config.enabled_tools}"
            else:
                message = f"Tool '{name}' is disabled. Disabled tools: {config.disabled_tools}"
            return error_content("FEATURE_DISABLED", message)

        if config.mcp_categories and not (name in PORTAL_TOOLS and config.multi_portal):
            from lm_mcp.categories import tool_in_categories

            tools_index = {t.name: t for t in TOOLS}
            if not tool_in_categories(name, tools_index, config.mcp_categories):
                return error_content(
                    "FEATURE_DISABLED",
                    f"Tool '{name}' is excluded by LM_MCP_CATEGORIES "
                    f"(active categories: {config.mcp_categories}).",
                )

        if not config.enable_write_operations:
            tool = next((t for t in TOOLS if t.name == name), None)
            if tool is not None and writes_to_portal(tool):
                if is_write_tool(name):
                    log_write_operation(name, arguments, success=False)
                return write_disabled_response()

        # Session and portal tools don't need an LM client
        if name in SESSION_TOOLS or name in PORTAL_TOOLS:
            result = await handler(**arguments)
        elif name in CLIENT_OPTIONAL_TOOLS:
            # These handlers ignore the client; pass the bound one as-is (possibly
            # None before use_portal) so discovery works portal-free.
            result = await handler(current_binding().client, **arguments)
        elif name in EDWIN_TOOLS:
            # Edwin tools take the Edwin client in place of the LogicMonitor one, so they
            # work before a portal is selected.
            result = await handler(current_binding().edwin, **arguments)
        else:
            client = current_binding().client
            if client is None:
                # No portal selected yet, or no startup client: the caller fixes that
                # first, so this is a refusal, not an upstream failure worth retrying.
                if is_write_tool(name):
                    log_write_operation(name, arguments, success=False)
                return error_content("INVALID_REQUEST", missing_client_message(config.multi_portal))
            result = await handler(client, **arguments)

        # Handlers return errors rather than raise, so the outcome comes from the result
        failed = is_error_result(result)

        # Audit trail for write operations
        if is_write_tool(name):
            log_write_operation(name, arguments, success=not failed)

        # Record the result in the history of the call's portal. Portal tools are
        # recorded too, in the history of the portal the call started on, so a
        # portal's history shows when it was left. History is shown back to
        # clients, so it holds the same redacted arguments the audit line shows.
        if name not in SESSION_TOOLS:
            session = get_session()
            recorded_arguments = redact_arguments(arguments)
            # Try to parse the result for session storage
            if result and len(result) > 0:
                try:
                    text = result[0].text
                    data = json.loads(text)
                    session.record_result(name, recorded_arguments, data, success=not failed)
                except (json.JSONDecodeError, AttributeError):
                    # Non-JSON result, just record with minimal info
                    session.record_result(name, recorded_arguments, {}, success=not failed)

        return result
    except ValueError as e:
        logger.exception("Tool %s rejected its arguments", name)
        if is_write_tool(name):
            log_write_operation(name, arguments, success=False)
        return error_content("INVALID_REQUEST", str(e))
    except Exception as e:
        logger.exception("Tool %s raised", name)
        if is_write_tool(name):
            log_write_operation(name, arguments, success=False)
        return error_from_exception(e)


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent] | CallToolResult:
    """MCP call_tool handler that delegates to execute_tool.

    Args:
        name: Tool name to execute.
        arguments: Tool arguments.

    Returns:
        List of TextContent with the tool result, or a CallToolResult with
        isError=True when the result is an error, which the SDK passes through.
    """
    result = await execute_tool(name, arguments)
    if is_error_result(result):
        return CallToolResult(content=list(result), isError=True)
    return result


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


@server.list_prompts()
async def list_prompts():
    """Return all available LogicMonitor workflow prompts.

    Prompts provide pre-built templates for incident triage, capacity review
    and remediation.
    """
    return PROMPTS


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
    """Get the messages for a LogicMonitor workflow prompt.

    Args:
        name: Prompt name (e.g., 'incident_triage', 'remediation').
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
    configure_logging(config)
    runner = get_transport_runner(config)
    await runner()


def main() -> None:
    """Entry point for the MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
