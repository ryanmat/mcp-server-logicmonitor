# Description: DataSource tools for LogicMonitor MCP server.
# Description: Provides DataSource CRUD functions including list, get, create, update, delete.

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


async def get_datasources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List DataSources (LogicModules) from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by DataSource name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~CPU,group:Core"
        limit: Maximum number of DataSources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with DataSource data or error.
    """
    module = MODULES["datasource"]
    return await list_tool(
        client,
        f"/setting/{module.path}",
        key="datasources",
        project=module.list_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"name~": name_filter, "appliesTo~": applies_to_filter},
    )


async def get_datasource(
    client: LogicMonitorClient,
    datasource_id: int,
    raw: bool = False,
) -> list[TextContent]:
    """Get detailed information about a specific DataSource.

    Args:
        client: LogicMonitor API client.
        datasource_id: DataSource ID.
        raw: Return the REST object whole instead of the summary.

    Returns:
        List of TextContent with DataSource details or error.
    """
    return await get_module(client, "datasource", datasource_id, raw)


@require_write_permission
async def create_datasource(
    client: LogicMonitorClient,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create a DataSource via REST API using a full definition dict.

    Accepts REST API format (the format get_datasource returns with raw=true).
    Use this for creating DataSources from exported definitions or from
    scratch. For LM Exchange format imports, use import_datasource instead.

    Note: script DataSource datapoints require appropriate type values.

    Args:
        client: LogicMonitor API client.
        definition: Full DataSource definition dict in REST API format.
        overwrite: If True, replace the DataSource holding the definition's name in
            place (a PUT to its id); nothing is deleted first.

    Returns:
        List of TextContent with created DataSource info or error.
    """
    return await create_module(client, "datasource", definition, overwrite)


@require_write_permission
async def update_datasource(
    client: LogicMonitorClient,
    datasource_id: int,
    definition: dict,
    confirm: bool = False,
) -> list[TextContent]:
    """Update an existing DataSource via REST API (full replace).

    Internal PUT behind update_logicmodule, which reads the current
    definition, merges the caller's changes and passes the merged full
    definition here; the server registers no tool for it. The LM API
    update is full-replace and can blank any field the definition leaves out,
    the Groovy script included; the name and displayName fields are required
    even for targeted changes.

    Args:
        client: LogicMonitor API client.
        datasource_id: DataSource ID to update.
        definition: Full DataSource definition dict with all fields.
        confirm: Must be True to proceed; update_logicmodule always passes it.
            Without it the call returns INVALID_REQUEST and writes nothing.

    Returns:
        List of TextContent with updated DataSource info or error.
    """
    return await update_module(client, "datasource", datasource_id, definition, confirm)


@require_write_permission
async def delete_datasource(
    client: LogicMonitorClient,
    datasource_id: int,
) -> list[TextContent]:
    """Delete a DataSource from LogicMonitor.

    WARNING: This removes the DataSource definition. Monitoring data collected
    by this DataSource is retained on devices but no new data will be collected.

    Args:
        client: LogicMonitor API client.
        datasource_id: DataSource ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    return await delete_module(client, "datasource", datasource_id)
