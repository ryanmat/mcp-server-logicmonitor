# Description: HTTP transport implementation for MCP server.
# Description: Uses Starlette and Uvicorn for streamable HTTP mode.

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.applications import Starlette

logger = logging.getLogger(__name__)


def create_asgi_app() -> "Starlette":
    """Create the ASGI application with MCP and health endpoints.

    Returns:
        Starlette application configured with routes and middleware.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    from lm_mcp.config import LMConfig

    config = LMConfig()

    async def health(request: Request) -> Response:
        """Detailed health check endpoint."""
        from lm_mcp.health import run_health_checks

        result = await run_health_checks(include_connectivity=False)
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
        """Kubernetes readiness probe endpoint."""
        from lm_mcp.health import run_health_checks

        include_connectivity = config.health_check_connectivity
        result = await run_health_checks(include_connectivity=include_connectivity)
        if result.status == "unhealthy":
            return Response(content="not ready", status_code=503)
        return Response(content="ready", status_code=200)

    async def mcp_endpoint(request: Request) -> Response:
        """MCP JSON-RPC endpoint for tool calls.

        This is a simplified HTTP endpoint for MCP. For full streamable
        HTTP support, consider using the MCP SDK's built-in ASGI support.
        """
        from lm_mcp.registry import TOOLS, get_tool_handler
        from lm_mcp.server import SESSION_TOOLS, get_client

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status_code=400,
            )

        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id")

        try:
            if method == "tools/list":
                result = [{"name": t.name, "description": t.description} for t in TOOLS]
                return JSONResponse({"jsonrpc": "2.0", "result": result, "id": req_id})

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if not tool_name:
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "error": {"code": -32602, "message": "Missing tool name"},
                            "id": req_id,
                        },
                        status_code=400,
                    )

                handler = get_tool_handler(tool_name)

                if tool_name in SESSION_TOOLS:
                    result = await handler(**arguments)
                else:
                    client = get_client()
                    result = await handler(client, **arguments)

                # Extract text content from result
                if result and len(result) > 0:
                    text = result[0].text
                    try:
                        content = json.loads(text)
                    except json.JSONDecodeError:
                        content = text
                else:
                    content = None

                return JSONResponse({"jsonrpc": "2.0", "result": content, "id": req_id})

            elif method == "resources/list":
                from lm_mcp.resources import RESOURCES

                result = [{"uri": str(r.uri), "name": r.name} for r in RESOURCES]
                return JSONResponse({"jsonrpc": "2.0", "result": result, "id": req_id})

            elif method == "prompts/list":
                from lm_mcp.prompts import PROMPTS

                result = [{"name": p.name, "description": p.description} for p in PROMPTS]
                return JSONResponse({"jsonrpc": "2.0", "result": result, "id": req_id})

            else:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                        "id": req_id,
                    },
                    status_code=400,
                )

        except ValueError as e:
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32602, "message": str(e)}, "id": req_id},
                status_code=400,
            )
        except Exception as e:
            logger.exception("Error handling MCP request")
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": req_id},
                status_code=500,
            )

    async def root(request: Request) -> Response:
        """Root endpoint with server info."""
        from lm_mcp import __version__

        return JSONResponse(
            {
                "name": "LogicMonitor MCP Server",
                "version": __version__,
                "transport": "http",
                "endpoints": {
                    "mcp": "/mcp",
                    "health": "/health",
                    "healthz": "/healthz",
                    "readyz": "/readyz",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    routes = [
        Route("/", root, methods=["GET"]),
        Route("/mcp", mcp_endpoint, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/healthz", healthz, methods=["GET"]),
        Route("/readyz", readyz, methods=["GET"]),
    ]

    # Configure CORS middleware
    cors_origins = config.cors_origins_list
    middleware = []
    if cors_origins:
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        )

    return Starlette(routes=routes, middleware=middleware)


async def create_http_server() -> None:
    """Create and run the HTTP server.

    Initializes the LogicMonitor client and starts Uvicorn.
    """
    import uvicorn

    from lm_mcp.auth import create_auth_provider
    from lm_mcp.client import LogicMonitorClient
    from lm_mcp.config import LMConfig
    from lm_mcp.server import _set_client
    from lm_mcp.session import get_session

    # Load config and create client
    config = LMConfig()
    auth = create_auth_provider(config)
    client = LogicMonitorClient(
        base_url=config.base_url,
        auth=auth,
        timeout=config.timeout,
        api_version=config.api_version,
        ingest_url=config.ingest_url,
    )
    _set_client(client)

    # Initialize session with config settings
    if config.session_enabled:
        session = get_session()
        session.max_history_size = config.session_history_size

    # Create ASGI app
    app = create_asgi_app()

    # Configure Uvicorn
    uvicorn_config = uvicorn.Config(
        app,
        host=config.http_host,
        port=config.http_port,
        log_level="info",
    )

    server = uvicorn.Server(uvicorn_config)

    logger.info(f"Starting HTTP server on {config.http_host}:{config.http_port}")

    try:
        await server.serve()
    finally:
        await client.close()
