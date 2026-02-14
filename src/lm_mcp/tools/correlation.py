# Description: Correlation and analysis tools for LogicMonitor MCP server.
# Description: Provides correlate_alerts, get_alert_statistics, get_metric_anomalies.

from __future__ import annotations

import math
import statistics
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, quote_filter_value
from lm_mcp.tools.stats_helpers import fetch_metric_series, pearson_correlation

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# Severity integer-to-name mapping (reverse of alerts.SEVERITY_MAP)
SEVERITY_NAMES = {4: "critical", 3: "error", 2: "warning", 1: "info"}

# Severity name-to-integer mapping for filter building
SEVERITY_MAP = {"critical": 4, "error": 3, "warning": 2, "info": 1}

# Temporal proximity window for clustering (seconds)
TEMPORAL_WINDOW_SECONDS = 300  # 5 minutes


def _build_alert_filter(
    hours_back: int,
    severity: str | None = None,
    device: str | None = None,
    group_id: int | None = None,
) -> str:
    """Build a filter string for alert queries.

    Args:
        hours_back: Number of hours to look back from now.
        severity: Optional severity name filter.
        device: Optional device name filter.
        group_id: Optional device group ID filter.

    Returns:
        Comma-separated filter string for the LM API.
    """
    now_epoch = int(time.time())
    start_epoch = now_epoch - (hours_back * 3600)

    filters = [f"startEpoch>:{start_epoch}", "cleared:false"]

    if severity and severity.lower() in SEVERITY_MAP:
        filters.append(f"severity:{SEVERITY_MAP[severity.lower()]}")
    if device:
        filters.append(f"monitorObjectName~{quote_filter_value(device)}")
    if group_id is not None:
        filters.append(f"hostGroupIds~{group_id}")

    return ",".join(filters)


def _cluster_by_device(alerts: list[dict]) -> list[dict]:
    """Group alerts by device name.

    Args:
        alerts: List of raw alert dicts from API.

    Returns:
        List of cluster dicts for devices with 2+ alerts.
    """
    by_device: dict[str, list[dict]] = defaultdict(list)
    for alert in alerts:
        device = alert.get("monitorObjectName", "unknown")
        by_device[device].append(alert)

    clusters = []
    for device, device_alerts in sorted(
        by_device.items(), key=lambda x: len(x[1]), reverse=True
    ):
        if len(device_alerts) >= 2:
            epochs = [a.get("startEpoch", 0) for a in device_alerts]
            clusters.append({
                "type": "device",
                "key": device,
                "count": len(device_alerts),
                "alert_ids": [a.get("id") for a in device_alerts],
                "first_alert_time": min(epochs),
                "last_alert_time": max(epochs),
            })
    return clusters


def _cluster_by_datasource(alerts: list[dict]) -> list[dict]:
    """Group alerts by datasource name across devices.

    Args:
        alerts: List of raw alert dicts from API.

    Returns:
        List of cluster dicts for datasources with 2+ alerts.
    """
    by_ds: dict[str, list[dict]] = defaultdict(list)
    for alert in alerts:
        ds = alert.get("resourceTemplateName", "unknown")
        by_ds[ds].append(alert)

    clusters = []
    for ds, ds_alerts in sorted(
        by_ds.items(), key=lambda x: len(x[1]), reverse=True
    ):
        if len(ds_alerts) >= 2:
            devices = list({a.get("monitorObjectName", "") for a in ds_alerts})
            epochs = [a.get("startEpoch", 0) for a in ds_alerts]
            clusters.append({
                "type": "datasource",
                "key": ds,
                "count": len(ds_alerts),
                "devices": devices,
                "alert_ids": [a.get("id") for a in ds_alerts],
                "first_alert_time": min(epochs),
                "last_alert_time": max(epochs),
            })
    return clusters


