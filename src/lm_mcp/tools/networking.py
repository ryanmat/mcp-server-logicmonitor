# Description: Network intelligence tools for LogicMonitor MCP server.
# Description: Interface metrics, device NetFlow (flows and top talkers), link flaps, power events.

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    SEVERITY_MAP,
    format_response,
    handle_error,
    list_tool,
    quote_filter_value,
    resolve_group_filter,
    sanitize_filter_value,
    validation_error,
)
from lm_mcp.tools.alerts import ALERT_WINDOW_TRUNCATED_WARNING, paginate_alerts
from lm_mcp.tools.stats_helpers import PAGE_CAP_WARNING, fetch_metric_pages, window_params

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# Interface-family DataSource name patterns for interface metric resolution.
_INTERFACE_DATASOURCE_PATTERNS = ("interface", "interfaces", "if-", "port", "ethernet")

# Preferred Interface DataSource when multiple match.
_PREFERRED_INTERFACE_DATASOURCE = "SNMP_Network_Interfaces"

# Default datapoints pulled when caller does not specify.
_DEFAULT_INTERFACE_METRICS = (
    "RxRate,TxRate,ErrorsIn,ErrorsOut,DiscardsIn,DiscardsOut,InterfaceStatus"
)

# UPS/PDU DataSource name patterns used by get_power_events.
_DEFAULT_POWER_PATTERNS = (
    "UPS",
    "PDU",
    "APC",
    "Liebert",
    "Eaton",
    "Battery",
    "PowerSupply",
    "Power_",
)

# get_device_top_talkers' by: the device path each reads and the response key of its rows;
# graph reads the top talkers graph whole.
_TOP_TALKERS_PATHS = {"endpoint": ("endpoints", "endpoints"), "port": ("ports", "ports")}
_TOP_TALKERS_BY = (*_TOP_TALKERS_PATHS, "graph")


async def get_interface_metrics(
    client: LogicMonitorClient,
    device_id: int,
    interface: str,
    metrics: str | None = None,
    hours_back: int = 1,
) -> list[TextContent]:
    """Fetch per-interface time-series metrics for a device.

    Resolves the Interface-family DataSource applied to the device, matches
    the interface name (contains match, case-insensitive) against its
    instances, then fetches the requested datapoints over the time window.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        interface: Interface name or partial match (e.g., "Gi0/1", "eth0").
        metrics: Comma-separated datapoint names. Defaults to a common set
            (RxRate, TxRate, ErrorsIn, ErrorsOut, DiscardsIn, DiscardsOut,
            InterfaceStatus).
        hours_back: How many hours of history to pull (default: 1).

    Returns:
        List of TextContent with metric data or error.
    """
    try:
        ds_result = await client.get(
            f"/device/devices/{device_id}/devicedatasources",
            params={"size": 200},
        )
        interface_ds = _pick_interface_datasource(ds_result.get("items", []))
        if interface_ds is None:
            return format_response(
                {
                    "error": True,
                    "code": "NOT_FOUND",
                    "message": (f"No Interface-family DataSource found on device {device_id}"),
                    "suggestion": (
                        "Verify SNMP monitoring is configured and that "
                        "SNMP_Network_Interfaces (or equivalent) is applied to the device."
                    ),
                }
            )

        dsid = interface_ds["id"]
        ds_name = interface_ds.get("dataSourceName")

        instances_result = await client.get(
            f"/device/devices/{device_id}/devicedatasources/{dsid}/instances",
            params={"size": 500},
        )
        instances = instances_result.get("items", [])
        instance = _match_interface_instance(instances, interface)
        if instance is None:
            available = [item.get("displayName") or item.get("name") for item in instances[:50]]
            return format_response(
                {
                    "error": True,
                    "code": "NOT_FOUND",
                    "message": (
                        f"Interface '{interface}' not found among instances on device "
                        f"{device_id} (DataSource: {ds_name})"
                    ),
                    "available_instances": available,
                    "suggestion": (
                        "Check the interface name case and format. The match is "
                        "case-insensitive substring on name and displayName."
                    ),
                }
            )

        end_time = int(time.time())
        start_time = end_time - (hours_back * 3600)
        datapoints = metrics or _DEFAULT_INTERFACE_METRICS

        dp_names, times, values, truncated = await fetch_metric_pages(
            client,
            f"/device/devices/{device_id}/devicedatasources/{dsid}/instances/{instance['id']}/data",
            {"datapoints": datapoints, "start": start_time, "end": end_time},
        )

        response = {
            "device_id": device_id,
            "interface": interface,
            "resolved_datasource": ds_name,
            "resolved_datasource_id": dsid,
            "resolved_instance": instance.get("displayName") or instance.get("name"),
            "resolved_instance_id": instance["id"],
            "window_hours": hours_back,
            "datapoints": dp_names,
            "values": values,
            "time": times,
            "truncated": truncated,
        }
        if truncated:
            response["warning"] = PAGE_CAP_WARNING
        return format_response(response)
    except Exception as e:
        return handle_error(e)


