# Description: TopologySource tools for LogicMonitor MCP server.
# Description: Provides topology source query functions.

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


async def get_topologysources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List TopologySources from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~Network,technology:snmp"
        limit: Maximum number of TopologySources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with TopologySource data or error.
    """
    module = MODULES["topologysource"]
    return await list_tool(
        client,
        f"/setting/{module.path}",
        key="topologysources",
        project=module.list_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"name~": name_filter, "appliesTo~": applies_to_filter},
    )


@require_write_permission
async def create_topologysource(
    client: LogicMonitorClient,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create a TopologySource via REST API using a full definition dict.

    Accepts REST API format (the format get_topologysource returns with raw=true).
    Use this for creating TopologySources from definitions.
    For LM Exchange format imports, use import_topologysource instead.

    Args:
        client: LogicMonitor API client.
        definition: Full TopologySource definition dict in REST API format.
        overwrite: If True, replace the TopologySource holding the definition's name in
            place (a PUT to its id); nothing is deleted first.

    Returns:
        List of TextContent with created TopologySource info or error.
    """
    return await create_module(client, "topologysource", definition, overwrite)


@require_write_permission
async def update_topologysource(
    client: LogicMonitorClient,
    topologysource_id: int,
    definition: dict,
    confirm: bool = False,
) -> list[TextContent]:
    """Update an existing TopologySource via REST API (full replace).

    Internal PUT behind update_logicmodule, which reads the current
    definition, merges the caller's changes and passes the merged full
    definition here; the server registers no tool for it. The LM API
    update is full-replace and can blank any field the definition leaves out.

    Args:
        client: LogicMonitor API client.
        topologysource_id: TopologySource ID to update.
        definition: Full TopologySource definition dict with all fields.
        confirm: Must be True to proceed; update_logicmodule always passes it.
            Without it the call returns INVALID_REQUEST and writes nothing.

    Returns:
        List of TextContent with updated TopologySource info or error.
    """
    return await update_module(client, "topologysource", topologysource_id, definition, confirm)


@require_write_permission
async def delete_topologysource(
    client: LogicMonitorClient,
    topologysource_id: int,
) -> list[TextContent]:
    """Delete a TopologySource from LogicMonitor.

    Removes the TopologySource definition. Existing topology data
    is retained but no new topology will be collected.

    Args:
        client: LogicMonitor API client.
        topologysource_id: TopologySource ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    return await delete_module(client, "topologysource", topologysource_id)


async def get_topologysource(
    client: LogicMonitorClient,
    topologysource_id: int,
    raw: bool = False,
) -> list[TextContent]:
    """Get detailed information about a specific TopologySource.

    Args:
        client: LogicMonitor API client.
        topologysource_id: TopologySource ID.
        raw: Return the REST object whole instead of the summary.

    Returns:
        List of TextContent with TopologySource details or error.
    """
    return await get_module(client, "topologysource", topologysource_id, raw)
