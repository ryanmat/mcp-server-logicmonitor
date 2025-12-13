# Description: MCP tool utilities for LogicMonitor server.
# Description: Provides response formatting and error handling helpers.

from __future__ import annotations

import functools
import json
from typing import Any, Callable, TypeVar

from mcp.types import TextContent

from lm_mcp.exceptions import LMError

__all__ = ["format_response", "handle_error", "require_write_permission"]

F = TypeVar("F", bound=Callable[..., Any])


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
    if isinstance(data, (dict, list)):
        text = json.dumps(data, indent=2, default=str)
    else:
        text = str(data)

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
        from lm_mcp.config import LMConfig

        config = LMConfig()
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
