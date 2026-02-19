# Description: Structured logging module for LogicMonitor MCP server.
# Description: Provides helper functions for API request and write audit logging.

from __future__ import annotations

import logging

# Module-level loggers
_client_logger = logging.getLogger("lm_mcp.client")
_audit_logger = logging.getLogger("lm_mcp.audit")


def log_api_request(
    method: str,
    path: str,
    params: dict | None = None,
) -> None:
    """Log an API request at DEBUG level.

    Uses the lm_mcp.client logger. Only produces output when the logger
    level is set to DEBUG or lower; zero overhead otherwise due to
    isEnabledFor guard.

    Args:
        method: HTTP method.
        path: API resource path.
        params: Query parameters.
    """
    if _client_logger.isEnabledFor(logging.DEBUG):
        _client_logger.debug(
            "%s %s params=%s",
            method,
            path,
            params,
        )


def log_api_response(
    status_code: int,
    elapsed_seconds: float,
    path: str,
) -> None:
    """Log an API response at DEBUG level.

    Args:
        status_code: HTTP response status code.
        elapsed_seconds: Request duration in seconds.
        path: API resource path.
    """
    if _client_logger.isEnabledFor(logging.DEBUG):
        _client_logger.debug(
            "%s %d %.0fms",
            path,
            status_code,
            elapsed_seconds * 1000,
        )


# Prefixes that identify write operations
WRITE_TOOL_PREFIXES = (
    "create_",
    "update_",
    "delete_",
    "acknowledge_",
    "add_",
    "run_",
    "bulk_",
    "import_",
    "ingest_",
    "push_",
    "launch_",
    "cancel_",
    "relaunch_",
)


def is_write_tool(tool_name: str) -> bool:
    """Check if a tool name indicates a write operation.

    Args:
        tool_name: MCP tool name to check.

    Returns:
        True if the tool performs write/modify operations.
    """
    return any(tool_name.startswith(prefix) for prefix in WRITE_TOOL_PREFIXES)


def log_write_operation(
    tool_name: str,
    arguments: dict,
    success: bool,
) -> None:
    """Log a write operation for audit trail purposes.

    Successful operations are logged at INFO level.
    Failed operations are logged at WARNING level.

    Args:
        tool_name: Name of the MCP tool.
        arguments: Arguments passed to the tool.
        success: Whether the operation succeeded.
    """
    if success:
        _audit_logger.info(
            "Write operation: %s args=%s",
            tool_name,
            arguments,
        )
    else:
        _audit_logger.warning(
            "Write operation failed: %s args=%s",
            tool_name,
            arguments,
        )
