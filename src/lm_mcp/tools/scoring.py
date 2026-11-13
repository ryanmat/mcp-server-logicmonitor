# Description: Scoring and availability analysis tools for LogicMonitor.
# Description: Provides the availability and error budget tools.

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.exceptions import LMError, NotFoundError
from lm_mcp.tools import (
    SEVERITY_MAP,
    format_response,
    handle_error,
    lm_error_code,
    quote_filter_value,
    resolve_group_filter,
    validation_error,
)
from lm_mcp.tools.alerts import read_cleared_and_active

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

logger = logging.getLogger(__name__)

# The report calculate_availability returns, as a JSON Schema. A window with no alerts
# has no measurement_window_context; a resolved device adds device_resolved and device_id.
CALCULATE_AVAILABILITY_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "availability_percent": {"type": "number"},
        "total_downtime_minutes": {"type": "number"},
        "total_uptime_minutes": {"type": "number"},
        "mttr_minutes": {"type": "number"},
        "incident_count": {"type": "integer"},
        "longest_incident_minutes": {"type": "number"},
        "by_device": {"type": "object", "description": "Availability per device name."},
        "hours_back": {"type": "integer"},
        "severity_threshold": {"type": "string"},
        "measurement_window_context": {"type": "object"},
        "truncated": {"type": "boolean"},
        "api_total": {"type": ["integer", "null"]},
        "device_resolved": {"type": "boolean"},
        "device_id": {"type": "integer"},
        "error_budget": {"type": "object"},
    },
    "required": [
        "availability_percent",
        "total_downtime_minutes",
        "total_uptime_minutes",
        "mttr_minutes",
        "incident_count",
        "longest_incident_minutes",
        "by_device",
        "hours_back",
        "severity_threshold",
        "truncated",
        "api_total",
    ],
    "additionalProperties": False,
}


