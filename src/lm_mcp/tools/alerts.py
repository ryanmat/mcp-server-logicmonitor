# Description: Alert management tools for LogicMonitor MCP server.
# Description: Provides get_alerts, get_alert_details, acknowledge_alert, add_alert_note.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# Severity mapping for LogicMonitor alerts
SEVERITY_MAP = {
    "critical": 4,
    "error": 3,
    "warning": 2,
    "info": 1,
}


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


async def get_alerts(
    client: "LogicMonitorClient",
    severity: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get alerts from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        severity: Filter by severity (critical, error, warning, info).
        status: Filter by status (active, acknowledged).
        limit: Maximum number of alerts to return.

    Returns:
        List of TextContent with alert data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if severity and severity.lower() in SEVERITY_MAP:
            filters.append(f"severity:{SEVERITY_MAP[severity.lower()]}")
        if status:
            if status.lower() == "active":
                filters.append("cleared:false,acked:false")
            elif status.lower() == "acknowledged":
                filters.append("acked:true")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/alert/alerts", params=params)

        alerts = []
        for item in result.get("items", []):
            alerts.append(
                {
                    "id": item.get("id"),
                    "severity": item.get("severity"),
                    "device": item.get("monitorObjectName"),
                    "message": item.get("alertValue"),
                    "start_time": item.get("startEpoch"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(alerts),
                "alerts": alerts,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_alert_details(
    client: "LogicMonitorClient",
    alert_id: str,
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
        result = await client.get(f"/alert/alerts/{clean_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def acknowledge_alert(
    client: "LogicMonitorClient",
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
    client: "LogicMonitorClient",
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
                "code": "VALIDATION_ERROR",
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
