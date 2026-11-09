# Description: Metric correlation tool for the LogicMonitor MCP server.
# Description: Provides correlate_metrics, the Pearson correlation of metric series.

from __future__ import annotations

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


async def correlate_metrics(
    client: LogicMonitorClient,
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
        Correlation matrix and list of strong correlations; warnings names any
        source the page cap cut short.
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
        sample_counts = []
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
            if dp_name in series:
                warnings.extend(truncation_warnings({label: series[dp_name]}))

        # Align series to the shortest length
        min_len = min(len(v) for v in all_values) if all_values else 0
        if min_len < 2:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "Insufficient overlapping data for correlation.",
                    "suggestion": "Ensure sources have at least 2 data points in the time window.",
                }
            )

        # Series run oldest first, so the tail is the newest samples. Pairing is by
        # position, not timestamp, so sources with different intervals stay approximate.
        aligned = [v[-min_len:] for v in all_values]

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
            "sample_count": min_len,
            "hours_back": hours_back,
        }
        if warnings:
            response["warnings"] = warnings
        return format_response(response)
    except Exception as e:
        return handle_error(e)