def _cluster_by_time(alerts: list[dict]) -> list[dict]:
    """Group alerts that start within a temporal window.

    Uses a sliding window approach: sort by start time, group alerts
    where consecutive alerts are within TEMPORAL_WINDOW_SECONDS of each other.

    Args:
        alerts: List of raw alert dicts from API.

    Returns:
        List of temporal cluster dicts for groups of 2+ alerts.
    """
    if len(alerts) < 2:
        return []

    sorted_alerts = sorted(alerts, key=lambda a: a.get("startEpoch", 0))
    clusters = []
    current_group: list[dict] = [sorted_alerts[0]]

    for alert in sorted_alerts[1:]:
        prev_epoch = current_group[-1].get("startEpoch", 0)
        curr_epoch = alert.get("startEpoch", 0)

        if (curr_epoch - prev_epoch) <= TEMPORAL_WINDOW_SECONDS:
            current_group.append(alert)
        else:
            if len(current_group) >= 2:
                epochs = [a.get("startEpoch", 0) for a in current_group]
                clusters.append({
                    "type": "temporal",
                    "key": f"window_{min(epochs)}",
                    "count": len(current_group),
                    "alert_ids": [a.get("id") for a in current_group],
                    "first_alert_time": min(epochs),
                    "last_alert_time": max(epochs),
                })
            current_group = [alert]

    # Handle the last group
    if len(current_group) >= 2:
        epochs = [a.get("startEpoch", 0) for a in current_group]
        clusters.append({
            "type": "temporal",
            "key": f"window_{min(epochs)}",
            "count": len(current_group),
            "alert_ids": [a.get("id") for a in current_group],
            "first_alert_time": min(epochs),
            "last_alert_time": max(epochs),
        })

    return clusters


async def correlate_alerts(
    client: "LogicMonitorClient",
    hours_back: int = 4,
    device: str | None = None,
    group_id: int | None = None,
    severity: str | None = None,
    limit: int = 500,
) -> list[TextContent]:
    """Correlate alerts by device, datasource, and temporal proximity.

    Fetches recent alerts and groups them into clusters based on:
    - Same device (2+ alerts on one device)
    - Same datasource across devices (2+ alerts for one datasource)
    - Temporal proximity (alerts starting within 5 minutes of each other)

    Args:
        client: LogicMonitor API client.
        hours_back: Number of hours to look back (default: 4).
        device: Optional device name filter.
        group_id: Optional device group ID filter.
        severity: Optional severity filter (critical, error, warning, info).
        limit: Maximum alerts to fetch (default: 500).

    Returns:
        List of TextContent with correlation clusters or error.
    """
    try:
        filter_str = _build_alert_filter(hours_back, severity, device, group_id)
        params: dict[str, Any] = {
            "size": min(limit, 1000),
            "filter": filter_str,
        }

        result = await client.get("/alert/alerts", params=params)
        alerts = result.get("items", [])

        # Build all cluster types
        device_clusters = _cluster_by_device(alerts)
        ds_clusters = _cluster_by_datasource(alerts)
        temporal_clusters = _cluster_by_time(alerts)

        all_clusters = device_clusters + ds_clusters + temporal_clusters

        return format_response({
            "total_alerts": len(alerts),
            "cluster_count": len(all_clusters),
            "time_window_hours": hours_back,
            "clusters": all_clusters,
        })
    except Exception as e:
        return handle_error(e)


