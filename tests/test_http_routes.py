# Description: R1.5, R1.6, R4.1: the HTTP transport's routes on a live socket, /mcp from the SDK.
# Description: /mcp answers stateless JSON; the analysis API answers 404; no preflight gets CORS.

from __future__ import annotations

import importlib

import httpx
import pytest
from mcp.types import LATEST_PROTOCOL_VERSION

from tests.live_uvicorn import free_port, live_uvicorn

# 16 characters: the configured minimum, and below the length a secret scanner flags.
TOKEN = "route-test-tok16"

# The Accept header a Streamable HTTP client sends; the SDK refuses a POST without application/json.
_MCP_ACCEPT = {"Accept": "application/json, text/event-stream"}
_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": LATEST_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "route-test", "version": "0"},
    },
}

_REMOVED_ROUTES = [
    ("POST", "/api/v1/analyze", {"json": {"workflow": "health_check", "arguments": {}}}),
    ("GET", "/api/v1/analysis/x", {}),
    ("POST", "/api/v1/webhooks/alert", {"json": {"deviceId": 1, "alertId": 2}}),
]


@pytest.fixture
def http_env(monkeypatch):
    """A single-portal HTTP start on a free loopback port with no inbound token."""
    for name in (
        "LM_MULTI_PORTAL",
        "LM_HTTP_AUTH_TOKEN",
        "LM_HTTP_ALLOW_UNAUTHENTICATED",
        "LM_HEALTH_CHECK_CONNECTIVITY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_TRANSPORT", "http")
    monkeypatch.setenv("LM_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("LM_HTTP_PORT", str(free_port("127.0.0.1")))


async def _send(monkeypatch, requests):
    """Start create_http_server on a real socket and send each (method, path, httpx kwargs)."""
    from lm_mcp.transport.http import create_http_server

    live = live_uvicorn(monkeypatch)
    async with (
        live(create_http_server()) as port,
        httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client,
    ):
        return [await client.request(method, path, **kwargs) for method, path, kwargs in requests]


async def test_health_and_readyz_answer(http_env, monkeypatch):
    health, readyz = await _send(monkeypatch, [("GET", "/health", {}), ("GET", "/readyz", {})])

    assert health.status_code == 200
    assert readyz.status_code == 200


async def test_removed_routes_are_404(http_env, monkeypatch):
    responses = await _send(monkeypatch, _REMOVED_ROUTES)

    assert [r.status_code for r in responses] == [404, 404, 404]


async def test_mcp_initialize_answers_through_the_sdk_stateless(http_env, monkeypatch):
    """R4.1: the SDK's session manager answers initialize as JSON, with no session id."""
    (response,) = await _send(
        monkeypatch, [("POST", "/mcp", {"json": _INITIALIZE, "headers": _MCP_ACCEPT})]
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in response.headers
    result = response.json()["result"]
    assert result["serverInfo"]["name"] == "logicmonitor"
    assert result["protocolVersion"] == LATEST_PROTOCOL_VERSION


async def test_mcp_body_over_4_mib_is_413(http_env, monkeypatch):
    """README and the CHANGELOG say 4 MiB; the server sets that limit itself."""
    from lm_mcp.transport.http import _MCP_MAX_BODY_BYTES

    oversized = b"[" + b" " * _MCP_MAX_BODY_BYTES + b"]"
    headers = {**_MCP_ACCEPT, "Content-Type": "application/json"}

    (response,) = await _send(
        monkeypatch, [("POST", "/mcp", {"content": oversized, "headers": headers})]
    )

    assert _MCP_MAX_BODY_BYTES == 4 * 1024 * 1024
    assert response.status_code == 413


async def test_mcp_body_limit_is_the_servers_not_the_sdk_default(http_env, monkeypatch):
    """With the server's limit cut to 1 KiB, a 2 KiB initialize gets 413 from the mount."""
    monkeypatch.setattr("lm_mcp.transport.http._MCP_MAX_BODY_BYTES", 1024)
    padded = {**_INITIALIZE, "params": {**_INITIALIZE["params"], "pad": "x" * 2048}}

    (response,) = await _send(
        monkeypatch, [("POST", "/mcp", {"json": padded, "headers": _MCP_ACCEPT})]
    )

    assert response.status_code == 413


async def test_preflight_gets_no_cors_answer_with_origins_set(http_env, monkeypatch):
    """R1.6: the server has no CORS support, so LM_CORS_ORIGINS changes nothing."""
    monkeypatch.setenv("LM_CORS_ORIGINS", "https://example.com")
    origin = {"Origin": "https://example.com", "Access-Control-Request-Method": "GET"}

    (response,) = await _send(monkeypatch, [("OPTIONS", "/health", {"headers": origin})])

    assert "access-control-allow-origin" not in response.headers


async def test_mcp_refuses_a_non_json_body_with_415(http_env, monkeypatch):
    """The Content-Type middleware answers before the SDK, whose own check would say 400."""
    plain = {"content": "{}", "headers": {**_MCP_ACCEPT, "Content-Type": "text/plain"}}

    (response,) = await _send(monkeypatch, [("POST", "/mcp", plain)])

    assert response.status_code == 415
    assert response.json() == {"error": "Content-Type must be application/json"}


async def test_bearer_middleware_refuses_mcp_without_the_token(http_env, monkeypatch):
    """With a token set, /mcp is 401 before the SDK sees the request, and answered after."""
    monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", TOKEN)
    anonymous = {"json": _INITIALIZE, "headers": _MCP_ACCEPT}
    authorized = {
        "json": _INITIALIZE,
        "headers": {**_MCP_ACCEPT, "Authorization": f"Bearer {TOKEN}"},
    }

    refused, answered = await _send(
        monkeypatch, [("POST", "/mcp", anonymous), ("POST", "/mcp", authorized)]
    )

    assert refused.status_code == 401
    assert refused.headers["www-authenticate"] == "Bearer"
    assert answered.status_code == 200
    assert answered.json()["result"]["serverInfo"]["name"] == "logicmonitor"


async def test_root_listing_names_the_health_routes_and_mcp(http_env, monkeypatch):
    (root,) = await _send(monkeypatch, [("GET", "/", {})])

    assert root.json()["endpoints"] == {
        "health": "/health",
        "healthz": "/healthz",
        "readyz": "/readyz",
        "mcp": "/mcp",
    }


@pytest.mark.parametrize("level", [None, "debug", "error"])
async def test_uvicorn_log_level_follows_lm_log_level(http_env, monkeypatch, level):
    """R4.6: uvicorn's loggers take LM_LOG_LEVEL (warning when unset), where info was fixed."""
    import logging

    from lm_mcp.transport.http import create_http_server

    if level is None:
        monkeypatch.delenv("LM_LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("LM_LOG_LEVEL", level)
    expected_name = level or "warning"
    names = ("uvicorn.error", "uvicorn.access")
    before = {name: logging.getLogger(name).level for name in names}

    live = live_uvicorn(monkeypatch)
    try:
        async with live(create_http_server()):
            levels = {name: logging.getLogger(name).level for name in names}
    finally:
        for name, previous in before.items():
            logging.getLogger(name).setLevel(previous)

    expected = logging.getLevelNamesMapping()[expected_name.upper()]
    assert live.servers[0].config.log_level == expected_name
    assert levels == dict.fromkeys(names, expected)


def test_analysis_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("lm_mcp.analysis")


def test_analysis_concurrency_is_not_a_setting():
    from lm_mcp.config import LMConfig

    assert "analysis_max_concurrency" not in LMConfig.model_fields
