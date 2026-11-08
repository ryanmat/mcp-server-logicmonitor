# Description: Shared fixtures for the error tests: the documented code set (spec R2.7).
# Description: Also raises a transport failure the way the client does, cause attached.

from __future__ import annotations

from lm_mcp.client._retry import transport_error
from lm_mcp.exceptions import LMError

DOCUMENTED_CODES = {
    "NOT_FOUND",
    "INVALID_REQUEST",
    "WRITE_DISABLED",
    "RATE_LIMITED",
    "UPSTREAM_ERROR",
    "TIMEOUT",
    "AUTH_FAILED",
    "SCOPE_MISSING",
    "FEATURE_DISABLED",
    "REJECTED_BY_TOOL",
}
CATEGORIES = {"transient", "validation", "business", "permission"}


def client_raised(cause: Exception) -> LMError:
    """Raise transport_error the way the client does, so __cause__ is the httpx error."""
    try:
        try:
            raise cause
        except Exception as inner:
            raise transport_error(inner, "LogicMonitor API", "GET", "https://x/y") from inner
    except LMError as wrapped:
        return wrapped
