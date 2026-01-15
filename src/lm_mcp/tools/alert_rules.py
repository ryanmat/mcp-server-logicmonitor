# Description: Alert rule tools for LogicMonitor MCP server.
# Description: Provides alert rule CRUD operations.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

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


@require_write_permission
async def create_alert_rule(
    client: "LogicMonitorClient",
    name: str,
    priority: int,
    escalation_chain_id: int,
    level_str: str | None = None,
    devices: list[str] | None = None,
    device_groups: list[str] | None = None,
    datasource: str | None = None,
    datapoint: str | None = None,
    instance: str | None = None,
    suppress_alert_clear: bool = False,
    suppress_alert_ack_sdt: bool = False,
) -> list[TextContent]:
    """Create an alert rule in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Name of the alert rule.
        priority: Priority level (lower = higher priority).
        escalation_chain_id: Escalation chain ID for the rule.
        level_str: Alert level filter (Critical, Error, Warning, All).
        devices: List of device patterns to match.
        device_groups: List of device group patterns to match.
        datasource: DataSource pattern to match.
        datapoint: DataPoint pattern to match.
        instance: Instance pattern to match.
        suppress_alert_clear: Whether to suppress alert clear notifications.
        suppress_alert_ack_sdt: Whether to suppress ack/SDT notifications.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {
            "name": name,
            "priority": priority,
            "escalatingChainId": escalation_chain_id,
            "suppressAlertClear": suppress_alert_clear,
            "suppressAlertAckSdt": suppress_alert_ack_sdt,
        }

        if level_str:
            body["levelStr"] = level_str
        if devices:
            body["devices"] = devices
        if device_groups:
            body["deviceGroups"] = device_groups
        if datasource:
            body["datasource"] = datasource
        if datapoint:
            body["datapoint"] = datapoint
        if instance:
            body["instance"] = instance

        result = await client.post("/setting/alert/rules", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Alert rule '{name}' created",
                "rule_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_alert_rule(
    client: "LogicMonitorClient",
    rule_id: int,
    name: str | None = None,
    priority: int | None = None,
    escalation_chain_id: int | None = None,
    level_str: str | None = None,
    suppress_alert_clear: bool | None = None,
    suppress_alert_ack_sdt: bool | None = None,
) -> list[TextContent]:
    """Update an alert rule in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        rule_id: ID of the alert rule to update.
        name: Updated name.
        priority: Updated priority level.
        escalation_chain_id: Updated escalation chain ID.
        level_str: Updated alert level filter.
        suppress_alert_clear: Updated suppress alert clear setting.
        suppress_alert_ack_sdt: Updated suppress ack/SDT setting.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {}

        if name is not None:
            body["name"] = name
        if priority is not None:
            body["priority"] = priority
        if escalation_chain_id is not None:
            body["escalatingChainId"] = escalation_chain_id
        if level_str is not None:
            body["levelStr"] = level_str
        if suppress_alert_clear is not None:
            body["suppressAlertClear"] = suppress_alert_clear
        if suppress_alert_ack_sdt is not None:
            body["suppressAlertAckSdt"] = suppress_alert_ack_sdt

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "VALIDATION_ERROR",
                    "message": "No fields provided to update",
                }
            )

        result = await client.patch(f"/setting/alert/rules/{rule_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Alert rule {rule_id} updated",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_alert_rule(
    client: "LogicMonitorClient",
    rule_id: int,
) -> list[TextContent]:
    """Delete an alert rule from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        rule_id: ID of the alert rule to delete.

    Returns:
        List of TextContent with result or error.
    """
    try:
        await client.delete(f"/setting/alert/rules/{rule_id}")

        return format_response(
            {
                "success": True,
                "message": f"Alert rule {rule_id} deleted",
            }
        )
    except Exception as e:
        return handle_error(e)
