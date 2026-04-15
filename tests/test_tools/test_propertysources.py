# Description: Tests for PropertySource create/update MCP tools.
# Description: Validates create_propertysource and update_propertysource functions.

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


class TestCreatePropertysource:
    """Tests for create_propertysource tool."""

    async def test_create_propertysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.propertysources import create_propertysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_propertysource(client, definition={"name": "TestPS"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_propertysource_posts_definition(self, client, enable_writes):
        from lm_mcp.tools.propertysources import create_propertysource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/propertyrules").mock(
            return_value=httpx.Response(200, json={"id": 7001, "name": "CustomPS"})
        )

        result = await create_propertysource(
            client, definition={"name": "CustomPS", "technology": "script"}
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["propertysource"]["id"] == 7001

    @respx.mock
    async def test_create_propertysource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.propertysources import create_propertysource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/propertyrules").mock(
            return_value=httpx.Response(200, json={"id": 7002, "name": "PS"}),
        )

        await create_propertysource(client, definition={"id": 999, "name": "PS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body


class TestUpdatePropertysource:
    """Tests for update_propertysource tool."""

    async def test_update_propertysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.propertysources import update_propertysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_propertysource(
            client, propertysource_id=100, definition={"name": "Updated"}
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_propertysource_puts_definition(self, client, enable_writes):
        from lm_mcp.tools.propertysources import update_propertysource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/propertyrules/100"
        ).mock(return_value=httpx.Response(200, json={"id": 100, "name": "UpdatedPS"}))

        result = await update_propertysource(
            client, propertysource_id=100, definition={"name": "UpdatedPS"}
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["propertysource"]["id"] == 100

    @respx.mock
    async def test_update_propertysource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.propertysources import update_propertysource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/propertyrules/100"
        ).mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "PS"}),
        )

        await update_propertysource(
            client, propertysource_id=100, definition={"id": 999, "name": "PS"}
        )
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body


class TestDeletePropertysource:
    """Tests for delete_propertysource tool."""

    async def test_delete_propertysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.propertysources import delete_propertysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_propertysource(client, propertysource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_propertysource_success(self, client, enable_writes):
        from lm_mcp.tools.propertysources import delete_propertysource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/propertyrules/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "OldPS"})
        )
        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/propertyrules/1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_propertysource(client, propertysource_id=1)
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "OldPS" in data["message"]

    @respx.mock
    async def test_delete_propertysource_not_found(self, client, enable_writes):
        from lm_mcp.tools.propertysources import delete_propertysource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/propertyrules/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_propertysource(client, propertysource_id=999)
        assert "Error" in result[0].text
