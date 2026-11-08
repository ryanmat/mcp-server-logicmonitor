# Description: MCP tool utilities for LogicMonitor server.
# Description: Provides response formatting and error handling helpers.

from __future__ import annotations

import functools
import inspect
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar, TypeVar, overload

import httpx
from mcp.types import TextContent

from lm_mcp.exceptions import LMError

logger = logging.getLogger(__name__)

__all__ = [
    "ERROR_CODES",
    "SEVERITY_MAP",
    "SEVERITY_NAMES",
    "ErrorContent",
    "call_sub_tool",
    "error_content",
    "format_response",
    "handle_error",
    "is_error_result",
    "list_tool",
    "lm_error_code",
    "normalize_definition_fields",
    "portal_url",
    "quote_filter_value",
    "require_write_permission",
    "resolve_group_filter",
    "safe_total",
    "sanitize_filter_value",
    "validation_error",
]

# Severity name-to-integer mapping used by alert, trace, and scoring tools
SEVERITY_MAP: dict[str, int] = {
    "critical": 4,
    "error": 3,
    "warning": 2,
    "info": 1,
}

# Severity integer-to-name mapping (reverse of SEVERITY_MAP)
SEVERITY_NAMES: dict[int, str] = {v: k for k, v in SEVERITY_MAP.items()}

F = TypeVar("F", bound=Callable[..., Any])

# Mapping of common alternate field names to REST API camelCase equivalents.
# Covers LM Exchange format names, snake_case variants from get_* output,
# and common typos. Keys already in correct camelCase pass through unchanged.
_FIELD_ALIASES: dict[str, str] = {
    # LM Exchange format -> REST API
    "displayedAs": "displayName",
    "collectionMethod": "collectMethod",
    "collectionAttrs": "collectorAttribute",
    "datapoints": "dataPoints",
    # snake_case -> REST API camelCase
    "display_name": "displayName",
    "collect_method": "collectMethod",
    "collector_attribute": "collectorAttribute",
    "data_points": "dataPoints",
    "applies_to": "appliesTo",
    "collect_interval": "collectInterval",
    "has_multi_instances": "hasMultiInstances",
    "alert_expr": "alertExpr",
    "post_processor_method": "postProcessorMethod",
    "post_processor_param": "postProcessorParam",
    "auto_discovery_config": "autoDiscoveryConfig",
    "enable_auto_discovery": "enableAutoDiscovery",
}


def normalize_definition_fields(definition: dict, *, keep: frozenset[str] = frozenset()) -> dict:
    """Normalize field names in a LogicModule definition to REST API camelCase.

    Recursively walks the definition dict, renaming keys that appear in
    _FIELD_ALIASES to their REST API equivalents. Keys already in the correct
    camelCase form pass through unchanged for backwards compatibility.

    When both an alias and its canonical key exist in the same dict, the
    canonical key value wins to prevent silent data loss.

    Args:
        definition: LogicModule definition dict (may use LM Exchange,
            snake_case, or REST API field names).
        keep: Keys the module's REST model uses as they are, left unrenamed
            although _FIELD_ALIASES maps them (LogSource and TopologySource
            name their collection method collectionMethod).

    Returns:
        New dict with all recognized keys mapped to REST API camelCase names.
    """
    result: dict = {}
    for key, value in definition.items():
        canonical = key if key in keep else _FIELD_ALIASES.get(key, key)
        # If this key is an alias but the canonical key already exists
        # in the original dict, skip the alias (canonical wins).
        if canonical != key and canonical in definition:
            continue
        normalized = _normalize_value(value, keep)
        result[canonical] = normalized
    return result


def _normalize_value(value: Any, keep: frozenset[str]) -> Any:
    """Recursively normalize values within a definition structure."""
    if isinstance(value, dict):
        return normalize_definition_fields(value, keep=keep)
    if isinstance(value, list):
        return [_normalize_value(item, keep) for item in value]
    return value


# Wildcard note appended to response when filter values are sanitized
WILDCARD_STRIP_NOTE = (
    "Wildcard characters were removed from filter value. "
    "The ~ operator performs substring matching automatically — no wildcards needed."
)


def safe_total(result: dict) -> int:
    """Extract the total count from an LM API response, handling negative sentinels.

    The LogicMonitor API returns negative total values (e.g., -501 for limit=500)
    as a sentinel when the result set is truncated beyond the requested limit.

    Args:
        result: The raw API response dict.

    Returns:
        The absolute value of the total field, defaulting to 0.
    """
    return abs(result.get("total", 0))


