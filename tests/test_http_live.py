# Description: R4.1: the mcp Python client over Streamable HTTP against create_http_server, live.
# Description: Initializes, lists the tools stdio lists, calls tools, and meets the Host refusal.

from __future__ import annotations

import contextlib
import json

import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.live_uvicorn import free_port, live_uvicorn

# 16 characters: the configured minimum, and below the length a secret scanner flags.
TOKEN = "live-client-tk16"


@pytest.fixture
def http_env(monkeypatch):
    """A single-portal HTTP start on a free loopback port, writes off, a bearer token on."""
    for name in (
        "LM_MULTI_PORTAL",
        "LM_HTTP_ALLOW_UNAUTHENTICATED",
        "LM_HTTP_ALLOWED_HOSTS",
        "LM_HEALTH_CHECK_CONNECTIVITY",
        "LM_ENABLED_TOOLS",
        "LM_DISABLED_TOOLS",
        "LM_MCP_CATEGORIES",
        "EDWIN_CLIENT_ID",
        "EDWIN_CLIENT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
    monkeypatch.setenv("LM_TRANSPORT", "http")
    monkeypatch.setenv("LM_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("LM_HTTP_PORT", str(free_port("127.0.0.1")))
    monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", TOKEN)


@contextlib.asynccontextmanager
async def _client_session(monkeypatch, extra_headers=None):
    """Serve create_http_server on a live socket and yield an initialized mcp ClientSession."""
    from lm_mcp.transport.http import create_http_server

    live = live_uvicorn(monkeypatch)
    headers = {"Authorization": f"Bearer {TOKEN}", **(extra_headers or {})}
    async with (
        live(create_http_server()) as port,
        httpx.AsyncClient(headers=headers) as http,
        streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http) as (r, w, _),
        ClientSession(r, w) as session,
    ):
        yield session


def _exception_leaves(exc: BaseException) -> list[BaseException]:
    """The exceptions inside ``exc``, nested groups opened."""
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for inner in exc.exceptions for leaf in _exception_leaves(inner)]
    return [exc]


async def test_client_initializes_and_lists_the_filtered_core_tools(http_env, monkeypatch):
    """The HTTP half of test_transport's stdio listing: exactly the filtered TOOLS, in order."""
    from lm_mcp.config import get_config
    from lm_mcp.registry import TOOLS
    from lm_mcp.server import _filter_tools

    async with _client_session(monkeypatch) as session:
        initialized = await session.initialize()
        listed = await session.list_tools()

    expected = [t.name for t in _filter_tools(list(TOOLS), get_config())]
    assert initialized.serverInfo.name == "logicmonitor"
    assert listed.nextCursor is None
    assert [tool.name for tool in listed.tools] == expected


async def test_client_calls_search_tools(http_env, monkeypatch):
    async with _client_session(monkeypatch) as session:
        await session.initialize()
        result = await session.call_tool("search_tools", {"query": "alerts"})

    assert result.isError is False
    payload = json.loads(result.content[0].text)
    assert payload["query"] == "alerts"
    assert "get_alerts" in {match["name"] for match in payload["matches"]}


async def test_refused_write_reaches_the_client_as_is_error_with_the_envelope(
    http_env, monkeypatch
):
    async with _client_session(monkeypatch) as session:
        await session.initialize()
        result = await session.call_tool("delete_device", {"device_id": 1})

    assert result.isError is True
    error = json.loads(result.content[0].text)["error"]
    assert error["code"] == "WRITE_DISABLED"
    assert error["message"].startswith("Write operations are disabled")


async def test_host_refusal_reaches_the_client_as_an_http_error(http_env, monkeypatch):
    """A Host the allowlist refuses ends initialize with the 400, not a wait for an answer.

    The client raises from its transport's task group, so the HTTP error arrives
    inside an exception group; the 10-second bound turns a hang into a failure.
    """
    with anyio.fail_after(10), pytest.raises(BaseExceptionGroup) as raised:
        async with _client_session(monkeypatch, {"Host": "evil.example"}) as session:
            await session.initialize()

    leaves = _exception_leaves(raised.value)
    assert [type(leaf) for leaf in leaves] == [httpx.HTTPStatusError]
    assert leaves[0].response.status_code == 400
