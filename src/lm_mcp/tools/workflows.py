# Description: Composite workflow tools for LogicMonitor MCP server.
# Description: Provides triage, diagnose, capacity_plan, portal_overview, update_logicmodule.

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import call_sub_tool, format_response, handle_error
from lm_mcp.tools.alerts import ALERT_WINDOW_TRUNCATED_WARNING
from lm_mcp.tools.logicmodules import MODULES, update_module

# Audit logger for write workflows. Configured via standard logging; if no
# handler is attached, records propagate to the root logger.
_AUDIT = logging.getLogger("lm_mcp.audit")

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def check_required_tools(required: list[str]) -> list[TextContent] | None:
    """Check all sub-tools pass LM_ENABLED_TOOLS, LM_DISABLED_TOOLS, and LM_MCP_CATEGORIES.

    Returns None if OK, error TextContent list if any tool is blocked.
    """
    from lm_mcp.categories import passes_name_filter
    from lm_mcp.config import get_config

    config = get_config()
    blocked = [t for t in required if not passes_name_filter(t, config)]

    if not blocked and config.mcp_categories:
        from lm_mcp.categories import tool_in_categories
        from lm_mcp.registry import TOOLS

        tools_index = {t.name: t for t in TOOLS}
        blocked = [
            t for t in required if not tool_in_categories(t, tools_index, config.mcp_categories)
        ]
        if blocked:
            return format_response(
                {
                    "error": True,
                    "code": "FEATURE_DISABLED",
                    "message": (
                        f"Composite tool requires tools excluded by LM_MCP_CATEGORIES="
                        f"{config.mcp_categories}: {', '.join(blocked)}"
                    ),
                    "suggestion": (
                        "Add the required category (e.g., 'read') to LM_MCP_CATEGORIES, "
                        "or unset it to allow all categories."
                    ),
                }
            )

    if blocked:
        return format_response(
            {
                "error": True,
                "code": "FEATURE_DISABLED",
                "message": f"Composite tool requires disabled tools: {', '.join(blocked)}",
                "suggestion": "Enable these tools or use individual tools instead",
            }
        )
    return None


async def _resolve_device(
    client: LogicMonitorClient,
    device_id: int | None = None,
    device_name: str | None = None,
) -> tuple[int, dict]:
    """Resolve device by ID or name search. Returns (id, device_dict)."""
    from lm_mcp.tools.devices import get_device, get_devices

    if device_id is not None:
        data = await call_sub_tool(get_device, client, device_id=device_id)
        return device_id, data
    if device_name:
        data = await call_sub_tool(
            get_devices,
            client,
            name_filter=device_name,
            limit=1,
        )
        devices = data.get("devices", [])
        if not devices:
            raise ValueError(f"No device found matching name '{device_name}'")
        dev = devices[0]
        return dev["id"], dev
    raise ValueError("Either device_id or device_name is required")


def _trim_detail(report: dict, detail_level: str, full_keys: set[str]) -> dict:
    """Remove full_keys from report when detail_level is 'summary'."""
    if detail_level == "summary":
        return {k: v for k, v in report.items() if k not in full_keys}
    return report


# ---------------------------------------------------------------------------
# Composite tool: triage
# ---------------------------------------------------------------------------

_TRIAGE_REQUIRED = [
    "analyze_alerts",
    "analyze_blast_radius",
]

# Device clusters, largest first, whose blast radius triage reads.
_TRIAGE_BLAST_CLUSTERS = 3

_OBJECT_OR_NULL = {"type": ["object", "null"]}

_DETAIL_LEVEL = {"type": "string", "enum": ["summary", "full"]}

_COUNT = {"type": "integer", "minimum": 0}

_BLAST_RADIUS_ROW = {
    "type": "object",
    "properties": {
        "device": {"type": "string", "description": "The device cluster's key, its name."},
        "device_id": {"type": "integer", "description": "The device the cluster's alerts share."},
        "total_affected_devices": {**_COUNT, "description": "Devices reached, every depth."},
        "neighbor_count": {**_COUNT, "description": "Devices reached at depth 1."},
        "dependent_count": {**_COUNT, "description": "Devices reached at depth 2 and beyond."},
        "critical_alert_count": {
            **_COUNT,
            "description": "Devices reached with a critical alert open.",
        },
        "unreadable_count": {
            **_COUNT,
            "description": "Devices whose neighbors neither topology path answered.",
        },
        "warning": {"type": "string", "description": "Present when unreadable_count is not 0."},
        "degraded_detail": {
            "type": "string",
            "description": "Present when an alert check failed; critical counts may be low.",
        },
        "affected_devices": {
            "type": "array",
            "items": {"type": "object"},
            "description": "Full: each device reached, with its depth and open alerts.",
        },
        "critical_path_devices": {
            "type": "array",
            "items": {"type": "object"},
            "description": "Full: devices reached from two or more others.",
        },
    },
    "required": [
        "device",
        "device_id",
        "total_affected_devices",
        "neighbor_count",
        "dependent_count",
        "critical_alert_count",
        "unreadable_count",
    ],
    "additionalProperties": False,
}

# The report triage returns, as a JSON Schema. An analyze_alerts section is null when
# the window read failed, with a warning naming the failure.
TRIAGE_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "hours_back": {"type": "integer", "description": "Hours the alert window reaches back."},
        "detail_level": _DETAIL_LEVEL,
        "statistics": {**_OBJECT_OR_NULL, "description": "analyze_alerts 'statistics'."},
        "clusters": {**_OBJECT_OR_NULL, "description": "analyze_alerts 'clusters'."},
        "noise": {**_OBJECT_OR_NULL, "description": "analyze_alerts 'noise'."},
        "changes": {**_OBJECT_OR_NULL, "description": "analyze_alerts 'changes'."},
        "blast_radius": {
            "type": "array",
            "items": _BLAST_RADIUS_ROW,
            "description": "One row per device cluster read, up to three.",
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "hours_back",
        "detail_level",
        "statistics",
        "clusters",
        "noise",
        "changes",
        "blast_radius",
    ],
    "additionalProperties": False,
}


def _blast_radius_row(cluster: dict, radius: dict, detail_level: str) -> dict:
    """Project an analyze_blast_radius result onto its counts, with the device lists in full."""
    row = {
        "device": cluster["key"],
        "device_id": cluster["device_id"],
        "total_affected_devices": radius["total_affected_devices"],
        "neighbor_count": radius["neighbor_count"],
        "dependent_count": radius["dependent_count"],
        "critical_alert_count": radius["critical_alert_count"],
        "unreadable_count": len(radius["unreadable"]),
    }
    for key in ("warning", "degraded_detail"):
        if key in radius:
            row[key] = radius[key]
    if detail_level == "full":
        row["affected_devices"] = radius["affected_devices"]
        row["critical_path_devices"] = radius["critical_path_devices"]
    return row


