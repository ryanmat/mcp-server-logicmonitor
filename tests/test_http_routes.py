# Description: R1.5, R1.6: the HTTP transport serves health and info routes only, on a live socket.
# Description: The analysis API, its webhook and /mcp answer 404; no preflight gets a CORS answer.

from __future__ import annotations

import importlib

import httpx
import pytest

from tests.live_uvicorn import free_port, live_uvicorn

# 16 characters: the configured minimum, and below the length a secret scanner flags.
TOKEN = "route-test-tok16"

_REMOVED_ROUTES = [
    ("POST", "/mcp", {"json": {"jsonrpc": "2.0", "method": "tools/list", "id": 1}}),
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

    assert [r.status_code for r in responses] == [404, 404, 404, 404]


async def test_preflight_gets_no_cors_answer_with_origins_set(http_env, monkeypatch):
    """R1.6: the server has no CORS support, so LM_CORS_ORIGINS changes nothing."""
    monkeypatch.setenv("LM_CORS_ORIGINS", "https://example.com")
    origin = {"Origin": "https://example.com", "Access-Control-Request-Method": "GET"}

    (response,) = await _send(monkeypatch, [("OPTIONS", "/health", {"headers": origin})])

    assert "access-control-allow-origin" not in response.headers


async def test_post_to_mcp_is_404_whatever_its_body_type(http_env, monkeypatch):
    """No route takes a request body, so the Content-Type check refuses nothing."""
    plain = {"content": "{}", "headers": {"Content-Type": "text/plain"}}

    (response,) = await _send(monkeypatch, [("POST", "/mcp", plain)])

    assert response.status_code == 404


async def test_bearer_middleware_still_refuses_an_unauthenticated_gated_path(http_env, monkeypatch):
    """With a token set, a path outside the open set is 401 before routing, and 404 after."""
    monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", TOKEN)
    method, path, kwargs = _REMOVED_ROUTES[0]
    authorized = {**kwargs, "headers": {"Authorization": f"Bearer {TOKEN}"}}

    anonymous, with_token = await _send(
        monkeypatch, [(method, path, kwargs), (method, path, authorized)]
    )

    assert anonymous.status_code == 401
    assert anonymous.headers["www-authenticate"] == "Bearer"
    assert with_token.status_code == 404


async def test_root_listing_names_only_the_health_routes(http_env, monkeypatch):
    (root,) = await _send(monkeypatch, [("GET", "/", {})])

    assert root.json()["endpoints"] == {
        "health": "/health",
        "healthz": "/healthz",
        "readyz": "/readyz",
    }


def test_analysis_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("lm_mcp.analysis")


def test_analysis_concurrency_is_not_a_setting():
    from lm_mcp.config import LMConfig

    assert "analysis_max_concurrency" not in LMConfig.model_fields
