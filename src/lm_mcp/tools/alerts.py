# Description: Alert management tools for LogicMonitor MCP server.
# Description: Provides get_alerts, get_alert_details, acknowledge_alert, add_alert_note,
# and paginate_alerts and read_cleared_and_active, the alert-window reads the analytics share.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    SEVERITY_MAP,
    format_response,
    handle_error,
    list_tool,
    portal_url,
    require_write_permission,
    resolve_group_filter,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# Hard cap on alerts pulled for one windowed analysis.
MAX_ALERTS_PER_WINDOW = 5000
ALERTS_PAGE_SIZE = 1000

# Warning a windowed analysis carries when the cap cut its window short.
ALERT_WINDOW_TRUNCATED_WARNING = (
    f"Truncated at {MAX_ALERTS_PER_WINDOW} alerts. "
    "Narrow the window or scope for complete analysis."
)


async def paginate_alerts(
    client: LogicMonitorClient,
    filter_str: str,
    cap: int = MAX_ALERTS_PER_WINDOW,
    path: str = "/alert/alerts",
) -> tuple[list[dict], bool, int | None]:
    """Pull the alerts matching a filter across pages, up to a cap.

    The cap is clamped to MAX_ALERTS_PER_WINDOW. While rows remain past a
    page the API reports a negative total, a lower bound, so the API total is
    known only when the last page read reported an exact one.

    Args:
        client: LogicMonitor API client.
        filter_str: Filter string for the alert list.
        cap: Most alerts to collect.
        path: Alert list to read; /device/devices/{id}/alerts scopes it to
            one device, which the /alert/alerts filters cannot do by id.

    Returns:
        The alerts, whether the cap stopped collection while more matched,
        and the API's exact total, or None when it reported only a lower bound.
    """
    cap = min(cap, MAX_ALERTS_PER_WINDOW)
    collected: list[dict] = []
    more = False
    api_total: int | None = None
    while len(collected) < cap:
        offset = len(collected)
        params: dict = {
            "size": min(ALERTS_PAGE_SIZE, cap - offset),
            "offset": offset,
            "filter": filter_str,
        }
        result = await client.get(path, params=params)
        items = result.get("items", [])
        raw_total = result.get("total", 0)
        api_total = raw_total if raw_total >= 0 else None
        collected.extend(items)
        more = bool(items) and (raw_total < 0 or offset + len(items) < raw_total)
        if not more:
            break
    return collected[:cap], more or len(collected) > cap, api_total


async def read_cleared_and_active(
    client: LogicMonitorClient,
    filter_str: str,
    path: str = "/alert/alerts",
) -> tuple[list[dict], bool, int | None]:
    """Read a window's active and cleared alerts as one list.

    Both alert lists return active alerts only unless the filter carries
    cleared:true, so the window takes two reads, each under the alert cap. An
    alert that clears between the reads appears in both and is kept once, as
    the cleared copy, which carries its endEpoch.

    Args:
        client: LogicMonitor API client.
        filter_str: Filter string for the active read; the cleared read adds
            cleared:true to it.
        path: Alert list to read, as paginate_alerts takes it.

    Returns:
        The alerts, whether the cap cut either read short, and the sum of both
        API totals, or None when either reported only a lower bound.
    """
    active, active_cut, active_total = await paginate_alerts(client, filter_str, path=path)
    cleared, cleared_cut, cleared_total = await paginate_alerts(
        client, f"{filter_str},cleared:true", path=path
    )
    cleared_ids = {alert["id"] for alert in cleared if alert.get("id") is not None}
    alerts = [alert for alert in active if alert.get("id") not in cleared_ids] + cleared
    api_total = (
        None if active_total is None or cleared_total is None else active_total + cleared_total
    )
    return alerts, active_cut or cleared_cut, api_total


def _normalize_alert_id(alert_id: str) -> str:
    """Strip LMA prefix from alert ID if present.

    Args:
        alert_id: Alert ID, possibly with LMA prefix.

    Returns:
        Numeric alert ID string.
    """
    if alert_id.upper().startswith("LMA"):
        return alert_id[3:]
    return alert_id


def _alert_row(item: dict) -> dict:
    """Project one /alert/alerts row onto the get_alerts fields."""
    return {
        "id": item.get("id"),
        "severity": item.get("severity"),
        "device": item.get("monitorObjectName"),
        "message": item.get("alertValue"),
        "start_time": item.get("startEpoch"),
    }


