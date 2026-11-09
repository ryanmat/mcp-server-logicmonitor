# Description: analyze_alerts reads one alert window, active and cleared, and reports it by section.
# Description: Holds the alert-window math behind each of its sections.

from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import (
    SEVERITY_MAP,
    SEVERITY_NAMES,
    format_response,
    handle_error,
    quote_filter_value,
    resolve_group_filter,
    sanitize_filter_value,
    validation_error,
)
from lm_mcp.tools.alerts import read_cleared_and_active
from lm_mcp.tools.stats_helpers import shannon_entropy

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# The sections analyze_alerts offers, in the order it reports them.
SECTIONS = ("statistics", "clusters", "noise")

DEFAULT_HOURS = 24

# A cleared alert that re-fires on the same device and datapoint within this many
# seconds of clearing is a flap.
FLAP_WINDOW_SECONDS = 1800


async def window_filter(
    client: Any,
    start_epoch: int,
    severity: str | None = None,
    device: str | None = None,
    group_id: int | None = None,
) -> str:
    """Build the alert-list filter for a window that opens at start_epoch.

    Args:
        client: LogicMonitor API client (needed for group_id resolution).
        start_epoch: Epoch seconds the window opens at.
        severity: Severity name from SEVERITY_MAP.
        device: Device name, matched as a substring.
        group_id: Device group ID, resolved to its full path.

    Returns:
        Comma-separated filter string with no cleared clause.
    """
    filters = [f"startEpoch>:{start_epoch}"]
    if severity:
        filters.append(f"severity:{SEVERITY_MAP[severity]}")
    if device:
        clean_val, _ = sanitize_filter_value(device)
        filters.append(f"monitorObjectName~{quote_filter_value(clean_val)}")
    if group_id is not None:
        filters.append(await resolve_group_filter(client, group_id))
    return ",".join(filters)


def alert_counts(alerts: list[dict]) -> dict[str, Any]:
    """Count alerts by severity name, and the ten busiest devices and datasources.

    Args:
        alerts: Raw alert rows.

    Returns:
        by_severity with every severity name, by_device and by_datasource busiest first.
    """
    by_severity = dict.fromkeys(SEVERITY_MAP, 0)
    device_counts: dict[str, int] = defaultdict(int)
    ds_counts: dict[str, int] = defaultdict(int)
    for alert in alerts:
        name = SEVERITY_NAMES.get(alert.get("severity", 0), "unknown")
        if name in by_severity:
            by_severity[name] += 1
        device_counts[alert.get("monitorObjectName", "unknown")] += 1
        ds_counts[alert.get("resourceTemplateName", "unknown")] += 1
    return {
        "by_severity": by_severity,
        "by_device": [
            {"device": d, "count": c}
            for d, c in sorted(device_counts.items(), key=lambda x: x[1], reverse=True)
        ][:10],
        "by_datasource": [
            {"datasource": ds, "count": c}
            for ds, c in sorted(ds_counts.items(), key=lambda x: x[1], reverse=True)
        ][:10],
    }


def statistics_section(alerts: list[dict], start_epoch: int, hours: int) -> dict[str, Any]:
    """Active and cleared totals, the alert_counts tables, and the volume of each hour.

    Each alert counts in the hour it opened. One stamped before the window or after
    its end, which a portal clock ahead of this server's produces, counts in the
    first or the last hour, so the hours add up to the window's alerts.

    Args:
        alerts: The window's alerts, active and cleared.
        start_epoch: Epoch seconds the window opens at.
        hours: Hours in the window, at least one.

    Returns:
        active, cleared, by_severity, by_device, by_datasource and hourly, oldest hour first.
    """
    volume = [0] * hours
    for alert in alerts:
        hour = (alert.get("startEpoch", 0) - start_epoch) // 3600
        volume[min(max(hour, 0), hours - 1)] += 1
    cleared = sum(1 for alert in alerts if alert.get("cleared"))
    return {
        "active": len(alerts) - cleared,
        "cleared": cleared,
        **alert_counts(alerts),
        "hourly": [
            {"start": start_epoch + i * 3600, "count": count} for i, count in enumerate(volume)
        ],
    }


