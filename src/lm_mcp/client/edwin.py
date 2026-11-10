# Description: Async HTTP and websocket client for the Edwin AI API at <portal>.dexda.ai.
# Description: Exchanges the client credential for a cached JWT and maps Edwin's errors.

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator
from time import monotonic
from typing import Any

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.typing import Subprotocol

from lm_mcp.client import _retry
from lm_mcp.client._retry import DEFAULT_RETRY_AFTER_CAP, retry_after_seconds
from lm_mcp.client.api import _check_path
from lm_mcp.exceptions import (
    AuthenticationError,
    ConfigurationError,
    LMError,
    NotFoundError,
    RateLimitError,
    ScopeMissingError,
    ServerError,
)
from lm_mcp.logging import log_api_request, log_api_response

_SERVICE = "Edwin AI"

# A cached token is exchanged again this many seconds before it expires.
REFRESH_MARGIN_SECONDS = 60

# The scope each Edwin endpoint needs, by path prefix, as observed with the sweep's
# read-scope and full-scope credentials (2026-11-06 to 2026-11-10). A path missing
# here answered at the read scopes, or has not been probed.
SCOPE_TABLE: tuple[tuple[str, str], ...] = (
    ("/ui/query/metrics", "query_aggregate"),
    ("/ui/query/records", "query_records"),
    ("/ui/query/record/", "query_record"),
)

CREDENTIAL_HINT = (
    "Check EDWIN_CLIENT_ID and EDWIN_CLIENT_TOKEN; an Edwin API credential can expire."
)


# The websockets library logs every handshake header at DEBUG, and the JWT travels in
# Sec-WebSocket-Protocol; this logger stops at INFO whatever level the root is set to.
_ws_logger = logging.getLogger("lm_mcp.client.edwin.websocket")
_ws_logger.setLevel(logging.INFO)


def websocket_url(host: str, path: str) -> str:
    """The websocket URL for ``path`` on an Edwin host: wss for https, ws for http."""
    scheme, rest = host.split("://", 1)
    return f"{'wss' if scheme == 'https' else 'ws'}://{rest}{path}"


def required_scope(path: str) -> str | None:
    """Return the scope the Edwin endpoint at ``path`` needs, or None when the table has none."""
    for prefix, scope in SCOPE_TABLE:
        if path.startswith(prefix):
            return scope
    return None


def _edwin_message(response: httpx.Response) -> str:
    """Edwin's words for a failed response: ``message``, ``error`` or ``detail``, else the text.

    The query API answers ``{"code", "message", "id"}``, the token exchange
    ``{"error"}``, and the agent API ``{"detail"}``.
    """
    text = response.text or response.reason_phrase
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        return text
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or body.get("detail") or text)
    return text


