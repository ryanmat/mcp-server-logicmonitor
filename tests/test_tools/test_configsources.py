# Description: Tests for ConfigSource create/update MCP tools.
# Description: Validates create_configsource and update_configsource functions.

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


class TestCreateConfigsource:
    """Tests for create_configsource tool."""

    async def test_create_configsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.configsources import create_configsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_configsource(client, definition={"name": "TestCS"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_configsource_posts_definition(self, client, enable_writes):
        from lm_mcp.tools.configsources import create_configsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/configsources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 6001, "name": "CustomCS", "displayName": "Custom ConfigSource"},
            )
        )

        result = await create_configsource(
            client,
            definition={"name": "CustomCS", "displayName": "Custom ConfigSource"},
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["configsource"]["id"] == 6001

    @respx.mock
    async def test_create_configsource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.configsources import create_configsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/configsources").mock(
            return_value=httpx.Response(200, json={"id": 6002, "name": "CS"}),
        )

        await create_configsource(client, definition={"id": 999, "name": "CS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body


class TestUpdateConfigsource:
    """Tests for update_configsource tool."""

    async def test_update_configsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.configsources import update_configsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_configsource(
            client, configsource_id=100, definition={"name": "Updated"}
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_configsource_puts_definition(self, client, enable_writes):
        from lm_mcp.tools.configsources import update_configsource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/configsources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "UpdatedCS", "displayName": "Updated ConfigSource"},
            )
        )

        result = await update_configsource(
            client,
            configsource_id=100,
            definition={"name": "UpdatedCS", "displayName": "Updated ConfigSource"},
            confirm=True,
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["configsource"]["id"] == 100

    @respx.mock
    async def test_update_configsource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.configsources import update_configsource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/configsources/100"
        ).mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "CS"}),
        )

        await update_configsource(
            client, configsource_id=100, definition={"id": 999, "name": "CS"}, confirm=True
        )
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    async def test_update_configsource_without_confirm_errors_with_pointer(
        self, client, enable_writes
    ):
        from lm_mcp.tools.configsources import update_configsource

        result = await update_configsource(
            client, configsource_id=100, definition={"name": "X"}
        )
        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text


class TestDeleteConfigsource:
    """Tests for delete_configsource tool."""

    async def test_delete_configsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.configsources import delete_configsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_configsource(client, configsource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_configsource_success(self, client, enable_writes):
        from lm_mcp.tools.configsources import delete_configsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/configsources/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "OldCS"})
        )
        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/configsources/1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_configsource(client, configsource_id=1)
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "OldCS" in data["message"]

    @respx.mock
    async def test_delete_configsource_not_found(self, client, enable_writes):
        from lm_mcp.tools.configsources import delete_configsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/configsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_configsource(client, configsource_id=999)
        assert "Error" in result[0].text
