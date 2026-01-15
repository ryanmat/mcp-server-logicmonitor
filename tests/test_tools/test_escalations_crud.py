# Description: Tests for escalation chain and recipient group CRUD operations.
# Description: Validates create/update/delete for escalation chains and recipient groups.

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


class TestCreateEscalationChain:
    """Tests for create_escalation_chain tool."""

    @respx.mock
    async def test_create_escalation_chain_blocked_by_default(self, client, monkeypatch):
        """create_escalation_chain is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import create_escalation_chain

        result = await create_escalation_chain(
            client,
            name="Test Chain",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_escalation_chain_succeeds_when_enabled(self, client, monkeypatch):
        """create_escalation_chain works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import create_escalation_chain

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 10,
                    "name": "Test Chain",
                    "description": "Test escalation chain",
                },
            )
        )

        result = await create_escalation_chain(
            client,
            name="Test Chain",
            description="Test escalation chain",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["chain_id"] == 10


class TestUpdateEscalationChain:
    """Tests for update_escalation_chain tool."""

    @respx.mock
    async def test_update_escalation_chain_blocked_by_default(self, client, monkeypatch):
        """update_escalation_chain is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import update_escalation_chain

        result = await update_escalation_chain(
            client,
            chain_id=10,
            name="Updated Chain",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_escalation_chain_succeeds_when_enabled(self, client, monkeypatch):
        """update_escalation_chain works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import update_escalation_chain

        respx.patch("https://test.logicmonitor.com/santaba/rest/setting/alert/chains/10").mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "name": "Updated Chain"},
            )
        )

        result = await update_escalation_chain(
            client,
            chain_id=10,
            name="Updated Chain",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestDeleteEscalationChain:
    """Tests for delete_escalation_chain tool."""

    @respx.mock
    async def test_delete_escalation_chain_blocked_by_default(self, client, monkeypatch):
        """delete_escalation_chain is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import delete_escalation_chain

        result = await delete_escalation_chain(client, chain_id=10)

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_escalation_chain_succeeds_when_enabled(self, client, monkeypatch):
        """delete_escalation_chain works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import delete_escalation_chain

        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/alert/chains/10").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_escalation_chain(client, chain_id=10)

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestCreateRecipientGroup:
    """Tests for create_recipient_group tool."""

    @respx.mock
    async def test_create_recipient_group_blocked_by_default(self, client, monkeypatch):
        """create_recipient_group is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import create_recipient_group

        result = await create_recipient_group(
            client,
            name="Test Group",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_recipient_group_succeeds_when_enabled(self, client, monkeypatch):
        """create_recipient_group works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import create_recipient_group

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/recipientgroups").mock(
            return_value=httpx.Response(
                200,
                json={"id": 20, "name": "Test Group"},
            )
        )

        result = await create_recipient_group(
            client,
            name="Test Group",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["group_id"] == 20


class TestUpdateRecipientGroup:
    """Tests for update_recipient_group tool."""

    @respx.mock
    async def test_update_recipient_group_blocked_by_default(self, client, monkeypatch):
        """update_recipient_group is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import update_recipient_group

        result = await update_recipient_group(
            client,
            group_id=20,
            name="Updated Group",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_recipient_group_succeeds_when_enabled(self, client, monkeypatch):
        """update_recipient_group works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import update_recipient_group

        respx.patch("https://test.logicmonitor.com/santaba/rest/setting/recipientgroups/20").mock(
            return_value=httpx.Response(200, json={"id": 20, "name": "Updated Group"})
        )

        result = await update_recipient_group(
            client,
            group_id=20,
            name="Updated Group",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestDeleteRecipientGroup:
    """Tests for delete_recipient_group tool."""

    @respx.mock
    async def test_delete_recipient_group_blocked_by_default(self, client, monkeypatch):
        """delete_recipient_group is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import delete_recipient_group

        result = await delete_recipient_group(client, group_id=20)

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_recipient_group_succeeds_when_enabled(self, client, monkeypatch):
        """delete_recipient_group works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import delete_recipient_group

        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/recipientgroups/20").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_recipient_group(client, group_id=20)

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestEscalationsCRUDToolRegistration:
    """Tests for escalation CRUD tool registration."""

    def test_create_escalation_chain_registered_in_registry(self):
        """create_escalation_chain is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "create_escalation_chain" in tool_names

    def test_update_escalation_chain_registered_in_registry(self):
        """update_escalation_chain is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "update_escalation_chain" in tool_names

    def test_delete_escalation_chain_registered_in_registry(self):
        """delete_escalation_chain is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "delete_escalation_chain" in tool_names

    def test_create_recipient_group_registered_in_registry(self):
        """create_recipient_group is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "create_recipient_group" in tool_names

    def test_update_recipient_group_registered_in_registry(self):
        """update_recipient_group is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "update_recipient_group" in tool_names

    def test_delete_recipient_group_registered_in_registry(self):
        """delete_recipient_group is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "delete_recipient_group" in tool_names

    def test_create_escalation_chain_handler_registered(self):
        """create_escalation_chain handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("create_escalation_chain")
        assert handler is not None

    def test_delete_recipient_group_handler_registered(self):
        """delete_recipient_group handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("delete_recipient_group")
        assert handler is not None