async def triage(
    client: LogicMonitorClient,
    severity: str | None = None,
    device: str | None = None,
    group_id: int | None = None,
    hours_back: int = 4,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite triage: one alert window read, then blast-radius counts.

    Reads the alert window once through analyze_alerts for its statistics,
    clusters, noise and changes, then counts the blast radius of up to three
    device clusters, largest first, by the device_id the cluster names; a
    cluster without one (a website) is passed over. TRIAGE_OUTPUT_SCHEMA
    documents the report.

    Args:
        client: LogicMonitor API client.
        severity: Filter alerts by severity.
        device: Filter by device name.
        group_id: Filter by device group ID.
        hours_back: Hours to look back (default: 4).
        detail_level: 'summary' or 'full'; full adds each blast radius' devices.

    Returns:
        Incident report as TextContent list.
    """
    blocked = check_required_tools(_TRIAGE_REQUIRED)
    if blocked:
        return blocked

    try:
        from lm_mcp.tools.analyze_alerts import analyze_alerts
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        warnings: list[str] = []
        report: dict = {"hours_back": hours_back, "detail_level": detail_level}

        # 1. One read of the alert window feeds statistics, clusters, noise and changes
        window: dict = {}
        try:
            window = await call_sub_tool(
                analyze_alerts,
                client,
                hours=hours_back,
                severity=severity,
                device=device,
                group_id=group_id,
                analyses=["statistics", "clusters", "noise", "changes"],
            )
        except Exception as exc:
            warnings.append(f"analyze_alerts failed: {exc}")
        if window.get("truncated"):
            warnings.append(ALERT_WINDOW_TRUNCATED_WARNING)
        for section in ("statistics", "clusters", "noise", "changes"):
            report[section] = window.get(section)

        # 2. Blast-radius counts for the largest device clusters that name their device
        clusters = (window.get("clusters") or {}).get("clusters", [])
        devices = [
            c for c in clusters if c.get("type") == "device" and c.get("device_id") is not None
        ]
        blast_rows: list[dict] = []
        for cluster in devices[:_TRIAGE_BLAST_CLUSTERS]:
            try:
                radius = await call_sub_tool(
                    analyze_blast_radius, client, device_id=cluster["device_id"]
                )
                blast_rows.append(_blast_radius_row(cluster, radius, detail_level))
            except Exception as exc:
                _AUDIT.warning(
                    "triage: blast radius failed for %s: %s", cluster["key"], exc, exc_info=True
                )
                warnings.append(f"blast_radius for {cluster['key']} failed: {exc}")
        report["blast_radius"] = blast_rows

        if warnings:
            report["warnings"] = warnings

        return format_response(report)
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# Composite tool: health_check
# ---------------------------------------------------------------------------

_HEALTH_CHECK_REQUIRED = [
    "get_devices",
    "get_device",
    "get_device_datasources",
    "get_device_instances",
    "analyze_metric",
    "get_alerts",
    "calculate_availability",
]

# health_check reads each datasource's series over this window, for the latest
# sample's z-score and the anomaly fences.
_HEALTH_CHECK_HOURS = 24
_HEALTH_CHECK_ANALYSES = ["summary", "anomalies"]


async def health_check(
    client: LogicMonitorClient,
    device_id: int | None = None,
    device_name: str | None = None,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite health check for a single device.

    Resolves the device, gathers datasource coverage, analyzes the first
    instance of up to five datasources (summary and anomalies over 24 hours,
    one read each), checks active alerts, and calculates availability.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_name: Device display name (used if device_id not provided).
        detail_level: 'summary' or 'full' (default: summary).

    Returns:
        Device health report as TextContent list.
    """
    blocked = check_required_tools(_HEALTH_CHECK_REQUIRED)
    if blocked:
        return blocked

    try:
        from lm_mcp.tools.alerts import get_alerts
        from lm_mcp.tools.analyze_metric import analyze_metric
        from lm_mcp.tools.metrics import get_device_datasources, get_device_instances
        from lm_mcp.tools.scoring import calculate_availability

        warnings: list[str] = []

        # 1. Resolve device
        resolved_id, device_info = await _resolve_device(
            client,
            device_id=device_id,
            device_name=device_name,
        )
        report: dict = {
            "device_id": resolved_id,
            "device_name": device_info.get("displayName", device_info.get("name", "")),
            "detail_level": detail_level,
        }

        # 2. Get datasources
        ds_list: list[dict] = []
        try:
            ds_data = await call_sub_tool(
                get_device_datasources,
                client,
                device_id=resolved_id,
            )
            ds_list = ds_data.get("datasources", [])
            report["datasource_count"] = len(ds_list)
        except Exception as exc:
            warnings.append(f"get_device_datasources failed: {exc}")
            report["datasource_count"] = 0

        # 3. Analyze the first instance of each of the first 5 datasources, skipping
        # any with no instance
        metrics: list[dict] = []
        for ds in ds_list[:5]:
            ds_id = ds.get("id")
            if ds_id is None:
                continue
            ds_name = ds.get("name", ds_id)
            try:
                inst_data = await call_sub_tool(
                    get_device_instances,
                    client,
                    device_id=resolved_id,
                    device_datasource_id=ds_id,
                )
            except Exception as exc:
                _AUDIT.warning(
                    "health: instance fetch failed for datasource %s: %s",
                    ds_name,
                    exc,
                    exc_info=True,
                )
                warnings.append(f"instance fetch for {ds_name} failed: {exc}")
                continue
            instances = inst_data.get("instances", [])
            if not instances or instances[0].get("id") is None:
                continue
            instance = instances[0]
            try:
                analysis = await call_sub_tool(
                    analyze_metric,
                    client,
                    device_id=resolved_id,
                    device_datasource_id=ds_id,
                    instance_id=instance["id"],
                    hours=_HEALTH_CHECK_HOURS,
                    analyses=_HEALTH_CHECK_ANALYSES,
                )
                metrics.append(
                    {
                        "datasource": ds.get("name", ""),
                        "instance": instance.get("name", ""),
                        "analysis": analysis,
                    }
                )
            except Exception as exc:
                _AUDIT.warning(
                    "health: analysis failed for datasource %s: %s", ds_name, exc, exc_info=True
                )
                warnings.append(f"analyze_metric for {ds_name} failed: {exc}")

        report["metrics"] = metrics

        # 4. Active alerts for the device
        try:
            device_display = report["device_name"]
            alert_data = await call_sub_tool(
                get_alerts,
                client,
                device=device_display,
                cleared=False,
            )
            report["active_alerts"] = alert_data
        except Exception as exc:
            warnings.append(f"get_alerts failed: {exc}")
            report["active_alerts"] = None

        # 5. Availability (30-day)
        try:
            avail = await call_sub_tool(
                calculate_availability,
                client,
                device_id=resolved_id,
            )
            report["availability"] = avail
        except Exception as exc:
            warnings.append(f"calculate_availability failed: {exc}")
            report["availability"] = None

        if warnings:
            report["warnings"] = warnings

        full_keys = {"metrics"}
        report = _trim_detail(report, detail_level, full_keys)

        return format_response(report)
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# Composite tool: capacity_plan
# ---------------------------------------------------------------------------

_CAPACITY_PLAN_REQUIRED = [
    "get_devices",
    "get_device",
    "get_device_datasources",
    "analyze_metric",
]

# capacity_plan reads each instance once for these sections, forecasting the
# crossing of this level.
_CAPACITY_PLAN_ANALYSES = ["trend", "seasonality", "change_points", "forecast"]
_CAPACITY_THRESHOLD = 90.0


async def capacity_plan(
    client: LogicMonitorClient,
    device_id: int | None = None,
    device_name: str | None = None,
    datasource: str | None = None,
    hours_back: int = 168,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite capacity planning for a device.

    Reads each instance's series once through analyze_metric for its trend,
    seasonality, change points and forecast against 90, across up to five
    datasources and three instances each.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_name: Device display name (used if device_id not provided).
        datasource: Filter to a specific datasource name.
        hours_back: Hours of historical data (default: 168 = 1 week).
        detail_level: 'summary' or 'full' (default: summary).

    Returns:
        Per-datasource capacity projections as TextContent list.
    """
    blocked = check_required_tools(_CAPACITY_PLAN_REQUIRED)
    if blocked:
        return blocked

    try:
        from lm_mcp.tools.analyze_metric import analyze_metric
        from lm_mcp.tools.metrics import get_device_datasources, get_device_instances

        warnings: list[str] = []

        # 1. Resolve device
        resolved_id, device_info = await _resolve_device(
            client,
            device_id=device_id,
            device_name=device_name,
        )
        report: dict = {
            "device_id": resolved_id,
            "device_name": device_info.get("displayName", device_info.get("name", "")),
            "hours_back": hours_back,
            "detail_level": detail_level,
        }

        # 2. Get datasources (filtered if datasource param given)
        try:
            ds_data = await call_sub_tool(
                get_device_datasources,
                client,
                device_id=resolved_id,
                name_filter=datasource,
            )
            ds_list = ds_data.get("datasources", [])
        except Exception as exc:
            warnings.append(f"get_device_datasources failed: {exc}")
            ds_list = []

        # 3. Per datasource (up to 5), per instance (up to 3): one analysis
        ds_reports: list[dict] = []
        for ds in ds_list[:5]:
            ds_id = ds.get("id")
            if ds_id is None:
                continue

            ds_report: dict = {"datasource": ds.get("name", ""), "instances": []}

            try:
                inst_data = await call_sub_tool(
                    get_device_instances,
                    client,
                    device_id=resolved_id,
                    device_datasource_id=ds_id,
                )
                instances = inst_data.get("instances", [])
            except Exception as exc:
                _AUDIT.warning(
                    "capacity_plan: instance fetch failed for datasource %s: %s",
                    ds.get("name", ds_id),
                    exc,
                    exc_info=True,
                )
                warnings.append(f"instance fetch for {ds.get('name', ds_id)} failed: {exc}")
                instances = []

            for inst in instances[:3]:
                inst_id = inst.get("id")
                if inst_id is None:
                    continue

                inst_report: dict = {"instance": inst.get("name", "")}
                try:
                    inst_report["analysis"] = await call_sub_tool(
                        analyze_metric,
                        client,
                        device_id=resolved_id,
                        device_datasource_id=ds_id,
                        instance_id=inst_id,
                        hours=hours_back,
                        analyses=_CAPACITY_PLAN_ANALYSES,
                        threshold=_CAPACITY_THRESHOLD,
                    )
                except Exception as exc:
                    _AUDIT.warning(
                        "capacity_plan: analysis failed for instance %s: %s",
                        inst_id,
                        exc,
                        exc_info=True,
                    )
                    inst_report["analysis"] = None
                    inst_report["analysis_error"] = str(exc)

                ds_report["instances"].append(inst_report)

            ds_reports.append(ds_report)

        report["datasources"] = ds_reports

        # The summary level trims the raw datasources block, so it keeps each
        # forecast's headline and every per-instance error and warning in its place.
        if detail_level == "summary":
            report["forecast_summary"] = _forecast_summary(ds_reports)
            warnings.extend(_instance_errors(ds_reports))
            warnings.extend(_instance_warnings(ds_reports))

        if warnings:
            report["warnings"] = warnings

        full_keys = {"datasources"}
        report = _trim_detail(report, detail_level, full_keys)

        return format_response(report)
    except Exception as e:
        return handle_error(e)


def _forecast_summary(ds_reports: list[dict]) -> list[dict]:
    """One headline row per datapoint: trend label and each method's hours to breach.

    A datapoint too short to analyze carries its status instead.
    """
    rows: list[dict] = []
    for ds in ds_reports:
        for inst in ds["instances"]:
            datapoints = (inst.get("analysis") or {}).get("datapoints") or {}
            for datapoint, sections in datapoints.items():
                row = {
                    "datasource": ds["datasource"],
                    "instance": inst["instance"],
                    "datapoint": datapoint,
                }
                forecast = sections["forecast"]
                if "status" in forecast:
                    row["status"] = forecast["status"]
                else:
                    row["trend"] = sections["trend"]["label"]
                    row["hours_until_breach"] = {
                        method: forecast[method]["hours_until_breach"]
                        for method in ("linear", "holt_winters")
                    }
                rows.append(row)
    return rows


def _instance_errors(ds_reports: list[dict]) -> list[str]:
    """Every failed instance analysis, as a warning line naming datasource and instance."""
    return [
        f"analyze_metric for {ds['datasource']}/{inst['instance']} failed: {inst['analysis_error']}"
        for ds in ds_reports
        for inst in ds["instances"]
        if "analysis_error" in inst
    ]


def _instance_warnings(ds_reports: list[dict]) -> list[str]:
    """Every analysis warning, naming datasource and instance."""
    return [
        f"{ds['datasource']}/{inst['instance']}: {warning}"
        for ds in ds_reports
        for inst in ds["instances"]
        for warning in (inst.get("analysis") or {}).get("warnings", [])
    ]


# ---------------------------------------------------------------------------
# Composite tool: portal_overview
# ---------------------------------------------------------------------------

_PORTAL_OVERVIEW_REQUIRED = [
    "analyze_alerts",
    "get_alerts",
    "get_collectors",
    "get_active_sdts",
    "get_devices",
]

# The report portal_overview returns, as a JSON Schema. A key whose read failed is null,
# with a warning naming the failure. critical_alerts, error_alerts and dead_devices are
# full-mode keys: summary does not read them.
PORTAL_OVERVIEW_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "hours_back": {"type": "integer", "description": "Hours the alert window reaches back."},
        "detail_level": _DETAIL_LEVEL,
        "alert_statistics": {**_OBJECT_OR_NULL, "description": "analyze_alerts 'statistics'."},
        "alert_clusters": {**_OBJECT_OR_NULL, "description": "analyze_alerts 'clusters'."},
        "noise": {**_OBJECT_OR_NULL, "description": "analyze_alerts 'noise'."},
        "collectors": {**_OBJECT_OR_NULL, "description": "get_collectors' first page."},
        "active_sdts": {**_OBJECT_OR_NULL, "description": "get_active_sdts' first page."},
        "critical_alerts": {
            **_OBJECT_OR_NULL,
            "description": "Full: up to 20 open critical alerts, portal-wide (get_alerts).",
        },
        "error_alerts": {
            **_OBJECT_OR_NULL,
            "description": "Full: up to 20 open error alerts, portal-wide (get_alerts).",
        },
        "dead_devices": {
            **_OBJECT_OR_NULL,
            "description": "Full: up to 20 dead devices (get_devices status=dead).",
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "hours_back",
        "detail_level",
        "alert_statistics",
        "alert_clusters",
        "noise",
        "collectors",
        "active_sdts",
    ],
    "additionalProperties": False,
}


async def portal_overview(
    client: LogicMonitorClient,
    hours_back: int = 4,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite portal overview for shift-handoff reporting.

    Reads the alert window once through analyze_alerts for its statistics,
    clusters and noise, collectors once and active SDTs once. Full mode adds
    the open critical and error alerts across the portal and the dead
    devices, reads summary mode skips. PORTAL_OVERVIEW_OUTPUT_SCHEMA documents
    the report.

    Args:
        client: LogicMonitor API client.
        hours_back: Hours to look back (default: 4).
        detail_level: 'summary' or 'full' (default: summary).

    Returns:
        Portal overview report as TextContent list.
    """
    blocked = check_required_tools(_PORTAL_OVERVIEW_REQUIRED)
    if blocked:
        return blocked

    try:
        from lm_mcp.tools.alerts import get_alerts
        from lm_mcp.tools.analyze_alerts import analyze_alerts
        from lm_mcp.tools.collectors import get_collectors
        from lm_mcp.tools.devices import get_devices
        from lm_mcp.tools.sdts import get_active_sdts

        warnings: list[str] = []
        report: dict = {"hours_back": hours_back, "detail_level": detail_level}

        # 1. One read of the alert window feeds statistics, clusters and noise
        window: dict = {}
        try:
            window = await call_sub_tool(
                analyze_alerts,
                client,
                hours=hours_back,
                analyses=["statistics", "clusters", "noise"],
            )
        except Exception as exc:
            warnings.append(f"analyze_alerts failed: {exc}")
        if window.get("truncated"):
            warnings.append(ALERT_WINDOW_TRUNCATED_WARNING)
        report["alert_statistics"] = window.get("statistics")
        report["alert_clusters"] = window.get("clusters")
        report["noise"] = window.get("noise")

        # 2. Collector health
        try:
            report["collectors"] = await call_sub_tool(get_collectors, client)
        except Exception as exc:
            warnings.append(f"get_collectors failed: {exc}")
            report["collectors"] = None

        # 3. Active SDTs
        try:
            report["active_sdts"] = await call_sub_tool(get_active_sdts, client)
        except Exception as exc:
            warnings.append(f"get_active_sdts failed: {exc}")
            report["active_sdts"] = None

        if detail_level == "full":
            # 4. Open critical and error alerts across the portal, not only the window
            try:
                report["critical_alerts"] = await call_sub_tool(
                    get_alerts, client, severity="critical", cleared=False, limit=20
                )
                report["error_alerts"] = await call_sub_tool(
                    get_alerts, client, severity="error", cleared=False, limit=20
                )
            except Exception as exc:
                warnings.append(f"get_alerts failed: {exc}")
                report["critical_alerts"] = None
                report["error_alerts"] = None

            # 5. Dead devices
            try:
                report["dead_devices"] = await call_sub_tool(
                    get_devices, client, status="dead", limit=20
                )
            except Exception as exc:
                warnings.append(f"get_devices (dead) failed: {exc}")
                report["dead_devices"] = None

        if warnings:
            report["warnings"] = warnings

        return format_response(report)
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# Composite tool: diagnose
# ---------------------------------------------------------------------------

_DIAGNOSE_REQUIRED = [
    "get_alerts",
    "get_alert_details",
    "get_device",
    "get_device_properties",
    "analyze_alerts",
    "analyze_blast_radius",
]


async def diagnose(
    client: LogicMonitorClient,
    alert_id: str | None = None,
    device_name: str | None = None,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite diagnosis for an alert or device.

    Gathers alert details, device context, correlated alerts, recent
    changes, blast radius, and health score. Produces a diagnosis
    report with probable root cause indicators.

    Args:
        client: LogicMonitor API client.
        alert_id: Alert ID to diagnose.
        device_name: Device name (finds most recent critical alert).
        detail_level: 'summary' or 'full' (default: summary).

    Returns:
        Diagnosis report as TextContent list.
    """
    blocked = check_required_tools(_DIAGNOSE_REQUIRED)
    if blocked:
        return blocked

    try:
        from lm_mcp.tools.alerts import get_alert_details, get_alerts
        from lm_mcp.tools.analyze_alerts import analyze_alerts
        from lm_mcp.tools.devices import get_device
        from lm_mcp.tools.resources import get_device_properties
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        warnings: list[str] = []
        report: dict = {"detail_level": detail_level}

        # 1. Resolve target
        alert_data: dict | None = None
        target_device_id: int | None = None

        if alert_id:
            try:
                alert_data = await call_sub_tool(
                    get_alert_details,
                    client,
                    alert_id=alert_id,
                )
                target_device_id = alert_data.get("monitorObjectId")
                report["alert"] = alert_data
            except Exception as exc:
                warnings.append(f"get_alert_details failed: {exc}")
        elif device_name:
            try:
                alerts_data = await call_sub_tool(
                    get_alerts,
                    client,
                    device=device_name,
                    severity="critical",
                    cleared=False,
                    limit=1,
                )
                alert_list = alerts_data.get("alerts", [])
                if alert_list:
                    resolved_alert_id = alert_list[0].get("id", "")
                    alert_data = await call_sub_tool(
                        get_alert_details,
                        client,
                        alert_id=str(resolved_alert_id),
                    )
                    target_device_id = alert_data.get("monitorObjectId")
                    report["alert"] = alert_data
                else:
                    report["alert"] = None
                    warnings.append(f"No critical alerts found for device '{device_name}'")
            except Exception as exc:
                warnings.append(f"get_alerts/get_alert_details failed: {exc}")
        else:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "Either alert_id or device_name is required",
                }
            )

        # 2. Device context
        if target_device_id is not None:
            try:
                dev = await call_sub_tool(
                    get_device,
                    client,
                    device_id=target_device_id,
                )
                report["device"] = dev
            except Exception as exc:
                warnings.append(f"get_device failed: {exc}")

            try:
                props = await call_sub_tool(
                    get_device_properties,
                    client,
                    device_id=target_device_id,
                )
                report["device_properties"] = props
            except Exception as exc:
                warnings.append(f"get_device_properties failed: {exc}")

        # 3. Correlated alerts and changes: one read of the last four hours
        try:
            window = await call_sub_tool(
                analyze_alerts,
                client,
                hours=4,
                analyses=["clusters", "changes"],
            )
            report["correlated_alerts"] = window.get("clusters")
            report["changes"] = window.get("changes")
            if window.get("truncated"):
                warnings.append(ALERT_WINDOW_TRUNCATED_WARNING)
        except Exception as exc:
            warnings.append(f"analyze_alerts failed: {exc}")

        # 4. Blast radius
        if target_device_id is not None:
            try:
                blast = await call_sub_tool(
                    analyze_blast_radius,
                    client,
                    device_id=target_device_id,
                )
                report["blast_radius"] = blast
            except Exception as exc:
                warnings.append(f"analyze_blast_radius failed: {exc}")

        if warnings:
            report["warnings"] = warnings

        full_keys = {"device_properties", "blast_radius"}
        report = _trim_detail(report, detail_level, full_keys)

        return format_response(report)
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# Discovery tool: search_tools
# ---------------------------------------------------------------------------

# Keyword aliases map workflow concepts to composite tool names
_WORKFLOW_ALIASES: dict[str, list[str]] = {
    "incident": ["triage", "diagnose"],
    "outage": ["triage", "diagnose"],
    "issue": ["triage", "diagnose"],
    "health": ["health_check"],
    "status": ["health_check", "portal_overview"],
    "capacity": ["capacity_plan"],
    "forecast": ["capacity_plan"],
    "growth": ["capacity_plan"],
    "overview": ["portal_overview"],
    "shift": ["portal_overview"],
    "handoff": ["portal_overview"],
    "rca": ["diagnose"],
    "root cause": ["diagnose"],
    "diagnos": ["diagnose"],
    "troubleshoot": ["diagnose"],
    # Reference-layer aliases (map schema/filter/syntax lookups to get_reference)
    "schema": ["get_reference"],
    "filter": ["get_reference"],
    "syntax": ["get_reference"],
    "reference": ["get_reference"],
    "guide": ["get_reference"],
}


async def search_tools(
    client: LogicMonitorClient,
    query: str,
    category: str | None = None,
    limit: int = 10,
) -> list[TextContent]:
    """Search available MCP tools by keyword or category.

    Searches tool names and descriptions using word-level tokenization.
    Scores matches by: exact name match (highest), word in name (medium),
    word in description (lower). Suggests composite tools when the query
    matches workflow concepts.

    Args:
        client: LogicMonitor API client (unused, required by convention).
        query: Search keywords.
        category: Filter to a specific category.
        limit: Maximum results (default: 10).

    Returns:
        Matching tools with relevance scores.
    """
    try:
        from lm_mcp.registry import TOOLS
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        search_corpus = list(TOOLS)

        # Tokenize query into lowercase words
        query_words = re.findall(r"[a-z0-9_]+", query.lower())
        if not query_words:
            return format_response(
                {
                    "matches": [],
                    "total": 0,
                    "query": query,
                    "suggestions": [],
                }
            )

        # Optionally filter by category
        category_tool_names: set[str] | None = None
        if category:
            cats = TOOL_CATEGORIES.get("categories", {})
            cat_data = cats.get(category)
            if cat_data:
                category_tool_names = set(cat_data.get("tools", []))
            else:
                return format_response(
                    {
                        "matches": [],
                        "total": 0,
                        "query": query,
                        "category": category,
                        "available_categories": list(cats.keys()),
                        "suggestions": [],
                    }
                )

        # Score each tool
        scored: list[tuple[float, dict]] = []
        for tool in search_corpus:
            name = tool.name
            desc = (tool.description or "").lower()

            if category_tool_names is not None and name not in category_tool_names:
                continue

            score = 0.0
            name_lower = name.lower()
            name_parts = re.findall(r"[a-z0-9]+", name_lower)

            for word in query_words:
                # Exact name match
                if word == name_lower:
                    score += 10.0
                # Word appears in name parts
                elif word in name_parts:
                    score += 5.0
                # Partial match in name
                elif word in name_lower:
                    score += 3.0
                # Word in description
                elif word in desc:
                    score += 1.0

            if score > 0:
                scored.append(
                    (
                        score,
                        {
                            "name": name,
                            "description": tool.description,
                            "score": round(score, 1),
                        },
                    )
                )

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        matches = [item for _, item in scored[:limit]]

        # Suggest composite tools if query matches workflow concepts
        suggestions: list[str] = []
        query_joined = " ".join(query_words)
        for keyword, tools in _WORKFLOW_ALIASES.items():
            if keyword in query_joined or any(keyword in w for w in query_words):
                for t in tools:
                    if t not in suggestions:
                        suggestions.append(t)

        return format_response(
            {
                "matches": matches,
                "total": len(scored),
                "query": query,
                "category": category,
                "suggestions": suggestions if suggestions else None,
            }
        )
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# Composite tool: update_logicmodule (safe read-modify-update for source types)
# ---------------------------------------------------------------------------

# update_logicmodule reads and PUTs through the module table: MODULES names each type's
# settings path and the fields the merged definition must keep. The read and update_module
# are internal, not registered tools; LM_ENABLED_TOOLS and LM_DISABLED_TOOLS patterns on the
# type's get_<type> name gate the read.


async def _get_module_raw(client: LogicMonitorClient, module_type: str, module_id: int) -> dict:
    """Read one LogicModule's full REST object, the body its full-replace PUT takes back."""
    path = MODULES[module_type].path
    result: dict = await client.get(f"/setting/{path}/{module_id}")
    return result


def _deep_merge(base: dict, overlay: dict, *, path: str = "") -> tuple[dict, list[str]]:
    """Merge overlay onto base for safe partial logicmodule updates.

    Semantics:
    - dict + dict: recurse
    - list + list: REPLACE wholesale (LM treats dataPoints, instanceLevelAttribute,
      etc. as atomic collections; by-id merging would require per-collection
      schema knowledge that is not available)
    - primitive + anything (compatible types): overlay wins
    - None in overlay: explicit delete (pop key from result); emits a warning
      if the key was not present, to surface typo'd field names
    - type conflicts (e.g., dict in base, list in overlay) raise ValueError

    Returns the merged dict plus a list of human-readable warnings about
    no-op deletions or other notable merge events.
    """
    out = dict(base)
    warnings: list[str] = []
    for k, v in overlay.items():
        full = f"{path}.{k}" if path else k
        if v is None:
            if k in out:
                out.pop(k)
            else:
                warnings.append(f"deletion of missing key '{full}' was a no-op")
            continue
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            sub, sub_warns = _deep_merge(out[k], v, path=full)
            out[k] = sub
            warnings.extend(sub_warns)
        elif k in out and out[k] is not None and type(out[k]) is not type(v):
            raise ValueError(
                f"type conflict at '{full}': base is {type(out[k]).__name__}, "
                f"overlay is {type(v).__name__}"
            )
        else:
            out[k] = v
    return out, warnings


def _diff(before: dict, after: dict, path: str = "") -> list[dict]:
    """Compute a flat list of diff entries between two dicts.

    Each entry: {"path": "a.b.c", "op": "add" | "remove" | "change",
                 "before": <value or None>, "after": <value or None>}.
    Lists are compared by equality only; nested dict diffs recurse.
    """
    entries: list[dict] = []
    keys = set(before) | set(after)
    for k in sorted(keys):
        full = f"{path}.{k}" if path else k
        if k not in before:
            entries.append({"path": full, "op": "add", "before": None, "after": after[k]})
        elif k not in after:
            entries.append({"path": full, "op": "remove", "before": before[k], "after": None})
        elif before[k] == after[k]:
            continue
        elif isinstance(before[k], dict) and isinstance(after[k], dict):
            entries.extend(_diff(before[k], after[k], path=full))
        else:
            entries.append({"path": full, "op": "change", "before": before[k], "after": after[k]})
    return entries


async def update_logicmodule(
    client: LogicMonitorClient,
    type: str,
    id: int,
    changes: dict,
    mode: str = "preview",
) -> list[TextContent]:
    """Safe partial update for LogicMonitor source types.

    Workflow: read the current full definition, deep-merge the provided
    changes onto it, validate that LM-required fields (name, plus
    displayName for DataSources and ConfigSources) are present, then either
    return a dry-run diff (mode='preview') or apply the merged definition
    through the type's internal full-replace PUT handler (mode='apply').

    The LogicModule PUT is full-replace and can blank fields left out of
    the payload, so sending the merged full definition keeps every field
    the caller did not change.

    Args:
        client: LogicMonitor API client.
        type: One of configsource, datasource, diagnosticsource, eventsource,
            logsource, propertysource, remediationsource, topologysource.
        id: LogicModule ID.
        changes: Partial update — only the fields to modify. Use None as a
            value to explicitly delete a key.
        mode: "preview" (default, returns diff without writing) or "apply"
            (writes the merged definition).

    Returns:
        TextContent with diff preview or apply result; or error info.
    """
    try:
        if type not in MODULES:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": f"type must be one of {sorted(MODULES)}",
                }
            )
        if mode not in ("preview", "apply"):
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "mode must be 'preview' or 'apply'",
                }
            )
        if not isinstance(changes, dict):
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "changes must be a dict (partial update with field overrides)",
                }
            )

        blocked = check_required_tools([f"get_{type}"])
        if blocked:
            return blocked

        base = await _get_module_raw(client, type, id)

        merged, merge_warnings = _deep_merge(base, changes)

        for required in MODULES[type].required:
            if not merged.get(required):
                return format_response(
                    {
                        "error": True,
                        "code": "INVALID_REQUEST",
                        "message": (
                            f"merged definition missing required field '{required}'. "
                            "LM API will reject the update. Either keep it from the "
                            "current definition or set it explicitly in changes."
                        ),
                    }
                )

        diff = _diff(base, merged)
        preview = {
            "type": type,
            "id": id,
            "mode": mode,
            "diff": diff,
            "merged_field_count": len(merged),
            "warnings": merge_warnings,
        }

        if mode == "preview":
            preview["dry_run"] = True
            preview["next_step"] = (
                "Re-call with mode='apply' to push the merged definition. "
                "Note: the underlying update is full-replace; the merged payload "
                "becomes the new full definition."
            )
            return format_response(preview)

        # mode == "apply"
        _AUDIT.info(
            "update_logicmodule attempting type=%s id=%s diff_count=%d",
            type,
            id,
            len(diff),
        )
        try:
            result = await call_sub_tool(
                update_module,
                client,
                module_type=type,
                module_id=id,
                definition=merged,
                confirm=True,
            )
        except Exception as exc:
            _AUDIT.error("update_logicmodule failed type=%s id=%s error=%s", type, id, exc)
            raise

        # Audit log "applied" only after the underlying PUT succeeded.
        _AUDIT.info("update_logicmodule applied type=%s id=%s", type, id)
        return format_response({**preview, "applied": True, "result": result})
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# Composite tool: detect_site_outage
# ---------------------------------------------------------------------------

