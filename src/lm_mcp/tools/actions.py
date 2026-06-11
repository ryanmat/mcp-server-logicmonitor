# Description: Action chain and action rule tools for LogicMonitor MCP server.
# Description: CRUD for /setting/action/chains and /setting/action/rules (ADR automation).

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    require_write_permission,
    safe_total,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

_STAGE_TYPES = ("diagnosticSource", "remediationSource")


def _project_chain(item: dict) -> dict:
    """Project an ActionChain to snake_case with stage summary."""
    stages = item.get("stages") or []
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "stage_count": len(stages),
        "stages": [
            {"id": s.get("id"), "type": s.get("type"), "name": s.get("name")} for s in stages
        ],
    }


def _validate_stages(stages: list) -> str | None:
    """Validate the create/update stages payload; return an error message or None.

    Each stage is {id: <source id>, type: diagnosticSource|remediationSource,
    name?}. The id references a DiagnosticSource or RemediationSource.
    """
    if not isinstance(stages, list) or not stages:
        return "stages must be a non-empty list of {id, type} objects."
    for i, stage in enumerate(stages):
        if not isinstance(stage, dict):
            return f"stages[{i}] must be an object with id and type."
        if not isinstance(stage.get("id"), int):
            return f"stages[{i}].id must be an integer source ID."
        if stage.get("type") not in _STAGE_TYPES:
            return f"stages[{i}].type must be one of {list(_STAGE_TYPES)}."
    return None


