# Description: Scoring and availability analysis tools for LogicMonitor.
# Description: Provides score_alert_noise, calculate_availability, score_device_health.

from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, quote_filter_value
from lm_mcp.tools.stats_helpers import (
    fetch_metric_series,
    shannon_entropy,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# Severity name-to-integer mapping
SEVERITY_MAP = {"critical": 4, "error": 3, "warning": 2, "info": 1}


async def score_alert_noise(
    client: "LogicMonitorClient",
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
        Noise score with entropy, flapping alerts, and recommendations.
    """
    try:
        now_epoch = int(time.time())
        start_epoch = now_epoch - (hours_back * 3600)

        # Fetch all alerts (active + cleared) in the time window
        filters = [f"startEpoch>:{start_epoch}"]
        if device:
            filters.append(f"monitorObjectName~{quote_filter_value(device)}")
        if group_id is not None:
            filters.append(f"hostGroupIds~{group_id}")

        params: dict[str, Any] = {
            "size": 1000,
            "filter": ",".join(filters),
        }

        result = await client.get("/alert/alerts", params=params)
        alerts = result.get("items", [])

        if not alerts:
            return format_response({
                "noise_score": 0,
                "entropy": 0.0,
                "total_alerts": 0,
                "flapping_alerts": [],
                "top_noisy_devices": [],
                "top_noisy_datasources": [],
                "recommendations": ["No alerts in the time window."],
                "hours_back": hours_back,
            })

        # Count alerts by datasource+datapoint combo for entropy
        combo_counts: dict[str, int] = defaultdict(int)
        device_counts: dict[str, int] = defaultdict(int)
        ds_counts: dict[str, int] = defaultdict(int)

        for alert in alerts:
            ds = alert.get("resourceTemplateName", "unknown")
            dp = alert.get("dataPointName", "unknown")
            dev = alert.get("monitorObjectName", "unknown")
            combo_counts[f"{ds}:{dp}"] += 1
            device_counts[dev] += 1
            ds_counts[ds] += 1

        # Shannon entropy of alert frequency distribution
        total = sum(combo_counts.values())
        probabilities = [c / total for c in combo_counts.values()]
        entropy = shannon_entropy(probabilities)
        # Normalize: max entropy = log2(num combos)
        max_entropy = math.log2(len(combo_counts)) if len(combo_counts) > 1 else 1.0
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

        # Flap detection: same device+datapoint clears then re-fires within 30 min
        alert_events: dict[str, list[dict]] = defaultdict(list)
        for alert in alerts:
            dev = alert.get("monitorObjectName", "unknown")
            dp = alert.get("dataPointName", "unknown")
            key = f"{dev}:{dp}"
            alert_events[key].append(alert)

        flapping_alerts = []
        flap_count = 0
        for key, events in alert_events.items():
            # Sort by start time
            sorted_events = sorted(events, key=lambda a: a.get("startEpoch", 0))
            for i in range(1, len(sorted_events)):
                prev = sorted_events[i - 1]
                curr = sorted_events[i]
                prev_end = prev.get("endEpoch", 0)
                curr_start = curr.get("startEpoch", 0)
                # endEpoch=0 means still active, skip for flap detection
                if prev_end > 0 and curr_start - prev_end < 1800:
                    flap_count += 1
                    if len(flapping_alerts) < 10:
                        flapping_alerts.append({
                            "key": key,
                            "gap_seconds": curr_start - prev_end,
                            "alert_id": curr.get("id"),
                        })

        # Repeat ratio: alerts from same combo appearing 3+ times
        repeat_count = sum(1 for c in combo_counts.values() if c >= 3)
        repeat_ratio = repeat_count / len(combo_counts) if combo_counts else 0.0

        flap_ratio = flap_count / len(alerts) if alerts else 0.0

        # Noise score: weighted combination
        noise_score = min(100, int(
            normalized_entropy * 40
            + flap_ratio * 100 * 30
            + repeat_ratio * 100 * 30
        ))

        # Top noisy devices and datasources
        top_devices = sorted(
            device_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]
        top_datasources = sorted(
            ds_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # Recommendations
        recommendations = []
        if flap_count > 0:
            recommendations.append(
                f"{flap_count} flapping alert(s) detected. "
                "Consider adding alert delay or hysteresis."
            )
        if repeat_ratio > 0.5:
            recommendations.append(
                "High repeat ratio. Review alert thresholds and "
                "consider consolidation rules."
            )
        if noise_score > 70:
            recommendations.append(
                "Very high noise level. Review top noisy devices "
                "and datasources for tuning opportunities."
            )
        if not recommendations:
            recommendations.append("Alert noise levels are acceptable.")

        return format_response({
            "noise_score": noise_score,
            "entropy": round(entropy, 4),
            "normalized_entropy": round(normalized_entropy, 4),
            "total_alerts": len(alerts),
            "flap_count": flap_count,
            "flapping_alerts": flapping_alerts,
            "repeat_ratio": round(repeat_ratio, 4),
            "top_noisy_devices": [
                {"device": d, "count": c} for d, c in top_devices
            ],
            "top_noisy_datasources": [
                {"datasource": ds, "count": c} for ds, c in top_datasources
            ],
            "recommendations": recommendations,
            "hours_back": hours_back,
        })
    except Exception as e:
        return handle_error(e)


async def calculate_availability(
    client: "LogicMonitorClient",
    device_id: int | None = None,
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
        group_id: Optional device group ID filter.
        hours_back: Hours to look back (default: 720 = 30 days).
        severity_threshold: Minimum severity to count as downtime
            (critical, error, warning, info). Default: error.

    Returns:
        Availability percentage, downtime, MTTR, and per-device breakdown.
    """
    try:
        now_epoch = int(time.time())
        start_epoch = now_epoch - (hours_back * 3600)
        total_window_minutes = hours_back * 60

        # Build filter for alerts at or above severity threshold
        min_severity = SEVERITY_MAP.get(severity_threshold.lower(), 3)
        filters = [f"startEpoch>:{start_epoch}"]

        if min_severity < 4:
            filters.append(f"severity>:{min_severity}")
        else:
            filters.append(f"severity:{min_severity}")

        if device_id is not None:
            filters.append(f"monitorObjectId:{device_id}")
        if group_id is not None:
            filters.append(f"hostGroupIds~{group_id}")

        params: dict[str, Any] = {
            "size": 1000,
            "filter": ",".join(filters),
        }

        result = await client.get("/alert/alerts", params=params)
        alerts = result.get("items", [])

        if not alerts:
            return format_response({
                "availability_percent": 100.0,
                "total_downtime_minutes": 0,
                "total_uptime_minutes": total_window_minutes,
                "mttr_minutes": 0,
                "incident_count": 0,
                "longest_incident_minutes": 0,
                "by_device": {},
                "hours_back": hours_back,
                "severity_threshold": severity_threshold,
            })

        # Group alerts by device and compute downtime windows
        device_alerts: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for alert in alerts:
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
            worst_availability = min(
                d["availability_percent"] for d in by_device.values()
            )
        else:
            worst_availability = 100.0

        mttr = (
            sum(incident_durations) / len(incident_durations)
            if incident_durations else 0
        )

        return format_response({
            "availability_percent": round(worst_availability, 4),
            "total_downtime_minutes": round(
                total_downtime_seconds / 60.0, 2
            ),
            "total_uptime_minutes": round(
                total_window_minutes - total_downtime_seconds / 60.0, 2
            ),
            "mttr_minutes": round(mttr, 2),
            "incident_count": incident_count,
            "longest_incident_minutes": round(longest_incident, 2),
            "by_device": by_device,
            "hours_back": hours_back,
            "severity_threshold": severity_threshold,
        })
    except Exception as e:
        return handle_error(e)


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


async def score_device_health(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours_back: int = 4,
    weights: dict[str, float] | None = None,
) -> list[TextContent]:
    """Compute a composite health score (0-100) for a device instance.

    Fetches metric data, computes z-scores for the latest value of each
    datapoint against its historical distribution, and aggregates into
    a single health score.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours_back: Hours of historical data for z-score baseline (default: 4).
        weights: Optional dict of datapoint_name -> weight for scoring.

    Returns:
        Health score with status, contributing factors, and anomaly count.
    """
    try:
        series = await fetch_metric_series(
            client, device_id, device_datasource_id, instance_id,
            datapoints=datapoints, hours_back=hours_back,
        )

        if not series:
            return format_response({
                "device_id": device_id,
                "health_score": 100,
                "status": "unknown",
                "message": "No metric data available",
                "contributing_factors": [],
                "anomaly_count": 0,
            })

        factors = []
        anomaly_count = 0

        for dp_name, dp_data in series.items():
            values = dp_data["values"]

            if len(values) < 2:
                continue

            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            stddev = math.sqrt(variance) if variance > 0 else 0.0

            latest = values[-1]

            if stddev > 0:
                z_score = abs(latest - mean) / stddev
            else:
                z_score = 0.0

            weight = 1.0
            if weights and dp_name in weights:
                weight = weights[dp_name]

            if z_score > 2.0:
                anomaly_count += 1

            factors.append({
                "datapoint": dp_name,
                "latest_value": round(latest, 4),
                "mean": round(mean, 4),
                "stddev": round(stddev, 4),
                "z_score": round(z_score, 2),
                "weight": weight,
                "weighted_impact": round(z_score * weight, 4),
            })

        # Sort by weighted impact (most impactful first)
        factors.sort(key=lambda f: f["weighted_impact"], reverse=True)

        # Health score: start at 100, subtract weighted z-scores
        if factors:
            total_weight = sum(f["weight"] for f in factors)
            weighted_z_sum = sum(
                f["z_score"] * f["weight"] for f in factors
            )
            avg_weighted_z = weighted_z_sum / total_weight if total_weight > 0 else 0
            health_score = max(0, int(100 - avg_weighted_z * 15))
        else:
            health_score = 100

        # Status classification
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 50:
            status = "degraded"
        else:
            status = "critical"

        return format_response({
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "instance_id": instance_id,
            "health_score": health_score,
            "status": status,
            "contributing_factors": factors,
            "anomaly_count": anomaly_count,
            "hours_back": hours_back,
        })
    except Exception as e:
        return handle_error(e)