class EdwinClient:
    """Async client for one Edwin AI host.

    Each request carries a JWT from ``POST /auth/token``, exchanged with the client
    credential and cached in memory until ``REFRESH_MARGIN_SECONDS`` before it
    expires. A 401 drops the cached token, exchanges once more and resends once.
    The credential and the token are never logged.
    """

    def __init__(
        self,
        host: str,
        client_id: str,
        client_secret: str,
        *,
        timeout: int = 30,
        max_retries: int = 3,
        retry_after_cap: int = DEFAULT_RETRY_AFTER_CAP,
    ):
        """Initialize the client.

        Args:
            host: Edwin base URL, e.g. ``https://acme.dexda.ai``.
            client_id: Edwin API credential client id.
            client_secret: That credential's secret.
            timeout: Request timeout in seconds.
            max_retries: Most resends of a 429, or of a 5xx on an idempotent method.
            retry_after_cap: Longest wait in seconds between retries.
        """
        self.host = host.rstrip("/")
        self.max_retries = max_retries
        self.retry_after_cap = retry_after_cap
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires = 0.0
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> EdwinClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit async context manager and close client."""
        await self.close()

    async def _send(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict | None = None,
        json_body: Any = None,
        form: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send one request through the shared retry policy and return the last response."""
        url = f"{self.host}{path}"
        log_api_request(method, path, params)
        started = monotonic()
        response = await _retry.run(
            lambda: self._client.request(
                method, url, headers=headers, params=params, json=json_body, data=form
            ),
            method=method,
            service=_SERVICE,
            url=url,
            max_retries=self.max_retries,
            retry_after_cap=self.retry_after_cap,
        )
        log_api_response(response.status_code, monotonic() - started, path)
        return response

    async def _access_token(self) -> str:
        """Return the cached JWT, exchanging the credential when none is held or it nears expiry.

        Raises:
            AuthenticationError: If Edwin refuses the credential.
        """
        if self._token is not None and monotonic() < self._token_expires - REFRESH_MARGIN_SECONDS:
            return self._token
        response = await self._send(
            "POST",
            "/auth/token",
            form={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        if response.status_code in (400, 401):
            raise AuthenticationError(
                f"Edwin AI refused the client credential at POST /auth/token "
                f"({response.status_code} {_edwin_message(response)})",
                suggestion=CREDENTIAL_HINT,
            )
        if response.status_code >= 400:
            self._raise_for_status("POST", "/auth/token", response)
        body = response.json()
        self._token = str(body["access_token"])
        self._token_expires = monotonic() + int(body["expires_in"])
        return self._token

    def _raise_for_status(self, method: str, path: str, response: httpx.Response) -> None:
        """Raise the client exception for an Edwin error response.

        Raises:
            AuthenticationError: For 401.
            ScopeMissingError: For 403, naming the scope from :data:`SCOPE_TABLE`.
            NotFoundError: For 404.
            RateLimitError: For 429.
            ServerError: For 5xx.
            LMError: ``HTTP_<status>`` for any other 4xx.
        """
        status = response.status_code
        message = _edwin_message(response)
        where = f"{method} {path}"
        if status == 401:
            raise AuthenticationError(
                f"Edwin AI refused the token for {where} after one refresh",
                suggestion=CREDENTIAL_HINT,
                details=message,
            )
        if status == 403:
            scope = required_scope(path)
            if scope is None:
                raise ScopeMissingError(
                    f"Edwin AI refused {where}: the credential's scopes do not cover it",
                    scope=None,
                    details=message,
                )
            raise ScopeMissingError(
                f"Edwin AI credential lacks the {scope} scope that {where} needs",
                scope=scope,
                suggestion=f"Add the {scope} scope to the Edwin API credential "
                "EDWIN_CLIENT_ID names, or set a credential that has it.",
                details=message,
            )
        if status == 404:
            raise NotFoundError(f"Edwin AI found nothing at {where}: {message}")
        if status == 429:
            raise RateLimitError(
                f"Edwin AI rate-limited {where}: {message}",
                retry_after=retry_after_seconds(response),
            )
        if status >= 500:
            raise ServerError(
                f"Edwin AI answered {status} for {where}: {message}",
                suggestion="Edwin AI returned a server error. Try again later.",
            )
        raise LMError(
            message=f"Edwin AI refused {where} ({status}): {message}",
            code=f"HTTP_{status}",
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
    ) -> Any:
        """Make an authenticated request to the Edwin API.

        Args:
            method: HTTP method.
            path: API path under the host, e.g. ``/ui/query/records``.
            params: Query parameters.
            json_body: JSON body.

        Returns:
            The parsed JSON response.

        Raises:
            ValidationError: If a path segment could escape its resource.
            LMError: The mapped Edwin error; see :meth:`_raise_for_status`.
        """
        _check_path(path)

        async def send() -> httpx.Response:
            token = await self._access_token()
            return await self._send(
                method,
                path,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                json_body=json_body,
            )

        response = await send()
        if response.status_code == 401:
            self._token = None
            response = await send()
        if response.status_code >= 400:
            self._raise_for_status(method, path, response)
        return response.json()

    @contextlib.asynccontextmanager
    async def websocket(self, path: str) -> AsyncIterator[ClientConnection]:
        """Open a websocket to ``path`` with the JWT as its only subprotocol.

        Edwin reads the token from ``Sec-WebSocket-Protocol`` and echoes it; no
        Authorization header is sent.

        Raises:
            ValidationError: If a path segment could escape its resource.
            AuthenticationError: If Edwin refuses the credential at the exchange.
        """
        _check_path(path)
        token = await self._access_token()
        async with connect(
            websocket_url(self.host, path),
            subprotocols=[Subprotocol(token)],
            logger=_ws_logger,
        ) as ws:
            yield ws

    async def get(self, path: str, params: dict | None = None) -> Any:
        """Make a GET request."""
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json_body: Any = None) -> Any:
        """Make a POST request."""
        return await self.request("POST", path, json_body=json_body)


def build_edwin_client(portal: str | None) -> EdwinClient | None:
    """Build the Edwin client for one portal, or None when Edwin is not configured.

    The host is ``EDWIN_HOST`` when set, else ``https://<portal name>.dexda.ai`` from
    the portal's first label; the timeout and retry limits come from the LM config.

    Args:
        portal: LogicMonitor portal hostname, e.g. ``acme.logicmonitor.com``.

    Raises:
        ConfigurationError: If Edwin is configured with no EDWIN_HOST and no portal.
    """
    from lm_mcp.config import get_config
    from lm_mcp.edwin_config import load_edwin_config

    edwin = load_edwin_config()
    if edwin is None:
        return None
    if edwin.host:
        host = edwin.host
    elif portal:
        host = f"https://{portal.split('.')[0]}.dexda.ai"
    else:
        raise ConfigurationError("No Edwin AI host: set EDWIN_HOST or LM_PORTAL")
    # load_edwin_config returns settings only when both credentials are set.
    assert edwin.client_id is not None and edwin.client_token is not None
    config = get_config()
    return EdwinClient(
        host,
        edwin.client_id,
        edwin.client_token,
        timeout=config.timeout,
        max_retries=config.max_retries,
        retry_after_cap=config.retry_after_cap_seconds,
    )
