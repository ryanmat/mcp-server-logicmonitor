# Description: analyze_metric reads one device instance's series once and analyzes it by section.
# Description: Holds the series math the per-series tools share until they leave the registry.

from __future__ import annotations

import math
import statistics
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, validation_error
from lm_mcp.tools.stats_helpers import (
    autocorrelation,
    coefficient_of_variation,
    detrend,
    fetch_metric_series,
    holt_winters,
    iqr_anomalies,
    linear_regression,
    mad_anomalies,
    remove_daily_cycle,
    theil_sen_slope,
    truncation_warnings,
    window_shifts,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# The sections analyze_metric offers, in the order it reports them.
SECTIONS = ("summary", "trend", "seasonality", "change_points", "anomalies", "forecast", "baseline")

DEFAULT_HOURS = 168

# Seasonality tests these periods where the lag fits inside half the series.
SEASONAL_PERIOD_HOURS = (1, 4, 12, 24, 168)

# Samples on each side of the change-point section's window comparison.
CHANGE_POINT_WINDOW = 30

# Anomaly fences: |z| above 3, outside 1.5 IQR of the quartiles, |modified z| above 3.5.
ZSCORE_THRESHOLD = 3.0
IQR_MULTIPLIER = 1.5
MAD_THRESHOLD = 3.5

# Each anomaly method lists at most this many hits, its most extreme, oldest first.
MAX_ANOMALY_HITS = 20

# The forecast projects this far past the latest sample, or to the threshold first.
FORECAST_HORIZON_DAYS = 30


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


def change_point_stats(values: list[float], timestamps: list[int]) -> dict[str, Any]:
    """Level shifts: where the mean of the next 30 samples leaves the mean of the previous 30.

    The series is read as it is and, with three days or more of samples, less its daily
    profile; whichever leaves the smaller noise scale is analyzed. Changes found in the
    series less its profile are found again with the profile rebuilt without the day
    around each; when no day is clear enough to rebuild it, the cycle cannot be told
    from the changes and the series is analyzed as it is. A change in the last 30
    samples has no window after it and is not reported.

    Args:
        values: At least two samples, oldest first.
        timestamps: Epoch seconds of the samples.

    Returns:
        window, deseasonalized, and points: each with timestamp, direction, and the
        mean level of the window before and after it, with the daily cycle removed
        when it was.
    """
    series = values
    found, scale = window_shifts(values, CHANGE_POINT_WINDOW)
    deseasonalized = False
    seasonal, has_profile = remove_daily_cycle(values, timestamps)
    if has_profile:
        seasonal_found, seasonal_scale = window_shifts(seasonal, CHANGE_POINT_WINDOW)
        if seasonal_scale < scale:
            if not seasonal_found:
                series, found, deseasonalized = seasonal, seasonal_found, True
            else:
                # A change bends the 24-hour level of the samples around it; rebuild the
                # daily profile without them so the bend does not repeat on other days.
                changes = [timestamps[p["index"]] for p in seasonal_found]
                rebuilt, rebuilt_ok = remove_daily_cycle(values, timestamps, exclude_near=changes)
                if rebuilt_ok:
                    series, deseasonalized = rebuilt, True
                    found, _ = window_shifts(rebuilt, CHANGE_POINT_WINDOW)
    points = []
    for p in found:
        onset = p["index"]
        before = series[onset - CHANGE_POINT_WINDOW : onset]
        after = series[onset : onset + CHANGE_POINT_WINDOW]
        points.append(
            {
                "timestamp": timestamps[onset],
                "direction": p["direction"],
                "before": sum(before) / len(before),
                "after": sum(after) / len(after),
            }
        )
    return {
        "window": CHANGE_POINT_WINDOW,
        "deseasonalized": deseasonalized,
        "points": points,
    }


def _change_points_section(values: list[float], timestamps: list[int]) -> dict[str, Any]:
    stats = change_point_stats(values, timestamps)
    stats["points"] = [
        {**p, "before": round(p["before"], 4), "after": round(p["after"], 4)}
        for p in stats["points"]
    ]
    return stats


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


def _no_crossing(reason: str) -> dict[str, Any]:
    return {"breach_eta": None, "hours_until_breach": None, "direction": None, "reason": reason}


def linear_forecast(
    values: list[float], timestamps: list[int], threshold: float | None
) -> dict[str, Any]:
    """The least-squares line per hour and when it crosses the threshold, within 30 days.

    Args:
        values: At least two samples, oldest first.
        timestamps: Epoch seconds of the samples.
        threshold: The level to reach, or None.

    Returns:
        slope_per_hour, r_squared and the crossing (breach_eta in epoch seconds,
        hours_until_breach, direction), or a reason in place of the crossing.
    """
    x_hours = _x_hours(timestamps)
    slope, intercept, r_squared = linear_regression(x_hours, values)
    out: dict[str, Any] = {"slope_per_hour": round(slope, 6), "r_squared": round(r_squared, 4)}
    if threshold is None:
        return {**out, **_no_crossing("no threshold given")}
    if abs(slope) < 1e-12:
        return {**out, **_no_crossing("flat: the fitted line never reaches the threshold")}
    hours_ahead = (threshold - intercept) / slope - x_hours[-1]
    if hours_ahead <= 0:
        return {
            **out,
            **_no_crossing("the fitted line crossed the threshold before the window ended"),
        }
    if hours_ahead > FORECAST_HORIZON_DAYS * 24:
        return {
            **out,
            **_no_crossing(
                f"the fitted line does not reach the threshold within {FORECAST_HORIZON_DAYS} days"
            ),
        }
    return {
        **out,
        "breach_eta": round(timestamps[-1] + hours_ahead * 3600),
        "hours_until_breach": round(hours_ahead, 4),
        "direction": "rising" if slope > 0 else "falling",
    }


def holt_winters_forecast(
    values: list[float], timestamps: list[int], threshold: float | None
) -> dict[str, Any]:
    """Holt-Winters with a daily season, projected to the threshold or the 30-day cap.

    The season is a day of samples at the average interval, and the fit needs two of
    them. The projection is scanned step by step to the first value on the far side
    of the threshold from the latest sample.

    Args:
        values: At least two samples, oldest first.
        timestamps: Epoch seconds of the samples.
        threshold: The level to reach, or None.

    Returns:
        season_length, slope_per_hour (the fit's final smoothed trend) and the
        crossing, or a reason in place of the crossing.
    """
    interval = _avg_interval(timestamps)
    season = round(86400 / interval) if interval > 0 else 0
    out: dict[str, Any] = {"season_length": season, "slope_per_hour": None}
    if season < 2 or len(values) < 2 * season:
        return {
            **out,
            **_no_crossing("Holt-Winters needs two days of samples to fit a daily season"),
        }
    horizon = math.ceil(FORECAST_HORIZON_DAYS * 86400 / interval)
    fit = holt_winters(values, season_length=season, forecast_periods=horizon)
    out["slope_per_hour"] = round(fit["trend"] * 3600 / interval, 6)
    if threshold is None:
        return {**out, **_no_crossing("no threshold given")}
    latest = values[-1]
    for step, projected in enumerate(fit["forecast"], start=1):
        rising = latest < threshold <= projected
        falling = latest > threshold >= projected
        if rising or falling:
            hours_ahead = step * interval / 3600
            return {
                **out,
                "breach_eta": round(timestamps[-1] + step * interval),
                "hours_until_breach": round(hours_ahead, 4),
                "direction": "rising" if rising else "falling",
            }
    return {
        **out,
        **_no_crossing(
            f"the forecast does not reach the threshold within {FORECAST_HORIZON_DAYS} days"
        ),
    }


def _forecast_section(
    values: list[float], timestamps: list[int], threshold: float | None
) -> dict[str, Any]:
    return {
        "threshold": threshold,
        "horizon_days": FORECAST_HORIZON_DAYS,
        "linear": linear_forecast(values, timestamps, threshold),
        "holt_winters": holt_winters_forecast(values, timestamps, threshold),
    }


def _window_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean": None, "stddev": None, "min": None, "max": None, "sample_count": 0}
    return {
        "mean": round(statistics.mean(values), 4),
        "stddev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "sample_count": len(values),
    }


def baseline_comparison(current: list[float], baseline: list[float]) -> dict[str, Any]:
    """The window against an earlier one: both windows' statistics and the mean's deviation.

    Within 20 percent of the baseline mean is normal, within 50 percent elevated or
    reduced, past 50 percent anomalous. Against a baseline mean of 0 there is no
    percentage, and any nonzero mean is anomalous.

    Args:
        current: The window's samples.
        baseline: The earlier window's samples.

    Returns:
        baseline and current statistics, deviation_percent and status.
    """
    base = _window_stats(baseline)
    now = _window_stats(current)
    out: dict[str, Any] = {"baseline": base, "current": now}
    if base["mean"] is None or now["mean"] is None:
        return {**out, "deviation_percent": None, "status": "no_data"}
    base_mean = statistics.mean(baseline)
    now_mean = statistics.mean(current)
    if base_mean == 0:
        return {
            **out,
            "deviation_percent": None,
            "status": "normal" if now_mean == 0 else "anomalous",
        }
    deviation = abs((now_mean - base_mean) / base_mean) * 100
    if deviation <= 20:
        status = "normal"
    elif deviation <= 50:
        status = "elevated" if now_mean > base_mean else "reduced"
    else:
        status = "anomalous"
    return {**out, "deviation_percent": round(deviation, 2), "status": status}


_SECTION_BUILDERS = {
    "summary": _summary_section,
    "trend": _trend_section,
    "seasonality": _seasonality_section,
    "change_points": _change_points_section,
    "anomalies": _anomalies_section,
}


async def _fetch_series(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None,
    hours: int,
    end_hours_ago: int = 0,
) -> dict[str, dict[str, Any]]:
    """One paged read: the window every section is computed from, or the baseline's."""
    return await fetch_metric_series(
        client,
        device_id,
        device_datasource_id,
        instance_id,
        datapoints=datapoints,
        hours_back=hours,
        end_hours_ago=end_hours_ago,
    )


async def analyze_metric(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours: int = DEFAULT_HOURS,
    analyses: list[str] | None = None,
    threshold: float | None = None,
    baseline_hours_ago: int | None = None,
) -> list[TextContent]:
    """Analyze each datapoint of one device instance's series, one section per analysis.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours: Hours of history to read (default: 168).
        analyses: Sections to compute (default: all of SECTIONS, the baseline only when
            baseline_hours_ago is given).
        threshold: Level the forecast reports the crossing of.
        baseline_hours_ago: Hours before now the baseline window ends; it is as long
            as the analyzed window and read with one more paged read.

    Returns:
        Per-datapoint sample count, truncated flag and the requested sections;
        warnings names any datapoint the page cap cut short.
    """
    if analyses is None:
        selected = [s for s in SECTIONS if s != "baseline" or baseline_hours_ago is not None]
    else:
        selected = list(analyses)
    unknown = [a for a in selected if a not in SECTIONS]
    if unknown or not selected:
        named = f"Unknown analyses {unknown}" if unknown else "No analyses named"
        return validation_error(
            "INVALID_REQUEST",
            f"{named}; analyze_metric offers {', '.join(SECTIONS)}.",
            "Name one or more of those sections, or omit analyses to run them all.",
        )
    if "baseline" in selected and baseline_hours_ago is None:
        return validation_error(
            "INVALID_REQUEST",
            "The baseline section compares against an earlier window; name it with "
            "baseline_hours_ago.",
            "Pass baseline_hours_ago, such as 168 for the same window a week earlier.",
        )

    try:
        series = await _fetch_series(
            client, device_id, device_datasource_id, instance_id, datapoints, hours
        )
        baseline_series: dict[str, dict[str, Any]] = {}
        if "baseline" in selected and baseline_hours_ago is not None:
            baseline_series = await _fetch_series(
                client,
                device_id,
                device_datasource_id,
                instance_id,
                datapoints,
                hours,
                end_hours_ago=baseline_hours_ago,
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
                elif section == "forecast":
                    entry[section] = _forecast_section(values, timestamps, threshold)
                elif section == "baseline":
                    earlier = baseline_series.get(dp_name, {}).get("values", [])
                    entry[section] = baseline_comparison(values, earlier)
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
        if baseline_hours_ago is not None and "baseline" in selected:
            response["baseline_hours_ago"] = baseline_hours_ago
        warnings = truncation_warnings(series) + truncation_warnings(
            {f"{name} (baseline)": data for name, data in baseline_series.items()}
        )
        if warnings:
            response["warnings"] = warnings
        return format_response(response)
    except Exception as e:
        return handle_error(e)
