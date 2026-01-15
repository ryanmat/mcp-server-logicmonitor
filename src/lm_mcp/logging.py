# Description: Structured logging module for LogicMonitor MCP server.
# Description: Provides log event types and helper functions for API operations.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
