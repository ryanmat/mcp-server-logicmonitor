# Description: Structured logging module for LogicMonitor MCP server.
# Description: Provides log event types and helper functions for API operations.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

# Module-level loggers
_client_logger = logging.getLogger("lm_mcp.client")
_audit_logger = logging.getLogger("lm_mcp.audit")


class LogLevel(str, Enum):
    """Log severity levels aligned with MCP logging specification."""

    DEBUG = "debug"
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    ALERT = "alert"
    EMERGENCY = "emergency"


@dataclass
class LogEvent:
    """Structured log event for MCP logging.

    Attributes:
        level: Log severity level.
        logger: Logger name (e.g., 'lm_mcp.client').
        message: Human-readable log message.
        data: Additional structured data for the event.
    """

    level: LogLevel
    logger: str
    message: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert event to dictionary format.

        Returns:
            Dictionary representation of the event.
        """
        return {
            "level": self.level.value,
            "logger": self.logger,
            "message": self.message,
            "data": self.data,
        }


def create_rate_limit_event(
    path: str,
    attempt: int,
    retry_after: int,
) -> LogEvent:
    """Create a log event for rate limit hits.

    Args:
        path: API path that was rate limited.
        attempt: Retry attempt number.
        retry_after: Seconds to wait before retry.

    Returns:
        LogEvent for the rate limit hit.
    """
    return LogEvent(
        level=LogLevel.WARNING,
        logger="lm_mcp.client",
        message=f"Rate limit hit on {path}, retry attempt {attempt} after {retry_after}s",
        data={
            "path": path,
            "attempt": attempt,
            "retry_after": retry_after,
        },
    )


def create_server_error_event(
    path: str,
    status_code: int,
    attempt: int,
) -> LogEvent:
    """Create a log event for server errors.

    Args:
        path: API path that returned an error.
        status_code: HTTP status code.
        attempt: Retry attempt number.

    Returns:
        LogEvent for the server error.
    """
    return LogEvent(
        level=LogLevel.WARNING,
        logger="lm_mcp.client",
        message=f"Server error {status_code} on {path}, retry attempt {attempt}",
        data={
            "path": path,
            "status_code": status_code,
            "attempt": attempt,
        },
    )


def create_slow_request_event(
    path: str,
    method: str,
    elapsed_seconds: float,
) -> LogEvent:
    """Create a log event for slow requests.

    Args:
        path: API path.
        method: HTTP method.
        elapsed_seconds: Request duration in seconds.

    Returns:
        LogEvent for the slow request.
    """
    return LogEvent(
        level=LogLevel.INFO,
        logger="lm_mcp.client",
        message=f"Slow request: {method} {path} took {elapsed_seconds:.2f}s",
        data={
            "path": path,
            "method": method,
            "elapsed_seconds": elapsed_seconds,
        },
    )


def create_auth_failure_event(
    status_code: int,
    message: str,
) -> LogEvent:
    """Create a log event for authentication failures.

    Args:
        status_code: HTTP status code.
        message: Error message.

    Returns:
        LogEvent for the auth failure.
    """
    return LogEvent(
        level=LogLevel.ERROR,
        logger="lm_mcp.auth",
        message=f"Authentication failed: {message}",
        data={
            "status_code": status_code,
            "message": message,
        },
    )


def create_api_request_event(
    method: str,
    path: str,
    params: dict | None = None,
) -> dict:
    """Create a structured dict for an API request event.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.).
        path: API resource path.
        params: Query parameters sent with the request.

    Returns:
        Dictionary describing the API request.
    """
    return {
        "event": "api_request",
        "method": method,
        "path": path,
        "params": params,
    }


def create_api_response_event(
    status_code: int,
    elapsed_seconds: float,
    path: str,
) -> dict:
    """Create a structured dict for an API response event.

    Args:
        status_code: HTTP response status code.
        elapsed_seconds: Request duration in seconds.
        path: API resource path.

    Returns:
        Dictionary describing the API response.
    """
    return {
        "event": "api_response",
        "status_code": status_code,
        "elapsed_ms": round(elapsed_seconds * 1000, 1),
        "path": path,
    }


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


def create_write_operation_event(
    tool_name: str,
    arguments: dict,
    success: bool,
) -> dict:
    """Create a structured dict for a write operation audit event.

    Args:
        tool_name: Name of the MCP tool that performed the write.
        arguments: Arguments passed to the tool.
        success: Whether the operation succeeded.

    Returns:
        Dictionary describing the write operation.
    """
    return {
        "event": "write_operation",
        "tool": tool_name,
        "arguments": arguments,
        "success": success,
    }


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
