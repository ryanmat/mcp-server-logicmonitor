# Description: User and role management tools for LogicMonitor MCP server.
# Description: Provides user and role query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_users(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List users from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by username (supports wildcards).
        limit: Maximum number of users to return.

    Returns:
        List of TextContent with user data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"username~{name_filter}"

        result = await client.get("/setting/admins", params=params)

        users = []
        for item in result.get("items", []):
            users.append(
                {
                    "id": item.get("id"),
                    "username": item.get("username"),
                    "email": item.get("email"),
                    "first_name": item.get("firstName"),
                    "last_name": item.get("lastName"),
                    "status": item.get("status"),
                    "roles": [r.get("name") for r in item.get("roles", [])],
                    "two_fa_enabled": item.get("twoFAEnabled"),
                    "api_only": item.get("apionly"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(users),
                "users": users,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_user(
    client: "LogicMonitorClient",
    user_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific user.

    Args:
        client: LogicMonitor API client.
        user_id: User ID.

    Returns:
        List of TextContent with user details or error.
    """
    try:
        result = await client.get(f"/setting/admins/{user_id}")

        user = {
            "id": result.get("id"),
            "username": result.get("username"),
            "email": result.get("email"),
            "first_name": result.get("firstName"),
            "last_name": result.get("lastName"),
            "status": result.get("status"),
            "roles": [{"id": r.get("id"), "name": r.get("name")} for r in result.get("roles", [])],
            "two_fa_enabled": result.get("twoFAEnabled"),
            "api_only": result.get("apionly"),
            "phone": result.get("phone"),
            "sms_email": result.get("smsEmail"),
            "note": result.get("note"),
            "created_by": result.get("createdBy"),
            "last_login_on": result.get("lastLoginOn"),
        }

        return format_response(user)
    except Exception as e:
        return handle_error(e)


async def get_roles(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List roles from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by role name (supports wildcards).
        limit: Maximum number of roles to return.

    Returns:
        List of TextContent with role data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/setting/roles", params=params)

        roles = []
        for item in result.get("items", []):
            roles.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "requires_eula": item.get("requireEULA"),
                    "two_fa_required": item.get("twoFARequired"),
                    "associated_user_count": item.get("associatedUserCount"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(roles),
                "roles": roles,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_role(
    client: "LogicMonitorClient",
    role_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific role.

    Args:
        client: LogicMonitor API client.
        role_id: Role ID.

    Returns:
        List of TextContent with role details or error.
    """
    try:
        result = await client.get(f"/setting/roles/{role_id}")

        role = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "requires_eula": result.get("requireEULA"),
            "two_fa_required": result.get("twoFARequired"),
            "custom_help_label": result.get("customHelpLabel"),
            "custom_help_url": result.get("customHelpURL"),
            "privileges": result.get("privileges", []),
        }

        return format_response(role)
    except Exception as e:
        return handle_error(e)