async def calculate_availability(
    client: LogicMonitorClient,
    device_id: int | None = None,
    device_name: str | None = None,
    group_id: int | None = None,
    hours_back: int = 720,
    severity_threshold: str = "error",
    target_slo: float | None = None,
) -> list[TextContent]:
    """Calculate availability percentage from alert history.

    Fetches cleared and active alerts at or above the severity threshold,
    computes downtime windows, merges overlapping incidents, and calculates
    SLA-style availability metrics; with target_slo, the error budget for the
    window too.

    Args:
        client: LogicMonitor API client.
        device_id: Optional device ID filter.
        device_name: Optional device display name filter.
        group_id: Optional device group ID filter; not with a device.
        hours_back: Hours to look back (default: 720 = 30 days).
        severity_threshold: Minimum severity to count as downtime
            (critical, error, warning, info). Default: error.
        target_slo: Target availability percentage, above 0 and at most 100; adds
            error_budget, measured over the hours_back window.

    Returns:
        Availability percentage, downtime, MTTR, and per-device breakdown;
        a device that does not resolve is an error, never 100 percent.
    """
    if target_slo is not None and not 0 < target_slo <= 100:
        return validation_error(
            "INVALID_REQUEST",
            f"target_slo must be above 0 and at most 100, got {target_slo}.",
            "Pass the target availability percentage, such as 99.9.",
        )

    try:
        now_epoch = int(time.time())
        start_epoch = now_epoch - (hours_back * 3600)
        total_window_minutes = hours_back * 60

        # A device's alert list ignores group filters, so a device and a group
        # together have no single scope to read.
        if group_id is not None and (device_id is not None or device_name is not None):
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": (
                        "Pass a device (device_id or device_name) or group_id, not both: "
                        "a device's alert list cannot be filtered by group."
                    ),
                    "suggestion": (
                        "Drop group_id for the device's availability, "
                        "or drop the device for the group's."
                    ),
                }
            )

        # Resolve the device before reading any alert. A device that does not
        # exist is an error, not a clean 100 percent, and a failed lookup must
        # not fall through to availability for an unfiltered alert set.
        device: dict | None = None
        if device_id is not None or device_name is not None:
            device = await _resolve_device(client, device_id, device_name)
            if device.get("error"):
                return format_response(device)

        # Build filter for alerts at or above severity threshold
        min_severity = SEVERITY_MAP.get(severity_threshold.lower(), 3)
        filters = [f"startEpoch>:{start_epoch}"]

        if min_severity < 4:
            filters.append(f"severity>:{min_severity}")
        else:
            filters.append(f"severity:{min_severity}")

        if group_id is not None:
            filters.append(await resolve_group_filter(client, group_id))

        # The /alert/alerts filters ignore a device id, so a resolved device
        # reads its own alert list, which keeps alerts recorded under an
        # earlier display name.
        alert_path = "/alert/alerts" if device is None else f"/device/devices/{device['id']}/alerts"
        alerts, truncated, api_total = await read_cleared_and_active(
            client, ",".join(filters), path=alert_path
        )

        scope: dict[str, Any] = {"truncated": truncated, "api_total": api_total}
        if device is not None:
            scope["device_resolved"] = True
            scope["device_id"] = device["id"]

        if not alerts:
            empty: dict[str, Any] = {
                "availability_percent": 100.0,
                "total_downtime_minutes": 0,
                "total_uptime_minutes": total_window_minutes,
                "mttr_minutes": 0,
                "incident_count": 0,
                "longest_incident_minutes": 0,
                "by_device": {},
                "hours_back": hours_back,
                "severity_threshold": severity_threshold,
                **scope,
            }
            if target_slo is not None:
                empty["error_budget"] = error_budget(target_slo, hours_back, 0.0)
            return format_response(empty)

        # Group alerts by device and compute downtime windows; a resolved
        # device's alerts all count under its current display name.
        device_alerts: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for alert in alerts:
            if device is not None:
                dev = device.get("displayName") or str(device["id"])
            else:
                dev = alert.get("monitorObjectName", "unknown")
            alert_start = max(alert.get("startEpoch", 0), start_epoch)
            alert_end = alert.get("endEpoch", 0)
            if alert_end == 0:
                alert_end = now_epoch  # Still active
            alert_end = min(alert_end, now_epoch)
            if alert_start < alert_end:
                device_alerts[dev].append((alert_start, alert_end))

        # Merge overlapping intervals per device
        by_device = {}
        total_downtime_seconds = 0
        incident_count = 0
        longest_incident = 0
        incident_durations = []

        for dev, intervals in device_alerts.items():
            merged = _merge_intervals(intervals)
            dev_downtime = sum(end - start for start, end in merged)
            dev_downtime_min = dev_downtime / 60.0
            dev_availability = max(
                0.0,
                (1.0 - dev_downtime / (total_window_minutes * 60)) * 100,
            )

            for start, end in merged:
                dur = (end - start) / 60.0
                incident_durations.append(dur)
                if dur > longest_incident:
                    longest_incident = dur

            total_downtime_seconds += dev_downtime
            incident_count += len(merged)

            by_device[dev] = {
                "availability_percent": round(dev_availability, 4),
                "downtime_minutes": round(dev_downtime_min, 2),
                "incident_count": len(merged),
            }

        # Aggregate availability across all devices
        # Use worst-device availability as the aggregate
        if by_device:
            worst_availability = min(d["availability_percent"] for d in by_device.values())
        else:
            worst_availability = 100.0

        mttr = sum(incident_durations) / len(incident_durations) if incident_durations else 0

        # Measurement window context for low availability
        measurement_context: dict = {}
        if worst_availability < 99.9:
            from lm_mcp.resources.best_practices import get_best_practices

            bp = get_best_practices("availability_low").get("availability_low", {})
            measurement_context = {
                "measurement_window_hours": hours_back,
                "severity_threshold": severity_threshold,
                "recommendations": bp.get("recommended_actions", []),
                "anti_patterns": bp.get("anti_patterns", []),
            }

        response: dict[str, Any] = {
            "availability_percent": round(worst_availability, 4),
            "total_downtime_minutes": round(total_downtime_seconds / 60.0, 2),
            "total_uptime_minutes": round(
                max(0.0, total_window_minutes - total_downtime_seconds / 60.0), 2
            ),
            "mttr_minutes": round(mttr, 2),
            "incident_count": incident_count,
            "longest_incident_minutes": round(longest_incident, 2),
            "by_device": by_device,
            "hours_back": hours_back,
            "severity_threshold": severity_threshold,
            "measurement_window_context": measurement_context,
            **scope,
        }
        if target_slo is not None:
            response["error_budget"] = error_budget(
                target_slo, hours_back, total_downtime_seconds / 60.0
            )
        return format_response(response)
    except Exception as e:
        return handle_error(e)


