# Description: Metric forecasting and trend analysis tools for LogicMonitor.
# Description: Provides forecast_metric, detect_change_points, classify_trend, detect_seasonality.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error
from lm_mcp.tools.analyze_metric import seasonality_stats, trend_stats
from lm_mcp.tools.stats_helpers import (
    autocorrelation,
    cusum,
    fetch_metric_series,
    holt_winters,
    linear_regression,
    prediction_interval,
    truncation_warnings,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

logger = logging.getLogger(__name__)


async def forecast_metric(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    threshold: float,
    datapoints: str | None = None,
    hours_back: int = 168,
    method: str = "auto",
) -> list[TextContent]:
    """Forecast when a metric will breach a threshold.

    Supports linear regression and Holt-Winters (triple exponential smoothing).
    Auto mode selects between them based on data characteristics.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        threshold: Value that, if exceeded, constitutes a breach.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours_back: Hours of historical data for the regression (default: 168).
        method: Forecasting method - auto, linear, or holt_winters (default: auto).

    Returns:
        Per-datapoint forecast with slope, breach time, trend direction,
        method_used, and confidence_interval; fallback_reason says why linear
        ran when the selected method could not; warnings names any datapoint the
        page cap cut short.
    """
    try:
        series = await fetch_metric_series(
            client,
            device_id,
            device_datasource_id,
            instance_id,
            datapoints=datapoints,
            hours_back=hours_back,
        )

        forecasts = {}
        for dp_name, dp_data in series.items():
            values = dp_data["values"]
            timestamps = dp_data["timestamps"]

            if len(values) < 2:
                forecasts[dp_name] = {
                    "status": "insufficient_data",
                    "sample_count": len(values),
                }
                continue

            # Determine method to use
            method_used = _select_forecast_method(
                method,
                values,
                timestamps,
                hours_back,
            )

            # Convert timestamps to hours relative to first
            t0 = timestamps[0]
            x_hours = [(t - t0) / 3600.0 for t in timestamps]

            if method_used == "holt_winters":
                forecast_result = _forecast_holt_winters(
                    values,
                    timestamps,
                    threshold,
                    t0,
                    x_hours,
                )
            else:
                forecast_result = _forecast_linear(
                    values,
                    timestamps,
                    threshold,
                    t0,
                    x_hours,
                )

            forecasts[dp_name] = forecast_result

        response: dict[str, Any] = {
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "instance_id": instance_id,
            "hours_back": hours_back,
            "forecasts": forecasts,
        }
        warnings = truncation_warnings(series)
        if warnings:
            response["warnings"] = warnings
        return format_response(response)
    except Exception as e:
        return handle_error(e)


def _select_forecast_method(
    method: str,
    values: list[float],
    timestamps: list[int],
    hours_back: int,
) -> str:
    """Select the forecasting method based on data characteristics.

    Args:
        method: Requested method (auto, linear, holt_winters).
        values: Time series values.
        timestamps: Epoch timestamps.
        hours_back: Hours of historical data.

    Returns:
        The method to use ('linear' or 'holt_winters').
    """
    if method == "linear":
        return "linear"
    if method == "holt_winters":
        return "holt_winters"

    # Auto selection: too little history to judge seasonality stays linear
    if hours_back < 168 or len(values) < 48:
        return "linear"

    # Check autocorrelation at standard periods to detect seasonality
    if len(timestamps) >= 2:
        avg_interval = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
    else:
        avg_interval = 300

    # Check common periods: 12h, 24h
    best_ac = 0.0
    for period_hours in [12, 24]:
        lag = int(period_hours * 3600 / avg_interval) if avg_interval > 0 else 0
        if 1 <= lag < len(values) // 2:
            ac = abs(autocorrelation(values, lag=lag))
            if ac > best_ac:
                best_ac = ac

    # Require strong seasonality and enough data for 2 full seasons
    min_season_len = 12
    if best_ac > 0.5 and len(values) >= 2 * min_season_len:
        return "holt_winters"

    return "linear"


def _forecast_linear_fallback(
    values: list[float],
    timestamps: list[int],
    threshold: float,
    fallback_reason: str,
) -> dict:
    """Linear regression forecast for when the selected method cannot run."""
    t0 = timestamps[0]
    x_hours = [(t - t0) / 3600.0 for t in timestamps]
    result = _forecast_linear(values, timestamps, threshold, t0, x_hours)
    result["fallback_reason"] = fallback_reason
    return result


def _forecast_linear(
    values: list[float],
    timestamps: list[int],
    threshold: float,
    t0: int,
    x_hours: list[float],
) -> dict:
    """Perform linear regression forecast.

    Args:
        values: Time series values.
        timestamps: Epoch timestamps.
        threshold: Breach threshold.
        t0: First timestamp.
        x_hours: Hours relative to t0.

    Returns:
        Forecast result dict.
    """
    slope, intercept, r_squared = linear_regression(x_hours, values)
    current_value = values[-1]

    # Determine trend direction
    if abs(slope) < 1e-10:
        trend = "stable"
    elif slope > 0:
        trend = "increasing"
    else:
        trend = "decreasing"

    # Calculate breach time
    days_until_breach = None
    predicted_breach_epoch = None

    if slope != 0:
        hours_to_breach = (threshold - intercept) / slope
        current_hours = (timestamps[-1] - t0) / 3600.0
        remaining_hours = hours_to_breach - current_hours

        if remaining_hours > 0:
            days_until_breach = round(remaining_hours / 24.0, 2)
            predicted_breach_epoch = int(timestamps[-1] + remaining_hours * 3600)

    # Compute predicted values for confidence interval
    y_predicted = [slope * xh + intercept for xh in x_hours]
    conf_interval = prediction_interval(values, y_predicted)

    return {
        "current_value": round(current_value, 4),
        "threshold": threshold,
        "trend": trend,
        "slope_per_hour": round(slope, 6),
        "intercept": round(intercept, 4),
        "r_squared": round(r_squared, 4),
        "days_until_breach": days_until_breach,
        "predicted_breach_epoch": predicted_breach_epoch,
        "sample_count": len(values),
        "confidence_interval": conf_interval,
        "method_used": "linear",
    }


def _forecast_holt_winters(
    values: list[float],
    timestamps: list[int],
    threshold: float,
    t0: int,
    x_hours: list[float],
) -> dict:
    """Perform Holt-Winters forecast.

    Args:
        values: Time series values.
        timestamps: Epoch timestamps.
        threshold: Breach threshold.
        t0: First timestamp.
        x_hours: Hours relative to t0.

    Returns:
        Forecast result dict.
    """
    # Determine season length from data interval
    if len(timestamps) >= 2:
        avg_interval = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
    else:
        avg_interval = 300

    # Use 24h as default season; fall back to 12 points minimum
    season_length = max(12, int(86400 / avg_interval)) if avg_interval > 0 else 12

    # Ensure we have enough data for the season length
    if len(values) < 2 * season_length:
        season_length = max(4, len(values) // 2)

    try:
        hw_result = holt_winters(
            values,
            season_length=season_length,
            forecast_periods=24,
        )
    except ValueError as exc:
        logger.warning(
            "Holt-Winters forecast failed; falling back to linear regression: %s",
            exc,
            exc_info=True,
        )
        return _forecast_linear_fallback(
            values,
            timestamps,
            threshold,
            f"Holt-Winters failed: {exc}",
        )

    fitted = hw_result["fitted"]
    forecast_vals = hw_result["forecast"]
    current_value = values[-1]

    # Trend from last fitted values
    recent_slope = (fitted[-1] - fitted[0]) / max(len(fitted) - 1, 1) if len(fitted) >= 2 else 0.0

    if abs(recent_slope) < 1e-10:
        trend = "stable"
    elif recent_slope > 0:
        trend = "increasing"
    else:
        trend = "decreasing"

    # Check if forecast breaches threshold
    days_until_breach = None
    predicted_breach_epoch = None
    last_ts = timestamps[-1]

    if len(timestamps) >= 2:
        interval = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
    else:
        interval = 300

    for i, fv in enumerate(forecast_vals):
        if fv > threshold:
            hours_to_breach = (i + 1) * interval / 3600.0
            days_until_breach = round(hours_to_breach / 24.0, 2)
            predicted_breach_epoch = int(last_ts + (i + 1) * interval)
            break

    # Confidence interval from fitted vs actual
    conf_interval = prediction_interval(values, fitted)

    return {
        "current_value": round(current_value, 4),
        "threshold": threshold,
        "trend": trend,
        "slope_per_hour": round(recent_slope, 6),
        "days_until_breach": days_until_breach,
        "predicted_breach_epoch": predicted_breach_epoch,
        "sample_count": len(values),
        "season_length": season_length,
        "forecast_values": forecast_vals[:24],
        "confidence_interval": conf_interval,
        "method_used": "holt_winters",
    }


async def detect_change_points(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours_back: int = 24,
    sensitivity: float = 1.0,
) -> list[TextContent]:
    """Detect regime shifts in metric data using the CUSUM algorithm.

    Identifies points where the mean value changes significantly,
    indicating a state change in the monitored resource.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours_back: Hours of data to analyze (default: 24).
        sensitivity: Detection sensitivity (lower = more sensitive, default: 1.0).

    Returns:
        Per-datapoint list of change points with timestamps and direction;
        warnings names any datapoint the page cap cut short.
    """
    try:
        series = await fetch_metric_series(
            client,
            device_id,
            device_datasource_id,
            instance_id,
            datapoints=datapoints,
            hours_back=hours_back,
        )

        results = {}
        total_change_points = 0
        for dp_name, dp_data in series.items():
            values = dp_data["values"]
            timestamps = dp_data["timestamps"]

            raw_points = cusum(values, sensitivity=sensitivity)

            # Map indices back to timestamps
            change_points = []
            for cp in raw_points:
                idx = cp["index"]
                ts = timestamps[idx] if idx < len(timestamps) else None
                change_points.append(
                    {
                        "timestamp": ts,
                        "direction": cp["direction"],
                        "magnitude": cp["magnitude"],
                        "index": idx,
                    }
                )

            total_change_points += len(change_points)
            results[dp_name] = {
                "change_point_count": len(change_points),
                "change_points": change_points,
                "sample_count": len(values),
            }

        response: dict[str, Any] = {
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "instance_id": instance_id,
            "hours_back": hours_back,
            "sensitivity": sensitivity,
            "total_change_points": total_change_points,
            "datapoints": results,
        }
        warnings = truncation_warnings(series)
        if warnings:
            response["warnings"] = warnings
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def classify_trend(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours_back: int = 24,
) -> list[TextContent]:
    """Classify metric trends as stable, increasing, decreasing, cyclic, or volatile.

    Combines linear regression slope, coefficient of variation, and
    autocorrelation to categorize each datapoint's behavior.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours_back: Hours of data to analyze (default: 24).

    Returns:
        Per-datapoint classification with confidence and supporting metrics;
        warnings names any datapoint the page cap cut short.
    """
    try:
        series = await fetch_metric_series(
            client,
            device_id,
            device_datasource_id,
            instance_id,
            datapoints=datapoints,
            hours_back=hours_back,
        )

        classifications = {}
        for dp_name, dp_data in series.items():
            values = dp_data["values"]
            timestamps = dp_data["timestamps"]

            if len(values) < 2:
                classifications[dp_name] = {
                    "classification": "insufficient_data",
                    "confidence": 0.0,
                    "sample_count": len(values),
                }
                continue

            stats = trend_stats(values, timestamps)
            classifications[dp_name] = {
                "classification": stats["label"],
                "confidence": round(stats["confidence"], 4),
                "slope_per_hour": round(stats["slope_per_hour"], 6),
                "volatility_index": round(stats["coefficient_of_variation"], 4),
                "autocorrelation_24h": round(stats["autocorrelation_24h"], 4),
                "r_squared": round(stats["r_squared"], 4),
                "sample_count": len(values),
            }

        response: dict[str, Any] = {
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "instance_id": instance_id,
            "hours_back": hours_back,
            "classifications": classifications,
        }
        warnings = truncation_warnings(series)
        if warnings:
            response["warnings"] = warnings
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def detect_seasonality(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours_back: int = 168,
) -> list[TextContent]:
    """Detect periodic patterns in metric data using autocorrelation.

    Computes autocorrelation at standard period lags (1h, 4h, 12h, 24h, 168h)
    to identify seasonal patterns. Also bins values by hour-of-day to find
    peak activity hours.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours_back: Hours of data to analyze (default: 168 = 1 week).

    Returns:
        Per-datapoint seasonality analysis with dominant period and peak hours;
        warnings names any datapoint the page cap cut short.
    """
    try:
        series = await fetch_metric_series(
            client,
            device_id,
            device_datasource_id,
            instance_id,
            datapoints=datapoints,
            hours_back=hours_back,
        )

        results = {}
        for dp_name, dp_data in series.items():
            values = dp_data["values"]
            timestamps = dp_data["timestamps"]

            if len(values) < 4:
                results[dp_name] = {
                    "is_seasonal": False,
                    "status": "insufficient_data",
                    "sample_count": len(values),
                }
                continue

            stats = seasonality_stats(values, timestamps)
            results[dp_name] = {
                "is_seasonal": stats["is_seasonal"],
                "dominant_period": stats["dominant_period"],
                "max_autocorrelation": stats["max_autocorrelation"],
                "correlations": stats["autocorrelation"],
                "peak_hours": stats["peak_hours_utc"],
                "sample_count": len(values),
            }

        response: dict[str, Any] = {
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "instance_id": instance_id,
            "hours_back": hours_back,
            "seasonality": results,
        }
        warnings = truncation_warnings(series)
        if warnings:
            response["warnings"] = warnings
        return format_response(response)
    except Exception as e:
        return handle_error(e)