async def get_action_chains(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List action chains (ordered diagnostic/remediation stages).

    Action chains are the ADR automation unit: named sequences of
    DiagnosticSource and RemediationSource stages that action rules bind
    to alerts. The list endpoint declares no filter support, so
    name_filter is applied client-side.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by chain name (substring, client-side).
        limit: Maximum number of chains to return.
        offset: Results to skip for pagination.

    Returns:
        List of TextContent with action chains or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}
        result = await client.get("/setting/action/chains", params=params)

        chains = []
        for item in result.get("items", []):
            if name_filter and name_filter.lower() not in str(item.get("name", "")).lower():
                continue
            chains.append(_project_chain(item))

        return format_response(
            {
                "total": safe_total(result),
                "count": len(chains),
                "action_chains": chains,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_action_chain(
    client: LogicMonitorClient,
    chain_id: int,
) -> list[TextContent]:
    """Get details about a specific action chain including its stages.

    Args:
        client: LogicMonitor API client.
        chain_id: Action chain ID.

    Returns:
        List of TextContent with chain details or error.
    """
    try:
        result = await client.get(f"/setting/action/chains/{chain_id}")
        return format_response(_project_chain(result))
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_action_chain(
    client: LogicMonitorClient,
    name: str,
    stages: list,
    description: str | None = None,
) -> list[TextContent]:
    """Create an action chain from ordered diagnostic/remediation stages.

    Args:
        client: LogicMonitor API client.
        name: Chain name.
        stages: Ordered list of stages, each
            {id: <source id>, type: "diagnosticSource"|"remediationSource",
            name?: <source name>}.
        description: Optional chain description.

    Returns:
        List of TextContent with created chain info or error.
    """
    stage_error = _validate_stages(stages)
    if stage_error:
        return format_response({"error": True, "code": "VALIDATION_ERROR", "message": stage_error})
    try:
        payload: dict = {"name": name, "stages": stages}
        if description is not None:
            payload["description"] = description

        result = await client.post("/setting/action/chains", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"Action chain '{result.get('name', name)}' created",
                "action_chain": _project_chain(result),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_action_chain(
    client: LogicMonitorClient,
    chain_id: int,
    name: str | None = None,
    stages: list | None = None,
    description: str | None = None,
) -> list[TextContent]:
    """Update an action chain (PATCH; only provided fields are sent).

    Args:
        client: LogicMonitor API client.
        chain_id: Action chain ID to update.
        name: New chain name.
        stages: Replacement ordered stage list, each
            {id, type: "diagnosticSource"|"remediationSource", name?}.
        description: New description.

    Returns:
        List of TextContent with updated chain info or error.
    """
    body: dict = {}
    if name is not None:
        body["name"] = name
    if stages is not None:
        stage_error = _validate_stages(stages)
        if stage_error:
            return format_response(
                {"error": True, "code": "VALIDATION_ERROR", "message": stage_error}
            )
        body["stages"] = stages
    if description is not None:
        body["description"] = description

    if not body:
        return format_response(
            {
                "error": True,
                "code": "NO_CHANGES",
                "message": "Provide at least one of name, stages, or description.",
            }
        )
    try:
        result = await client.patch(f"/setting/action/chains/{chain_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Action chain '{result.get('name')}' updated",
                "action_chain": _project_chain(result),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_action_chain(
    client: LogicMonitorClient,
    chain_id: int,
) -> list[TextContent]:
    """Delete an action chain.

    WARNING: Action rules referencing this chain stop triggering it.

    Args:
        client: LogicMonitor API client.
        chain_id: Action chain ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        chain = await client.get(f"/setting/action/chains/{chain_id}")
        chain_name = chain.get("name", f"ID:{chain_id}")

        await client.delete(f"/setting/action/chains/{chain_id}")

        return format_response(
            {
                "success": True,
                "message": f"Action chain '{chain_name}' deleted",
                "chain_id": chain_id,
            }
        )
    except Exception as e:
        return handle_error(e)


def _project_rule(item: dict) -> dict:
    """Project an ActionRule to snake_case."""
    chain = item.get("actionChain") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "level": item.get("levelStr"),
        "device_groups": item.get("deviceGroups"),
        "devices": item.get("devices"),
        "datasource": item.get("datasource"),
        "instance": item.get("instance"),
        "datapoint": item.get("datapoint"),
        "resource_properties": item.get("resourceProperties"),
        "action_chain_id": item.get("actionChainId"),
        "action_chain_name": chain.get("name"),
        "enabled": item.get("enabled"),
    }


async def get_action_rules(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List action rules (alert conditions that trigger action chains).

    An action rule binds an action chain to alerts by severity, device
    groups, and optional datasource/instance/datapoint matchers. The list
    endpoint declares no filter support, so name_filter is client-side.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by rule name (substring, client-side).
        limit: Maximum number of rules to return.
        offset: Results to skip for pagination.

    Returns:
        List of TextContent with action rules or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}
        result = await client.get("/setting/action/rules", params=params)

        rules = []
        for item in result.get("items", []):
            if name_filter and name_filter.lower() not in str(item.get("name", "")).lower():
                continue
            rules.append(_project_rule(item))

        return format_response(
            {
                "total": safe_total(result),
                "count": len(rules),
                "action_rules": rules,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_action_rule(
    client: LogicMonitorClient,
    rule_id: int,
) -> list[TextContent]:
    """Get details about a specific action rule.

    Args:
        client: LogicMonitor API client.
        rule_id: Action rule ID.

    Returns:
        List of TextContent with rule details or error.
    """
    try:
        result = await client.get(f"/setting/action/rules/{rule_id}")
        return format_response(_project_rule(result))
    except Exception as e:
        return handle_error(e)


def _build_rule_body(
    name: str | None,
    level: str | None,
    device_groups: list | None,
    action_chain_id: int | None,
    devices: list | None,
    datasource: str | None,
    instance: str | None,
    datapoint: str | None,
    resource_properties: list | None,
    enabled: bool | None,
) -> dict:
    """Build an ActionRule write body from provided fields only."""
    body: dict = {}
    if name is not None:
        body["name"] = name
    if level is not None:
        body["levelStr"] = level
    if device_groups is not None:
        body["deviceGroups"] = device_groups
    if action_chain_id is not None:
        body["actionChainId"] = action_chain_id
    if devices is not None:
        body["devices"] = devices
    if datasource is not None:
        body["datasource"] = datasource
    if instance is not None:
        body["instance"] = instance
    if datapoint is not None:
        body["datapoint"] = datapoint
    if resource_properties is not None:
        body["resourceProperties"] = resource_properties
    if enabled is not None:
        body["enabled"] = enabled
    return body


@require_write_permission
async def create_action_rule(
    client: LogicMonitorClient,
    name: str,
    level: str,
    device_groups: list,
    action_chain_id: int,
    devices: list | None = None,
    datasource: str | None = None,
    instance: str | None = None,
    datapoint: str | None = None,
    resource_properties: list | None = None,
    enabled: bool = True,
) -> list[TextContent]:
    """Create an action rule binding an action chain to alert conditions.

    Args:
        client: LogicMonitor API client.
        name: Rule name.
        level: Alert severity to match (e.g. Error, Critical).
        device_groups: Device group full paths to match (["*"] for all).
        action_chain_id: Action chain to trigger.
        devices: Device display names to match (["*"] for all).
        datasource: Datasource name matcher.
        instance: Instance matcher.
        datapoint: Datapoint matcher.
        resource_properties: Property matchers, each {name, value}.
        enabled: Whether the rule starts enabled.

    Returns:
        List of TextContent with created rule info or error.
    """
    try:
        body = _build_rule_body(
            name,
            level,
            device_groups,
            action_chain_id,
            devices,
            datasource,
            instance,
            datapoint,
            resource_properties,
            enabled,
        )

        result = await client.post("/setting/action/rules", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Action rule '{result.get('name', name)}' created",
                "action_rule": _project_rule(result),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_action_rule(
    client: LogicMonitorClient,
    rule_id: int,
    name: str | None = None,
    level: str | None = None,
    device_groups: list | None = None,
    action_chain_id: int | None = None,
    devices: list | None = None,
    datasource: str | None = None,
    instance: str | None = None,
    datapoint: str | None = None,
    resource_properties: list | None = None,
    enabled: bool | None = None,
) -> list[TextContent]:
    """Update an action rule (PATCH; only provided fields are sent).

    Args:
        client: LogicMonitor API client.
        rule_id: Action rule ID to update.
        name: New rule name.
        level: Alert severity to match (e.g. Error, Critical).
        device_groups: Device group full paths to match.
        action_chain_id: Action chain to trigger.
        devices: Device display names to match.
        datasource: Datasource name matcher.
        instance: Instance matcher.
        datapoint: Datapoint matcher.
        resource_properties: Property matchers, each {name, value}.
        enabled: Enable/disable the rule (set_action_rule_status is the
            lighter tool for this alone).

    Returns:
        List of TextContent with updated rule info or error.
    """
    body = _build_rule_body(
        name,
        level,
        device_groups,
        action_chain_id,
        devices,
        datasource,
        instance,
        datapoint,
        resource_properties,
        enabled,
    )
    if not body:
        return format_response(
            {
                "error": True,
                "code": "NO_CHANGES",
                "message": "Provide at least one field to update.",
            }
        )
    try:
        result = await client.patch(f"/setting/action/rules/{rule_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Action rule '{result.get('name')}' updated",
                "action_rule": _project_rule(result),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_action_rule(
    client: LogicMonitorClient,
    rule_id: int,
) -> list[TextContent]:
    """Delete an action rule.

    Args:
        client: LogicMonitor API client.
        rule_id: Action rule ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        rule = await client.get(f"/setting/action/rules/{rule_id}")
        rule_name = rule.get("name", f"ID:{rule_id}")

        await client.delete(f"/setting/action/rules/{rule_id}")

        return format_response(
            {
                "success": True,
                "message": f"Action rule '{rule_name}' deleted",
                "rule_id": rule_id,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def set_action_rule_status(
    client: LogicMonitorClient,
    rule_id: int,
    enabled: bool,
) -> list[TextContent]:
    """Enable or disable an action rule without touching its matchers.

    Args:
        client: LogicMonitor API client.
        rule_id: Action rule ID.
        enabled: True to enable, False to disable.

    Returns:
        List of TextContent with the new status or error.
    """
    try:
        result = await client.put(
            f"/setting/action/rules/{rule_id}/status", json_body={"enabled": enabled}
        )

        return format_response(
            {
                "success": True,
                "rule_id": rule_id,
                "enabled": result.get("enabled", enabled),
                "message": f"Action rule {rule_id} {'enabled' if enabled else 'disabled'}",
            }
        )
    except Exception as e:
        return handle_error(e)
