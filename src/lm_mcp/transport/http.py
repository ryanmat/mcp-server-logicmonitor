# Description: HTTP transport implementation for MCP server.
# Description: Serves health, readiness and info routes over Starlette behind the HTTP middleware.

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from starlette.applications import Starlette
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Probe and info routes stay reachable without a token so orchestration works
# out of the box: their bodies carry no LM data, only component status. (Probes
# *can* send headers -- Kubernetes httpGet takes httpHeaders and curl takes -H --
# so an operator who wants them gated can front them with a proxy.) Only /health
# reaches the LM API, and only for a caller that passes the bearer check (or on a
# server with no token configured) when LM_HEALTH_CHECK_CONNECTIVITY is enabled.
_OPEN_PATHS = frozenset({"/", "/health", "/healthz", "/readyz"})


def _is_open_path(path: str) -> bool:
    """Match the probe allowlist, tolerating a trailing slash.

    Starlette redirects /healthz/ to /healthz, but that redirect never runs when
    auth rejects the request first, so a probe written with a trailing slash
    would start failing the moment a token is configured. Only exact members and
    their trailing-slash forms match; everything else stays gated.
    """
    return path in _OPEN_PATHS or path.rstrip("/") in _OPEN_PATHS


def _bearer_matches(headers: Iterable[tuple[bytes, bytes]], token: bytes) -> bool:
    """Return True when the ASGI headers carry ``Authorization: Bearer <token>``.

    Shared by the auth middleware and the /health connectivity gate so both
    accept exactly the same credentials.
    """
    provided = b""
    for name, value in headers:
        if name == b"authorization":
            provided = value
            break

    # RFC 7235 defines auth-scheme as case-insensitive. Only the credentials
    # are secret, so only they get the constant-time comparison; a missing or
    # malformed header degrades to comparing against empty bytes.
    scheme, _, credentials = provided.partition(b" ")
    return scheme.lower() == b"bearer" and secrets.compare_digest(credentials, token)


async def _send_json_error(
    send: Send,
    status: int,
    message: str,
    extra_headers: Iterable[tuple[bytes, bytes]] = (),
) -> None:
    """Answer an ASGI request with ``{"error": message}`` and the given status."""
    body = json.dumps({"error": message}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *extra_headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class BearerAuthMiddleware:
    """Require a bearer token on every route outside _OPEN_PATHS.

    Installed only when LM_HTTP_AUTH_TOKEN is configured. The allowlist is
    deliberate: any route added later is authenticated by default rather than
    silently exposed. Written as raw ASGI so this module keeps its runtime
    imports free of starlette, matching the rest of the transport.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _is_open_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        if _bearer_matches(scope.get("headers", []), self._token):
            await self.app(scope, receive, send)
            return

        await _send_json_error(send, 401, "Unauthorized", [(b"www-authenticate", b"Bearer")])


# Methods that carry no request body, so they have no Content-Type to check.
_BODYLESS_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _requires_json_body(path: str) -> bool:
    """Match the routes whose request bodies must be JSON; no route takes a body."""
    return False


def _media_type(headers: Iterable[tuple[bytes, bytes]]) -> str:
    """Return the request's Content-Type without parameters, lowercased; "" if absent."""
    for name, value in headers:
        if name == b"content-type":
            return value.decode("latin-1").split(";", 1)[0].strip().lower()
    return ""


class JsonContentTypeMiddleware:
    """Refuse a non-JSON request body with 415 on the routes _requires_json_body matches.

    A browser sends a text/plain or form POST cross-origin without a CORS
    preflight, so a page the operator has open could otherwise drive those
    routes on a server it can reach. Requiring application/json forces the
    preflight, which gets no CORS headers back, so the browser sends nothing
    further. Raw ASGI, like BearerAuthMiddleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] in _BODYLESS_METHODS
            or not _requires_json_body(scope["path"])
            or _media_type(scope.get("headers", [])) == "application/json"
        ):
            await self.app(scope, receive, send)
            return

        await _send_json_error(send, 415, "Content-Type must be application/json")


# Orchestrators probe by pod or container IP, which no Host allowlist names.
_HOST_EXEMPT_PATHS = frozenset({"/healthz", "/readyz"})


def _request_host(headers: Iterable[tuple[bytes, bytes]]) -> str:
    """Return the Host header's name without its port, lowercased; "" if absent.

    A bracketed IPv6 literal such as ``[::1]:8080`` yields the address inside the
    brackets.
    """
    for name, value in headers:
        if name == b"host":
            host = value.decode("latin-1").strip().lower()
            if host.startswith("["):
                end = host.find("]")
                return host[1:end] if end != -1 else ""
            return host.split(":", 1)[0]
    return ""


class HostAllowlistMiddleware:
    """Answer only requests whose Host header names this server, with 400 otherwise.

    A DNS-rebinding page points its own name at the server's address, so its
    requests arrive carrying that foreign name in Host. /healthz and /readyz stay
    exempt for probes. Raw ASGI, like BearerAuthMiddleware: Starlette's
    TrustedHostMiddleware has no path exemption and cuts an IPv6 literal at its
    first colon.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: frozenset[str]) -> None:
        self.app = app
        self._allowed = allowed_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["path"].rstrip("/") in _HOST_EXEMPT_PATHS
            or _request_host(scope.get("headers", [])) in self._allowed
        ):
            await self.app(scope, receive, send)
            return

        await _send_json_error(send, 400, "Invalid Host header")


