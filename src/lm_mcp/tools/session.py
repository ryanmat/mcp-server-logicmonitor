# Description: Session management tools for LogicMonitor MCP server.
# Description: Provides tools to view/manage session context, variables, and history.

from __future__ import annotations

from mcp.types import TextContent

from lm_mcp.session import get_session
from lm_mcp.tools import format_response, handle_error


async def get_session_context() -> list[TextContent]:
    """Get the current session context.

    Returns the current session state including:
    - Last results from recent operations (for implicit ID resolution)
    - User-defined variables
    - Recent tool call history

    Returns:
        List of TextContent with session context data.
    """
    try:
        session = get_session()
        return format_response(session.to_dict())
    except Exception as e:
        return handle_error(e)


async def set_session_variable(
    name: str,
    value: str | int | float | bool | list | dict,
) -> list[TextContent]:
    """Set a user-defined session variable.

    Variables persist across tool calls within the same session.
    Useful for storing device IDs, filter strings, or other values
    for reuse in subsequent operations.

    Args:
        name: Variable name (must be a valid identifier).
        value: Variable value (must be JSON-serializable).

    Returns:
        List of TextContent with confirmation.
    """
    try:
        if not name or not isinstance(name, str):
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_ARGUMENT",
                    "message": "Variable name must be a non-empty string",
                }
            )

        session = get_session()
        session.set_variable(name, value)

        return format_response(
            {
                "success": True,
                "message": f"Variable '{name}' set successfully",
                "name": name,
                "value": value,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_session_variable(
    name: str,
) -> list[TextContent]:
    """Get a user-defined session variable.

    Args:
        name: Variable name to retrieve.

    Returns:
        List of TextContent with variable value or error if not found.
    """
    try:
        session = get_session()
        value = session.get_variable(name)

        if value is None and name not in session.variables:
            return format_response(
                {
                    "error": True,
                    "code": "VARIABLE_NOT_FOUND",
                    "message": f"Variable '{name}' not found in session",
                    "suggestion": "Use get_session_context to see all available variables",
                }
            )

        return format_response(
            {
                "name": name,
                "value": value,
            }
        )
    except Exception as e:
        return handle_error(e)


async def delete_session_variable(
    name: str,
) -> list[TextContent]:
    """Delete a user-defined session variable.

    Args:
        name: Variable name to delete.

    Returns:
        List of TextContent with confirmation or error if not found.
    """
    try:
        session = get_session()
        deleted = session.delete_variable(name)

        if not deleted:
            return format_response(
                {
                    "error": True,
                    "code": "VARIABLE_NOT_FOUND",
                    "message": f"Variable '{name}' not found in session",
                }
            )

        return format_response(
            {
                "success": True,
                "message": f"Variable '{name}' deleted successfully",
            }
        )
    except Exception as e:
        return handle_error(e)


async def clear_session_context() -> list[TextContent]:
    """Clear all session context.

    Resets:
    - All last operation results
    - All user-defined variables
    - Tool call history

    Returns:
        List of TextContent with confirmation.
    """
    try:
        session = get_session()
        session.clear()

        return format_response(
            {
                "success": True,
                "message": "Session context cleared",
            }
        )
    except Exception as e:
        return handle_error(e)


async def list_session_history(
    limit: int = 10,
) -> list[TextContent]:
    """List recent tool call history.

    Args:
        limit: Maximum number of history entries to return (default: 10, max: 50).

    Returns:
        List of TextContent with history entries.
    """
    try:
        session = get_session()

        # Clamp limit
        limit = max(1, min(limit, 50))

        history = session.history[-limit:]
        entries = [
            {
                "tool": entry.tool_name,
                "timestamp": entry.timestamp,
                "success": entry.success,
                "summary": entry.result_summary,
                "arguments": entry.arguments,
            }
            for entry in reversed(history)  # Most recent first
        ]

        return format_response(
            {
                "count": len(entries),
                "total_history": len(session.history),
                "history": entries,
            }
        )
    except Exception as e:
        return handle_error(e)
