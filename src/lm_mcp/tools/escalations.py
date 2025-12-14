# Description: Escalation chain and recipient group tools for LogicMonitor MCP server.
# Description: Provides escalation chain and recipient group query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

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
