# Description: Tests for website CRUD operations.
# Description: Validates create/update/delete for websites and website groups.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient


@pytest.fixture
def auth():
    """Create a BearerAuth instance for testing."""
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
        api_version=3,
    )


class TestCreateWebsite:
    """Tests for create_website tool."""

    @respx.mock
    async def test_create_website_blocked_by_default(self, client, monkeypatch):
        """create_website is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import create_website

        result = await create_website(
            client,
            name="Test Website",
            website_type="webcheck",
            domain="www.example.com",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_website_succeeds_when_enabled(self, client, monkeypatch):
        """create_website works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import create_website

        respx.post("https://test.logicmonitor.com/santaba/rest/website/websites").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "Test Website",
                    "type": "webcheck",
                    "host": "www.example.com",
                    "status": "active",
                },
            )
        )

        result = await create_website(
            client,
            name="Test Website",
            website_type="webcheck",
            domain="www.example.com",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["website_id"] == 100

    @respx.mock
    async def test_create_website_with_optional_params(self, client, monkeypatch):
        """create_website includes optional parameters."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import create_website

        route = respx.post("https://test.logicmonitor.com/santaba/rest/website/websites").mock(
            return_value=httpx.Response(
                200,
                json={"id": 101, "name": "Production API", "type": "webcheck"},
            )
        )

        await create_website(
            client,
            name="Production API",
            website_type="webcheck",
            domain="api.example.com",
            description="API endpoint monitoring",
            group_id=5,
            polling_interval=5,
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Production API"
        assert request_body["description"] == "API endpoint monitoring"
        assert request_body["groupId"] == 5
        assert request_body["pollingInterval"] == 5


class TestUpdateWebsite:
    """Tests for update_website tool."""

    @respx.mock
    async def test_update_website_blocked_by_default(self, client, monkeypatch):
        """update_website is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import update_website

        result = await update_website(
            client,
            website_id=100,
            name="Updated Website",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_website_succeeds_when_enabled(self, client, monkeypatch):
        """update_website works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import update_website

        respx.patch("https://test.logicmonitor.com/santaba/rest/website/websites/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "Updated Website",
                    "type": "webcheck",
                    "status": "active",
                },
            )
        )

        result = await update_website(
            client,
            website_id=100,
            name="Updated Website",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True

    @respx.mock
    async def test_update_website_with_multiple_fields(self, client, monkeypatch):
        """update_website can update multiple fields."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import update_website

        route = respx.patch("https://test.logicmonitor.com/santaba/rest/website/websites/100").mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "Updated"})
        )

        await update_website(
            client,
            website_id=100,
            name="Updated Website",
            description="Updated description",
            polling_interval=10,
            is_internal=True,
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Updated Website"
        assert request_body["description"] == "Updated description"
        assert request_body["pollingInterval"] == 10
        assert request_body["isInternal"] is True


class TestDeleteWebsite:
    """Tests for delete_website tool."""

    @respx.mock
    async def test_delete_website_blocked_by_default(self, client, monkeypatch):
        """delete_website is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import delete_website

        result = await delete_website(client, website_id=100)

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_website_succeeds_when_enabled(self, client, monkeypatch):
        """delete_website works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import delete_website

        respx.delete("https://test.logicmonitor.com/santaba/rest/website/websites/100").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_website(client, website_id=100)

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestCreateWebsiteGroup:
    """Tests for create_website_group tool."""

    @respx.mock
    async def test_create_website_group_blocked_by_default(self, client, monkeypatch):
        """create_website_group is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import create_website_group

        result = await create_website_group(client, name="Test Group")

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_website_group_succeeds_when_enabled(self, client, monkeypatch):
        """create_website_group works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import create_website_group

        respx.post("https://test.logicmonitor.com/santaba/rest/website/groups").mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "name": "Test Group", "parentId": 1},
            )
        )

        result = await create_website_group(
            client,
            name="Test Group",
            parent_id=1,
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["group_id"] == 10


class TestDeleteWebsiteGroup:
    """Tests for delete_website_group tool."""

    @respx.mock
    async def test_delete_website_group_blocked_by_default(self, client, monkeypatch):
        """delete_website_group is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import delete_website_group

        result = await delete_website_group(client, group_id=10)

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_website_group_succeeds_when_enabled(self, client, monkeypatch):
        """delete_website_group works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.websites import delete_website_group

        respx.delete("https://test.logicmonitor.com/santaba/rest/website/groups/10").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_website_group(client, group_id=10)

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestWebsiteCRUDToolRegistration:
    """Tests for website CRUD tool registration."""

    def test_create_website_registered_in_registry(self):
        """create_website is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "create_website" in tool_names

    def test_update_website_registered_in_registry(self):
        """update_website is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "update_website" in tool_names

    def test_delete_website_registered_in_registry(self):
        """delete_website is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "delete_website" in tool_names

    def test_create_website_group_registered_in_registry(self):
        """create_website_group is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "create_website_group" in tool_names

    def test_delete_website_group_registered_in_registry(self):
        """delete_website_group is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "delete_website_group" in tool_names

    def test_create_website_handler_registered(self):
        """create_website handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("create_website")
        assert handler is not None

    def test_update_website_handler_registered(self):
        """update_website handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("update_website")
        assert handler is not None

    def test_delete_website_handler_registered(self):
        """delete_website handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("delete_website")
        assert handler is not None
