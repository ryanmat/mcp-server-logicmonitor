# Description: Alert rule tools for LogicMonitor MCP server.
# Description: Provides alert rule query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_alert_rules(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    priority_filter: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List alert rules from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by rule name (supports wildcards).
        priority_filter: Filter by priority level.
        limit: Maximum number of rules to return.

    Returns:
        List of TextContent with alert rule data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if name_filter:
            filters.append(f"name~{name_filter}")
        if priority_filter is not None:
            filters.append(f"priority:{priority_filter}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/setting/alert/rules", params=params)

        rules = []
        for item in result.get("items", []):
            rules.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "priority": item.get("priority"),
                    "escalation_chain_id": item.get("escalatingChainId"),
                    "escalation_chain_name": item.get("escalatingChain", {}).get("name"),
                    "level_str": item.get("levelStr"),
                    "devices": item.get("devices", []),
                    "device_groups": item.get("deviceGroups", []),
                    "datasource": item.get("datasource"),
                    "suppress_alert_clear": item.get("suppressAlertClear"),
                    "suppress_alert_ack_sdt": item.get("suppressAlertAckSdt"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(rules),
                "alert_rules": rules,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_alert_rule(
    client: "LogicMonitorClient",
    rule_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific alert rule.

    Args:
        client: LogicMonitor API client.
        rule_id: Alert rule ID.

    Returns:
        List of TextContent with alert rule details or error.
    """
    try:
        result = await client.get(f"/setting/alert/rules/{rule_id}")

        rule = {
            "id": result.get("id"),
            "name": result.get("name"),
            "priority": result.get("priority"),
            "escalation_chain_id": result.get("escalatingChainId"),
            "escalation_chain_name": result.get("escalatingChain", {}).get("name"),
            "escalation_interval": result.get("escalatingChain", {}).get("period"),
            "level_str": result.get("levelStr"),
            "devices": result.get("devices", []),
            "device_groups": result.get("deviceGroups", []),
            "datasource": result.get("datasource"),
            "datapoint": result.get("datapoint"),
            "instance": result.get("instance"),
            "suppress_alert_clear": result.get("suppressAlertClear"),
            "suppress_alert_ack_sdt": result.get("suppressAlertAckSdt"),
            "resource_properties": [
                {"name": p.get("name"), "value": p.get("value")}
                for p in result.get("resourceProperties", [])
            ],
        }

        return format_response(rule)
    except Exception as e:
        return handle_error(e)