async def get_alert_statistics(
    client: "LogicMonitorClient",
    hours_back: int = 24,
    device: str | None = None,
    group_id: int | None = None,
    bucket_size_hours: int = 1,
    limit: int = 1000,
) -> list[TextContent]:
    """Aggregate alert counts by severity, device, datasource, and time bucket.

    Args:
        client: LogicMonitor API client.
        hours_back: Number of hours to look back (default: 24).
        device: Optional device name filter.
        group_id: Optional device group ID filter.
        bucket_size_hours: Size of each time bucket in hours (default: 1).
        limit: Maximum alerts to fetch (default: 1000).

    Returns:
        List of TextContent with statistical summary or error.
    """
    try:
        filter_str = _build_alert_filter(hours_back, device=device, group_id=group_id)
        params: dict[str, Any] = {
            "size": min(limit, 1000),
            "filter": filter_str,
        }

        result = await client.get("/alert/alerts", params=params)
        alerts = result.get("items", [])

        # Count by severity
        by_severity: dict[str, int] = {
            "critical": 0, "error": 0, "warning": 0, "info": 0,
        }
        for alert in alerts:
            sev = alert.get("severity", 0)
            name = SEVERITY_NAMES.get(sev, "unknown")
            if name in by_severity:
                by_severity[name] += 1

        # Count by device (top 10)
        device_counts: dict[str, int] = defaultdict(int)
        for alert in alerts:
            dev = alert.get("monitorObjectName", "unknown")
            device_counts[dev] += 1
        by_device = [
            {"device": d, "count": c}
            for d, c in sorted(device_counts.items(), key=lambda x: x[1], reverse=True)
        ][:10]

        # Count by datasource (top 10)
        ds_counts: dict[str, int] = defaultdict(int)
        for alert in alerts:
            ds = alert.get("resourceTemplateName", "unknown")
            ds_counts[ds] += 1
        by_datasource = [
            {"datasource": ds, "count": c}
            for ds, c in sorted(ds_counts.items(), key=lambda x: x[1], reverse=True)
        ][:10]

        # Time bucketing
        now_epoch = int(time.time())
        start_epoch = now_epoch - (hours_back * 3600)
        bucket_seconds = bucket_size_hours * 3600
        num_buckets = max(1, math.ceil(hours_back / bucket_size_hours))

        time_buckets = []
        for i in range(num_buckets):
            bucket_start = start_epoch + (i * bucket_seconds)
            bucket_end = bucket_start + bucket_seconds
            count = sum(
                1 for a in alerts
                if bucket_start <= a.get("startEpoch", 0) < bucket_end
            )
            time_buckets.append({
                "bucket_start": bucket_start,
                "bucket_end": bucket_end,
                "count": count,
            })

        return format_response({
            "summary": {
                "total": len(alerts),
                "by_severity": by_severity,
                "by_device": by_device,
                "by_datasource": by_datasource,
            },
            "time_buckets": time_buckets,
            "time_window_hours": hours_back,
            "bucket_size_hours": bucket_size_hours,
        })
    except Exception as e:
        return handle_error(e)


def _detect_anomalies(
    datapoint_name: str,
    values: list[float],
    timestamps: list[int],
    threshold: float,
) -> list[dict]:
    """Detect anomalous data points using z-score method.

    For series with zero standard deviation (constant values), no anomalies
    are reported. Series with fewer than 2 data points are skipped.

    Args:
        datapoint_name: Name of the datapoint.
        values: List of numeric values.
        timestamps: List of epoch timestamps corresponding to values.
        threshold: Z-score threshold for anomaly detection.

    Returns:
        List of anomaly dicts with value, timestamp, z_score, mean, stddev.
    """
    # Filter out None/NaN values
    valid_pairs = [
        (v, t) for v, t in zip(values, timestamps)
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]

    if len(valid_pairs) < 2:
        return []

    clean_values = [p[0] for p in valid_pairs]
    clean_timestamps = [p[1] for p in valid_pairs]

    mean = statistics.mean(clean_values)
    try:
        stddev = statistics.stdev(clean_values)
    except statistics.StatisticsError:
        return []

    # Constant data — no anomalies possible
    if stddev == 0:
        return []

    anomalies = []
    for val, ts in zip(clean_values, clean_timestamps):
        z_score = abs(val - mean) / stddev
        if z_score > threshold:
            anomalies.append({
                "datapoint": datapoint_name,
                "value": val,
                "timestamp": ts,
                "z_score": round(z_score, 2),
                "mean": round(mean, 2),
                "stddev": round(stddev, 2),
            })

    return anomalies


