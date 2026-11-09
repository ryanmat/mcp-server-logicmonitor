# Description: Scoring and availability analysis tools for LogicMonitor.
# Description: Provides alert noise scoring, availability, and error budget tools.

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.exceptions import LMError, NotFoundError
from lm_mcp.tools import (
    SEVERITY_MAP,
    call_sub_tool,
    format_response,
    handle_error,
    lm_error_code,
    quote_filter_value,
    resolve_group_filter,
)
from lm_mcp.tools.alerts import read_cleared_and_active
from lm_mcp.tools.analyze_alerts import noise_stats, window_filter

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

logger = logging.getLogger(__name__)


async def score_alert_noise(
    client: LogicMonitorClient,
    hours_back: int = 24,
    device: str | None = None,
    group_id: int | None = None,
) -> list[TextContent]:
    """Score alert noise level using Shannon entropy and flap detection.

    Analyzes alert frequency distribution and identifies flapping alerts
    (alerts that clear and re-fire within 30 minutes). Produces a noise
    score from 0 (quiet) to 100 (extremely noisy).

    Args:
        client: LogicMonitor API client.
        hours_back: Hours to look back (default: 24).
        device: Optional device name filter.
        group_id: Optional device group ID filter.

    Returns:
        Noise score with entropy, flapping alerts, and recommendations;
        truncated says whether the 5000-alert cap cut the active or the cleared
        read short and api_total is the sum of both reads' API counts, null
        when either reported only a lower bound.
    """
    try:
        start_epoch = int(time.time()) - hours_back * 3600
        filter_str = await window_filter(client, start_epoch, device=device, group_id=group_id)
        alerts, truncated, api_total = await read_cleared_and_active(client, filter_str)
        return format_response(
            {
                **noise_stats(alerts),
                "truncated": truncated,
                "api_total": api_total,
                "hours_back": hours_back,
            }
        )
    except Exception as e:
        return handle_error(e)


async def calculate_availability(
    client: LogicMonitorClient,
    device_id: int | None = None,
    device_name: str | None = None,
    group_id: int | None = None,
    hours_back: int = 720,
    severity_threshold: str = "error",
) -> list[TextContent]:
    """Calculate availability percentage from alert history.

    Fetches cleared and active alerts at or above the severity threshold,
    computes downtime windows, merges overlapping incidents, and calculates
    SLA-style availability metrics.

    Args:
        client: LogicMonitor API client.
        device_id: Optional device ID filter.
        device_name: Optional device display name filter.
        group_id: Optional device group ID filter; not with a device.
        hours_back: Hours to look back (default: 720 = 30 days).
        severity_threshold: Minimum severity to count as downtime
            (critical, error, warning, info). Default: error.

    Returns:
        Availability percentage, downtime, MTTR, and per-device breakdown;
        a device that does not resolve is an error, never 100 percent.
    """
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
            return format_response(
                {
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
            )

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

        return format_response(
            {
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
        )
    except Exception as e:
        return handle_error(e)


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


async def calculate_error_budget(
    client: LogicMonitorClient,
    device_id: int | None = None,
    group_id: int | None = None,
    target_slo: float = 99.9,
    period_days: int = 30,
) -> list[TextContent]:
    """Calculate SLO error budget consumption and projected exhaustion.

    Calls calculate_availability internally, then computes remaining
    error budget based on the target SLO.

    Args:
        client: LogicMonitor API client.
        device_id: Optional device ID filter.
        group_id: Optional device group ID filter.
        target_slo: Target SLO percentage (default: 99.9).
        period_days: SLO measurement period in days (default: 30).

    Returns:
        Error budget status with remaining minutes and burn rate.
    """
    try:
        # Route through call_sub_tool so an upstream error from
        # calculate_availability (e.g. the failed device lookup above) surfaces
        # as a clean RuntimeError rather than a JSONDecodeError -- this is
        # the same hardening v3.8.2 added to workflow composites.
        avail_data = await call_sub_tool(
            calculate_availability,
            client,
            device_id=device_id,
            group_id=group_id,
            hours_back=period_days * 24,
        )

        total_minutes = period_days * 24 * 60
        total_budget_minutes = total_minutes * (1 - target_slo / 100)
        consumed_minutes = avail_data.get("total_downtime_minutes", 0)
        remaining_minutes = max(0.0, total_budget_minutes - consumed_minutes)

        # Calculate elapsed days in the period
        elapsed_days = period_days  # Full period for historical calculation

        # Burn rate: how fast we are consuming the budget
        if elapsed_days > 0 and total_budget_minutes > 0:
            burn_rate = consumed_minutes / (elapsed_days * (total_budget_minutes / period_days))
        else:
            burn_rate = 0.0

        # Projected exhaustion
        if burn_rate > 0 and remaining_minutes > 0:
            daily_consumption = consumed_minutes / elapsed_days if elapsed_days > 0 else 0
            projected_exhaustion_days = (
                remaining_minutes / daily_consumption if daily_consumption > 0 else None
            )
        else:
            projected_exhaustion_days = None

        # Budget consumption percentage
        budget_consumed_percent = (
            (consumed_minutes / total_budget_minutes * 100) if total_budget_minutes > 0 else 0.0
        )

        # Status classification
        # Edge case: 100% SLO means zero budget. If no downtime
        # occurred, treat it as healthy rather than exhausted.
        if total_budget_minutes == 0 and consumed_minutes == 0:
            status = "healthy"
        elif remaining_minutes <= 0:
            status = "exhausted"
        elif budget_consumed_percent > 90:
            status = "critical"
        elif budget_consumed_percent > 50:
            status = "warning"
        else:
            status = "healthy"

        return format_response(
            {
                "target_slo": target_slo,
                "period_days": period_days,
                "actual_availability": avail_data.get("availability_percent", 100.0),
                "total_budget_minutes": round(total_budget_minutes, 2),
                "consumed_minutes": round(consumed_minutes, 2),
                "remaining_minutes": round(remaining_minutes, 2),
                "budget_consumed_percent": round(budget_consumed_percent, 2),
                "burn_rate": round(burn_rate, 4),
                "projected_exhaustion_days": (
                    round(projected_exhaustion_days, 1)
                    if projected_exhaustion_days is not None
                    else None
                ),
                "status": status,
                "incident_count": avail_data.get("incident_count", 0),
            }
        )
    except Exception as e:
        return handle_error(e)
