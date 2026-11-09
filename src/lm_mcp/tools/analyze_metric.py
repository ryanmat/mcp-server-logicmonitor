# Description: analyze_metric reads one device instance's series once and analyzes it by section.
# Description: Holds the series math that classify_trend and the other per-series tools share.

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, validation_error
from lm_mcp.tools.stats_helpers import (
    autocorrelation,
    coefficient_of_variation,
    detrend,
    fetch_metric_series,
    iqr_anomalies,
    linear_regression,
    mad_anomalies,
    theil_sen_slope,
    truncation_warnings,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# The sections analyze_metric offers, in the order it reports them.
SECTIONS = ("summary", "trend", "seasonality", "anomalies")

DEFAULT_HOURS = 168

# Seasonality tests these periods where the lag fits inside half the series.
SEASONAL_PERIOD_HOURS = (1, 4, 12, 24, 168)

# Anomaly fences: |z| above 3, outside 1.5 IQR of the quartiles, |modified z| above 3.5.
ZSCORE_THRESHOLD = 3.0
IQR_MULTIPLIER = 1.5
MAD_THRESHOLD = 3.5

# Each anomaly method lists at most this many hits, its most extreme, oldest first.
MAX_ANOMALY_HITS = 20


def _x_hours(timestamps: list[int]) -> list[float]:
    t0 = timestamps[0] if timestamps else 0
    return [(t - t0) / 3600.0 for t in timestamps]


def _avg_interval(timestamps: list[int]) -> float:
    """Average seconds between samples, 300 when there are fewer than two."""
    if len(timestamps) >= 2:
        return (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
    return 300


def summary_stats(values: list[float]) -> dict[str, float]:
    """Latest, mean, sample standard deviation, min, max and the latest sample's z-score.

    Args:
        values: At least two samples, oldest first.

    Returns:
        Unrounded figures; z_score is signed and 0.0 when the series is flat.
    """
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    stddev = math.sqrt(variance) if variance > 0 else 0.0
    latest = values[-1]
    z_score = (latest - mean) / stddev if stddev > 0 else 0.0
    return {
        "latest": latest,
        "mean": mean,
        "stddev": stddev,
        "min": min(values),
        "max": max(values),
        "z_score": z_score,
    }


def trend_stats(values: list[float], timestamps: list[int]) -> dict[str, Any]:
    """Slope per hour, r-squared, coefficient of variation, 24-hour autocorrelation and label.

    The label is volatile when the coefficient of variation exceeds 0.5, else cyclic
    when the detrended 24-hour autocorrelation exceeds 0.7 in magnitude, else
    increasing or decreasing when r-squared exceeds 0.5, else stable.

    Args:
        values: At least two samples, oldest first.
        timestamps: Epoch seconds of the samples; slopes are per hour of these.

    Returns:
        Unrounded figures with the label and its confidence.
    """
    cv = coefficient_of_variation(values)

    x_hours = _x_hours(timestamps)
    slope, _intercept, r_squared = linear_regression(x_hours, values)

    # Autocorrelation at the lag that spans 24 hours of the average sample interval
    avg_interval = _avg_interval(timestamps)
    lag_24h = max(1, int(86400 / avg_interval)) if avg_interval > 0 else 1
    autocorr = autocorrelation(detrend(x_hours, values), lag=lag_24h)

    if cv > 0.5:
        label = "volatile"
        confidence = min(1.0, cv)
    elif abs(autocorr) > 0.7:
        label = "cyclic"
        confidence = abs(autocorr)
    elif r_squared > 0.5 and slope > 0:
        label = "increasing"
        confidence = r_squared
    elif r_squared > 0.5 and slope < 0:
        label = "decreasing"
        confidence = r_squared
    else:
        label = "stable"
        confidence = max(0.0, 1.0 - cv)

    return {
        "slope_per_hour": slope,
        "theil_sen_slope_per_hour": theil_sen_slope(x_hours, values),
        "r_squared": r_squared,
        "coefficient_of_variation": cv,
        "autocorrelation_24h": autocorr,
        "label": label,
        "confidence": confidence,
    }


def seasonality_stats(values: list[float], timestamps: list[int]) -> dict[str, Any]:
    """Detrended autocorrelation at each standard period, the dominant one, and peak UTC hours.

    A period is tested where its lag fits inside half the series. The dominant period
    is the one with the highest autocorrelation, seasonal above 0.5. Peak hours are the
    UTC hours of day whose mean exceeds the series mean.

    Args:
        values: At least two samples, oldest first.
        timestamps: Epoch seconds of the samples.

    Returns:
        The autocorrelation table keyed "1h" to "168h" (rounded to 4 places),
        dominant_period (None when no lag fits), max_autocorrelation, is_seasonal and
        peak_hours_utc.
    """
    avg_interval = _avg_interval(timestamps)
    residuals = detrend(_x_hours(timestamps), values)

    correlations: dict[str, float] = {}
    for hours in SEASONAL_PERIOD_HOURS:
        lag = int(hours * 3600 / avg_interval) if avg_interval > 0 else 0
        if lag < 1 or lag >= len(values) // 2:
            continue
        correlations[f"{hours}h"] = round(autocorrelation(residuals, lag=lag), 4)

    if correlations:
        dominant_period: str | None = max(correlations, key=lambda k: correlations[k])
        max_autocorr = correlations[dominant_period]
    else:
        dominant_period = None
        max_autocorr = 0.0

    hourly_bins: dict[int, list[float]] = {}
    for val, ts in zip(values, timestamps, strict=True):
        hourly_bins.setdefault((ts % 86400) // 3600, []).append(val)
    overall_mean = sum(values) / len(values)
    peak_hours = sorted(h for h, v in hourly_bins.items() if sum(v) / len(v) > overall_mean)

    return {
        "autocorrelation": correlations,
        "dominant_period": dominant_period,
        "max_autocorrelation": max_autocorr,
        "is_seasonal": max_autocorr > 0.5,
        "peak_hours_utc": peak_hours,
    }


def _summary_section(values: list[float], timestamps: list[int]) -> dict[str, Any]:
    return {k: round(v, 4) for k, v in summary_stats(values).items()}


def _trend_section(values: list[float], timestamps: list[int]) -> dict[str, Any]:
    stats = trend_stats(values, timestamps)
    return {
        "slope_per_hour": round(stats["slope_per_hour"], 6),
        "theil_sen_slope_per_hour": round(stats["theil_sen_slope_per_hour"], 6),
        "r_squared": round(stats["r_squared"], 4),
        "coefficient_of_variation": round(stats["coefficient_of_variation"], 4),
        "autocorrelation_24h": round(stats["autocorrelation_24h"], 4),
        "label": stats["label"],
        "confidence": round(stats["confidence"], 4),
    }


def _seasonality_section(values: list[float], timestamps: list[int]) -> dict[str, Any]:
    return seasonality_stats(values, timestamps)


def _keep_extreme(scored: list[tuple[float, dict[str, Any]]]) -> list[dict[str, Any]]:
    """The MAX_ANOMALY_HITS hits with the highest score, oldest first."""
    top = sorted(scored, key=lambda pair: pair[0], reverse=True)[:MAX_ANOMALY_HITS]
    return [hit for _, hit in sorted(top, key=lambda pair: pair[1]["timestamp"])]


def _anomalies_section(values: list[float], timestamps: list[int]) -> dict[str, Any]:
    stats = summary_stats(values)
    z_scored = []
    if stats["stddev"] > 0:
        for v, t in zip(values, timestamps, strict=True):
            z = (v - stats["mean"]) / stats["stddev"]
            if abs(z) > ZSCORE_THRESHOLD:
                z_scored.append(
                    (abs(z), {"timestamp": t, "value": round(v, 4), "score": round(z, 4)})
                )

    iqr = iqr_anomalies(values, multiplier=IQR_MULTIPLIER)
    iqr_scored = [
        (
            max(iqr["lower_fence"] - values[i], values[i] - iqr["upper_fence"]),
            {"timestamp": timestamps[i], "value": round(values[i], 4)},
        )
        for i in iqr["anomaly_indices"]
    ]

    mad = mad_anomalies(values, threshold=MAD_THRESHOLD)
    mad_scored = [
        (
            abs(mad["modified_z_scores"][i]),
            {
                "timestamp": timestamps[i],
                "value": round(values[i], 4),
                "score": mad["modified_z_scores"][i],
            },
        )
        for i in mad["anomaly_indices"]
    ]

    return {
        "zscore": {
            "threshold": ZSCORE_THRESHOLD,
            "count": len(z_scored),
            "hits": _keep_extreme(z_scored),
        },
        "iqr": {
            "multiplier": IQR_MULTIPLIER,
            "lower_fence": iqr["lower_fence"],
            "upper_fence": iqr["upper_fence"],
            "count": len(iqr_scored),
            "hits": _keep_extreme(iqr_scored),
        },
        "mad": {
            "threshold": MAD_THRESHOLD,
            "median": mad["median"],
            "mad": mad["mad"],
            "count": len(mad_scored),
            "hits": _keep_extreme(mad_scored),
        },
    }


_SECTION_BUILDERS = {
    "summary": _summary_section,
    "trend": _trend_section,
    "seasonality": _seasonality_section,
    "anomalies": _anomalies_section,
}


async def _fetch_series(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None,
    hours: int,
) -> dict[str, dict[str, Any]]:
    """The one paged read of the window that every section is computed from."""
    return await fetch_metric_series(
        client,
        device_id,
        device_datasource_id,
        instance_id,
        datapoints=datapoints,
        hours_back=hours,
    )


async def analyze_metric(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours: int = DEFAULT_HOURS,
    analyses: list[str] | None = None,
) -> list[TextContent]:
    """Analyze each datapoint of one device instance's series, one section per analysis.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours: Hours of history to read (default: 168).
        analyses: Sections to compute (default: all of SECTIONS).

    Returns:
        Per-datapoint sample count, truncated flag and the requested sections;
        warnings names any datapoint the page cap cut short.
    """
    selected = list(SECTIONS) if analyses is None else list(analyses)
    unknown = [a for a in selected if a not in SECTIONS]
    if unknown or not selected:
        named = f"Unknown analyses {unknown}" if unknown else "No analyses named"
        return validation_error(
            "INVALID_REQUEST",
            f"{named}; analyze_metric offers {', '.join(SECTIONS)}.",
            "Name one or more of those sections, or omit analyses to run them all.",
        )

    try:
        series = await _fetch_series(
            client, device_id, device_datasource_id, instance_id, datapoints, hours
        )

        results: dict[str, Any] = {}
        for dp_name, dp_data in series.items():
            values = dp_data["values"]
            timestamps = dp_data["timestamps"]
            entry: dict[str, Any] = {
                "sample_count": len(values),
                "truncated": dp_data["truncated"],
            }
            for section in selected:
                if len(values) < 2:
                    entry[section] = {"status": "insufficient_data"}
                else:
                    entry[section] = _SECTION_BUILDERS[section](values, timestamps)
            results[dp_name] = entry

        response: dict[str, Any] = {
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "instance_id": instance_id,
            "hours": hours,
            "analyses": selected,
            "datapoints": results,
        }
        warnings = truncation_warnings(series)
        if warnings:
            response["warnings"] = warnings
        return format_response(response)
    except Exception as e:
        return handle_error(e)
