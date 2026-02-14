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
