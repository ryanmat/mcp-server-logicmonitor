# Description: Shared statistical utility functions for ML analysis tools.
# Description: Provides linear regression, correlation, CUSUM, entropy, and metric fetching.

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def linear_regression(
    x: list[float], y: list[float]
) -> tuple[float, float, float]:
    """Compute simple linear regression (ordinary least squares).

    Args:
        x: Independent variable values.
        y: Dependent variable values.

    Returns:
        Tuple of (slope, intercept, r_squared).

    Raises:
        ValueError: If x and y have different lengths or fewer than 2 points.
    """
    n = len(x)
    if n != len(y):
        raise ValueError("x and y must have the same length")
    if n < 2:
        raise ValueError("At least 2 data points required for regression")

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        # All x values are identical; slope is undefined
        return 0.0, sum_y / n, 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # R-squared: coefficient of determination
    y_mean = sum_y / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))

    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

    return slope, intercept, r_squared


def pearson_correlation(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient between two series.

    Args:
        x: First series of values.
        y: Second series of values.

    Returns:
        Pearson r in [-1, 1]. Returns 0.0 if either series has zero variance.

    Raises:
        ValueError: If x and y have different lengths or fewer than 2 points.
    """
    n = len(x)
    if n != len(y):
        raise ValueError("x and y must have the same length")
    if n < 2:
        raise ValueError("At least 2 data points required for correlation")

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return 0.0

    return cov / denom


def autocorrelation(values: list[float], lag: int) -> float:
    """Compute autocorrelation of a series at a given lag.

    Args:
        values: Time series values.
        lag: The lag (number of steps) to compute autocorrelation for.

    Returns:
        Autocorrelation coefficient in [-1, 1]. Returns 0.0 if variance is
        zero or insufficient data for the given lag.
    """
    n = len(values)
    if lag <= 0 or lag >= n or n < 2:
        return 0.0

    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    if variance == 0:
        return 0.0

    cov = sum(
        (values[i] - mean) * (values[i + lag] - mean)
        for i in range(n - lag)
    ) / (n - lag)

    return cov / variance


def cusum(
    values: list[float],
    target: float | None = None,
    sensitivity: float = 1.0,
) -> list[dict]:
    """Detect change points using the CUSUM (Cumulative Sum) algorithm.

    Args:
        values: Time series values.
        target: Expected mean (uses series mean if None).
        sensitivity: Multiplier for the detection threshold. Lower values
            detect smaller shifts; higher values detect only large shifts.

    Returns:
        List of change point dicts with index, direction, and magnitude.
    """
    if len(values) < 4:
        return []

    if target is None:
        target = sum(values) / len(values)

    # Estimate standard deviation for threshold
    variance = sum((v - target) ** 2 for v in values) / len(values)
    stddev = math.sqrt(variance) if variance > 0 else 0.0
    if stddev == 0:
        return []

    threshold = sensitivity * stddev * 2.0

    s_pos = 0.0
    s_neg = 0.0
    change_points = []

    for i, value in enumerate(values):
        deviation = value - target
        s_pos = max(0.0, s_pos + deviation - stddev * 0.5)
        s_neg = max(0.0, s_neg - deviation - stddev * 0.5)

        if s_pos > threshold:
            change_points.append({
                "index": i,
                "direction": "increase",
                "magnitude": round(s_pos, 4),
            })
            s_pos = 0.0

        if s_neg > threshold:
            change_points.append({
                "index": i,
                "direction": "decrease",
                "magnitude": round(s_neg, 4),
            })
            s_neg = 0.0

    return change_points


def shannon_entropy(probabilities: list[float]) -> float:
    """Compute Shannon entropy of a probability distribution.

    Args:
        probabilities: List of probabilities (should sum to ~1.0).

    Returns:
        Entropy value in bits. Returns 0.0 for empty or single-event
        distributions.
    """
    if not probabilities or len(probabilities) <= 1:
        return 0.0

    entropy = 0.0
    for p in probabilities:
        if p > 0:
            entropy -= p * math.log2(p)

    return entropy


def coefficient_of_variation(values: list[float]) -> float:
    """Compute the coefficient of variation (stddev / mean).

    Args:
        values: List of numeric values.

    Returns:
        CV as a ratio. Returns 0.0 if mean is zero or fewer than 2 values.
    """
    if len(values) < 2:
        return 0.0

    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0

    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    stddev = math.sqrt(variance)

    return abs(stddev / mean)


def holt_winters(
    values: list[float],
    season_length: int,
    alpha: float = 0.3,
    beta: float = 0.1,
    gamma: float = 0.3,
    forecast_periods: int = 24,
) -> dict:
    """Triple exponential smoothing with additive seasonality.

    Args:
        values: Time series values.
        season_length: Number of data points per seasonal cycle.
        alpha: Level smoothing parameter (0 < alpha < 1).
        beta: Trend smoothing parameter (0 < beta < 1).
        gamma: Seasonal smoothing parameter (0 < gamma < 1).
        forecast_periods: Number of future periods to forecast.

    Returns:
        Dict with fitted, forecast, and residuals lists.

    Raises:
        ValueError: If insufficient data for the season length.
    """
    n = len(values)
    if n < 2 * season_length:
        raise ValueError(
            f"Need at least {2 * season_length} data points for "
            f"season_length={season_length}, got {n}"
        )

    # Initialize level and trend from first two seasons
    level = sum(values[:season_length]) / season_length
    trend = sum(
        values[season_length + i] - values[i] for i in range(season_length)
    ) / (season_length * season_length)

    # Initialize seasonal components from first season
    seasonals = [values[i] - level for i in range(season_length)]

    fitted = []
    for i in range(n):
        s_idx = i % season_length
        if i == 0:
            fitted.append(level + trend + seasonals[s_idx])
            continue

        val = values[i]
        prev_level = level
        level = alpha * (val - seasonals[s_idx]) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        seasonals[s_idx] = gamma * (val - level) + (1 - gamma) * seasonals[s_idx]
        fitted.append(level + trend + seasonals[s_idx])

    # Forecast future periods
    forecast = []
    for j in range(1, forecast_periods + 1):
        s_idx = (n + j - 1) % season_length
        forecast.append(round(level + j * trend + seasonals[s_idx], 6))

    residuals = [round(values[i] - fitted[i], 6) for i in range(n)]
    fitted = [round(f, 6) for f in fitted]

    return {"fitted": fitted, "forecast": forecast, "residuals": residuals}


def prediction_interval(
    y_values: list[float],
    y_predicted: list[float],
    confidence: float = 0.95,
) -> dict:
    """Compute prediction interval from actual and predicted values.

    Uses residual standard error with a t-distribution lookup table
    for common confidence levels.

    Args:
        y_values: Actual observed values.
        y_predicted: Predicted (fitted) values.
        confidence: Confidence level (default: 0.95).

    Returns:
        Dict with lower, upper bounds, confidence_level, and data_quality.
    """
    n = len(y_values)
    if n != len(y_predicted):
        raise ValueError("y_values and y_predicted must have the same length")
    if n < 2:
        return {
            "lower": 0.0,
            "upper": 0.0,
            "confidence_level": confidence,
            "data_quality": "insufficient",
        }

    residuals = [y_values[i] - y_predicted[i] for i in range(n)]
    sse = sum(r * r for r in residuals)
    rse = math.sqrt(sse / (n - 2)) if n > 2 else math.sqrt(sse / n)

    # t-distribution critical values (two-tailed)
    # Approximate for common confidence levels and moderate df
    t_table: dict[float, dict[int, float]] = {
        0.90: {5: 2.015, 10: 1.812, 20: 1.725, 30: 1.697, 50: 1.676, 100: 1.660},
        0.95: {5: 2.571, 10: 2.228, 20: 2.086, 30: 2.042, 50: 2.009, 100: 1.984},
        0.99: {5: 4.032, 10: 3.169, 20: 2.845, 30: 2.750, 50: 2.678, 100: 2.626},
    }

    # Find closest confidence level
    closest_conf = min(t_table.keys(), key=lambda c: abs(c - confidence))
    df_table = t_table[closest_conf]

    # Find closest degrees of freedom
    df = max(1, n - 2)
    closest_df = min(df_table.keys(), key=lambda d: abs(d - df))
    t_crit = df_table[closest_df]

    margin = t_crit * rse
    last_predicted = y_predicted[-1] if y_predicted else 0.0

    # Data quality assessment
    if n < 10:
        data_quality = "insufficient"
    elif n < 50:
        data_quality = "limited"
    else:
        data_quality = "good"

    return {
        "lower": round(last_predicted - margin, 4),
        "upper": round(last_predicted + margin, 4),
        "confidence_level": confidence,
        "data_quality": data_quality,
    }


def iqr_anomalies(values: list[float], multiplier: float = 1.5) -> dict:
    """Detect anomalies using the Interquartile Range method.

    Args:
        values: List of numeric values.
        multiplier: IQR multiplier for fence calculation (default: 1.5).

    Returns:
        Dict with q1, q3, iqr, fences, and anomaly_indices.
    """
    if len(values) < 4:
        return {
            "q1": 0.0,
            "q3": 0.0,
            "iqr": 0.0,
            "lower_fence": 0.0,
            "upper_fence": 0.0,
            "anomaly_indices": [],
        }

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    # Q1 and Q3 via linear interpolation
    q1_pos = 0.25 * (n - 1)
    q3_pos = 0.75 * (n - 1)

    q1_low = int(q1_pos)
    q1_frac = q1_pos - q1_low
    q1 = sorted_vals[q1_low] + q1_frac * (
        sorted_vals[min(q1_low + 1, n - 1)] - sorted_vals[q1_low]
    )

    q3_low = int(q3_pos)
    q3_frac = q3_pos - q3_low
    q3 = sorted_vals[q3_low] + q3_frac * (
        sorted_vals[min(q3_low + 1, n - 1)] - sorted_vals[q3_low]
    )

    iqr = q3 - q1
    lower_fence = q1 - multiplier * iqr
    upper_fence = q3 + multiplier * iqr

    anomaly_indices = [
        i for i, v in enumerate(values) if v < lower_fence or v > upper_fence
    ]

    return {
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "iqr": round(iqr, 4),
        "lower_fence": round(lower_fence, 4),
        "upper_fence": round(upper_fence, 4),
        "anomaly_indices": anomaly_indices,
    }


def mad_anomalies(values: list[float], threshold: float = 3.0) -> dict:
    """Detect anomalies using Median Absolute Deviation.

    Args:
        values: List of numeric values.
        threshold: Modified z-score threshold for anomaly detection.

    Returns:
        Dict with median, mad, anomaly_indices, and modified_z_scores.
    """
    if len(values) < 3:
        return {
            "median": 0.0,
            "mad": 0.0,
            "anomaly_indices": [],
            "modified_z_scores": [],
        }

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 1:
        median = sorted_vals[n // 2]
    else:
        median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2

    abs_devs = sorted(abs(v - median) for v in values)
    n_devs = len(abs_devs)
    if n_devs % 2 == 1:
        mad = abs_devs[n_devs // 2]
    else:
        mad = (abs_devs[n_devs // 2 - 1] + abs_devs[n_devs // 2]) / 2

    if mad == 0:
        return {
            "median": round(median, 4),
            "mad": 0.0,
            "anomaly_indices": [],
            "modified_z_scores": [0.0] * len(values),
        }

    # Modified z-score: 0.6745 * (x - median) / MAD
    modified_z_scores = [round(0.6745 * (v - median) / mad, 4) for v in values]
    anomaly_indices = [
        i for i, z in enumerate(modified_z_scores) if abs(z) > threshold
    ]

    return {
        "median": round(median, 4),
        "mad": round(mad, 4),
        "anomaly_indices": anomaly_indices,
        "modified_z_scores": modified_z_scores,
    }


async def fetch_metric_series(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours_back: int = 24,
) -> dict[str, dict[str, Any]]:
    """Fetch metric data from LM API and transpose to per-datapoint series.

    Consolidates the common pattern of fetching from the device data endpoint,
    transposing the list-of-lists response to per-datapoint columns, filtering
    "No Data" sentinels, and converting millisecond timestamps.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours_back: Number of hours to look back.

    Returns:
        Dict keyed by datapoint name, each containing:
        - values: list[float] of numeric values
        - timestamps: list[int] of epoch seconds
    """
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
    raw_timestamps = result.get("time", [])
    timestamps = [
        int(t / 1000) if t > 1e12 else int(t) for t in raw_timestamps
    ]

    series: dict[str, dict[str, Any]] = {}
    for dp_idx, dp_name in enumerate(dp_names):
        dp_values = []
        dp_timestamps = []
        for i, row in enumerate(value_rows):
            if dp_idx < len(row) and row[dp_idx] != "No Data":
                val = row[dp_idx]
                if val is not None and not (
                    isinstance(val, float) and math.isnan(val)
                ):
                    dp_values.append(float(val))
                    if i < len(timestamps):
                        dp_timestamps.append(timestamps[i])

        series[dp_name] = {
            "values": dp_values,
            "timestamps": dp_timestamps,
        }

    return series