def error_budget(target_slo: float, hours_back: int, consumed_minutes: float) -> dict[str, Any]:
    """The error budget a window of hours_back holds at target_slo, and how much is spent.

    The budget is the window's minutes times (1 - target_slo / 100). The burn rate is
    the consumed share of the budget, and the projected exhaustion is the days the
    remaining budget lasts at the window's daily downtime. Status is exhausted with
    nothing left, critical past 90 percent consumed, warning past 50, else healthy; a
    100 percent target with no downtime is healthy.

    Args:
        target_slo: Target availability percentage, above 0 and at most 100.
        hours_back: Window length in hours, the SLO period.
        consumed_minutes: Downtime in the window.

    Returns:
        target_slo, period_days, the budget, consumed and remaining minutes, the
        consumed percent, burn rate, projected exhaustion in days (None when nothing
        burns or nothing remains) and status.
    """
    period_days = hours_back / 24
    total_budget_minutes = hours_back * 60 * (1 - target_slo / 100)
    remaining_minutes = max(0.0, total_budget_minutes - consumed_minutes)
    burn_rate = consumed_minutes / total_budget_minutes if total_budget_minutes > 0 else 0.0
    daily_consumption = consumed_minutes / period_days if period_days > 0 else 0.0
    projected_exhaustion_days = (
        remaining_minutes / daily_consumption
        if daily_consumption > 0 and remaining_minutes > 0
        else None
    )
    consumed_percent = (
        consumed_minutes / total_budget_minutes * 100 if total_budget_minutes > 0 else 0.0
    )

    if total_budget_minutes == 0 and consumed_minutes == 0:
        status = "healthy"
    elif remaining_minutes <= 0:
        status = "exhausted"
    elif consumed_percent > 90:
        status = "critical"
    elif consumed_percent > 50:
        status = "warning"
    else:
        status = "healthy"

    return {
        "target_slo": target_slo,
        "period_days": round(period_days, 2),
        "total_budget_minutes": round(total_budget_minutes, 2),
        "consumed_minutes": round(consumed_minutes, 2),
        "remaining_minutes": round(remaining_minutes, 2),
        "budget_consumed_percent": round(consumed_percent, 2),
        "burn_rate": round(burn_rate, 4),
        "projected_exhaustion_days": (
            round(projected_exhaustion_days, 1) if projected_exhaustion_days is not None else None
        ),
        "status": status,
    }


async def _resolve_device(
    client: LogicMonitorClient,
    device_id: int | None,
    device_name: str | None,
) -> dict:
    """Resolve a device by id, or by exact display name, to its id and display name.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID; takes precedence over device_name.
        device_name: Exact device display name.

    Returns:
        The device with id and displayName, or an error dict: NOT_FOUND when
        it does not exist, else the code lm_error_code gives the failed lookup.
    """
    target = f"device {device_id}" if device_id is not None else f"device named '{device_name}'"
    try:
        if device_id is not None:
            found: dict | None = await client.get(f"/device/devices/{device_id}")
        else:
            result = await client.get(
                "/device/devices",
                params={
                    "filter": f"displayName:{quote_filter_value(device_name or '')}",
                    "fields": "id,displayName",
                    "size": 1,
                },
            )
            items = result.get("items", [])
            found = items[0] if items else None
    except NotFoundError:
        found = None
    except LMError as exc:
        logger.warning("Could not look up %s for availability", target, exc_info=True)
        return {
            "error": True,
            "code": lm_error_code(exc),
            "message": (
                f"Could not look up {target}: {exc}. "
                "Availability cannot be computed without confirming the device."
            ),
            "suggestion": "Verify the device exists and the API token has read access.",
        }
    if not found:
        return {
            "error": True,
            "code": "NOT_FOUND",
            "message": f"{target.capitalize()} not found, so its availability is unknown.",
            "suggestion": (
                "Check the device_id, or pass the exact display name; get_devices lists both."
            ),
        }
    return found


def _merge_intervals(
    intervals: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Merge overlapping time intervals using sort-by-start greedy merge.

    Args:
        intervals: List of (start, end) epoch pairs.

    Returns:
        Merged list of non-overlapping intervals.
    """
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]

    for start, end in sorted_intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged
