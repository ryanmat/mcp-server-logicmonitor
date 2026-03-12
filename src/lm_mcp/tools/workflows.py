# Description: Composite workflow tools for LogicMonitor MCP server.
# Description: Provides triage, health_check, capacity_plan, portal_overview, diagnose.

from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


async def _call_sub_tool(handler, client: "LogicMonitorClient", **kwargs) -> dict:
    """Call a sub-handler, parse JSON response, raise on errors."""
    result = await handler(client, **kwargs)
    data = json.loads(result[0].text)
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(data.get("message", "Sub-tool returned an error"))
    return data


def check_required_tools(required: list[str]) -> list[TextContent] | None:
    """Check all sub-tools pass LM_ENABLED_TOOLS/LM_DISABLED_TOOLS.

    Returns None if OK, error TextContent list if any tool is blocked.
    """
    from lm_mcp.config import get_config

    config = get_config()
    blocked: list[str] = []

    if config.enabled_tools:
        patterns = [p.strip() for p in config.enabled_tools.split(",") if p.strip()]
        blocked = [t for t in required if not any(fnmatch(t, p) for p in patterns)]
    elif config.disabled_tools:
        patterns = [p.strip() for p in config.disabled_tools.split(",") if p.strip()]
        blocked = [t for t in required if any(fnmatch(t, p) for p in patterns)]

    if blocked:
        return format_response({
            "error": True,
            "code": "REQUIRED_TOOLS_DISABLED",
            "message": f"Composite tool requires disabled tools: {', '.join(blocked)}",
            "suggestion": "Enable these tools or use individual tools instead",
        })
    return None


async def _resolve_device(
    client: "LogicMonitorClient",
    device_id: int | None = None,
    device_name: str | None = None,
) -> tuple[int, dict]:
    """Resolve device by ID or name search. Returns (id, device_dict)."""
    from lm_mcp.tools.devices import get_device, get_devices

    if device_id is not None:
        data = await _call_sub_tool(get_device, client, device_id=device_id)
        return device_id, data
    if device_name:
        data = await _call_sub_tool(
            get_devices, client, name_filter=device_name, limit=1,
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
    "get_alerts",
    "get_alert_statistics",
    "correlate_alerts",
    "score_alert_noise",
    "analyze_blast_radius",
    "correlate_changes",
]


async def triage(
    client: "LogicMonitorClient",
    severity: str | None = None,
    device: str | None = None,
    group_id: int | None = None,
    hours_back: int = 4,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite triage: correlate, cluster, score, and assess alerts.

    Fetches active alerts, builds time-bucketed statistics, clusters
    related alerts, scores noise, analyzes blast radius for critical
    clusters, and cross-references recent changes.

    Args:
        client: LogicMonitor API client.
        severity: Filter alerts by severity.
        device: Filter by device name.
        group_id: Filter by device group ID.
        hours_back: Hours to look back (default: 4).
        detail_level: 'summary' or 'full' (default: summary).

    Returns:
        Prioritized incident report as TextContent list.
    """
    blocked = check_required_tools(_TRIAGE_REQUIRED)
    if blocked:
        return blocked

    try:
        from lm_mcp.tools.correlation import correlate_alerts, get_alert_statistics
        from lm_mcp.tools.event_correlation import correlate_changes
        from lm_mcp.tools.scoring import score_alert_noise
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        warnings: list[str] = []
        report: dict = {"hours_back": hours_back, "detail_level": detail_level}

        # 1. Get alert statistics
        try:
            stats = await _call_sub_tool(
                get_alert_statistics, client,
                hours_back=hours_back, device=device, group_id=group_id,
            )
            report["statistics"] = stats
        except Exception as exc:
            warnings.append(f"get_alert_statistics failed: {exc}")
            report["statistics"] = None

        # 2. Correlate alerts (clusters)
        clusters_data: dict = {}
        try:
            clusters_data = await _call_sub_tool(
                correlate_alerts, client,
                hours_back=hours_back, severity=severity,
                device=device, group_id=group_id,
            )
            report["clusters"] = clusters_data
        except Exception as exc:
            warnings.append(f"correlate_alerts failed: {exc}")
            report["clusters"] = None

        # 3. Score alert noise
        try:
            noise = await _call_sub_tool(
                score_alert_noise, client,
                hours_back=hours_back, device=device, group_id=group_id,
            )
            report["noise"] = noise
        except Exception as exc:
            warnings.append(f"score_alert_noise failed: {exc}")
            report["noise"] = None

        # 4. Blast radius for critical clusters (up to 3 devices)
        blast_results: list[dict] = []
        clusters = clusters_data.get("clusters", []) if clusters_data else []
        device_clusters = [c for c in clusters if c.get("type") == "device"]
        for cluster in device_clusters[:3]:
            device_key = cluster.get("key", "")
            # Resolve device name to ID via search
            try:
                from lm_mcp.tools.devices import get_devices

                dev_data = await _call_sub_tool(
                    get_devices, client, name_filter=device_key, limit=1,
                )
                devs = dev_data.get("devices", [])
                if devs:
                    br = await _call_sub_tool(
                        analyze_blast_radius, client,
                        device_id=devs[0]["id"],
                    )
                    blast_results.append({
                        "device": device_key,
                        "blast_radius": br,
                    })
            except Exception:
                pass
        report["blast_radius"] = blast_results

        # 5. Correlate changes
        try:
            changes = await _call_sub_tool(
                correlate_changes, client, hours_back=hours_back,
            )
            report["changes"] = changes
        except Exception as exc:
            warnings.append(f"correlate_changes failed: {exc}")
            report["changes"] = None

        if warnings:
            report["warnings"] = warnings

        # Trim for summary mode
        full_keys = {
            "blast_radius",
        }
        report = _trim_detail(report, detail_level, full_keys)

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
    "score_device_health",
    "get_metric_anomalies",
    "get_alerts",
    "calculate_availability",
]


async def health_check(
    client: "LogicMonitorClient",
    device_id: int | None = None,
    device_name: str | None = None,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite health check for a single device.

    Resolves the device, gathers datasource coverage, scores health,
    detects anomalies, checks active alerts, and calculates availability.

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
        from lm_mcp.tools.correlation import get_metric_anomalies
        from lm_mcp.tools.metrics import get_device_datasources, get_device_instances
        from lm_mcp.tools.scoring import calculate_availability, score_device_health

        warnings: list[str] = []

        # 1. Resolve device
        resolved_id, device_info = await _resolve_device(
            client, device_id=device_id, device_name=device_name,
        )
        report: dict = {
            "device_id": resolved_id,
            "device_name": device_info.get("displayName", device_info.get("name", "")),
            "detail_level": detail_level,
        }

        # 2. Get datasources
        ds_list: list[dict] = []
        try:
            ds_data = await _call_sub_tool(
                get_device_datasources, client, device_id=resolved_id,
            )
            ds_list = ds_data.get("datasources", [])
            report["datasource_count"] = len(ds_list)
        except Exception as exc:
            warnings.append(f"get_device_datasources failed: {exc}")
            report["datasource_count"] = 0

        # 3. Score health for first 5 datasources (skip those with no instances)
        health_scores: list[dict] = []
        primary_ds_id: int | None = None
        primary_instance_id: int | None = None

        for ds in ds_list[:5]:
            ds_id = ds.get("id")
            if ds_id is None:
                continue
            try:
                inst_data = await _call_sub_tool(
                    get_device_instances, client,
                    device_id=resolved_id, device_datasource_id=ds_id,
                )
                instances = inst_data.get("instances", [])
                if not instances:
                    continue

                inst_id = instances[0].get("id")
                if primary_ds_id is None and inst_id is not None:
                    primary_ds_id = ds_id
                    primary_instance_id = inst_id

                try:
                    score = await _call_sub_tool(
                        score_device_health, client,
                        device_id=resolved_id,
                        device_datasource_id=ds_id,
                        instance_id=inst_id,
                    )
                    health_scores.append({
                        "datasource": ds.get("name", ""),
                        "score": score,
                    })
                except Exception:
                    pass
            except Exception:
                continue

        report["health_scores"] = health_scores

        # 4. Metric anomalies for primary datasource
        if primary_ds_id is not None and primary_instance_id is not None:
            try:
                anomalies = await _call_sub_tool(
                    get_metric_anomalies, client,
                    device_id=resolved_id,
                    device_datasource_id=primary_ds_id,
                    instance_id=primary_instance_id,
                )
                report["anomalies"] = anomalies
            except Exception as exc:
                warnings.append(f"get_metric_anomalies failed: {exc}")
        else:
            report["anomalies"] = None

        # 5. Active alerts for the device
        try:
            device_display = report["device_name"]
            alert_data = await _call_sub_tool(
                get_alerts, client, device=device_display, cleared=False,
            )
            report["active_alerts"] = alert_data
        except Exception as exc:
            warnings.append(f"get_alerts failed: {exc}")
            report["active_alerts"] = None

        # 6. Availability (30-day)
        try:
            avail = await _call_sub_tool(
                calculate_availability, client, device_id=resolved_id,
            )
            report["availability"] = avail
        except Exception as exc:
            warnings.append(f"calculate_availability failed: {exc}")
            report["availability"] = None

        if warnings:
            report["warnings"] = warnings

        full_keys = {"anomalies", "health_scores"}
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
    "forecast_metric",
    "classify_trend",
    "detect_seasonality",
    "detect_change_points",
]


async def capacity_plan(
    client: "LogicMonitorClient",
    device_id: int | None = None,
    device_name: str | None = None,
    datasource: str | None = None,
    hours_back: int = 168,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite capacity planning for a device.

    Forecasts metric breach dates, classifies trends, detects seasonality
    and change points across datasources and instances.

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
        from lm_mcp.tools.forecasting import (
            classify_trend,
            detect_change_points,
            detect_seasonality,
            forecast_metric,
        )
        from lm_mcp.tools.metrics import get_device_datasources, get_device_instances

        warnings: list[str] = []

        # 1. Resolve device
        resolved_id, device_info = await _resolve_device(
            client, device_id=device_id, device_name=device_name,
        )
        report: dict = {
            "device_id": resolved_id,
            "device_name": device_info.get("displayName", device_info.get("name", "")),
            "hours_back": hours_back,
            "detail_level": detail_level,
        }

        # 2. Get datasources (filtered if datasource param given)
        try:
            ds_data = await _call_sub_tool(
                get_device_datasources, client,
                device_id=resolved_id,
                name_filter=datasource,
            )
            ds_list = ds_data.get("datasources", [])
        except Exception as exc:
            warnings.append(f"get_device_datasources failed: {exc}")
            ds_list = []

        # 3. Per datasource (up to 5), per instance (up to 3): forecast + trend
        ds_reports: list[dict] = []
        for ds in ds_list[:5]:
            ds_id = ds.get("id")
            if ds_id is None:
                continue

            ds_report: dict = {"datasource": ds.get("name", ""), "instances": []}

            try:
                inst_data = await _call_sub_tool(
                    get_device_instances, client,
                    device_id=resolved_id, device_datasource_id=ds_id,
                )
                instances = inst_data.get("instances", [])
            except Exception:
                instances = []

            for inst in instances[:3]:
                inst_id = inst.get("id")
                if inst_id is None:
                    continue

                inst_report: dict = {"instance": inst.get("name", "")}
                common_kwargs = {
                    "device_id": resolved_id,
                    "device_datasource_id": ds_id,
                    "instance_id": inst_id,
                    "hours_back": hours_back,
                }

                # Forecast (use threshold=90 as default capacity threshold)
                try:
                    fc = await _call_sub_tool(
                        forecast_metric, client,
                        threshold=90.0, **common_kwargs,
                    )
                    inst_report["forecast"] = fc
                except Exception:
                    inst_report["forecast"] = None

                # Classify trend
                try:
                    trend = await _call_sub_tool(
                        classify_trend, client, **common_kwargs,
                    )
                    inst_report["trend"] = trend
                except Exception:
                    inst_report["trend"] = None

                # Seasonality
                try:
                    season = await _call_sub_tool(
                        detect_seasonality, client, **common_kwargs,
                    )
                    inst_report["seasonality"] = season
                except Exception:
                    inst_report["seasonality"] = None

                # Change points (only if volatile trend detected)
                is_volatile = False
                if inst_report.get("trend"):
                    classifications = inst_report["trend"].get("classifications", {})
                    for _dp, info in classifications.items():
                        if info.get("classification") == "volatile":
                            is_volatile = True
                            break

                if is_volatile:
                    try:
                        cps = await _call_sub_tool(
                            detect_change_points, client, **common_kwargs,
                        )
                        inst_report["change_points"] = cps
                    except Exception:
                        inst_report["change_points"] = None

                ds_report["instances"].append(inst_report)

            ds_reports.append(ds_report)

        report["datasources"] = ds_reports

        if warnings:
            report["warnings"] = warnings

        full_keys = {"datasources"}
        report = _trim_detail(report, detail_level, full_keys)

        return format_response(report)
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# Composite tool: portal_overview
# ---------------------------------------------------------------------------

_PORTAL_OVERVIEW_REQUIRED = [
    "get_alert_statistics",
    "get_alerts",
    "get_collectors",
    "get_active_sdts",
    "correlate_alerts",
    "score_alert_noise",
    "get_devices",
]


async def portal_overview(
    client: "LogicMonitorClient",
    hours_back: int = 4,
    detail_level: str = "summary",
) -> list[TextContent]:
    """Composite portal overview for shift-handoff reporting.

    Aggregates alert statistics, collector health, maintenance windows,
    noise scores, and dead/unmonitored devices.

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
        from lm_mcp.tools.collectors import get_collectors
        from lm_mcp.tools.correlation import correlate_alerts, get_alert_statistics
        from lm_mcp.tools.devices import get_devices
        from lm_mcp.tools.scoring import score_alert_noise
        from lm_mcp.tools.sdts import get_active_sdts

        warnings: list[str] = []
        report: dict = {"hours_back": hours_back, "detail_level": detail_level}

        # 1. Alert statistics
        try:
            stats = await _call_sub_tool(
                get_alert_statistics, client, hours_back=hours_back,
            )
            report["alert_statistics"] = stats
        except Exception as exc:
            warnings.append(f"get_alert_statistics failed: {exc}")
            report["alert_statistics"] = None

        # 2. High-severity active alerts (critical + error)
        try:
            crit_alerts = await _call_sub_tool(
                get_alerts, client, severity="critical", cleared=False, limit=20,
            )
            err_alerts = await _call_sub_tool(
                get_alerts, client, severity="error", cleared=False, limit=20,
            )
            report["critical_alerts"] = crit_alerts
            report["error_alerts"] = err_alerts
        except Exception as exc:
            warnings.append(f"get_alerts failed: {exc}")
            report["critical_alerts"] = None
            report["error_alerts"] = None

        # 3. Collector health
        try:
            coll_data = await _call_sub_tool(get_collectors, client)
            report["collectors"] = coll_data
        except Exception as exc:
            warnings.append(f"get_collectors failed: {exc}")
            report["collectors"] = None

        # 4. Active SDTs
        try:
            sdt_data = await _call_sub_tool(get_active_sdts, client)
            report["active_sdts"] = sdt_data
        except Exception as exc:
            warnings.append(f"get_active_sdts failed: {exc}")
            report["active_sdts"] = None

        # 5. Correlate alerts
        try:
            cluster_data = await _call_sub_tool(
                correlate_alerts, client, hours_back=hours_back,
            )
            report["alert_clusters"] = cluster_data
        except Exception as exc:
            warnings.append(f"correlate_alerts failed: {exc}")
            report["alert_clusters"] = None

        # 6. Noise assessment
        try:
            noise = await _call_sub_tool(
                score_alert_noise, client, hours_back=hours_back,
            )
            report["noise"] = noise
        except Exception as exc:
            warnings.append(f"score_alert_noise failed: {exc}")
            report["noise"] = None

        # 7. Dead/unmonitored devices
        try:
            dead = await _call_sub_tool(get_devices, client, status="dead", limit=20)
            report["dead_devices"] = dead
        except Exception as exc:
            warnings.append(f"get_devices (dead) failed: {exc}")
            report["dead_devices"] = None

        if warnings:
            report["warnings"] = warnings

        full_keys = {"critical_alerts", "error_alerts", "dead_devices"}
        report = _trim_detail(report, detail_level, full_keys)

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
    "correlate_alerts",
    "correlate_changes",
    "analyze_blast_radius",
    "score_device_health",
]