def create_asgi_app() -> Starlette:
    """Create the ASGI application with the health and info endpoints.

    Returns:
        Starlette application configured with routes and middleware.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    from lm_mcp.config import get_config

    config = get_config()

    async def health(request: Request) -> Response:
        """Detailed health check endpoint.

        Adds the LM API connectivity check when LM_HEALTH_CHECK_CONNECTIVITY is on
        and the caller would pass the bearer check on a gated path: no inbound token
        is configured, or the request carries it. /health is an open path, so
        anonymous callers get the local checks only and cannot spend the portal's
        API quota.
        """
        from lm_mcp.health import run_health_checks

        include_connectivity = config.health_check_connectivity and (
            not config.http_auth_token
            or _bearer_matches(request.scope["headers"], config.http_auth_token.encode())
        )
        result = await run_health_checks(include_connectivity=include_connectivity)
        status_code = 200 if result.status == "healthy" else 503
        return JSONResponse(result.to_dict(), status_code=status_code)

    async def healthz(request: Request) -> Response:
        """Kubernetes liveness probe endpoint."""
        from lm_mcp.health import run_health_checks

        result = await run_health_checks(include_connectivity=False)
        if result.status == "unhealthy":
            return Response(content="unhealthy", status_code=503)
        return Response(content="ok", status_code=200)

    async def readyz(request: Request) -> Response:
        """Kubernetes readiness probe endpoint.

        Never calls the LM API: probes are unauthenticated and frequent, and a
        connectivity failure grades ``warn``, which could not change this response.
        """
        from lm_mcp.health import run_health_checks

        result = await run_health_checks(include_connectivity=False)
        if result.status == "unhealthy":
            return Response(content="not ready", status_code=503)
        return Response(content="ready", status_code=200)

    async def root(request: Request) -> Response:
        """Root endpoint with server info."""
        from lm_mcp import __version__

        return JSONResponse(
            {
                "name": "LogicMonitor MCP Server",
                "version": __version__,
                "transport": "http",
                "endpoints": {
                    "health": "/health",
                    "healthz": "/healthz",
                    "readyz": "/readyz",
                },
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    routes = [
        Route("/", root, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/healthz", healthz, methods=["GET"]),
        Route("/readyz", readyz, methods=["GET"]),
    ]

    # Order matters: the first entry is outermost. The Host check runs first, so
    # a request addressed to a foreign name is refused before anything else. The
    # Content-Type check is innermost, so an anonymous caller gets the 401
    # whatever it sends.
    middleware = [Middleware(HostAllowlistMiddleware, allowed_hosts=config.http_host_allowlist)]

    if config.http_auth_token:
        middleware.append(Middleware(BearerAuthMiddleware, token=config.http_auth_token))
    else:
        logger.warning(
            "Inbound HTTP authentication is disabled; every route accepts "
            "unauthenticated requests. Set LM_HTTP_AUTH_TOKEN to require a bearer token."
        )
    middleware.append(Middleware(JsonContentTypeMiddleware))

    return Starlette(routes=routes, middleware=middleware)


async def create_http_server() -> None:
    """Create and run the HTTP server.

    Initializes the LogicMonitor client and starts Uvicorn.
    """
    import uvicorn

    from lm_mcp.auth import create_auth_provider
    from lm_mcp.client import LogicMonitorClient
    from lm_mcp.config import get_config
    from lm_mcp.server import _set_client
    from lm_mcp.session import get_session

    # Load config. Multi-portal mode is stdio-only and is rejected at config
    # construction, so the HTTP transport always binds a fixed client at startup.
    config = get_config()
    auth = create_auth_provider(config)
    client = LogicMonitorClient(
        base_url=config.base_url,
        auth=auth,
        timeout=config.timeout,
        max_retries=config.max_retries,
        retry_after_cap=config.retry_after_cap_seconds,
        ingest_url=config.ingest_url,
    )
    _set_client(client)

    from lm_mcp.transport import bootstrap

    backends = bootstrap.bootstrap_backends(config)

    # Initialize session with config settings
    get_session().max_history_size = config.session_history_size

    # Create ASGI app
    app = create_asgi_app()

    # Configure Uvicorn (with optional TLS)
    ssl_kwargs: dict = {}
    if config.http_ssl_certfile:
        ssl_kwargs["ssl_certfile"] = config.http_ssl_certfile
    if config.http_ssl_keyfile:
        ssl_kwargs["ssl_keyfile"] = config.http_ssl_keyfile
    if config.http_ssl_keyfile_password:
        ssl_kwargs["ssl_keyfile_password"] = config.http_ssl_keyfile_password

    uvicorn_config = uvicorn.Config(
        app,
        host=config.http_host,
        port=config.http_port,
        log_level="info",
        **ssl_kwargs,
    )

    server = uvicorn.Server(uvicorn_config)

    scheme = "https" if config.http_ssl_certfile else "http"
    logger.info(f"Starting {scheme} server on {config.http_host}:{config.http_port}")

    try:
        await server.serve()
    finally:
        await backends.close()
        if client is not None:
            await client.close()