_SITE_OUTAGE_REQUIRED = [
    "get_alerts",
    "get_devices",
    "get_collector_health",
    "analyze_alerts",
    "get_power_events",
]

_POWER_KEYWORDS = ("ups", "pdu", "battery", "power")

# Confidence each triggered signal adds to the site-outage score.
_SITE_OUTAGE_WEIGHTS = {
    "collector_down": 40,
    "interface_burst": 25,
    "power_events": 25,
    "device_silence": 10,
}


def _site_outage_verdict(score: int) -> str:
    """Map a site-outage confidence score to its verdict."""
    if score >= 70:
        return "site_outage_detected"
    if score >= 40:
        return "possible_site_outage"
    return "no_outage_signature"


def _unavailable_signal(error: str) -> dict:
    """Breakdown entry for a signal whose read failed: unknown, not untriggered."""
    return {"triggered": None, "status": "unavailable", "error": error}


async def detect_site_outage(
    client: LogicMonitorClient,
    group_id: int,
    window_seconds: int = 300,
    hours_back: int = 1,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite detector for site-level outages across a device group.

    Chains four signals into a single verdict:
      A) CollectorDown — any collector serving devices in this group is down
      B) Mass interface-down burst — analyze_alerts bursts on interface datasources
      C) Power events — UPS/PDU alerts in the last hour
      D) Device silence — count of dead devices in the group

    Confidence score (0-100):
      A>0: +40  |  B>0: +25  |  C>0: +25  |  D>threshold: +10

    Verdict: >=70 site_outage_detected; >=40 possible_site_outage; else no.

    A signal whose read fails is reported with status "unavailable" and its
    error, and is left out of the score. The report then carries
    confidence_level "reduced" and unavailable_signals; when the lost signals'
    weights could change the verdict, the verdict is "indeterminate".

    Args:
        client: LogicMonitor API client.
        group_id: Site = device group ID. Devices in this group define the
            scope of the analysis.
        window_seconds: Burst window size in seconds (default: 300).
        hours_back: Context window for power events in hours (default: 1).
        detail_level: "summary" or "full" (default: summary).

    Returns:
        TextContent list with verdict, confidence, signal breakdown, and
        affected-scope details.
    """
    blocked = check_required_tools(_SITE_OUTAGE_REQUIRED)
    if blocked:
        return blocked

    try:
        from lm_mcp.tools.analyze_alerts import analyze_alerts
        from lm_mcp.tools.collectors import get_collector_health
        from lm_mcp.tools.devices import get_devices
        from lm_mcp.tools.networking import get_power_events

        warnings: list[str] = []

        # Scope: enumerate devices in the group once.
        devices_data = await call_sub_tool(
            get_devices,
            client,
            group_id=group_id,
            limit=500,
        )
        devices = devices_data.get("devices", [])
        device_count = len(devices)
        dead_devices = _count_dead_devices(devices)
        collector_ids = _collector_ids_from_devices(devices)

        # Signals whose read failed, by signal name, with the error. They are left
        # out of the score instead of being scored as not triggered.
        unavailable: dict[str, str] = {}

        # Signal A: CollectorDown on collectors serving this group. Each
        # collector is probed independently so a single bad collector ID
        # (e.g., orphaned reference to a deleted collector) does not abort
        # the rest of the signal.
        collector_down_count = 0
        collectors_unknown = 0
        collectors_inspected: list[dict] = []
        collector_probe_failures: list[str] = []
        for cid in collector_ids:
            try:
                health_data = await call_sub_tool(
                    get_collector_health,
                    client,
                    collector_id=cid,
                    include_history=False,
                )
                entry = (health_data.get("collectors") or [{}])[0]
                collectors_inspected.append(entry)
                if entry.get("is_down"):
                    collector_down_count += 1
                elif entry.get("is_down") is None:
                    collectors_unknown += 1
            except Exception as exc:
                collector_probe_failures.append(f"collector_id={cid}: {exc}")

        if collector_probe_failures:
            failures_shown = "; ".join(collector_probe_failures[:5])
            suffix = "..." if len(collector_probe_failures) > 5 else ""
            warnings.append(
                f"{len(collector_probe_failures)}/{len(collector_ids)} "
                f"collector health probes failed: {failures_shown}{suffix}"
            )

        # One collector known to be down triggers the signal; otherwise any
        # collector whose state is unknown could have triggered it.
        collectors_unchecked = collectors_unknown + len(collector_probe_failures)
        if collector_down_count == 0 and collectors_unchecked:
            unavailable["collector_down"] = (
                f"{collectors_unchecked}/{len(collector_ids)} collector(s) could not be "
                "checked for CollectorDown"
            )

        # Signal B: mass interface-down burst in the window.
        burst_signal: dict | None = None
        try:
            window = await call_sub_tool(
                analyze_alerts,
                client,
                hours=hours_back,
                group_id=group_id,
                datasource="interface",
                analyses=["bursts"],
                window_seconds=window_seconds,
                min_alerts=5,
                min_devices=3,
            )
            burst_signal = window.get("bursts")
            if window.get("truncated"):
                warnings.append(ALERT_WINDOW_TRUNCATED_WARNING)
        except Exception as exc:
            warnings.append(f"Burst detection failed: {exc}")
            unavailable["interface_burst"] = f"Burst detection failed: {exc}"

        # Signal C: power events (UPS/PDU on-battery, battery-runtime, etc.).
        power_events_count = 0
        power_events_preview: list[dict] = []
        try:
            power_data = await call_sub_tool(
                get_power_events,
                client,
                group_id=group_id,
                hours_back=hours_back,
            )
            power_events_count = int(power_data.get("total_power_events", 0))
            power_events_preview = list(power_data.get("events", []))[:10]
        except Exception as exc:
            warnings.append(f"Power event query failed: {exc}")
            unavailable["power_events"] = f"Power event query failed: {exc}"

        # Score and verdict.
        silence_threshold = max(3, device_count // 5)  # 20% of group or 3 whichever higher
        confidence = 0
        signals_breakdown = {}
        if "collector_down" in unavailable:
            signals_breakdown["collector_down"] = _unavailable_signal(unavailable["collector_down"])
        elif collector_down_count > 0:
            confidence += _SITE_OUTAGE_WEIGHTS["collector_down"]
            signals_breakdown["collector_down"] = {
                "triggered": True,
                "count": collector_down_count,
                "weight": _SITE_OUTAGE_WEIGHTS["collector_down"],
            }
        else:
            signals_breakdown["collector_down"] = {"triggered": False, "count": 0}

        burst_count = int((burst_signal or {}).get("bursts_detected", 0))
        if "interface_burst" in unavailable:
            signals_breakdown["interface_burst"] = _unavailable_signal(
                unavailable["interface_burst"]
            )
        elif burst_count > 0:
            confidence += _SITE_OUTAGE_WEIGHTS["interface_burst"]
            signals_breakdown["interface_burst"] = {
                "triggered": True,
                "burst_count": burst_count,
                "weight": _SITE_OUTAGE_WEIGHTS["interface_burst"],
            }
        else:
            signals_breakdown["interface_burst"] = {"triggered": False, "burst_count": 0}

        if "power_events" in unavailable:
            signals_breakdown["power_events"] = _unavailable_signal(unavailable["power_events"])
        elif power_events_count > 0:
            confidence += _SITE_OUTAGE_WEIGHTS["power_events"]
            signals_breakdown["power_events"] = {
                "triggered": True,
                "count": power_events_count,
                "weight": _SITE_OUTAGE_WEIGHTS["power_events"],
            }
        else:
            signals_breakdown["power_events"] = {"triggered": False, "count": 0}

        if dead_devices >= silence_threshold:
            confidence += _SITE_OUTAGE_WEIGHTS["device_silence"]
            signals_breakdown["device_silence"] = {
                "triggered": True,
                "dead_devices": dead_devices,
                "threshold": silence_threshold,
                "weight": _SITE_OUTAGE_WEIGHTS["device_silence"],
            }
        else:
            signals_breakdown["device_silence"] = {
                "triggered": False,
                "dead_devices": dead_devices,
                "threshold": silence_threshold,
            }

        confidence = min(confidence, 100)
        verdict = _site_outage_verdict(confidence)
        # The lost signals could have added at most their weights. When that
        # ceiling names a different verdict, the signals that read cannot decide.
        ceiling = min(confidence + sum(_SITE_OUTAGE_WEIGHTS[name] for name in unavailable), 100)
        if _site_outage_verdict(ceiling) != verdict:
            verdict = "indeterminate"

        recommendations = _site_outage_recommendations(
            verdict, signals_breakdown, power_events_count, collector_down_count
        )

        report: dict = {
            "verdict": verdict,
            "confidence": confidence,
            **(
                {"confidence_level": "reduced", "unavailable_signals": list(unavailable)}
                if unavailable
                else {}
            ),
            "group_id": group_id,
            "window_seconds": window_seconds,
            "hours_back": hours_back,
            "scope": {
                "devices_in_group": device_count,
                "dead_devices": dead_devices,
                "collectors_serving_group": len(collector_ids),
            },
            "signals": signals_breakdown,
            "recommendations": recommendations,
            "warnings": warnings,
            "collectors_inspected": collectors_inspected,
            "interface_burst_detail": burst_signal,
            "power_events_preview": power_events_preview,
        }

        report = _trim_detail(
            report,
            detail_level,
            {"collectors_inspected", "interface_burst_detail", "power_events_preview"},
        )
        return format_response(report)
    except Exception as e:
        return handle_error(e)


def _count_dead_devices(devices: list[dict]) -> int:
    """Count devices in dead or dead-collector status.

    The v3 API reports hostStatus as a word: normal, dead, dead-collector,
    unmonitored or disabled. Both dead and dead-collector count because the
    device is not reporting metrics in either case. The formatted `get_devices`
    response surfaces hostStatus as `status`; the raw API item keeps `hostStatus`.
    """
    count = 0
    for dev in devices:
        status = dev.get("hostStatus")
        if status is None:
            status = dev.get("status")
        alert_status = (dev.get("alertStatus") or "").lower()
        if status in ("dead", "dead-collector") or alert_status in (
            "dead",
            "dead-collector",
            "unreachable",
        ):
            count += 1
    return count


def _collector_ids_from_devices(devices: list[dict]) -> list[int]:
    """Distinct collector IDs from a device list.

    Accepts both the formatted `get_devices` shape (`collector_id`) and the
    raw LM API shape (`currentCollectorId` / `preferredCollectorId`) so the
    helper works whether the caller passes formatted sub-tool output or raw
    API items. Formatted shape is preferred because that's what the composite
    sub-tool dispatch produces today.
    """
    seen: set[int] = set()
    ordered: list[int] = []
    for dev in devices:
        cid = (
            dev.get("collector_id")
            or dev.get("currentCollectorId")
            or dev.get("preferredCollectorId")
        )
        if cid and cid not in seen:
            seen.add(cid)
            ordered.append(cid)
    return ordered


def _site_outage_recommendations(
    verdict: str,
    signals: dict,
    power_events: int,
    collector_down: int,
) -> list[str]:
    """Actionable next steps based on which signals fired."""
    recs: list[str] = []
    if verdict == "site_outage_detected":
        recs.append("Treat as a single site-level incident; do not triage individual alerts.")
    if verdict == "indeterminate":
        lost = [name for name, sig in signals.items() if sig.get("status") == "unavailable"]
        recs.append(
            f"Signals could not be read ({', '.join(lost)}), and they could change the "
            "verdict. Re-run once the failed reads in warnings succeed."
        )
    if collector_down > 0:
        recs.append(
            "Verify collector host connectivity — collector is the typical first signal "
            "of site-level power or network loss."
        )
    if power_events > 0:
        recs.append(
            "Review UPS/PDU events for on-battery transitions and runtime-remaining "
            "alerts to confirm power-infrastructure involvement."
        )
    if signals.get("interface_burst", {}).get("triggered"):
        recs.append(
            "Mass interface-down detected — correlate affected ports to a common rack, "
            "switch, or uplink to localize the fault domain."
        )
    if signals.get("device_silence", {}).get("triggered"):
        recs.append(
            "Elevated count of dead devices — expect delayed alert clearing; "
            "re-run after site recovery to confirm scope."
        )
    if not recs:
        recs.append(
            "No outage signature detected. If symptoms persist, widen the group scope "
            "or lengthen the hours_back window."
        )
    return recs


# ---------------------------------------------------------------------------
# Composite tool: audit_network_monitoring_coverage
# ---------------------------------------------------------------------------

_AUDIT_COVERAGE_REQUIRED = [
    "get_devices",
    "get_collectors",
]


async def audit_network_monitoring_coverage(
    client: LogicMonitorClient,
    group_id: int | None = None,
) -> list[TextContent]:
    """Audit portal monitoring coverage and surface actionable gaps.

    Inventories devices, collectors, and coverage indicators (power
    monitoring, SNMP credentials, NetFlow exporters). Returns a gap list
    with specific recommendations — turns "you can't detect X" into
    "here's how to enable detection of X."

    Args:
        client: LogicMonitor API client.
        group_id: Scope the audit to a device group. None = portal-wide.

    Returns:
        TextContent list with inventory, coverage percentages, and prioritized gaps.
    """
    blocked = check_required_tools(_AUDIT_COVERAGE_REQUIRED)
    if blocked:
        return blocked

    try:
        from lm_mcp.tools.collectors import get_collectors
        from lm_mcp.tools.devices import get_devices

        warnings: list[str] = []

        devices_data = await call_sub_tool(
            get_devices,
            client,
            group_id=group_id,
            limit=1000,
        )
        devices = devices_data.get("devices", [])
        collectors_data = await call_sub_tool(get_collectors, client, limit=200)
        collectors = collectors_data.get("collectors", [])

        inventory = _build_inventory(devices, collectors)
        coverage = _compute_coverage(devices, collectors)
        gaps = _derive_gaps(inventory, coverage)

        return format_response(
            {
                "scope": {"group_id": group_id, "portal_wide": group_id is None},
                "inventory": inventory,
                "coverage_percentages": coverage["percentages"],
                "coverage_counts": coverage["counts"],
                "gaps": gaps,
                "summary": _audit_summary(inventory, coverage, gaps),
                "warnings": warnings,
            }
        )
    except Exception as e:
        return handle_error(e)


def _build_inventory(devices: list[dict], collectors: list[dict]) -> dict:
    """Counts by deviceType and likely power infrastructure."""
    total_devices = len(devices)
    power_like = 0
    network_like = 0
    server_like = 0
    unknown = 0

    for dev in devices:
        name = (dev.get("displayName") or dev.get("name") or "").lower()
        system_categories = (dev.get("systemCategories") or "").lower()
        combined = f"{name} {system_categories}"
        if any(kw in combined for kw in _POWER_KEYWORDS):
            power_like += 1
        elif any(kw in combined for kw in ("switch", "router", "firewall", "wlan")):
            network_like += 1
        elif any(kw in combined for kw in ("server", "linux", "windows", "host")):
            server_like += 1
        else:
            unknown += 1

    return {
        "total_devices": total_devices,
        "likely_power_infrastructure": power_like,
        "likely_network_gear": network_like,
        "likely_servers": server_like,
        "unclassified": unknown,
        "total_collectors": len(collectors),
    }


def _compute_coverage(devices: list[dict], collectors: list[dict]) -> dict:
    """Count devices with specific monitoring properties set."""
    total = len(devices) or 1
    snmp_count = 0
    netflow_count = 0
    power_monitored = 0

    for dev in devices:
        props = _properties_dict(dev)
        categories = (dev.get("systemCategories") or "").lower()
        name = (dev.get("displayName") or dev.get("name") or "").lower()

        if props.get("snmp.version") or props.get("snmp.community"):
            snmp_count += 1
        if (
            props.get("netflow.enabled")
            or "netflow" in categories
            or "netflowexporter" in categories
        ):
            netflow_count += 1
        if any(kw in f"{name} {categories}" for kw in _POWER_KEYWORDS):
            power_monitored += 1

    collectors_up = sum(1 for c in collectors if c.get("status") not in ("dead", "down"))

    return {
        "counts": {
            "snmp_credentialed": snmp_count,
            "netflow_exporters": netflow_count,
            "power_monitored_devices": power_monitored,
            "collectors_up": collectors_up,
            "collectors_total": len(collectors),
        },
        "percentages": {
            "snmp_coverage_pct": round(100.0 * snmp_count / total, 1),
            "netflow_coverage_pct": round(100.0 * netflow_count / total, 1),
            "power_monitoring_coverage_pct": round(100.0 * power_monitored / total, 1),
        },
    }


def _properties_dict(device: dict) -> dict[str, str]:
    """Flatten a device's customProperties list into a name->value dict."""
    result: dict[str, str] = {}
    for prop in device.get("customProperties", []) or []:
        name = prop.get("name")
        if name:
            result[name] = prop.get("value", "")
    for prop in device.get("systemProperties", []) or []:
        name = prop.get("name")
        if name and name not in result:
            result[name] = prop.get("value", "")
    return result


