# Description: Tests for TopologySource create/update MCP tools.
# Description: Validates create_topologysource and update_topologysource functions.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient


@pytest.fixture
def auth():
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
        api_version=3,
    )


@pytest.fixture
def enable_writes(monkeypatch):
    """Enable write operations for testing."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


class TestCreateTopologysource:
    """Tests for create_topologysource tool."""

    async def test_create_topologysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.topologysources import create_topologysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_topologysource(client, definition={"name": "TestTS"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_topologysource_posts_definition(self, client, enable_writes):
        from lm_mcp.tools.topologysources import create_topologysource

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 8001, "name": "CustomTS", "displayName": "Custom TopologySource"},
            )
        )

        result = await create_topologysource(
            client,
            definition={
                "name": "CustomTS",
                "collectionMethod": "script",
                "collectorAttribute": {},
            },
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["topologysource"]["id"] == 8001

    @respx.mock
    async def test_create_topologysource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.topologysources import create_topologysource

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources"
        ).mock(
            return_value=httpx.Response(200, json={"id": 8002, "name": "TS"}),
        )

        await create_topologysource(client, definition={"id": 999, "name": "TS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body


class TestUpdateTopologysource:
    """Tests for update_topologysource tool."""

    async def test_update_topologysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.topologysources import update_topologysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_topologysource(
            client, topologysource_id=100, definition={"name": "Updated"}
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_topologysource_puts_definition(self, client, enable_writes):
        from lm_mcp.tools.topologysources import update_topologysource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "UpdatedTS", "displayName": "Updated TopologySource"},
            )
        )

        result = await update_topologysource(
            client,
            topologysource_id=100,
            definition={"name": "UpdatedTS", "displayName": "Updated TopologySource"},
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["topologysource"]["id"] == 100

    @respx.mock
    async def test_update_topologysource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.topologysources import update_topologysource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources/100"
        ).mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "TS"}),
        )

        await update_topologysource(
            client, topologysource_id=100, definition={"id": 999, "name": "TS"}
        )
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body
