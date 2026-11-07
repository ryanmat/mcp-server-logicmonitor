# Description: Guards the per-file client fixtures that stub 5xx responses against real backoff.
# Description: A zero-retry client sends once and never waits; a default client still waits.

from __future__ import annotations

import importlib
import inspect

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.exceptions import ServerError

_API = "https://test.logicmonitor.com/santaba/rest"

_ZERO_RETRY_MODULES = [
    "test_alert_rules",
    "test_baselines",
    "test_correlation",
    "test_diagnosticsources",
    "test_event_correlation",
    "test_forecasting",
    "test_networking",
    "test_remediationsources",
    "test_scoring",
    "test_topology_analysis",
    "test_traces",
    "test_users",
]


@pytest.fixture
def waits(monkeypatch):
    """Record each backoff wait instead of sleeping."""
    recorded: list[float] = []

    async def fake_sleep(seconds):
        recorded.append(seconds)

    monkeypatch.setattr("lm_mcp.client.api.asyncio.sleep", fake_sleep)
    return recorded


@pytest.mark.parametrize("module_name", _ZERO_RETRY_MODULES)
def test_client_fixture_builds_a_zero_retry_client(module_name):
    """Each file's client fixture stubs 5xx responses, so it must not back off."""
    module = importlib.import_module(f"tests.test_tools.{module_name}")
    build_client = inspect.unwrap(module.client)

    client = build_client(BearerAuth("test-token"))

    assert client.max_retries == 0


@respx.mock
async def test_zero_retry_client_sends_once_and_never_waits(waits):
    """A 5xx against max_retries=0 raises after one request and no wait."""
    route = respx.get(f"{_API}/device/devices/1").mock(
        return_value=httpx.Response(500, json={"errorMessage": "boom"})
    )
    async with LogicMonitorClient(
        base_url=_API, auth=BearerAuth("test-token"), max_retries=0
    ) as client:
        with pytest.raises(ServerError):
            await client.get("/device/devices/1")

    assert route.call_count == 1
    assert waits == []


@respx.mock
async def test_default_client_waits_between_tries(waits):
    """A 5xx against the default retry count waits between every try."""
    route = respx.get(f"{_API}/device/devices/1").mock(
        return_value=httpx.Response(500, json={"errorMessage": "boom"})
    )
    async with LogicMonitorClient(base_url=_API, auth=BearerAuth("test-token")) as client:
        with pytest.raises(ServerError):
            await client.get("/device/devices/1")

    assert route.call_count == client.max_retries + 1
    assert len(waits) == client.max_retries
    assert client.max_retries > 0
