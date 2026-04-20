# Description: Escalation chain and recipient group tools for LogicMonitor MCP server.
# Description: Provides CRUD operations for escalation chains and recipient groups.

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


async def get_escalation_chains(
    client: LogicMonitorClient,
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
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f"name~{quote_filter_value(clean_name)}"

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

        response = {
            "total": result.get("total", 0),
            "count": len(chains),
            "escalation_chains": chains,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_escalation_chain(
    client: LogicMonitorClient,
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

        # Parse destinations into readable format.
        # LM API can return stages as [[{...}]] (nested) or [{...}] (flat).
        destinations = []
        for dest in result.get("destinations", []):
            stages = []
            for stage_entry in dest.get("stages", []):
                # Flatten nested stage arrays: [[{...}]] -> [{...}]
                stage_items = stage_entry if isinstance(stage_entry, list) else [stage_entry]
                for stage in stage_items:
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


def _recipient_group_name(item: dict) -> str | None:
    """Return the group name from an LM response dict.

    LogicMonitor's v3 API uses the camelCase key ``groupName`` on read.
    Older portal versions and some write paths accept the plain ``name``
    alias, so we fall back to that for defensive compatibility.
    """
    return item.get("groupName") or item.get("name")


def _format_recipient(recipient: dict) -> dict:
    """Project an LM Recipient dict into the MCP response shape."""
    return {
        "type": recipient.get("type"),
        "method": recipient.get("method"),
        "address": recipient.get("addr"),
        "contact": recipient.get("contact"),
    }


async def get_recipient_groups(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    detail: bool = False,
) -> list[TextContent]:
    """List recipient groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.
        detail: When true, fetch each group's full recipient list via an
            extra GET per group. Off by default to avoid N+1 API calls.

    Returns:
        List of TextContent with recipient group data or error.
    """
    try:
        params: dict = {"size": limit}
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f"name~{quote_filter_value(clean_name)}"

        result = await client.get("/setting/recipientgroups", params=params)

        groups = []
        for item in result.get("items", []):
            entry = {
                "id": item.get("id"),
                "name": _recipient_group_name(item),
                "description": item.get("description"),
            }
            if detail and entry["id"] is not None:
                full = await client.get(f"/setting/recipientgroups/{entry['id']}")
                entry["recipients"] = [_format_recipient(r) for r in full.get("recipients", [])]
            groups.append(entry)

        response = {
            "total": result.get("total", 0),
            "count": len(groups),
            "recipient_groups": groups,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_recipient_group(
    client: LogicMonitorClient,
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

        recipients = [_format_recipient(r) for r in result.get("recipients", [])]

        group = {
            "id": result.get("id"),
            "name": _recipient_group_name(result),
            "description": result.get("description"),
            "recipients": recipients,
        }

        return format_response(group)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_escalation_chain(
    client: LogicMonitorClient,
    name: str,
    description: str | None = None,
    enable_throttling: bool = False,
    throttling_period: int | None = None,
    throttling_alerts: int | None = None,
    destinations: list[dict] | None = None,
    cc_destinations: list[dict] | None = None,
) -> list[TextContent]:
    """Create an escalation chain in LogicMonitor.

    Each destination is a Chain object with shape::

        {
            "type": "single" | "timebased",
            "period": null | {"hour1": 9, "hour2": 17, ...},
            "stages": [[<Recipient>, ...], [<Recipient>, ...]]
        }

    ``stages`` is a list of stage arrays; each stage is itself a list of
    Recipient objects. To route to an LM Integration (e.g., a Custom HTTP
    Delivery), use a Recipient of the form::

        {"type": "admin", "addr": "<username>", "method": "<integration display name>"}

    Lowercase ``admin`` is required. ``method`` is the integration's
    display name string, not its id. ``addr`` is a username that owns
    the integration as one of their contact methods.

    Args:
        client: LogicMonitor API client.
        name: Name of the escalation chain.
        description: Optional description.
        enable_throttling: Whether to enable alert throttling.
        throttling_period: Throttling period in minutes.
        throttling_alerts: Number of alerts before throttling.
        destinations: List of Chain objects (see shape above).
        cc_destinations: List of Recipient objects for CC notifications.

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
        if destinations is not None:
            body["destinations"] = destinations
        if cc_destinations is not None:
            body["ccDestinations"] = cc_destinations

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
    client: LogicMonitorClient,
    chain_id: int,
    name: str | None = None,
    description: str | None = None,
    enable_throttling: bool | None = None,
    throttling_period: int | None = None,
    throttling_alerts: int | None = None,
    destinations: list[dict] | None = None,
    cc_destinations: list[dict] | None = None,
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
        destinations: Updated destination stage dicts for the escalation chain.
        cc_destinations: Updated CC destination dicts for the escalation chain.

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
        if destinations is not None:
            body["destinations"] = destinations
        if cc_destinations is not None:
            body["ccDestinations"] = cc_destinations

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
    client: LogicMonitorClient,
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
    client: LogicMonitorClient,
    name: str,
    description: str | None = None,
    recipients: list[dict] | None = None,
) -> list[TextContent]:
    """Create a recipient group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Name of the recipient group. Sent as ``groupName`` per the
            LM v3 API model.
        description: Optional description.
        recipients: Optional list of Recipient objects to preload into the
            group. Each entry is a dict with keys ``type``, ``method``,
            ``addr``, and optional ``contact``. ``type`` and ``method``
            are required by the LM API. Example entry::

                {"type": "admin", "method": "email", "addr": "oncall@example.com"}

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {"groupName": name}

        if description:
            body["description"] = description
        if recipients is not None:
            body["recipients"] = recipients

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
    client: LogicMonitorClient,
    group_id: int,
    name: str | None = None,
    description: str | None = None,
    recipients: list[dict] | None = None,
) -> list[TextContent]:
    """Update a recipient group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: ID of the recipient group to update.
        name: Updated name. Sent as ``groupName`` per the LM v3 API model.
        description: Updated description.
        recipients: Optional replacement recipient list. When provided,
            LM replaces the group's current recipient set with this list.
            Same entry shape as ``create_recipient_group``.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {}

        if name is not None:
            body["groupName"] = name
        if description is not None:
            body["description"] = description
        if recipients is not None:
            body["recipients"] = recipients

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
    client: LogicMonitorClient,
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