def _pick_interface_datasource(items: list[dict]) -> dict | None:
    """Pick the best Interface-family DataSource from a device's DataSource list."""
    matches = [
        item
        for item in items
        if any(
            p in (item.get("dataSourceName") or "").lower() for p in _INTERFACE_DATASOURCE_PATTERNS
        )
    ]
    if not matches:
        return None
    for item in matches:
        if item.get("dataSourceName") == _PREFERRED_INTERFACE_DATASOURCE:
            return item
    return matches[0]


def _match_interface_instance(instances: list[dict], interface: str) -> dict | None:
    """Case-insensitive contains match on name or displayName."""
    needle = interface.lower()
    for item in instances:
        name = (item.get("name") or "").lower()
        display = (item.get("displayName") or "").lower()
        if needle in name or needle in display:
            return item
    return None


def _netflow_window(hours_back: int) -> dict[str, int]:
    """The start and end of a NetFlow read: the last hours_back hours, ending now."""
    return window_params(int(time.time()) - hours_back * 3600, None)


async def get_device_flows(
    client: LogicMonitorClient,
    device_id: int,
    hours_back: int = 1,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List a device's NetFlow flow records over the last hours_back hours, rows as the API
    returns them.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID of the NetFlow exporter.
        hours_back: Hours of flows to read, ending now.
        limit: Maximum number of flows to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the flows or error; FEATURE_DISABLED when the portal
        answers that NetFlow is off.
    """
    return await list_tool(
        client,
        f"/device/devices/{device_id}/flows",
        key="flows",
        project=dict,
        limit=limit,
        offset=offset,
        params=_netflow_window(hours_back),
        extra={"device_id": device_id, "window_hours": hours_back},
    )


async def get_device_top_talkers(
    client: LogicMonitorClient,
    device_id: int,
    by: str = "endpoint",
    hours_back: int = 1,
    limit: int = 10,
    offset: int = 0,
) -> list[TextContent]:
    """Read a device's NetFlow top talkers over the last hours_back hours.

    by="endpoint" pages the endpoints it saw and by="port" the ports, rows as the API
    returns them; by="graph" returns its top talkers graph whole, with no paging.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID of the NetFlow exporter.
        by: endpoint, port or graph.
        hours_back: Hours of flows to read, ending now.
        limit: Maximum number of rows to return (endpoint and port).
        offset: Number of results to skip for pagination (endpoint and port).

    Returns:
        List of TextContent with the rows or the graph, or error; FEATURE_DISABLED when
        the portal answers that NetFlow is off.
    """
    if by not in _TOP_TALKERS_BY:
        return validation_error(
            "INVALID_REQUEST",
            f"by must be one of {list(_TOP_TALKERS_BY)}",
            suggestion="Use endpoint, port or graph.",
        )
    device_path = f"/device/devices/{device_id}"
    head = {"device_id": device_id, "by": by, "window_hours": hours_back}
    if by == "graph":
        try:
            graph = await client.get(
                f"{device_path}/topTalkersGraph", params=_netflow_window(hours_back)
            )
            return format_response({**head, "graph": graph})
        except Exception as e:
            return handle_error(e)
    tail, key = _TOP_TALKERS_PATHS[by]
    return await list_tool(
        client,
        f"{device_path}/{tail}",
        key=key,
        project=dict,
        limit=limit,
        offset=offset,
        params=_netflow_window(hours_back),
        extra=head,
    )


async def get_link_flaps(
    client: LogicMonitorClient,
    group_id: int | None = None,
    device: str | None = None,
    hours_back: int = 24,
    min_transitions: int = 4,
    interface_pattern: str = "interface|interfaces|if-|port|ethernet",
) -> list[TextContent]:
    """Identify interfaces with repeated up/down transitions.

    Pulls interface-family alerts (both active and cleared) in the window,
    groups by (device, instance), counts transitions, and returns the
    noisiest flapping interfaces.

    Args:
        client: LogicMonitor API client.
        group_id: Scope to a device group.
        device: Scope to a device name (substring match).
        hours_back: Lookback window in hours (default: 24).
        min_transitions: Minimum alert fires to qualify as flapping (default: 4).
        interface_pattern: Regex (case-insensitive) matching interface
            DataSource names (default covers common interface DS names).

    Returns:
        List of TextContent with flap rankings or error.
    """
    try:
        now = int(time.time())
        start_epoch = now - (hours_back * 3600)
        filters: list[str] = [f"startEpoch>:{start_epoch}"]
        wildcards_stripped = False

        if group_id is not None:
            filters.append(await resolve_group_filter(client, group_id))
        if device:
            clean_device, was_modified = sanitize_filter_value(device)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f"monitorObjectName~{quote_filter_value(clean_device)}")

        alerts, truncated, _ = await paginate_alerts(client, ",".join(filters))

        pattern_re = re.compile(interface_pattern, re.IGNORECASE)
        interface_alerts = [
            a for a in alerts if pattern_re.search(a.get("resourceTemplateName") or "")
        ]

        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for alert in interface_alerts:
            dev = alert.get("monitorObjectName") or "unknown"
            inst = alert.get("instanceName") or alert.get("resourceInstanceName") or "unknown"
            grouped[(dev, inst)].append(alert)

        flaps: list[dict] = []
        for (dev, inst), group_alerts in grouped.items():
            if len(group_alerts) < min_transitions:
                continue
            group_alerts.sort(key=lambda a: int(a.get("startEpoch") or 0))
            still_active = any(not a.get("cleared", False) for a in group_alerts)
            first_epoch = int(group_alerts[0].get("startEpoch") or 0)
            last_epoch = int(group_alerts[-1].get("startEpoch") or 0)

            flaps.append(
                {
                    "device": dev,
                    "interface": inst,
                    "transitions": len(group_alerts),
                    "first_transition": first_epoch,
                    "last_transition": last_epoch,
                    "still_active": still_active,
                    "datasource": group_alerts[0].get("resourceTemplateName"),
                }
            )

        flaps.sort(key=lambda f: f["transitions"], reverse=True)
        top_flaps = flaps[:50]

        response: dict = {
            "window_hours": hours_back,
            "min_transitions": min_transitions,
            "total_interface_alerts": len(interface_alerts),
            "flapping_interfaces": len(flaps),
            "results": top_flaps,
        }
        if truncated:
            response["warning"] = ALERT_WINDOW_TRUNCATED_WARNING
        if wildcards_stripped:
            response["note"] = (
                "Wildcard characters stripped from device filter — the ~ operator "
                "already performs substring matching."
            )
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_power_events(
    client: LogicMonitorClient,
    group_id: int | None = None,
    device: str | None = None,
    hours_back: int = 2,
    severity: str | None = None,
    patterns: list[str] | None = None,
) -> list[TextContent]:
    """Filter alerts for UPS, PDU, and power-infrastructure signatures.

    Queries alerts in the lookback window, then client-side filters by
    substring match on resourceTemplateName or alertName against UPS/PDU/battery
    patterns. Patterns are case-insensitive.

    Args:
        client: LogicMonitor API client.
        group_id: Scope to a device group.
        device: Scope to a device name (substring match).
        hours_back: Lookback window in hours (default: 2).
        severity: Filter by severity name.
        patterns: Override default patterns. Default covers APC, Liebert, Eaton,
            UPS, PDU, Battery, PowerSupply, Power_.

    Returns:
        List of TextContent with power events or error.
    """
    try:
        now = int(time.time())
        start_epoch = now - (hours_back * 3600)
        filters: list[str] = [f"startEpoch>:{start_epoch}"]
        wildcards_stripped = False

        if severity and severity.lower() in SEVERITY_MAP:
            filters.append(f"severity:{SEVERITY_MAP[severity.lower()]}")
        if group_id is not None:
            filters.append(await resolve_group_filter(client, group_id))
        if device:
            clean_device, was_modified = sanitize_filter_value(device)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f"monitorObjectName~{quote_filter_value(clean_device)}")

        alerts, truncated, _ = await paginate_alerts(client, ",".join(filters))

        active_patterns = patterns or list(_DEFAULT_POWER_PATTERNS)
        lower_patterns = [p.lower() for p in active_patterns]
        pattern_counts: dict[str, int] = defaultdict(int)
        matched: list[dict] = []

        for alert in alerts:
            ds_name = (alert.get("resourceTemplateName") or "").lower()
            alert_name = (alert.get("alertName") or "").lower()
            combined = f"{ds_name} {alert_name}"
            matching_patterns = [p for p in lower_patterns if p in combined]
            if not matching_patterns:
                continue
            for p in matching_patterns:
                pattern_counts[p] += 1
            matched.append(
                {
                    "id": alert.get("id"),
                    "severity": alert.get("severity"),
                    "device": alert.get("monitorObjectName"),
                    "datasource": alert.get("resourceTemplateName"),
                    "datapoint": alert.get("dataPointName"),
                    "alert_value": alert.get("alertValue"),
                    "start_epoch": alert.get("startEpoch"),
                    "cleared": alert.get("cleared", False),
                    "matched_patterns": matching_patterns,
                }
            )

        response: dict = {
            "window_hours": hours_back,
            "patterns_used": active_patterns,
            "total_alerts_scanned": len(alerts),
            "total_power_events": len(matched),
            "patterns_matched_counts": dict(pattern_counts),
            "events": matched,
        }
        if truncated:
            response["warning"] = ALERT_WINDOW_TRUNCATED_WARNING
        if wildcards_stripped:
            response["note"] = (
                "Wildcard characters stripped from device filter — the ~ operator "
                "already performs substring matching."
            )
        return format_response(response)
    except Exception as e:
        return handle_error(e)
