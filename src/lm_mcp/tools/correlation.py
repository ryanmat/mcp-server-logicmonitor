# Description: Metric correlation tool for the LogicMonitor MCP server.
# Description: Provides correlate_metrics, the Pearson correlation of metric series.

from __future__ import annotations

import statistics
from collections import defaultdict
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
)
from lm_mcp.tools.stats_helpers import (
    fetch_metric_series,
    pearson_correlation,
    truncation_warnings,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# Bucket width when no series holds two samples to measure an interval from.
DEFAULT_BUCKET_SECONDS = 300


def bucket_width(timestamps: list[list[int]]) -> int:
    """The coarsest median sample interval among the series, in seconds.

    Each series is measured by the median gap between its samples, so one missing
    sample does not widen it; the widest series sets the bucket so every series has
    about one sample per bucket and finer ones are averaged into it.
    """
    widths = [
        int(statistics.median(b - a for a, b in pairwise(ts))) for ts in timestamps if len(ts) >= 2
    ]
    return max([w for w in widths if w > 0], default=DEFAULT_BUCKET_SECONDS)


def bucket_means(values: list[float], timestamps: list[int], width: int) -> dict[int, float]:
    """The mean of a series' samples in each bucket of width seconds, keyed by bucket start."""
    sums: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    for value, ts in zip(values, timestamps, strict=True):
        bucket = (ts // width) * width
        sums[bucket] += value
        counts[bucket] += 1
    return {bucket: sums[bucket] / counts[bucket] for bucket in sums}


async def correlate_metrics(
    client: LogicMonitorClient,
    sources: list[dict],
    hours_back: int = 24,
) -> list[TextContent]:
    """Compute Pearson correlation between multiple metric series.

    Fetches data from each source, joins the series by timestamp bucket, and
    builds an NxN correlation matrix over the buckets every series shares.
    Highlights strong correlations (|r| > 0.7).

    Args:
        client: LogicMonitor API client.
        sources: List of source dicts, each containing device_id,
            device_datasource_id, instance_id, and datapoint.
            Maximum 10 sources.
        hours_back: Hours of data to analyze (default: 24).

    Returns:
        Correlation matrix, strong correlations, shared_samples (the buckets every
        series holds) and bucket_seconds; warnings names any source the page cap
        cut short.
    """
    try:
        if len(sources) > 10:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "Maximum 10 sources allowed for correlation.",
                    "suggestion": "Reduce the number of sources to 10 or fewer.",
                }
            )

        if len(sources) < 2:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "At least 2 sources required for correlation.",
                }
            )

        # Fetch each series
        labels = []
        all_values = []
        all_times = []
        warnings: list[str] = []

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
            if not (dp_name and dp_name in series) and series:
                dp_name = next(iter(series))
            vals = series[dp_name]["values"] if dp_name in series else []
            times = series[dp_name]["timestamps"] if dp_name in series else []

            label = f"d{src['device_id']}:{dp_name}"
            labels.append(label)
            all_values.append(vals)
            all_times.append(times)
            if dp_name in series:
                warnings.extend(truncation_warnings({label: series[dp_name]}))

        # Join the series on the timestamp buckets every one of them holds
        width = bucket_width(all_times)
        means = [
            bucket_means(vals, times, width)
            for vals, times in zip(all_values, all_times, strict=True)
        ]
        shared = sorted(set.intersection(*(set(m) for m in means))) if means else []
        if len(shared) < 2:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "Insufficient overlapping data for correlation.",
                    "suggestion": "Ensure sources have at least 2 data points in the time window.",
                }
            )

        aligned = [[m[bucket] for bucket in shared] for m in means]

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
                        strong_correlations.append(
                            {
                                "source_a": labels[i],
                                "source_b": labels[j],
                                "correlation": r,
                                "strength": ("strong_positive" if r > 0 else "strong_negative"),
                            }
                        )
            matrix.append(row)

        response: dict[str, Any] = {
            "labels": labels,
            "correlation_matrix": matrix,
            "strong_correlations": strong_correlations,
            "shared_samples": len(shared),
            "bucket_seconds": width,
            "hours_back": hours_back,
        }
        if warnings:
            response["warnings"] = warnings
        return format_response(response)
    except Exception as e:
        return handle_error(e)