async def get_alerts(
    client: LogicMonitorClient,
    severity: str | None = None,
    status: str | None = None,
    cleared: bool | None = None,
    acked: bool | None = None,
    sdted: bool | None = None,
    start_epoch: int | None = None,
    end_epoch: int | None = None,
    datapoint: str | None = None,
    instance: str | None = None,
    datasource: str | None = None,
    device: str | None = None,
    group_id: int | None = None,
    device_id: int | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get alerts from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        severity: Filter by severity (critical, error, warning, info).
        status: Filter by status (active, acknowledged).
        cleared: Filter by cleared status (True/False).
        acked: Filter by acknowledged status (True/False).
        sdted: Filter by SDT status (True/False).
        start_epoch: Filter alerts started after this epoch timestamp.
        end_epoch: Filter alerts started before this epoch timestamp.
        datapoint: Filter by datapoint name (supports wildcards).
        instance: Filter by instance name (supports wildcards).
        datasource: Filter by datasource/template name (supports wildcards).
        device: Filter by device/monitor object name (supports wildcards).
        group_id: Filter by device group ID (matches all devices in the group).
        device_id: Filter by device/resource ID.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "severity:4,cleared:false",
            "monitorObjectName~prod,resourceTemplateName:CPU"
        limit: Maximum number of alerts to return (max 1000).
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with alert data or error.
    """
    clauses = []
    if severity and severity.lower() in SEVERITY_MAP:
        clauses.append(f"severity:{SEVERITY_MAP[severity.lower()]}")
    if status:
        if status.lower() == "active":
            clauses.append("cleared:false")
            clauses.append("acked:false")
        elif status.lower() == "acknowledged":
            clauses.append("acked:true")
    if cleared is not None:
        clauses.append(f"cleared:{str(cleared).lower()}")
    if acked is not None:
        clauses.append(f"acked:{str(acked).lower()}")
    if sdted is not None:
        clauses.append(f"sdted:{str(sdted).lower()}")
    if start_epoch is not None:
        clauses.append(f"startEpoch>:{start_epoch}")
    if end_epoch is not None:
        clauses.append(f"endEpoch<:{end_epoch}")
    # The group lookup is an API call, so it runs only when no raw filter replaces the clauses.
    if group_id is not None and not filter:
        try:
            clauses.append(await resolve_group_filter(client, group_id))
        except Exception as e:
            return handle_error(e)
    if device_id is not None:
        clauses.append(f"monitorObjectId:{device_id}")

    return await list_tool(
        client,
        "/alert/alerts",
        key="alerts",
        project=_alert_row,
        limit=min(limit, 1000),
        offset=offset,
        filter=filter,
        named={
            "dataPointName~": datapoint,
            "instanceName~": instance,
            "resourceTemplateName~": datasource,
            "monitorObjectName~": device,
        },
        clauses=clauses,
    )


async def get_alert_details(
    client: LogicMonitorClient,
    alert_id: str,
    include_message: bool = False,
) -> list[TextContent]:
    """Get detailed information about a specific alert.

    Args:
        client: LogicMonitor API client.
        alert_id: Alert ID (with or without LMA prefix).

    Returns:
        List of TextContent with alert details or error.
    """
    try:
        clean_id = _normalize_alert_id(alert_id)
        params = {"needMessage": "true"} if include_message else None
        result = await client.get(f"/alert/alerts/{clean_id}", params=params)
        result["portal_url"] = portal_url("alert", clean_id)
        return format_response(result)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def acknowledge_alert(
    client: LogicMonitorClient,
    alert_id: str,
    note: str = "",
) -> list[TextContent]:
    """Acknowledge an alert in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        alert_id: Alert ID (with or without LMA prefix).
        note: Optional note to add with acknowledgment.

    Returns:
        List of TextContent with result or error.
    """
    try:
        clean_id = _normalize_alert_id(alert_id)
        body = {}
        if note:
            body["ackComment"] = note

        result = await client.post(f"/alert/alerts/{clean_id}/ack", json_body=body or None)
        return format_response(
            {
                "success": True,
                "message": f"Alert {alert_id} acknowledged",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def add_alert_note(
    client: LogicMonitorClient,
    alert_id: str,
    note: str,
) -> list[TextContent]:
    """Add a note to an alert without acknowledging it.

    Args:
        client: LogicMonitor API client.
        alert_id: Alert ID (with or without LMA prefix).
        note: Note text to add.

    Returns:
        List of TextContent with result or error.
    """
    if not note or not note.strip():
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": "Note cannot be empty",
                "suggestion": "Provide a non-empty note text",
            }
        )

    try:
        clean_id = _normalize_alert_id(alert_id)
        result = await client.post(
            f"/alert/alerts/{clean_id}/note",
            json_body={"note": note},
        )
        return format_response(
            {
                "success": True,
                "message": f"Note added to alert {alert_id}",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


# Maximum items for bulk operations to prevent accidental mass changes
BULK_OPERATION_LIMIT = 100


@require_write_permission
async def bulk_acknowledge_alerts(
    client: LogicMonitorClient,
    alert_ids: list[str],
    note: str = "",
) -> list[TextContent]:
    """Acknowledge multiple alerts at once.

    Args:
        client: LogicMonitor API client.
        alert_ids: List of alert IDs (with or without LMA prefix). Max 100 per call.
        note: Optional note to add with acknowledgment.

    Returns:
        List of TextContent with results for each alert.
    """
    if not alert_ids:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": "No alert IDs provided",
                "suggestion": "Provide at least one alert ID",
            }
        )

    if len(alert_ids) > BULK_OPERATION_LIMIT:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": f"Too many items ({len(alert_ids)}). Max {BULK_OPERATION_LIMIT}.",
                "suggestion": "Split into smaller batches",
            }
        )

    results = {"success": [], "failed": []}

    for alert_id in alert_ids:
        try:
            clean_id = _normalize_alert_id(alert_id)
            body = {}
            if note:
                body["ackComment"] = note

            await client.post(f"/alert/alerts/{clean_id}/ack", json_body=body or None)
            results["success"].append(alert_id)
        except Exception as e:
            results["failed"].append({"id": alert_id, "error": str(e)})

    return format_response(
        {
            "total": len(alert_ids),
            "acknowledged": len(results["success"]),
            "failed": len(results["failed"]),
            "success_ids": results["success"],
            "failures": results["failed"],
        }
    )