def _derive_gaps(inventory: dict, coverage: dict) -> list[dict]:
    """Prioritized list of coverage gaps with concrete recommendations."""
    gaps: list[dict] = []
    counts = coverage["counts"]

    if counts["power_monitored_devices"] == 0 and inventory["total_devices"] > 0:
        gaps.append(
            {
                "severity": "high",
                "category": "power",
                "finding": (
                    "No UPS/PDU/battery devices detected in this scope. Power outage "
                    "correlation cannot use UPS-state signals."
                ),
                "recommendation": (
                    "Onboard UPS and PDU devices (APC, Liebert, Eaton). Apply the "
                    "APC_UPS_Battery, Liebert_UPS, or Eaton_UPS DataSources so "
                    "on-battery and runtime-remaining events surface as alerts."
                ),
            }
        )

    total = max(inventory["total_devices"], 1)
    snmp_pct = coverage["percentages"]["snmp_coverage_pct"]
    if snmp_pct < 25 and inventory["likely_network_gear"] > 0:
        gaps.append(
            {
                "severity": "high",
                "category": "snmp",
                "finding": (
                    f"SNMP credentials set on only {snmp_pct}% of devices while "
                    f"{inventory['likely_network_gear']} network devices are present. "
                    "Interface metrics and link-flap detection depend on SNMP."
                ),
                "recommendation": (
                    "Apply snmp.version and snmp.community properties to network "
                    "devices at the group level to enable Interface DataSources."
                ),
            }
        )

    if counts["netflow_exporters"] == 0 and inventory["likely_network_gear"] > 0:
        gaps.append(
            {
                "severity": "medium",
                "category": "netflow",
                "finding": "No NetFlow exporters detected. Traffic intelligence unavailable.",
                "recommendation": (
                    "Enable NetFlow export on core and WAN devices. Set "
                    "netflow.enabled=true on the device or add the NetflowExporter "
                    "DataSource so the /netflow/flows endpoint receives records."
                ),
            }
        )

    if counts["collectors_total"] == 0:
        gaps.append(
            {
                "severity": "critical",
                "category": "collectors",
                "finding": "No collectors registered. Nothing can be monitored.",
                "recommendation": "Deploy at least one collector and assign it to devices.",
            }
        )
    elif counts["collectors_up"] < counts["collectors_total"]:
        down = counts["collectors_total"] - counts["collectors_up"]
        gaps.append(
            {
                "severity": "high",
                "category": "collectors",
                "finding": f"{down} collector(s) are down or unreachable.",
                "recommendation": (
                    "Restore collectors before relying on alert data — downstream "
                    "device alerts are suppressed while their collector is down."
                ),
            }
        )

    if inventory["unclassified"] > total * 0.5:
        gaps.append(
            {
                "severity": "low",
                "category": "inventory",
                "finding": (
                    f"{inventory['unclassified']} devices are unclassified by "
                    "systemCategories. Device grouping and filtering accuracy is limited."
                ),
                "recommendation": (
                    "Apply systemCategories property at the device-group level so "
                    "audit and correlation tools can partition inventory."
                ),
            }
        )

    return gaps


def _audit_summary(inventory: dict, coverage: dict, gaps: list[dict]) -> str:
    """One-line human-readable summary."""
    total = inventory["total_devices"]
    critical = sum(1 for g in gaps if g["severity"] in ("critical", "high"))
    if critical == 0:
        return f"Coverage looks solid across {total} devices ({len(gaps)} low-priority findings)."
    return (
        f"{critical} high-priority coverage gaps detected across {total} devices. "
        "Review gap list for specific onboarding actions."
    )
