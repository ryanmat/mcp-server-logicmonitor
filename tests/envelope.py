# Description: Shared fixtures for the error tests: the documented code set (spec R2.7),
# Description: an envelope assertion, and a transport failure raised the way the client does.

from __future__ import annotations

import json

from lm_mcp.client._retry import transport_error
from lm_mcp.exceptions import LMError
from lm_mcp.tools import ErrorContent

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
ENVELOPE_KEYS = {"code", "message", "details", "retry_after", "errorCategory", "isRetryable"}


def envelope(result: list) -> dict:
    """Return the inner error dict of a tool result after checking the envelope's shape."""
    assert len(result) == 1
    assert isinstance(result[0], ErrorContent)
    body = json.loads(result[0].text)
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == ENVELOPE_KEYS
    assert error["code"] in DOCUMENTED_CODES
    assert error["errorCategory"] in CATEGORIES
    assert isinstance(error["isRetryable"], bool)
    assert error["retry_after"] is None or isinstance(error["retry_after"], int)
    assert error["details"] is None or isinstance(error["details"], dict)
    assert isinstance(error["message"], str) and error["message"]
    return error


def client_raised(cause: Exception) -> LMError:
    """Raise transport_error the way the client does, so __cause__ is the httpx error."""
    try:
        try:
            raise cause
        except Exception as inner:
            raise transport_error(inner, "LogicMonitor API", "GET", "https://x/y") from inner
    except LMError as wrapped:
        return wrapped