# Note added to a list response when the API total is a negative lower bound
INEXACT_TOTAL_NOTE = (
    "The API did not report an exact count, so the response carries no total; "
    "page on with offset while has_more is true."
)


def paginated_response(items: list[Any], result: dict, offset: int) -> dict[str, Any]:
    """Build the pagination fields of a list tool response.

    The API reports a negative total, -(offset + size + 1), when more results
    exist than it counted. That is no count, so the response leaves total out
    and carries a total_note. has_more is read from the total when it is
    non-negative and from the page when it is negative: a page with rows under a
    negative total has more past it, and an empty one ends the list.

    Args:
        items: The items returned on this page.
        result: The raw API response dict.
        offset: The offset the page was requested at.

    Returns:
        Dict with count, offset and has_more, plus total when the API total
        was non-negative and total_note when it was negative.
    """
    api_total = result.get("total", 0)
    inexact = api_total < 0
    response: dict[str, Any] = {} if inexact else {"total": api_total}
    response["count"] = len(items)
    response["offset"] = offset
    response["has_more"] = bool(items) if inexact else offset + len(items) < api_total
    if inexact:
        response["total_note"] = INEXACT_TOTAL_NOTE
    return response


async def list_tool(
    client: Any,
    path: str,
    *,
    key: str,
    project: Callable[[dict[str, Any]], Any],
    limit: int,
    offset: int = 0,
    filter: str | None = None,
    named: Mapping[str, str | None] | None = None,
    clauses: Sequence[str] = (),
    params: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> list[TextContent]:
    """Fetch one page of a LogicMonitor collection as a list tool response.

    The helper builds the size, offset and filter query, projects each row and
    returns the paginated_response envelope, so the list tools that call it share
    one query shape and one envelope.

    Args:
        client: LogicMonitor API client.
        path: Collection endpoint, such as /device/devices.
        key: Response key the projected rows go under, such as devices.
        project: Callback that maps one API row onto the tool's fields. A
            coroutine function is awaited row by row.
        limit: Page size, sent as size.
        offset: Rows to skip, sent as offset.
        filter: Raw filter expression. When given it is sent as written, and
            the named filters and clauses are not sent.
        named: Clause prefix (a field and its operator, such as displayName~)
            to value. Each value is stripped of wildcards and quoted; a None or
            empty value is left out.
        clauses: Clauses sent as written ahead of the named ones: fixed
            filters, numeric ids and enum clauses.
        params: Other query parameters the endpoint takes.
        extra: Fields added to the response beside the page.

    Returns:
        List of TextContent with the page, or an ErrorContent from
        handle_error when the call or the projection fails.
    """
    try:
        query: dict[str, Any] = {**(params or {}), "size": limit, "offset": offset}
        wildcards_stripped = False
        if filter:
            query["filter"] = filter
        else:
            parts = list(clauses)
            for prefix, value in (named or {}).items():
                if not value:
                    continue
                clean, was_modified = sanitize_filter_value(value)
                wildcards_stripped = wildcards_stripped or was_modified
                parts.append(f"{prefix}{quote_filter_value(clean)}")
            if parts:
                query["filter"] = ",".join(parts)

        result = await client.get(path, params=query)
        rows = []
        for item in result.get("items", []):
            row = project(item)
            rows.append(await row if inspect.isawaitable(row) else row)

        response = {**paginated_response(rows, result, offset), key: rows, **(extra or {})}
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


def quote_filter_value(value: str) -> str:
    """Wrap a string value in double quotes for LM API v3 filter compatibility.

    The LogicMonitor REST API v3 requires string filter values to be enclosed
    in double quotes. Numeric and boolean values work without quotes, but
    string values silently return zero results when unquoted.

    Backslashes and double quotes inside the value are escaped, backslash
    first, so the value cannot close its quotes and append filter clauses
    (an unescaped ``a"|"b`` would send two clauses joined by OR).

    Args:
        value: The string value to quote.

    Returns:
        The escaped value wrapped in double quotes.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@overload
def sanitize_filter_value(value: str) -> tuple[str, bool]: ...


@overload
def sanitize_filter_value(value: None) -> tuple[None, bool]: ...


@overload
def sanitize_filter_value(value: str | None) -> tuple[str | None, bool]: ...


def sanitize_filter_value(value: str | None) -> tuple[str | None, bool]:
    """Strip wildcard characters (* and ?) from a filter value.

    The LogicMonitor ~ operator already performs substring matching,
    so wildcards are unnecessary and cause issues when URL-encoded.

    The overloads keep a str input typed as a str output, so a call site that
    has already narrowed its argument can pass the cleaned value straight to
    quote_filter_value.

    Args:
        value: The filter value to sanitize. May be None.

    Returns:
        Tuple of (cleaned_value, was_modified). was_modified is True
        if any wildcard characters were removed.
    """
    if value is None:
        return None, False

    cleaned = value.replace("*", "").replace("?", "")
    was_modified = cleaned != value
    return cleaned, was_modified


def portal_url(resource_type: str, resource_id: int | str) -> str:
    """Build a clickable LM portal URL for a single resource.

    Args:
        resource_type: Resource type key (device, alert, dashboard,
            alert_rule, device_group, website).
        resource_id: Numeric resource ID.

    Returns:
        Full HTTPS URL to the resource in the LM portal UI,
        or empty string if the resource type is unknown or config
        is unavailable. In multi-portal mode the host is the call's bound portal.

    Raises:
        RuntimeError: In multi-portal mode, outside a tool call.
    """
    try:
        from lm_mcp.config import get_config

        config = get_config()
    except Exception:
        return ""

    path_map: dict[str, str] = {
        "device": f"devices/{resource_id}",
        "alert": f"alerts/{resource_id}",
        "dashboard": f"dashboard/{resource_id}",
        "alert_rule": f"setting/alert/rules/{resource_id}",
        "device_group": f"device/groups/{resource_id}",
        "website": f"setting/websites/{resource_id}",
    }

    path = path_map.get(resource_type)
    if path is None:
        return ""

    if config.multi_portal:
        from lm_mcp import portals
        from lm_mcp.context import current_binding

        host = portals.host(current_binding().portal)
    else:
        host = config.portal
    if not host:
        return ""

    return f"https://{host}/santaba/uiv4/{path}"


async def resolve_group_filter(client: Any, group_id: int) -> str:
    """Resolve a device group ID to a monitorObjectGroups filter clause.

    The LM API hostGroupIds~ filter does not reliably restrict alerts to a
    specific group. The monitorObjectGroups~ filter (which uses the group
    fullPath) works correctly.  This helper fetches the group fullPath from
    the API and returns the ready-to-use filter clause.

    Args:
        client: LogicMonitor API client.
        group_id: Device group ID to resolve.

    Returns:
        Filter clause string, e.g. monitorObjectGroups~"My Group/Sub".

    Raises:
        LMError: If the group cannot be found.
    """
    result = await client.get(f"/device/groups/{group_id}")
    full_path = result.get("fullPath", "")
    return f"monitorObjectGroups~{quote_filter_value(full_path)}"


class ErrorContent(TextContent):
    """TextContent that carries a tool error.

    The text is the JSON error envelope :func:`error_content` builds; the type is
    what lets the dispatcher recognize a failure without parsing the text.
    """

    is_error: ClassVar[bool] = True


# The documented error codes (spec R2.7), each with its house-rule category and
# whether the same call, sent again unchanged, can succeed.
ERROR_CODES: dict[str, tuple[str, bool]] = {
    "NOT_FOUND": ("validation", False),
    "INVALID_REQUEST": ("validation", False),
    "WRITE_DISABLED": ("permission", False),
    "RATE_LIMITED": ("transient", True),
    "UPSTREAM_ERROR": ("transient", True),
    "TIMEOUT": ("transient", True),
    "AUTH_FAILED": ("permission", False),
    "SCOPE_MISSING": ("permission", False),
    "FEATURE_DISABLED": ("permission", False),
    "REJECTED_BY_TOOL": ("business", False),
}

# Client exception codes outside the documented set, mapped onto it. Any other
# HTTP_<status> is a 4xx the API refused, and API_ERROR or API_ERROR_<errorCode>
# a request the API refused in a 200 body; any other code is a failure the portal
# or the client reported.
_LM_ERROR_CODES: dict[str, str] = {
    "PERMISSION_DENIED": "AUTH_FAILED",
    "VALIDATION_ERROR": "INVALID_REQUEST",
    "SERVER_ERROR": "UPSTREAM_ERROR",
    "CONNECTION_FAILED": "UPSTREAM_ERROR",
    "CONFIG_ERROR": "FEATURE_DISABLED",
}

# Keys of a handler's error dict that the envelope reads; any other key is detail.
_ERROR_DICT_KEYS = frozenset({"error", "code", "message", "suggestion", "details", "retry_after"})


def _with_suggestion(message: str, suggestion: str | None) -> str:
    """Join a remediation hint onto the message, so the message states the next step."""
    if not suggestion:
        return message
    separator = " " if message.endswith((".", "!", "?")) else ". "
    return f"{message}{separator}{suggestion}"


def error_content(
    code: str,
    message: str,
    *,
    details: Mapping[str, Any] | None = None,
    retry_after: int | None = None,
) -> list[TextContent]:
    """Build the one error envelope every tool failure returns.

    Args:
        code: One of :data:`ERROR_CODES`; any other code raises KeyError.
        message: Human-readable failure; a fix or next step, when known, ends it.
        details: Structured context, such as LogicMonitor's own code and words.
        retry_after: Seconds the caller should wait before retrying, when known.

    Returns:
        List with a single ErrorContent whose text is the JSON envelope.
    """
    category, retryable = ERROR_CODES[code]
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": dict(details) if details else None,
            "retry_after": retry_after,
            "errorCategory": category,
            "isRetryable": retryable,
        }
    }
    return [ErrorContent(type="text", text=json.dumps(body, default=str))]


def lm_error_code(error: LMError) -> str:
    """Map a client exception onto the documented code set."""
    if isinstance(error.__cause__, httpx.TimeoutException):
        return "TIMEOUT"
    if error.code in ERROR_CODES:
        return error.code
    if error.code in _LM_ERROR_CODES:
        return _LM_ERROR_CODES[error.code]
    if error.code.startswith(("HTTP_", "API_ERROR")):
        return "INVALID_REQUEST"
    return "UPSTREAM_ERROR"


def error_from_exception(error: Exception) -> list[TextContent]:
    """Map an exception onto the error envelope without logging it.

    :func:`handle_error` logs and then calls this; the dispatcher calls it
    directly after logging with the tool's name.
    """
    if isinstance(error, LMError):
        code = lm_error_code(error)
        details: dict[str, Any] = {}
        if code != error.code:
            details["lm_code"] = error.code
        if error.details:
            details["lm_message"] = error.details
        return error_content(
            code,
            _with_suggestion(error.message, error.suggestion),
            details=details,
            retry_after=getattr(error, "retry_after", None),
        )
    code = "TIMEOUT" if isinstance(error, httpx.TimeoutException) else "UPSTREAM_ERROR"
    return error_content(
        code,
        str(error) or type(error).__name__,
        details={"exception": type(error).__name__},
    )


def is_error_result(result: list) -> bool:
    """Return True when a tool result carries an ErrorContent item.

    Args:
        result: The content list a tool handler or execute_tool returned.

    Returns:
        True if any item is an ErrorContent, False otherwise (including empty).
    """
    return any(isinstance(item, ErrorContent) for item in result)


def format_response(data: Any) -> list[TextContent]:
    """Format data as MCP TextContent response.

    Args:
        data: The data to format. Can be dict, list, string, or other types.

    Returns:
        List containing a single TextContent with the formatted data; an
        ErrorContent carrying the error envelope when the data is a handler's
        error dict (``error``, ``code``, ``message``, optional ``suggestion``,
        ``details`` and ``retry_after``; any other key goes into ``details``).
    """
    if isinstance(data, dict) and data.get("error"):
        details = dict(data.get("details") or {})
        details.update({k: v for k, v in data.items() if k not in _ERROR_DICT_KEYS})
        return error_content(
            data["code"],
            _with_suggestion(data["message"], data.get("suggestion")),
            details=details,
            retry_after=data.get("retry_after"),
        )

    # Success response
    text = json.dumps(data, indent=2, default=str) if isinstance(data, (dict, list)) else str(data)

    return [TextContent(type="text", text=text)]


def stamp_portal(result: list[TextContent], portal: str | None) -> list[TextContent]:
    """Add the call's portal name to a result that is one JSON object (multi-portal mode).

    A success object carries it as ``portal``. An error envelope carries it as
    ``error.details.portal``, so the envelope keeps its one ``error`` key (spec R2.7).
    Any other result passes through unchanged.

    Args:
        result: The content list execute_tool produced.
        portal: The bound portal name, None before use_portal.
    """
    if len(result) != 1:
        return result
    try:
        data = json.loads(result[0].text)
    except json.JSONDecodeError:
        return result
    if not isinstance(data, dict):
        return result
    if isinstance(result[0], ErrorContent):
        error = data["error"]
        return error_content(
            error["code"],
            error["message"],
            details={**(error["details"] or {}), "portal": portal},
            retry_after=error["retry_after"],
        )
    return format_response({**data, "portal": portal})


def handle_error(error: Exception) -> list[TextContent]:
    """Log an exception and convert it to the error envelope.

    Args:
        error: The exception to handle.

    Returns:
        List containing a single ErrorContent with the error envelope.
    """
    if isinstance(error, LMError):
        # An API refusal is a WARNING with the server's own words attached, so a
        # 4xx or 5xx leaves a trace on stderr and not only in the tool result.
        logger.warning(
            "%s: %s%s",
            error.code,
            error.message,
            f" (details: {error.details})" if error.details else "",
        )
        return error_from_exception(error)

    # Log unexpected exceptions with stack trace before returning sanitized response.
    # Without this, JSONDecodeError, KeyError, ValueError, etc. are silently swallowed.
    logger.exception("unhandled error in tool handler")
    return error_from_exception(error)


async def call_sub_tool(handler: Callable[..., Any], client: Any, **kwargs: Any) -> Any:
    """Call a sub-handler, parse JSON response, raise RuntimeError on error.

    Converts the error envelope into a clean RuntimeError carrying its message
    for the composite caller, and non-JSON text into one naming the text,
    instead of a cryptic JSONDecodeError ("Expecting value: line 1 column 1
    (char 0)").

    Args:
        handler: Async tool function. Must accept ``client`` as first arg.
        client: LogicMonitor API client passed through to the handler.
        **kwargs: Forwarded to the handler.

    Returns:
        Parsed JSON payload from the sub-tool. For list/dict payloads the
        parsed structure is returned directly.

    Raises:
        RuntimeError: When the sub-tool returns an error envelope or non-JSON text.
    """
    result = await handler(client, **kwargs)
    text = result[0].text

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        snippet = text[:200]
        raise RuntimeError(f"Sub-tool returned non-JSON response: {snippet}") from None

    if isinstance(data, dict) and data.get("error"):
        error = data["error"]
        message = error.get("message") if isinstance(error, dict) else None
        raise RuntimeError(message or "Sub-tool returned an error")
    return data


def validation_error(
    code: str,
    message: str,
    suggestion: str | None = None,
) -> list[TextContent]:
    """Return a canonical input-validation error response.

    Use for argument validation that fails before any API call. Produces
    the same envelope as :func:`handle_error` so callers see a consistent
    structure regardless of where the error originated.

    Args:
        code: One of :data:`ERROR_CODES`, usually ``INVALID_REQUEST``.
        message: Human-readable description of the failure.
        suggestion: Optional remediation hint, joined onto the message.

    Returns:
        List with a single ErrorContent carrying the error envelope.
    """
    return error_content(code, _with_suggestion(message, suggestion))


def strip_readonly(payload: dict, fields: tuple[str, ...]) -> dict:
    """Return a copy of ``payload`` without the given server-managed read-only fields.

    LogicMonitor rejects or ignores read-only fields echoed back on a write; stripping
    them before a PUT avoids intermittent 400s. The field list is caller-supplied so it
    stays specific to each resource.
    """
    return {k: v for k, v in payload.items() if k not in fields}


def write_disabled_response() -> list[TextContent]:
    """The error a write tool returns while LM_ENABLE_WRITE_OPERATIONS is false."""
    return validation_error(
        "WRITE_DISABLED",
        "Write operations are disabled",
        "Set LM_ENABLE_WRITE_OPERATIONS=true to enable write operations",
    )


def require_write_permission(func: F) -> F:
    """Decorator to enforce write permission check.

    When LM_ENABLE_WRITE_OPERATIONS is false (default), decorated functions
    will return an error response instead of executing. In multi-portal mode the
    portal and its write flag come from the call's binding, and a decorated
    function called outside a tool call raises RuntimeError.

    Args:
        func: The async function to wrap.

    Returns:
        Wrapped function that checks write permission before executing.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        from lm_mcp.config import get_config

        config = get_config()
        if not config.enable_write_operations:
            return write_disabled_response()
        if config.multi_portal:
            from lm_mcp.context import current_binding

            binding = current_binding()
            if binding.portal is None:
                return format_response(
                    {
                        "error": True,
                        "code": "INVALID_REQUEST",
                        "message": "No portal selected",
                        "suggestion": "Call use_portal(<customer>) first (see list_portals)",
                    }
                )
            if not binding.writable:
                return format_response(
                    {
                        "error": True,
                        "code": "WRITE_DISABLED",
                        "message": "The active portal is read-only",
                        "suggestion": (
                            'Set "writable": true on this portal\'s vault record to allow writes'
                        ),
                    }
                )
        return await func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