async def diagnose(
    client: "LogicMonitorClient",
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
        from lm_mcp.tools.correlation import correlate_alerts
        from lm_mcp.tools.devices import get_device
        from lm_mcp.tools.event_correlation import correlate_changes
        from lm_mcp.tools.resources import get_device_properties
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        warnings: list[str] = []
        report: dict = {"detail_level": detail_level}

        # 1. Resolve target
        alert_data: dict | None = None
        target_device_id: int | None = None

        if alert_id:
            try:
                alert_data = await _call_sub_tool(
                    get_alert_details, client, alert_id=alert_id,
                )
                target_device_id = alert_data.get("monitorObjectId")
                report["alert"] = alert_data
            except Exception as exc:
                warnings.append(f"get_alert_details failed: {exc}")
        elif device_name:
            try:
                alerts_data = await _call_sub_tool(
                    get_alerts, client, device=device_name,
                    severity="critical", cleared=False, limit=1,
                )
                alert_list = alerts_data.get("alerts", [])
                if alert_list:
                    resolved_alert_id = alert_list[0].get("id", "")
                    alert_data = await _call_sub_tool(
                        get_alert_details, client,
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
            return format_response({
                "error": True,
                "code": "MISSING_PARAMS",
                "message": "Either alert_id or device_name is required",
            })

        # 2. Device context
        if target_device_id is not None:
            try:
                dev = await _call_sub_tool(
                    get_device, client, device_id=target_device_id,
                )
                report["device"] = dev
            except Exception as exc:
                warnings.append(f"get_device failed: {exc}")

            try:
                props = await _call_sub_tool(
                    get_device_properties, client, device_id=target_device_id,
                )
                report["device_properties"] = props
            except Exception as exc:
                warnings.append(f"get_device_properties failed: {exc}")

        # 3. Correlated alerts
        try:
            corr = await _call_sub_tool(
                correlate_alerts, client, hours_back=4,
            )
            report["correlated_alerts"] = corr
        except Exception as exc:
            warnings.append(f"correlate_alerts failed: {exc}")

        # 4. Change correlation
        try:
            changes = await _call_sub_tool(
                correlate_changes, client, hours_back=4,
            )
            report["changes"] = changes
        except Exception as exc:
            warnings.append(f"correlate_changes failed: {exc}")

        # 5. Blast radius
        if target_device_id is not None:
            try:
                blast = await _call_sub_tool(
                    analyze_blast_radius, client, device_id=target_device_id,
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
}


async def search_tools(
    client: "LogicMonitorClient",
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

        # Tokenize query into lowercase words
        query_words = re.findall(r"[a-z0-9_]+", query.lower())
        if not query_words:
            return format_response({
                "matches": [],
                "total": 0,
                "query": query,
                "suggestions": [],
            })

        # Optionally filter by category
        category_tool_names: set[str] | None = None
        if category:
            cats = TOOL_CATEGORIES.get("categories", {})
            cat_data = cats.get(category)
            if cat_data:
                category_tool_names = set(cat_data.get("tools", []))
            else:
                return format_response({
                    "matches": [],
                    "total": 0,
                    "query": query,
                    "category": category,
                    "available_categories": list(cats.keys()),
                    "suggestions": [],
                })

        # Score each tool
        scored: list[tuple[float, dict]] = []
        for tool in TOOLS:
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
                scored.append((score, {
                    "name": name,
                    "description": tool.description,
                    "score": round(score, 1),
                }))

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

        return format_response({
            "matches": matches,
            "total": len(scored),
            "query": query,
            "category": category,
            "suggestions": suggestions if suggestions else None,
        })
    except Exception as e:
        return handle_error(e)
