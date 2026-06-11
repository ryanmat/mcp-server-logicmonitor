# Description: OTLP Metrics query tools for LogicMonitor MCP server.
# Description: PromQL range queries and metric/label discovery for native OTLP metrics.

from __future__ import annotations

import contextlib
import math
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.exceptions import LMError, NotFoundError
from lm_mcp.tools import format_response, handle_error, validation_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

_FEATURE_UNAVAILABLE = "OTLP Metrics is not available on this portal (feature flag not enabled)."
_FEATURE_SUGGESTION = (
    "Ask LogicMonitor to enable the OTLP Metrics feature flag for this portal, "
    "and confirm the API token has the OTLP Metrics permission."
)
# query-range matrices can be huge; cap the payload handed back to the model.
_MAX_SERIES = 20
_MAX_POINTS_PER_SERIES = 500


def _handle_otlp_error(e: Exception) -> list[TextContent]:
    """Translate feature-unavailable errors into a friendly response.

    Flag-disabled portals 404 (the /metrics routes are absent entirely);
    flag-deployed-but-off portals 400 with an explicit feature message.
    Both mean the same thing to the caller. Everything else passes through
    to the standard error envelope.
    """
    feature_disabled = isinstance(e, NotFoundError) or (
        isinstance(e, LMError) and "OTLP Metrics feature is not enabled" in str(e)
    )
    if feature_disabled:
        return format_response(
            {
                "available": False,
                "message": _FEATURE_UNAVAILABLE,
                "suggestion": _FEATURE_SUGGESTION,
            }
        )
    return handle_error(e)


def _body_errors(result: dict) -> list[TextContent] | None:
    """Detect the HTTP-200-with-errors body the metrics backend can return.

    The metrics proxy reports backend failures as a 200 carrying an
    "errors" list (not the errorMessage/errorCode shape the client raises
    on), so the tool layer has to check for it.
    """
    errors = result.get("errors")
    if not errors:
        return None
    messages = "; ".join(str(err.get("message", err)) for err in errors)
    return format_response(
        {
            "error": True,
            "code": "OTLP_QUERY_ERROR",
            "message": messages,
            "suggestion": "Retry; if it persists, narrow the time window or simplify the query.",
        }
    )


def _format_string_list(result: dict, items_key: str, **extra: Any) -> list[TextContent]:
    """Normalize the shared list-response body of the three GET endpoints."""
    error_response = _body_errors(result)
    if error_response is not None:
        return error_response
    meta = result.get("meta") or {}
    # The "data" key is absent entirely when there are no matches.
    items = result.get("data") or []
    response: dict[str, Any] = {**extra, items_key: items, "count": len(items)}
    if meta.get("queryTimeMs") is not None:
        response["query_time_ms"] = meta["queryTimeMs"]
    if meta.get("message"):
        response["note"] = meta["message"]
    if meta.get("accessible") is False:
        response["accessible"] = False
    return format_response(response)


def _normalize_point(point: Any) -> list[Any]:
    """Normalize one sample to a [timestamp, value] pair.

    The live API returns {"value": "142.5", "timestamp": 1708689600};
    the Prometheus-native [ts, "val"] pair form is tolerated defensively.
    Values stay strings when they do not parse as floats (e.g. "NaN" is
    preserved as float nan only when float() accepts it).
    """
    if isinstance(point, dict):
        timestamp, value = point.get("timestamp"), point.get("value")
    elif isinstance(point, (list, tuple)) and len(point) == 2:
        timestamp, value = point
    else:
        return [None, point]
    with contextlib.suppress(TypeError, ValueError):
        value = float(value)  # type: ignore[arg-type]
    return [timestamp, value]


