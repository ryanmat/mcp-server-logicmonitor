# Description: Shared statistical utility functions for ML analysis tools.
# Description: Provides series statistics, change and cycle detection, Holt-Winters, paged reads.

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# The instance data endpoint returns at most 500 samples a page, newest first.
# A week of one-minute samples is 21 pages; longer windows keep the newest
# 25 pages (12,500 samples) and report truncated.
MAX_SERIES_PAGES = 25


def linear_regression(x: list[float], y: list[float]) -> tuple[float, float, float]:
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
    sum_xy = sum(xi * yi for xi, yi in zip(x, y, strict=True))
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
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y, strict=True))

    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

    return slope, intercept, r_squared


def detrend(x: list[float], y: list[float]) -> list[float]:
    """Return y less its least-squares line, so a trend does not read as a cycle.

    A series the line explains to rounding error (a straight ramp, or a flat line)
    returns all zeros rather than floating-point residue, which autocorrelation would
    otherwise read as structure.

    Args:
        x: Independent variable values.
        y: Dependent variable values, at least 2.

    Returns:
        The residuals, one per sample.
    """
    slope, intercept, _ = linear_regression(x, y)
    residuals = [yi - (slope * xi + intercept) for xi, yi in zip(x, y, strict=True)]
    mean = sum(y) / len(y)
    ss_tot = sum((yi - mean) ** 2 for yi in y)
    ss_res = sum(r * r for r in residuals)
    if ss_res <= 1e-12 * ss_tot or ss_tot == 0:
        return [0.0] * len(y)
    return residuals


# Theil-Sen reads every pair of samples; above this many samples it reads an evenly
# spaced subsample spanning the whole series, so a week of one-minute samples costs
# about 125,000 pairs rather than 50 million.
THEIL_SEN_MAX_SAMPLES = 500


def theil_sen_slope(x: list[float], y: list[float]) -> float:
    """Compute the Theil-Sen slope: the median of the slopes between every pair of samples.

    A spike moves one sample's pairs, a minority of the whole, so the median stays on
    the series' underlying slope where least squares is pulled toward the spike.

    Args:
        x: Independent variable values.
        y: Dependent variable values.

    Returns:
        The median pairwise slope; 0.0 when every x value is identical.

    Raises:
        ValueError: If x and y have different lengths or fewer than 2 points.
    """
    n = len(x)
    if n != len(y):
        raise ValueError("x and y must have the same length")
    if n < 2:
        raise ValueError("At least 2 data points required for regression")

    if n > THEIL_SEN_MAX_SAMPLES:
        picks = [
            round(i * (n - 1) / (THEIL_SEN_MAX_SAMPLES - 1)) for i in range(THEIL_SEN_MAX_SAMPLES)
        ]
        x = [x[i] for i in picks]
        y = [y[i] for i in picks]
        n = THEIL_SEN_MAX_SAMPLES

    slopes = sorted(
        (y[j] - y[i]) / (x[j] - x[i]) for i in range(n) for j in range(i + 1, n) if x[j] != x[i]
    )
    if not slopes:
        return 0.0
    mid = len(slopes) // 2
    if len(slopes) % 2:
        return slopes[mid]
    return (slopes[mid - 1] + slopes[mid]) / 2


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

    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y, strict=True))
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

    cov = sum((values[i] - mean) * (values[i + lag] - mean) for i in range(n - lag)) / (n - lag)

    return cov / variance


DAY_SECONDS = 86400

# A daily profile must reach this share of its time-of-day bins to be subtracted.
MIN_PROFILE_COVERAGE = 0.9


def remove_daily_cycle(
    values: list[float], timestamps: list[int], exclude_near: list[int] | None = None
) -> tuple[list[float], bool]:
    """Subtract the series' daily profile when the samples span three days or more.

    Each sample whose centered 24-hour window lies inside the series contributes its
    distance from that window's mean, a level that follows trends and steps, to the
    bin of its time of day at the sample interval. Each bin's profile is the median of
    those distances across days, so the one day a step crosses does not shape it.
    The profile, centered on zero, is subtracted from every sample in its bin.
    Samples within 12 hours of a time in `exclude_near`, whose 24-hour window straddles
    a known change, are left out of the profile. A profile that reaches fewer than
    MIN_PROFILE_COVERAGE of the bins does not describe the day, and none is applied.

    Args:
        values: Samples, oldest first.
        timestamps: Epoch seconds of the samples, ascending.
        exclude_near: Epoch seconds of changes already found, if any.

    Returns:
        The series less its daily profile and True, or the series unchanged and False
        when it spans less than three days or the profile reaches too few bins.
    """
    n = len(values)
    if n < 2 or timestamps[-1] - timestamps[0] < 3 * DAY_SECONDS:
        return list(values), False
    interval = (timestamps[-1] - timestamps[0]) / (n - 1)
    bins = max(1, round(DAY_SECONDS / interval))

    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + v)
    half = DAY_SECONDS / 2
    by_bin: dict[int, list[float]] = {}
    lo = hi = 0
    for i, t in enumerate(timestamps):
        if t - half < timestamps[0] or t + half > timestamps[-1]:
            continue
        if exclude_near and any(abs(t - c) < half for c in exclude_near):
            continue
        while timestamps[lo] < t - half:
            lo += 1
        while hi < n and timestamps[hi] <= t + half:
            hi += 1
        level = (prefix[hi] - prefix[lo]) / (hi - lo)
        by_bin.setdefault(round((t % DAY_SECONDS) / interval) % bins, []).append(values[i] - level)

    if len(by_bin) < MIN_PROFILE_COVERAGE * bins:
        return list(values), False
    profile: dict[int, float] = {}
    for b, distances in by_bin.items():
        ordered = sorted(distances)
        mid = len(ordered) // 2
        profile[b] = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    center = sum(profile.values()) / len(profile)
    return [
        v - (profile.get(round((t % DAY_SECONDS) / interval) % bins, center) - center)
        for v, t in zip(values, timestamps, strict=True)
    ], True


