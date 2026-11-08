# Description: API token tools for LogicMonitor MCP server.
# Description: Provides API token query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.exceptions import NotFoundError
from lm_mcp.tools import format_response, handle_error, list_tool

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def _api_token_row(item: dict) -> dict:
    """Project one apitokens row onto the get_api_tokens fields."""
    return {
        "id": item.get("id"),
        "admin_id": item.get("adminId"),
        "admin_name": item.get("adminName"),
        "note": item.get("note"),
        "status": item.get("status"),
        "created_on": item.get("createdOn"),
        "last_used_on": item.get("lastUsedOn"),
        "roles": item.get("roles", []),
    }


async def get_api_tokens(
    client: LogicMonitorClient,
    admin_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List API tokens for one user/admin, or across the portal when admin_id is omitted.

    Args:
        client: LogicMonitor API client.
        admin_id: Admin/user ID to list tokens for. Omit to list every token in the portal.
        limit: Maximum number of tokens to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with API token data or error.
    """
    path = (
        f"/setting/admins/{admin_id}/apitokens"
        if admin_id is not None
        else "/setting/admins/apitokens"
    )
    return await list_tool(
        client, path, key="api_tokens", project=_api_token_row, limit=limit, offset=offset
    )


async def get_api_token(
    client: LogicMonitorClient,
    token_id: int,
    admin_id: int | None = None,
) -> list[TextContent]:
    """Get detailed information about a specific API token.

    Args:
        client: LogicMonitor API client.
        token_id: API token ID.
        admin_id: Owning admin/user ID. Omit to look the token up across the portal.

    Returns:
        List of TextContent with API token details or error.
    """
    try:
        if admin_id is not None:
            result = await client.get(f"/setting/admins/{admin_id}/apitokens/{token_id}")
        else:
            listing = await client.get(
                "/setting/admins/apitokens", params={"filter": f"id:{token_id}", "size": 1}
            )
            items = listing.get("items") or []
            if not items:
                raise NotFoundError(f"API token {token_id} not found")
            result = items[0]

        token = {
            "id": result.get("id"),
            "admin_id": result.get("adminId"),
            "admin_name": result.get("adminName"),
            "note": result.get("note"),
            "status": result.get("status"),
            "created_on": result.get("createdOn"),
            "last_used_on": result.get("lastUsedOn"),
            "roles": result.get("roles", []),
        }

        return format_response(token)
    except Exception as e:
        return handle_error(e)
