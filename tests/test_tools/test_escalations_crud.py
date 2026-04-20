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

    @respx.mock
    async def test_create_escalation_chain_with_destinations(self, client, monkeypatch):
        """create_escalation_chain passes destinations to API."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import create_escalation_chain

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(
                200,
                json={"id": 11, "name": "Chain with Dests"},
            )
        )

        destinations = [
            {
                "type": "single",
                "period": 15,
                "stages": [[{"type": "admin", "addr": "oncall@example.com"}]],
            }
        ]
        result = await create_escalation_chain(
            client,
            name="Chain with Dests",
            destinations=destinations,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        sent_body = json.loads(route.calls[0].request.content)
        assert "destinations" in sent_body
        assert len(sent_body["destinations"]) == 1

    @respx.mock
    async def test_create_escalation_chain_with_cc_destinations(self, client, monkeypatch):
        """create_escalation_chain passes ccDestinations to API."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import create_escalation_chain

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(
                200,
                json={"id": 12, "name": "Chain with CC"},
            )
        )

        cc_destinations = [{"type": "ARBITRARY", "method": "email", "addr": "cc@example.com"}]
        result = await create_escalation_chain(
            client,
            name="Chain with CC",
            cc_destinations=cc_destinations,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        sent_body = json.loads(route.calls[0].request.content)
        assert "ccDestinations" in sent_body
        assert len(sent_body["ccDestinations"]) == 1


class TestDestinationsShorthand:
    """Tests for _normalize_destinations integration shorthand."""

    def test_shorthand_rewritten_to_admin_method(self):
        from lm_mcp.tools.escalations import _normalize_destinations

        destinations = [
            {
                "type": "single",
                "period": None,
                "stages": [
                    [
                        {
                            "type": "integration",
                            "integration_name": "Sentinel POC",
                            "admin": "rmatuszewski",
                        }
                    ]
                ],
            }
        ]
        result = _normalize_destinations(destinations)
        recip = result[0]["stages"][0][0]
        assert recip == {
            "type": "admin",
            "addr": "rmatuszewski",
            "method": "Sentinel POC",
        }

    def test_shorthand_accepts_method_and_addr_aliases(self):
        from lm_mcp.tools.escalations import _normalize_destinations

        destinations = [
            {
                "type": "single",
                "stages": [
                    [
                        {
                            "type": "integration",
                            "method": "Sentinel POC",
                            "addr": "rmatuszewski",
                        }
                    ]
                ],
            }
        ]
        result = _normalize_destinations(destinations)
        recip = result[0]["stages"][0][0]
        assert recip == {
            "type": "admin",
            "addr": "rmatuszewski",
            "method": "Sentinel POC",
        }

    def test_missing_admin_raises_with_actionable_message(self):
        from lm_mcp.tools.escalations import _normalize_destinations

        destinations = [
            {
                "type": "single",
                "stages": [[{"type": "integration", "integration_name": "X"}]],
            }
        ]
        with pytest.raises(ValueError) as exc_info:
            _normalize_destinations(destinations)
        msg = str(exc_info.value)
        assert "admin" in msg
        assert "username" in msg

    def test_integration_id_alone_is_rejected(self):
        from lm_mcp.tools.escalations import _normalize_destinations

        destinations = [
            {
                "type": "single",
                "stages": [[{"type": "integration", "integration_id": 3}]],
            }
        ]
        with pytest.raises(ValueError) as exc_info:
            _normalize_destinations(destinations)
        assert "integration_id alone is not enough" in str(exc_info.value)

    def test_non_integration_recipients_pass_through(self):
        from lm_mcp.tools.escalations import _normalize_destinations

        destinations = [
            {
                "type": "single",
                "stages": [
                    [
                        {
                            "type": "admin",
                            "addr": "existing@example.com",
                            "method": "email",
                        }
                    ]
                ],
            }
        ]
        original = [dict(destinations[0])]
        result = _normalize_destinations(destinations)
        assert result[0]["stages"] == original[0]["stages"]

    def test_flat_stages_are_handled(self):
        from lm_mcp.tools.escalations import _normalize_destinations

        destinations = [
            {
                "type": "single",
                "stages": [
                    {
                        "type": "integration",
                        "integration_name": "X",
                        "admin": "u",
                    }
                ],
            }
        ]
        result = _normalize_destinations(destinations)
        recip = result[0]["stages"][0]
        assert recip["type"] == "admin"
        assert recip["method"] == "X"

    @respx.mock
    async def test_create_escalation_chain_normalizes_shorthand(self, client, monkeypatch):
        """create_escalation_chain rewrites shorthand before sending."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import create_escalation_chain

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(200, json={"id": 99})
        )

        result = await create_escalation_chain(
            client,
            name="via shorthand",
            destinations=[
                {
                    "type": "single",
                    "period": None,
                    "stages": [
                        [
                            {
                                "type": "integration",
                                "integration_name": "Sentinel POC",
                                "admin": "rmatuszewski",
                            }
                        ]
                    ],
                }
            ],
        )

        assert "Error:" not in result[0].text
        sent_body = json.loads(route.calls[0].request.content)
        recip = sent_body["destinations"][0]["stages"][0][0]
        assert recip == {
            "type": "admin",
            "addr": "rmatuszewski",
            "method": "Sentinel POC",
        }


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

    @respx.mock
    async def test_update_escalation_chain_with_destinations(self, client, monkeypatch):
        """update_escalation_chain passes destinations to API."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import update_escalation_chain

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/alert/chains/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "name": "Updated Chain"},
            )
        )

        destinations = [
            {
                "type": "single",
                "period": 30,
                "stages": [[{"type": "admin", "addr": "new-oncall@example.com"}]],
            }
        ]
        result = await update_escalation_chain(
            client,
            chain_id=10,
            destinations=destinations,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        sent_body = json.loads(route.calls[0].request.content)
        assert "destinations" in sent_body
        assert len(sent_body["destinations"]) == 1


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

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/recipientgroups"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 20, "groupName": "Test Group"},
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

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["groupName"] == "Test Group"
        assert "name" not in sent_body

    @respx.mock
    async def test_create_recipient_group_accepts_recipients(self, client, monkeypatch):
        """create_recipient_group forwards recipients to the API."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import create_recipient_group

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/recipientgroups"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 21, "groupName": "Preloaded"},
            )
        )

        recipients = [
            {"type": "admin", "method": "email", "addr": "a@example.com"},
            {"type": "admin", "method": "email", "addr": "b@example.com"},
        ]
        result = await create_recipient_group(
            client,
            name="Preloaded",
            recipients=recipients,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["groupName"] == "Preloaded"
        assert sent_body["recipients"] == recipients


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

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/recipientgroups/20"
        ).mock(return_value=httpx.Response(200, json={"id": 20, "groupName": "Updated Group"}))

        result = await update_recipient_group(
            client,
            group_id=20,
            name="Updated Group",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["groupName"] == "Updated Group"
        assert "name" not in sent_body

    @respx.mock
    async def test_update_recipient_group_replaces_recipients(self, client, monkeypatch):
        """update_recipient_group forwards a new recipients list when provided."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.escalations import update_recipient_group

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/recipientgroups/20"
        ).mock(return_value=httpx.Response(200, json={"id": 20}))

        recipients = [{"type": "admin", "method": "email", "addr": "new@example.com"}]
        await update_recipient_group(client, group_id=20, recipients=recipients)

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {"recipients": recipients}


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