# A window difference this many noise scales from its center is a level shift.
SHIFT_THRESHOLD = 5.0

# Fewer block differences than this give no robust center or spread of their own.
MIN_SHIFT_BLOCKS = 15


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def window_shifts(values: list[float], window: int) -> tuple[list[dict], float]:
    """Find level shifts where the mean of the next `window` samples leaves the previous.

    At each sample the difference of the two means is centered on the median of the
    differences taken every fifth of a window, which a steady trend shifts by its slope
    times the window. It is scaled by the larger of two: 1.4826 times their median
    absolute deviation, which carries whatever autocorrelation the noise has, and the
    scale independent noise of the series' first differences would give. A change
    disturbs the differences within a window of it, about ten of them, so on a series
    of a day or more a few changes leave the center and the spread to the noise; on a
    shorter one a change inflates the spread and smaller shifts go unfound. With fewer
    than MIN_SHIFT_BLOCKS of those differences the center is zero and the first
    differences set the scale. Samples past SHIFT_THRESHOLD are kept from the largest
    down, at least `window` apart, each dated to its own sample.

    Args:
        values: Time series values, oldest first.
        window: Samples on each side of the comparison.

    Returns:
        The shifts, each with index and direction ("increase" or "decrease"), and the
        scale used; no shifts and an infinite scale when the series is shorter than
        two windows.
    """
    n = len(values)
    if n < 2 * window:
        return [], math.inf

    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + v)

    def difference(i: int) -> float:
        return (prefix[i + window] - 2 * prefix[i] + prefix[i - window]) / window

    diffs = [values[i + 1] - values[i] for i in range(n - 1)]
    mean_diff = sum(diffs) / len(diffs)
    independent = math.sqrt(
        sum((d - mean_diff) ** 2 for d in diffs) / max(1, len(diffs) - 1)
    ) / math.sqrt(window)
    blocks = [difference(i) for i in range(window, n - window + 1, max(1, window // 5))]
    center = spread = 0.0
    if len(blocks) >= MIN_SHIFT_BLOCKS:
        center = _median(blocks)
        spread = 1.4826 * _median([abs(b - center) for b in blocks])
    scale = max(spread, independent)
    if scale == 0:
        return [], 0.0

    candidates = []
    for i in range(window, n - window + 1):
        z = (difference(i) - center) / scale
        if abs(z) > SHIFT_THRESHOLD:
            candidates.append((abs(z), i, z))
    candidates.sort(reverse=True)
    kept: list[tuple[int, float]] = []
    for _, i, z in candidates:
        if all(abs(i - j) >= window for j, _ in kept):
            kept.append((i, z))
    points = [
        {"index": i, "direction": "increase" if z > 0 else "decrease"} for i, z in sorted(kept)
    ]
    return points, scale


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
        Dict with fitted, forecast, and residuals lists, and trend, the final smoothed
        trend per sample.

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
    trend = sum(values[season_length + i] - values[i] for i in range(season_length)) / (
        season_length * season_length
    )

    # The first season's mean sits at its middle sample; the seasonal components are
    # that season less its trend line, so the climb within it is not read as season.
    middle = (season_length - 1) / 2
    seasonals = [values[i] - (level + trend * (i - middle)) for i in range(season_length)]

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

    return {"fitted": fitted, "forecast": forecast, "residuals": residuals, "trend": trend}


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
    q1 = sorted_vals[q1_low] + q1_frac * (sorted_vals[min(q1_low + 1, n - 1)] - sorted_vals[q1_low])

    q3_low = int(q3_pos)
    q3_frac = q3_pos - q3_low
    q3 = sorted_vals[q3_low] + q3_frac * (sorted_vals[min(q3_low + 1, n - 1)] - sorted_vals[q3_low])

    iqr = q3 - q1
    lower_fence = q1 - multiplier * iqr
    upper_fence = q3 + multiplier * iqr

    anomaly_indices = [i for i, v in enumerate(values) if v < lower_fence or v > upper_fence]

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
    anomaly_indices = [i for i, z in enumerate(modified_z_scores) if abs(z) > threshold]

    return {
        "median": round(median, 4),
        "mad": round(mad, 4),
        "anomaly_indices": anomaly_indices,
        "modified_z_scores": modified_z_scores,
    }


# The warning a raw reader adds when MAX_SERIES_PAGES stopped its read.
PAGE_CAP_WARNING = (
    f"The read stopped at the {MAX_SERIES_PAGES}-page cap, so the oldest samples of the "
    "window are missing; shorten the window to read all of it."
)


async def fetch_metric_pages(
    client: LogicMonitorClient, path: str, params: dict[str, Any]
) -> tuple[list[str], list[Any], list[Any], bool]:
    """Read every page of a device instance data window, as the endpoint orders them.

    The endpoint pages newest first and names the next page in nextPageParams; the
    pages are followed up to MAX_SERIES_PAGES. A datapoints selection rides every page.

    Args:
        client: LogicMonitor API client.
        path: The instance's /data path.
        params: The first page's query.

    Returns:
        The datapoint names, the times and the value rows of every page read, newest
        first, and whether the page cap stopped the read with samples left.
    """
    datapoints = params.get("datapoints")
    dp_names: list[str] = []
    times: list[Any] = []
    values: list[Any] = []
    for page in range(MAX_SERIES_PAGES):
        result = await client.get(path, params=params)
        if page == 0:
            dp_names = result.get("datapoints", result.get("dataPoints", []))
        times.extend(result.get("time", []))
        values.extend(result.get("values", []))
        next_page = result.get("nextPageParams") or ""
        if not next_page:
            return dp_names, times, values, False
        params = dict(parse_qsl(next_page))
        if datapoints:
            params["datapoints"] = datapoints
    return dp_names, times, values, True


async def fetch_metric_series(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    hours_back: int = 24,
    end_hours_ago: int = 0,
) -> dict[str, dict[str, Any]]:
    """Fetch metric data from LM API and transpose to per-datapoint series.

    Consolidates the common pattern of fetching from the device data endpoint,
    transposing the list-of-lists response to per-datapoint columns, filtering
    "No Data" sentinels, and converting millisecond timestamps. The endpoint
    pages newest first, so every page named by nextPageParams is read, up to
    MAX_SERIES_PAGES, and the samples are returned oldest first.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if omitted).
        hours_back: Number of hours to look back.
        end_hours_ago: Hours before now the window ends; 0 reads up to now and sends
            no end.

    Returns:
        Dict keyed by datapoint name, each containing:
        - values: list[float] of numeric values, oldest first
        - timestamps: list[int] of epoch seconds, ascending
        - truncated: True when the page cap stopped the read with samples left
    """
    now_epoch = int(time.time())
    start_epoch = now_epoch - ((hours_back + end_hours_ago) * 3600)

    params: dict[str, Any] = {"start": start_epoch}
    if end_hours_ago:
        params["end"] = now_epoch - end_hours_ago * 3600
    if datapoints:
        params["datapoints"] = datapoints

    path = (
        f"/device/devices/{device_id}"
        f"/devicedatasources/{device_datasource_id}"
        f"/instances/{instance_id}/data"
    )

    dp_names, times, values, truncated = await fetch_metric_pages(client, path, params)
    rows = [
        (int(t / 1000) if t > 1e12 else int(t), row) for t, row in zip(times, values, strict=False)
    ]
    rows.sort(key=lambda r: r[0])

    series: dict[str, dict[str, Any]] = {}
    for dp_idx, dp_name in enumerate(dp_names):
        dp_values = []
        dp_timestamps = []
        for ts, row in rows:
            if dp_idx < len(row) and row[dp_idx] != "No Data":
                val = row[dp_idx]
                if val is not None and not (isinstance(val, float) and math.isnan(val)):
                    dp_values.append(float(val))
                    dp_timestamps.append(ts)

        series[dp_name] = {
            "values": dp_values,
            "timestamps": dp_timestamps,
            "truncated": truncated,
        }

    return series


def truncation_warnings(series: dict[str, dict[str, Any]]) -> list[str]:
    """Warn for each series the page cap cut short; the newest samples are the ones kept.

    Args:
        series: Series as fetch_metric_series returns them, keyed by the name the
            warning shows.

    Returns:
        One warning per truncated series; empty when every read was complete.
    """
    return [
        f"{name}: the read stopped at the {MAX_SERIES_PAGES}-page cap, so the oldest "
        "samples of the window are missing; shorten hours_back to read all of it."
        for name, data in series.items()
        if data["truncated"]
    ]