def _clusters(
    alerts: list[dict],
    kind: str,
    key_of: Callable[[dict], str],
    list_devices: bool,
) -> list[dict]:
    """Group alerts by key_of and report each group of two or more, largest first."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for alert in alerts:
        groups[key_of(alert)].append(alert)

    clusters = []
    for key, members in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
        if len(members) < 2:
            continue
        epochs = [a.get("startEpoch", 0) for a in members]
        cluster: dict[str, Any] = {"type": kind, "key": key, "count": len(members)}
        if list_devices:
            cluster["devices"] = sorted({a.get("monitorObjectName", "") for a in members})
        cluster["alert_ids"] = [a.get("id") for a in members]
        cluster["first_alert_time"] = min(epochs)
        cluster["last_alert_time"] = max(epochs)
        clusters.append(cluster)
    return clusters


def cluster_by_device(alerts: list[dict]) -> list[dict]:
    """Clusters of two or more alerts on one device."""
    return _clusters(alerts, "device", lambda a: a.get("monitorObjectName", "unknown"), False)


def cluster_by_datasource(alerts: list[dict]) -> list[dict]:
    """Clusters of two or more alerts from one datasource, with the devices they hit."""
    return _clusters(alerts, "datasource", lambda a: a.get("resourceTemplateName", "unknown"), True)


def cluster_by_signature(alerts: list[dict]) -> list[dict]:
    """Clusters of two or more alerts on one condition: the datasource and its datapoint.

    The alert list carries no message text (detailMessage is null on a live read), so
    the condition that fired is the alert's signature, keyed "datasource/datapoint".
    """
    return _clusters(
        alerts,
        "signature",
        lambda a: f"{a.get('resourceTemplateName', 'unknown')}/{a.get('dataPointName', 'unknown')}",
        True,
    )


def clusters_section(alerts: list[dict]) -> dict[str, Any]:
    """Device, datasource and signature clusters, in that order, with their count."""
    clusters = cluster_by_device(alerts) + cluster_by_datasource(alerts)
    clusters += cluster_by_signature(alerts)
    return {"cluster_count": len(clusters), "clusters": clusters}


def noise_stats(alerts: list[dict]) -> dict[str, Any]:
    """Score alert noise from 0 to 100 with Shannon entropy, flaps and repeats.

    Entropy is over datasource and datapoint combinations, normalized by its maximum.
    A flap is an alert on the same device and datapoint that opens within
    FLAP_WINDOW_SECONDS after the previous one cleared; one that opens while the
    previous is still open overlaps it and is no flap. A combination with three or
    more alerts repeats. The score weighs normalized entropy 40, the flap ratio 30
    and the repeat ratio 30.

    Args:
        alerts: The window's alerts, active and cleared.

    Returns:
        The score with its parts, the ten first flap pairs, the five noisiest devices
        and datasources, recommendations, and the high_alert_noise best practice when
        the score passes 50.
    """
    if not alerts:
        return {
            "noise_score": 0,
            "entropy": 0.0,
            "total_alerts": 0,
            "flapping_alerts": [],
            "top_noisy_devices": [],
            "top_noisy_datasources": [],
            "recommendations": ["No alerts in the time window."],
        }

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
        alert_events[f"{dev}:{dp}"].append(alert)

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
            # endEpoch=0 means still active, skip for flap detection; an alert
            # that starts before the previous one cleared overlaps it, no re-fire
            if prev_end > 0 and 0 <= curr_start - prev_end < FLAP_WINDOW_SECONDS:
                flap_count += 1
                if len(flapping_alerts) < 10:
                    flapping_alerts.append(
                        {
                            "key": key,
                            "gap_seconds": curr_start - prev_end,
                            "alert_id": curr.get("id"),
                        }
                    )

    # Repeat ratio: alerts from same combo appearing 3+ times
    repeat_count = sum(1 for c in combo_counts.values() if c >= 3)
    repeat_ratio = repeat_count / len(combo_counts) if combo_counts else 0.0

    flap_ratio = flap_count / len(alerts)

    # Noise score: weighted combination (entropy 40%, flap 30%, repeat 30%)
    noise_score = min(100, int(normalized_entropy * 40 + flap_ratio * 30 + repeat_ratio * 30))

    # Top noisy devices and datasources
    top_devices = sorted(device_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_datasources = sorted(ds_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    # Recommendations
    recommendations = []
    if flap_count > 0:
        recommendations.append(
            f"{flap_count} flapping alert(s) detected. Consider adding alert delay or hysteresis."
        )
    if repeat_ratio > 0.5:
        recommendations.append(
            "High repeat ratio. Review alert thresholds and consider consolidation rules."
        )
    if noise_score > 70:
        recommendations.append(
            "Very high noise level. Review top noisy devices "
            "and datasources for tuning opportunities."
        )
    if not recommendations:
        recommendations.append("Alert noise levels are acceptable.")

    # Best practice guardrails
    from lm_mcp.resources.best_practices import get_best_practices

    if noise_score > 50:
        bp = get_best_practices("high_alert_noise").get("high_alert_noise", {})
        structured_recs = bp.get("recommended_actions", [])
        anti_patterns = bp.get("anti_patterns", [])
    else:
        structured_recs = []
        anti_patterns = []

    result: dict[str, Any] = {
        "noise_score": noise_score,
        "entropy": round(entropy, 4),
        "normalized_entropy": round(normalized_entropy, 4),
        "total_alerts": len(alerts),
        "flap_count": flap_count,
        "flapping_alerts": flapping_alerts,
        "repeat_ratio": round(repeat_ratio, 4),
        "top_noisy_devices": [{"device": d, "count": c} for d, c in top_devices],
        "top_noisy_datasources": [{"datasource": ds, "count": c} for ds, c in top_datasources],
        "recommendations": recommendations,
        "structured_recommendations": structured_recs,
    }
    if noise_score > 50:
        result["anti_patterns"] = anti_patterns
    return result


async def analyze_alerts(
    client: LogicMonitorClient,
    hours: int = DEFAULT_HOURS,
    severity: str | None = None,
    device: str | None = None,
    group_id: int | None = None,
    analyses: list[str] | None = None,
) -> list[TextContent]:
    """Analyze one alert window, active and cleared, one section per analysis.

    Args:
        client: LogicMonitor API client.
        hours: Hours the window reaches back from now (default: 24).
        severity: Only alerts of this severity (critical, error, warning, info).
        device: Only alerts on devices whose name contains this.
        group_id: Only alerts on devices in this device group.
        analyses: Sections to compute (default: all of SECTIONS).

    Returns:
        total_alerts, truncated (the 5000-alert cap cut the active or the cleared read
        short) and api_total (null when either read reported only a lower bound), with
        the requested sections.
    """
    selected = list(SECTIONS) if analyses is None else list(analyses)
    unknown = [a for a in selected if a not in SECTIONS]
    if unknown or not selected:
        named = f"Unknown analyses {unknown}" if unknown else "No analyses named"
        return validation_error(
            "INVALID_REQUEST",
            f"{named}; analyze_alerts offers {', '.join(SECTIONS)}.",
            "Name one or more of those sections, or omit analyses to run them all.",
        )
    if severity is not None and severity not in SEVERITY_MAP:
        return validation_error(
            "INVALID_REQUEST",
            f"Unknown severity {severity!r}; analyze_alerts takes {', '.join(SEVERITY_MAP)}.",
            "Pass one of those names, or omit severity for every severity.",
        )
    if hours < 1:
        return validation_error(
            "INVALID_REQUEST",
            f"hours must be at least 1, got {hours}.",
            "Pass the number of hours the window reaches back, such as 24.",
        )

    try:
        start_epoch = int(time.time()) - hours * 3600
        filter_str = await window_filter(client, start_epoch, severity, device, group_id)
        alerts, truncated, api_total = await read_cleared_and_active(client, filter_str)

        response: dict[str, Any] = {
            "hours": hours,
            "analyses": selected,
            "total_alerts": len(alerts),
            "truncated": truncated,
            "api_total": api_total,
        }
        for section in selected:
            if section == "statistics":
                response[section] = statistics_section(alerts, start_epoch, hours)
            elif section == "clusters":
                response[section] = clusters_section(alerts)
            else:
                response[section] = noise_stats(alerts)
        return format_response(response)
    except Exception as e:
        return handle_error(e)