async def get_otlp_metric_names(
    client: LogicMonitorClient,
    contains: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List metric names from the native OTLP metrics store.

    Args:
        client: LogicMonitor API client.
        contains: Substring filter on metric names (wildcards unsupported).
        start: Window start as unix epoch seconds.
        end: Window end as unix epoch seconds.
        limit: Maximum number of names to return.

    Returns:
        List of TextContent with metric names or error.
    """
    try:
        params: dict = {"limit": limit}
        if contains:
            params["contains"] = contains
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        result = await client.get("/metrics/metric-names", params=params)
        return _format_string_list(result, "metric_names")
    except Exception as e:
        return _handle_otlp_error(e)


async def get_otlp_metric_labels(
    client: LogicMonitorClient,
    metric: str | None = None,
    label_name: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List label names present on OTLP metrics.

    Args:
        client: LogicMonitor API client.
        metric: Narrow to labels present on this metric name.
        label_name: Substring filter on label names.
        start: Window start as unix epoch seconds.
        end: Window end as unix epoch seconds.
        limit: Maximum number of labels to return.

    Returns:
        List of TextContent with label names or error.
    """
    try:
        params: dict = {"limit": limit}
        if metric:
            params["metric"] = metric
        if label_name:
            params["labelName"] = label_name
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        result = await client.get("/metrics/labels", params=params)
        return _format_string_list(result, "labels")
    except Exception as e:
        return _handle_otlp_error(e)


async def get_otlp_label_values(
    client: LogicMonitorClient,
    key: str,
    metric: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List values observed for one OTLP metric label.

    Args:
        client: LogicMonitor API client.
        key: Label name to list values for (e.g. service_name).
        metric: Narrow to values present on this metric name.
        start: Window start as unix epoch seconds.
        end: Window end as unix epoch seconds.
        limit: Maximum number of values to return.

    Returns:
        List of TextContent with label values or error.
    """
    if not key:
        return validation_error(
            "VALIDATION_ERROR",
            "key is required",
            "Pass a label name, e.g. service_name; discover names with get_otlp_metric_labels.",
        )
    try:
        params: dict = {"key": key, "limit": limit}
        if metric:
            params["metric"] = metric
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        result = await client.get("/metrics/label-values", params=params)
        return _format_string_list(result, "values", key=key)
    except Exception as e:
        return _handle_otlp_error(e)


async def query_otlp_metrics(
    client: LogicMonitorClient,
    query: str,
    start: int,
    end: int,
    step: str | None = None,
) -> list[TextContent]:
    """Run a PromQL range query against the native OTLP metrics store.

    Args:
        client: LogicMonitor API client.
        query: PromQL expression.
        start: Window start as unix epoch seconds.
        end: Window end as unix epoch seconds.
        step: Resolution step (e.g. "30s", "5m"); backend default if omitted.

    Returns:
        List of TextContent with the result matrix or error.
    """
    if not query:
        return validation_error(
            "VALIDATION_ERROR",
            "query is required",
            "Pass a PromQL expression, e.g. avg(container_cpu_usage_seconds_total).",
        )
    if start >= end:
        return validation_error(
            "VALIDATION_ERROR",
            "start must be before end (unix epoch seconds)",
            "Swap the values or widen the window.",
        )
    try:
        body: dict = {"query": query, "start": start, "end": end}
        if step:
            body["step"] = step
        result = await client.post("/metrics/query-range", json_body=body)

        error_response = _body_errors(result)
        if error_response is not None:
            return error_response

        meta = result.get("meta") or {}
        raw_series = result.get("data") or []
        truncated = len(raw_series) > _MAX_SERIES

        series = []
        for entry in raw_series[:_MAX_SERIES]:
            labels = dict(entry.get("metric") or {})
            name = labels.pop("__name__", None)
            points = [_normalize_point(p) for p in entry.get("values") or []]
            if len(points) > _MAX_POINTS_PER_SERIES:
                # Even-stride downsample so the window shape survives.
                stride = math.ceil(len(points) / _MAX_POINTS_PER_SERIES)
                points = points[::stride]
                truncated = True
            series.append(
                {
                    "name": name,
                    "labels": labels,
                    "points": points,
                    "point_count": len(points),
                }
            )

        response: dict[str, Any] = {
            "result_type": meta.get("resultType", "matrix"),
            "query": query,
            "start": start,
            "end": end,
            "step": step,
            "series_count_total": len(raw_series),
            "series_count_returned": len(series),
            "series": series,
        }
        if meta.get("queryTimeMs") is not None:
            response["query_time_ms"] = meta["queryTimeMs"]
        if truncated:
            response["truncated"] = True
            response["note"] = (
                f"Output capped at {_MAX_SERIES} series / {_MAX_POINTS_PER_SERIES} points per "
                "series. Use a larger step, a narrower time window, or a more specific query."
            )
        return format_response(response)
    except Exception as e:
        return _handle_otlp_error(e)
