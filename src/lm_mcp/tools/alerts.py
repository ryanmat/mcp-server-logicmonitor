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
    cleared: bool | None = None,
    acked: bool | None = None,
    sdted: bool | None = None,
    start_epoch: int | None = None,
    end_epoch: int | None = None,
    datapoint: str | None = None,
    instance: str | None = None,
    datasource: str | None = None,
    device: str | None = None,
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
    try:
        params: dict = {"size": min(limit, 1000), "offset": offset}

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        else:
            # Build filter from named parameters
            filters = []
            if severity and severity.lower() in SEVERITY_MAP:
                filters.append(f"severity:{SEVERITY_MAP[severity.lower()]}")
            if status:
                if status.lower() == "active":
                    filters.append("cleared:false")
                    filters.append("acked:false")
                elif status.lower() == "acknowledged":
                    filters.append("acked:true")
            if cleared is not None:
                filters.append(f"cleared:{str(cleared).lower()}")
            if acked is not None:
                filters.append(f"acked:{str(acked).lower()}")
            if sdted is not None:
                filters.append(f"sdted:{str(sdted).lower()}")
            if start_epoch is not None:
                filters.append(f"startEpoch>:{start_epoch}")
            if end_epoch is not None:
                filters.append(f"endEpoch<:{end_epoch}")
            if datapoint:
                filters.append(f"dataPointName~{datapoint}")
            if instance:
                filters.append(f"instanceName~{instance}")
            if datasource:
                filters.append(f"resourceTemplateName~{datasource}")
            if device:
                filters.append(f"monitorObjectName~{device}")

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

        total = result.get("total", 0)
        has_more = (offset + len(alerts)) < total

        return format_response(
            {
                "total": total,
                "count": len(alerts),
                "offset": offset,
                "has_more": has_more,
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


# Maximum items for bulk operations to prevent accidental mass changes
BULK_OPERATION_LIMIT = 100


@require_write_permission
async def bulk_acknowledge_alerts(
    client: "LogicMonitorClient",
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
                "code": "VALIDATION_ERROR",
                "message": "No alert IDs provided",
                "suggestion": "Provide at least one alert ID",
            }
        )

    if len(alert_ids) > BULK_OPERATION_LIMIT:
        return format_response(
            {
                "error": True,
                "code": "BULK_LIMIT_EXCEEDED",
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
