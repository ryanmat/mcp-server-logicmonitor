# Description: MCP tool utilities for LogicMonitor server.
# Description: Provides response formatting and error handling helpers.

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.types import TextContent

from lm_mcp.exceptions import LMError

__all__ = [
    "SEVERITY_MAP",
    "SEVERITY_NAMES",
    "format_response",
    "handle_error",
    "normalize_definition_fields",
    "portal_url",
    "quote_filter_value",
    "require_write_permission",
    "resolve_group_filter",
    "safe_total",
    "sanitize_filter_value",
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


def normalize_definition_fields(definition: dict) -> dict:
    """Normalize field names in a LogicModule definition to REST API camelCase.

    Recursively walks the definition dict, renaming keys that appear in
    _FIELD_ALIASES to their REST API equivalents. Keys already in the correct
    camelCase form pass through unchanged for backwards compatibility.

    When both an alias and its canonical key exist in the same dict, the
    canonical key value wins to prevent silent data loss.

    Args:
        definition: LogicModule definition dict (may use LM Exchange,
            snake_case, or REST API field names).

    Returns:
        New dict with all recognized keys mapped to REST API camelCase names.
    """
    result: dict = {}
    for key, value in definition.items():
        canonical = _FIELD_ALIASES.get(key, key)
        # If this key is an alias but the canonical key already exists
        # in the original dict, skip the alias (canonical wins).
        if canonical != key and canonical in definition:
            continue
        normalized = _normalize_value(value)
        result[canonical] = normalized
    return result


def _normalize_value(value: Any) -> Any:
    """Recursively normalize values within a definition structure."""
    if isinstance(value, dict):
        return normalize_definition_fields(value)
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
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


def quote_filter_value(value: str) -> str:
    """Wrap a string value in double quotes for LM API v3 filter compatibility.

    The LogicMonitor REST API v3 requires string filter values to be enclosed
    in double quotes. Numeric and boolean values work without quotes, but
    string values silently return zero results when unquoted.

    Args:
        value: The string value to quote.

    Returns:
        The value wrapped in double quotes.
    """
    return f'"{value}"'


def sanitize_filter_value(value: str | None) -> tuple[str | None, bool]:
    """Strip wildcard characters (* and ?) from a filter value.

    The LogicMonitor ~ operator already performs substring matching,
    so wildcards are unnecessary and cause issues when URL-encoded.

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
        is unavailable.
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

    return f"https://{config.portal}/santaba/uiv4/{path}"


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


def format_response(data: Any) -> list[TextContent]:
    """Format data as MCP TextContent response.

    Args:
        data: The data to format. Can be dict, list, string, or other types.

    Returns:
        List containing a single TextContent with the formatted data.
    """
    if isinstance(data, dict) and data.get("error"):
        # Error response - format for readability
        text = f"Error: {data['message']}"
        if data.get("suggestion"):
            text += f"\nSuggestion: {data['suggestion']}"
        return [TextContent(type="text", text=text)]

    # Success response
    text = json.dumps(data, indent=2, default=str) if isinstance(data, (dict, list)) else str(data)

    return [TextContent(type="text", text=text)]


def handle_error(error: Exception) -> list[TextContent]:
    """Convert exception to MCP response.

    Args:
        error: The exception to handle.

    Returns:
        List containing a single TextContent with the error details.
    """
    if isinstance(error, LMError):
        return format_response(error.to_dict())

    # Generic exception - wrap in standard format
    return format_response(
        {
            "error": True,
            "code": "UNEXPECTED_ERROR",
            "message": str(error),
        }
    )


def require_write_permission(func: F) -> F:
    """Decorator to enforce write permission check.

    When LM_ENABLE_WRITE_OPERATIONS is false (default), decorated functions
    will return an error response instead of executing.

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
            return format_response(
                {
                    "error": True,
                    "code": "WRITE_DISABLED",
                    "message": "Write operations are disabled",
                    "suggestion": "Set LM_ENABLE_WRITE_OPERATIONS=true to enable write operations",
                }
            )
        return await func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
