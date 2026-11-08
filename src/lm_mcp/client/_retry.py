# Description: Retry policy and transport-error translation shared by the HTTP clients.
# Description: Decides which responses may be resent and how long to wait between tries.

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable

import httpx

from lm_mcp.exceptions import LMConnectionError

# Methods safe to resend after a 5xx: repeating them cannot apply a change twice.
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE"})

# Default ceiling in seconds on a wait a server's Retry-After can impose.
DEFAULT_RETRY_AFTER_CAP = 120

# Failures before any response arrives: timeouts, connect, read and write errors,
# protocol and proxy errors. Each is translated to LMConnectionError and not
# resent: past the connect phase the server may already have acted.
TRANSPORT_ERRORS = (httpx.TransportError,)


def should_retry(method: str, status: int) -> bool:
    """Return whether a response with this status may be retried for this method.

    A 429 means the request was refused unprocessed, so any method is resent.
    A 5xx may come after the server applied the change, so only idempotent
    methods are resent; a POST or PATCH could otherwise create or apply twice.
    """
    if status == 429:
        return True
    return status >= 500 and method.upper() in IDEMPOTENT_METHODS


def retry_after_seconds(response: httpx.Response) -> int | None:
    """Return a response's Retry-After in whole seconds, or None if absent or not a number."""
    if "Retry-After" not in response.headers:
        return None
    with contextlib.suppress(ValueError):
        return int(response.headers["Retry-After"])
    return None


def backoff(attempt: int, retry_after: int | None, cap: int) -> float:
    """Seconds to wait before retry ``attempt + 1``.

    Exponential backoff with jitter spreads out retries from many clients. A
    server's Retry-After can lengthen the wait but never shorten it, and the
    result never exceeds ``cap``.
    """
    base_backoff = 2.0**attempt
    wait = base_backoff + random.uniform(0, 0.5 * base_backoff)
    if retry_after is not None:
        wait = max(retry_after, wait)
    return min(wait, cap)


def transport_error(exc: Exception, service: str, method: str, url: str) -> LMConnectionError:
    """Translate an httpx transport failure into LMConnectionError.

    httpx often raises these with an empty message, so the result always names
    the failure kind, the method and the URL.
    """
    if isinstance(exc, httpx.TimeoutException):
        what = "timed out"
    elif isinstance(exc, httpx.ConnectError):
        what = "could not connect"
    elif isinstance(exc, (httpx.NetworkError, httpx.ProtocolError)):
        what = "lost its connection"
    else:
        what = "failed"
    detail = str(exc) or "no detail from the HTTP library"
    return LMConnectionError(
        f"{service} request {method} {url} {what} ({type(exc).__name__}: {detail})"
    )


async def run(
    send: Callable[[], Awaitable[httpx.Response]],
    *,
    method: str,
    service: str,
    url: str,
    max_retries: int,
    retry_after_cap: int,
) -> httpx.Response:
    """Send a request, resending it as the retry policy allows, and return the last response.

    A transport failure raises LMConnectionError and is not resent. A 429, or a 5xx
    for an idempotent method, is resent up to ``max_retries`` times after
    :func:`backoff`. The response returned can still be an error; the caller maps it.

    Args:
        send: Sends the request once and returns its response.
        method: HTTP method, which decides whether a 5xx is resent.
        service: Name of the API for the transport error, e.g. "LogicMonitor API".
        url: Full URL, for the transport error.
        max_retries: Most resends after the first attempt.
        retry_after_cap: Ceiling in seconds on any one wait.
    """
    attempt = 0
    while True:
        try:
            response = await send()
        except TRANSPORT_ERRORS as e:
            raise transport_error(e, service, method, url) from e
        if not should_retry(method, response.status_code) or attempt >= max_retries:
            return response
        await asyncio.sleep(backoff(attempt, retry_after_seconds(response), retry_after_cap))
        attempt += 1
