# Description: Escalation chain and recipient group tools for LogicMonitor MCP server.
# Description: Provides CRUD operations for escalation chains and recipient groups.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_escalation_chains(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List escalation chains from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by chain name (supports wildcards).
        limit: Maximum number of chains to return.

    Returns:
        List of TextContent with escalation chain data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/setting/alert/chains", params=params)

        chains = []
        for item in result.get("items", []):
            chains.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "enable_throttling": item.get("enableThrottling"),
                    "throttling_period": item.get("throttlingPeriod"),
                    "throttling_alerts": item.get("throttlingAlerts"),
                    "in_alerting": item.get("inAlerting"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(chains),
                "escalation_chains": chains,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_escalation_chain(
    client: "LogicMonitorClient",
    chain_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific escalation chain.

    Args:
        client: LogicMonitor API client.
        chain_id: Escalation chain ID.

    Returns:
        List of TextContent with chain details or error.
    """
    try:
        result = await client.get(f"/setting/alert/chains/{chain_id}")

        # Parse destinations into readable format
        destinations = []
        for dest in result.get("destinations", []):
            stages = []
            for stage in dest.get("stages", []):
                stages.append(
                    {
                        "type": stage.get("type"),
                        "address": stage.get("addr"),
                        "contact": stage.get("contact"),
                    }
                )
            destinations.append(
                {
                    "type": dest.get("type"),
                    "period": dest.get("period"),
                    "stages": stages,
                }
            )

        # Parse CC destinations
        cc_destinations = []
        for cc in result.get("ccDestinations", []):
            cc_destinations.append(
                {
                    "type": cc.get("type"),
                    "method": cc.get("method"),
                    "address": cc.get("addr"),
                    "contact": cc.get("contact"),
                }
            )

        chain = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "enable_throttling": result.get("enableThrottling"),
            "throttling_period": result.get("throttlingPeriod"),
            "throttling_alerts": result.get("throttlingAlerts"),
            "in_alerting": result.get("inAlerting"),
            "destinations": destinations,
            "cc_destinations": cc_destinations,
        }

        return format_response(chain)
    except Exception as e:
        return handle_error(e)


async def get_recipient_groups(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List recipient groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.

    Returns:
        List of TextContent with recipient group data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/setting/recipientgroups", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "group_type": item.get("groupType"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(groups),
                "recipient_groups": groups,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_recipient_group(
    client: "LogicMonitorClient",
    group_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific recipient group.

    Args:
        client: LogicMonitor API client.
        group_id: Recipient group ID.

    Returns:
        List of TextContent with group details or error.
    """
    try:
        result = await client.get(f"/setting/recipientgroups/{group_id}")

        # Parse recipients
        recipients = []
        for r in result.get("recipients", []):
            recipients.append(
                {
                    "type": r.get("type"),
                    "method": r.get("method"),
                    "address": r.get("addr"),
                    "contact": r.get("contact"),
                }
            )

        group = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "group_type": result.get("groupType"),
            "recipients": recipients,
        }

        return format_response(group)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_escalation_chain(
    client: "LogicMonitorClient",
    name: str,
    description: str | None = None,
    enable_throttling: bool = False,
    throttling_period: int | None = None,
    throttling_alerts: int | None = None,
) -> list[TextContent]:
    """Create an escalation chain in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Name of the escalation chain.
        description: Optional description.
        enable_throttling: Whether to enable alert throttling.
        throttling_period: Throttling period in minutes.
        throttling_alerts: Number of alerts before throttling.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {
            "name": name,
            "enableThrottling": enable_throttling,
        }

        if description:
            body["description"] = description
        if throttling_period is not None:
            body["throttlingPeriod"] = throttling_period
        if throttling_alerts is not None:
            body["throttlingAlerts"] = throttling_alerts

        result = await client.post("/setting/alert/chains", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Escalation chain '{name}' created",
                "chain_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_escalation_chain(
    client: "LogicMonitorClient",
    chain_id: int,
    name: str | None = None,
    description: str | None = None,
    enable_throttling: bool | None = None,
    throttling_period: int | None = None,
    throttling_alerts: int | None = None,
) -> list[TextContent]:
    """Update an escalation chain in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        chain_id: ID of the escalation chain to update.
        name: Updated name.
        description: Updated description.
        enable_throttling: Updated throttling setting.
        throttling_period: Updated throttling period.
        throttling_alerts: Updated throttling alert count.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {}

        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if enable_throttling is not None:
            body["enableThrottling"] = enable_throttling
        if throttling_period is not None:
            body["throttlingPeriod"] = throttling_period
        if throttling_alerts is not None:
            body["throttlingAlerts"] = throttling_alerts

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "VALIDATION_ERROR",
                    "message": "No fields provided to update",
                }
            )

        result = await client.patch(f"/setting/alert/chains/{chain_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Escalation chain {chain_id} updated",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_escalation_chain(
    client: "LogicMonitorClient",
    chain_id: int,
) -> list[TextContent]:
    """Delete an escalation chain from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        chain_id: ID of the escalation chain to delete.

    Returns:
        List of TextContent with result or error.
    """
    try:
        await client.delete(f"/setting/alert/chains/{chain_id}")

        return format_response(
            {
                "success": True,
                "message": f"Escalation chain {chain_id} deleted",
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_recipient_group(
    client: "LogicMonitorClient",
    name: str,
    description: str | None = None,
) -> list[TextContent]:
    """Create a recipient group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Name of the recipient group.
        description: Optional description.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {"name": name}

        if description:
            body["description"] = description

        result = await client.post("/setting/recipientgroups", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Recipient group '{name}' created",
                "group_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_recipient_group(
    client: "LogicMonitorClient",
    group_id: int,
    name: str | None = None,
    description: str | None = None,
) -> list[TextContent]:
    """Update a recipient group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: ID of the recipient group to update.
        name: Updated name.
        description: Updated description.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {}

        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "VALIDATION_ERROR",
                    "message": "No fields provided to update",
                }
            )

        result = await client.patch(f"/setting/recipientgroups/{group_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Recipient group {group_id} updated",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_recipient_group(
    client: "LogicMonitorClient",
    group_id: int,
) -> list[TextContent]:
    """Delete a recipient group from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: ID of the recipient group to delete.

    Returns:
        List of TextContent with result or error.
    """
    try:
        await client.delete(f"/setting/recipientgroups/{group_id}")

        return format_response(
            {
                "success": True,
                "message": f"Recipient group {group_id} deleted",
            }
        )
    except Exception as e:
        return handle_error(e)
