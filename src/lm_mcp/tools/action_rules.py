# Description: Action rule tools for LogicMonitor MCP server.
# Description: Provides action rule CRUD operations for mapping alerts to action chains.

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


async def get_action_rules(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List action rules from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by rule name (supports wildcards).
        limit: Maximum number of rules to return.

    Returns:
        List of TextContent with action rule data or error.
    """
    try:
        params: dict = {"size": limit}
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f'name~{quote_filter_value(clean_name)}'

        result = await client.get("/setting/action/rules", params=params)

        rules = []
        for item in result.get("items", []):
            rules.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "action_chain_id": item.get("actionChainId"),
                    "device_groups": item.get("deviceGroups", []),
                    "devices": item.get("devices", []),
                    "datasource": item.get("datasource"),
                    "datapoint": item.get("datapoint"),
                    "instance": item.get("instance"),
                    "severity": item.get("severity"),
                }
            )

        response = {
            "total": result.get("total", 0),
            "count": len(rules),
            "action_rules": rules,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_action_rule(
    client: "LogicMonitorClient",
    rule_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific action rule.

    Args:
        client: LogicMonitor API client.
        rule_id: Action rule ID.

    Returns:
        List of TextContent with rule details or error.
    """
    try:
        result = await client.get(f"/setting/action/rules/{rule_id}")

        rule = {
            "id": result.get("id"),
            "name": result.get("name"),
            "action_chain_id": result.get("actionChainId"),
            "device_groups": result.get("deviceGroups", []),
            "devices": result.get("devices", []),
            "datasource": result.get("datasource"),
            "datapoint": result.get("datapoint"),
            "instance": result.get("instance"),
            "severity": result.get("severity"),
            "hostname": result.get("hostname"),
            "resource_property": result.get("resourceProperty"),
        }

        return format_response(rule)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_action_rule(
    client: "LogicMonitorClient",
    name: str,
    action_chain_id: int,
    device_groups: list[str] | None = None,
    devices: list[str] | None = None,
    datasource: str | None = None,
    datapoint: str | None = None,
    instance: str | None = None,
    severity: str | None = None,
) -> list[TextContent]:
    """Create an action rule in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Name of the action rule.
        action_chain_id: Action chain to trigger.
        device_groups: Device group patterns to match.
        devices: Device patterns to match.
        datasource: DataSource pattern to match.
        datapoint: DataPoint pattern to match.
        instance: Instance pattern to match.
        severity: Severity filter (warn, error, critical, all).

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {
            "name": name,
            "actionChainId": action_chain_id,
        }

        if device_groups:
            body["deviceGroups"] = device_groups
        if devices:
            body["devices"] = devices
        if datasource:
            body["datasource"] = datasource
        if datapoint:
            body["datapoint"] = datapoint
        if instance:
            body["instance"] = instance
        if severity:
            body["severity"] = severity

        result = await client.post("/setting/action/rules", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Action rule '{name}' created",
                "rule_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_action_rule(
    client: "LogicMonitorClient",
    rule_id: int,
    name: str | None = None,
    action_chain_id: int | None = None,
    device_groups: list[str] | None = None,
    devices: list[str] | None = None,
    datasource: str | None = None,
    datapoint: str | None = None,
    instance: str | None = None,
    severity: str | None = None,
) -> list[TextContent]:
    """Update an action rule in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        rule_id: ID of the action rule to update.
        name: Updated name.
        action_chain_id: Updated action chain ID.
        device_groups: Updated device group patterns.
        devices: Updated device patterns.
        datasource: Updated DataSource pattern.
        datapoint: Updated DataPoint pattern.
        instance: Updated instance pattern.
        severity: Updated severity filter.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {}

        if name is not None:
            body["name"] = name
        if action_chain_id is not None:
            body["actionChainId"] = action_chain_id
        if device_groups is not None:
            body["deviceGroups"] = device_groups
        if devices is not None:
            body["devices"] = devices
        if datasource is not None:
            body["datasource"] = datasource
        if datapoint is not None:
            body["datapoint"] = datapoint
        if instance is not None:
            body["instance"] = instance
        if severity is not None:
            body["severity"] = severity

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "VALIDATION_ERROR",
                    "message": "No fields provided to update",
                }
            )

        result = await client.patch(f"/setting/action/rules/{rule_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Action rule {rule_id} updated",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_action_rule(
    client: "LogicMonitorClient",
    rule_id: int,
) -> list[TextContent]:
    """Delete an action rule from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        rule_id: ID of the action rule to delete.

    Returns:
        List of TextContent with result or error.
    """
    try:
        await client.delete(f"/setting/action/rules/{rule_id}")

        return format_response(
            {
                "success": True,
                "message": f"Action rule {rule_id} deleted",
            }
        )
    except Exception as e:
        return handle_error(e)
