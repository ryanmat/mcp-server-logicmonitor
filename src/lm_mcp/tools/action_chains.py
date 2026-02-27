# Description: Action chain tools for LogicMonitor MCP server.
# Description: Provides action chain CRUD operations for diagnostic/remediation workflows.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    require_write_permission,
    sanitize_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_action_chains(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List action chains from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by chain name (supports wildcards).
        limit: Maximum number of chains to return.

    Returns:
        List of TextContent with action chain data or error.
    """
    try:
        params: dict = {"size": limit}
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f'name~{quote_filter_value(clean_name)}'

        result = await client.get("/setting/action/chains", params=params)

        chains = []
        for item in result.get("items", []):
            chains.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "actions": item.get("actionchain", []),
                }
            )

        response = {
            "total": result.get("total", 0),
            "count": len(chains),
            "action_chains": chains,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_action_chain(
    client: "LogicMonitorClient",
    chain_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific action chain.

    Args:
        client: LogicMonitor API client.
        chain_id: Action chain ID.

    Returns:
        List of TextContent with chain details or error.
    """
    try:
        result = await client.get(f"/setting/action/chains/{chain_id}")

        chain = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "actions": result.get("actionchain", []),
        }

        return format_response(chain)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_action_chain(
    client: "LogicMonitorClient",
    name: str,
    actions: list[dict],
    description: str | None = None,
) -> list[TextContent]:
    """Create an action chain in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Name of the action chain.
        actions: Ordered list of action steps. Each step has a type
            (diagnosticsource or remediation) and a source ID.
        description: Optional description.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {
            "name": name,
            "actionchain": actions,
        }

        if description:
            body["description"] = description

        result = await client.post("/setting/action/chains", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Action chain '{name}' created",
                "chain_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_action_chain(
    client: "LogicMonitorClient",
    chain_id: int,
    name: str | None = None,
    description: str | None = None,
    actions: list[dict] | None = None,
) -> list[TextContent]:
    """Update an action chain in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        chain_id: ID of the action chain to update.
        name: Updated name.
        description: Updated description.
        actions: Updated action steps.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {}

        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if actions is not None:
            body["actionchain"] = actions

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "VALIDATION_ERROR",
                    "message": "No fields provided to update",
                }
            )

        result = await client.patch(f"/setting/action/chains/{chain_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Action chain {chain_id} updated",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_action_chain(
    client: "LogicMonitorClient",
    chain_id: int,
) -> list[TextContent]:
    """Delete an action chain from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        chain_id: ID of the action chain to delete.

    Returns:
        List of TextContent with result or error.
    """
    try:
        await client.delete(f"/setting/action/chains/{chain_id}")

        return format_response(
            {
                "success": True,
                "message": f"Action chain {chain_id} deleted",
            }
        )
    except Exception as e:
        return handle_error(e)
