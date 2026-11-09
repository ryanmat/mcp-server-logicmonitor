# Description: PropertySource tools for LogicMonitor MCP server.
# Description: Provides property source query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    list_tool,
    require_write_permission,
)
from lm_mcp.tools.logicmodules import (
    MODULES,
    create_module,
    delete_module,
    get_module,
    update_module,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_propertysources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List PropertySources from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~Linux,technology:script"
        limit: Maximum number of PropertySources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with PropertySource data or error.
    """
    module = MODULES["propertysource"]
    return await list_tool(
        client,
        f"/setting/{module.path}",
        key="propertysources",
        project=module.list_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"name~": name_filter, "appliesTo~": applies_to_filter},
    )


@require_write_permission
async def create_propertysource(
    client: LogicMonitorClient,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create a PropertySource via REST API using a full definition dict.

    Accepts REST API format (the format get_propertysource returns with raw=true).
    Use this for creating PropertySources from exported definitions or from
    scratch. For LM Exchange format imports, use import_propertysource instead.

    Args:
        client: LogicMonitor API client.
        definition: Full PropertySource definition dict in REST API format.
        overwrite: If True, replace the PropertySource holding the definition's name in
            place (a PUT to its id); nothing is deleted first.

    Returns:
        List of TextContent with created PropertySource info or error.
    """
    return await create_module(client, "propertysource", definition, overwrite)


@require_write_permission
async def update_propertysource(
    client: LogicMonitorClient,
    propertysource_id: int,
    definition: dict,
    confirm: bool = False,
) -> list[TextContent]:
    """Update an existing PropertySource via REST API (full replace).

    Internal PUT behind update_logicmodule, which reads the current
    definition, merges the caller's changes and passes the merged full
    definition here; the server registers no tool for it. The LM API
    update is full-replace and can blank any field the definition leaves out.

    Args:
        client: LogicMonitor API client.
        propertysource_id: PropertySource ID to update.
        definition: Full PropertySource definition dict with all fields.
        confirm: Must be True to proceed; update_logicmodule always passes it.
            Without it the call returns INVALID_REQUEST and writes nothing.

    Returns:
        List of TextContent with updated PropertySource info or error.
    """
    return await update_module(client, "propertysource", propertysource_id, definition, confirm)


@require_write_permission
async def delete_propertysource(
    client: LogicMonitorClient,
    propertysource_id: int,
) -> list[TextContent]:
    """Delete a PropertySource from LogicMonitor.

    Removes the PropertySource definition. Existing collected properties
    are retained on devices but no new properties will be discovered.

    Args:
        client: LogicMonitor API client.
        propertysource_id: PropertySource ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    return await delete_module(client, "propertysource", propertysource_id)


async def get_propertysource(
    client: LogicMonitorClient,
    propertysource_id: int,
    raw: bool = False,
) -> list[TextContent]:
    """Get detailed information about a specific PropertySource.

    Args:
        client: LogicMonitor API client.
        propertysource_id: PropertySource ID.
        raw: Return the REST object whole instead of the summary.

    Returns:
        List of TextContent with PropertySource details or error.
    """
    return await get_module(client, "propertysource", propertysource_id, raw)