async def get_metric_anomalies(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours_back: int = 24,
    threshold: float = 2.0,
) -> list[TextContent]:
    """Detect metric anomalies using statistical analysis.

    Fetches metric data and identifies values that deviate significantly
    from the mean using z-score analysis. No external ML dependencies.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (optional, all if omitted).
        hours_back: Number of hours to look back (default: 24).
        threshold: Z-score threshold for anomaly detection (default: 2.0).

    Returns:
        List of TextContent with anomaly report or error.
    """
    try:
        now_epoch = int(time.time())
        start_epoch = now_epoch - (hours_back * 3600)

        params: dict[str, Any] = {"start": start_epoch}
        if datapoints:
            params["datapoints"] = datapoints

        path = (
            f"/device/devices/{device_id}"
            f"/devicedatasources/{device_datasource_id}"
            f"/instances/{instance_id}/data"
        )
        result = await client.get(path, params=params)

        dp_names = result.get("datapoints", result.get("dataPoints", []))
        value_rows = result.get("values", [])
        # Timestamps come as epoch milliseconds from the API
        raw_timestamps = result.get("time", [])
        timestamps = [int(t / 1000) if t > 1e12 else int(t) for t in raw_timestamps]

        # Transpose: rows-of-values into per-datapoint columns
        all_anomalies: list[dict] = []
        for dp_idx, dp_name in enumerate(dp_names):
            dp_values = [
                row[dp_idx] for row in value_rows
                if dp_idx < len(row) and row[dp_idx] != "No Data"
            ]
            dp_timestamps = [
                timestamps[i] for i, row in enumerate(value_rows)
                if dp_idx < len(row) and row[dp_idx] != "No Data"
            ]
            anomalies = _detect_anomalies(
                dp_name, dp_values, dp_timestamps, threshold,
            )
            all_anomalies.extend(anomalies)

        return format_response({
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "instance_id": instance_id,
            "total_datapoints_checked": len(dp_names),
            "anomaly_count": len(all_anomalies),
            "anomalies": all_anomalies,
            "threshold": threshold,
            "hours_back": hours_back,
        })
    except Exception as e:
        return handle_error(e)


async def correlate_metrics(
    client: "LogicMonitorClient",
    sources: list[dict],
    hours_back: int = 24,
) -> list[TextContent]:
    """Compute Pearson correlation between multiple metric series.

    Fetches data from each source, aligns timestamps, and builds an
    NxN correlation matrix. Highlights strong correlations (|r| > 0.7).

    Args:
        client: LogicMonitor API client.
        sources: List of source dicts, each containing device_id,
            device_datasource_id, instance_id, and datapoint.
            Maximum 10 sources.
        hours_back: Hours of data to analyze (default: 24).

    Returns:
        Correlation matrix and list of strong correlations.
    """
    try:
        if len(sources) > 10:
            return format_response({
                "error": True,
                "message": "Maximum 10 sources allowed for correlation.",
                "suggestion": "Reduce the number of sources to 10 or fewer.",
            })

        if len(sources) < 2:
            return format_response({
                "error": True,
                "message": "At least 2 sources required for correlation.",
            })

        # Fetch each series
        labels = []
        all_values = []
        sample_counts = []

        for src in sources:
            dp_name = src.get("datapoint", "")
            series = await fetch_metric_series(
                client,
                device_id=src["device_id"],
                device_datasource_id=src["device_datasource_id"],
                instance_id=src["instance_id"],
                datapoints=dp_name if dp_name else None,
                hours_back=hours_back,
            )

            # Use the specified datapoint or the first available
            if dp_name and dp_name in series:
                vals = series[dp_name]["values"]
            elif series:
                first_key = next(iter(series))
                vals = series[first_key]["values"]
                dp_name = first_key
            else:
                vals = []

            label = f"d{src['device_id']}:{dp_name}"
            labels.append(label)
            all_values.append(vals)
            sample_counts.append(len(vals))

        # Align series to the shortest length
        min_len = min(len(v) for v in all_values) if all_values else 0
        if min_len < 2:
            return format_response({
                "error": True,
                "message": "Insufficient overlapping data for correlation.",
                "suggestion": "Ensure sources have at least 2 data points in the time window.",
            })

        aligned = [v[:min_len] for v in all_values]

        # Build NxN correlation matrix
        n = len(aligned)
        matrix: list[list[float | None]] = []
        strong_correlations = []

        for i in range(n):
            row = []
            for j in range(n):
                if i == j:
                    row.append(1.0)
                else:
                    r = pearson_correlation(aligned[i], aligned[j])
                    r = round(r, 4)
                    row.append(r)
                    if i < j and abs(r) > 0.7:
                        strong_correlations.append({
                            "source_a": labels[i],
                            "source_b": labels[j],
                            "correlation": r,
                            "strength": (
                                "strong_positive" if r > 0
                                else "strong_negative"
                            ),
                        })
            matrix.append(row)

        return format_response({
            "labels": labels,
            "correlation_matrix": matrix,
            "strong_correlations": strong_correlations,
            "sample_count": min_len,
            "hours_back": hours_back,
        })
    except Exception as e:
        return handle_error(e)
