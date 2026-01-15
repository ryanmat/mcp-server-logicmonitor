# Description: Tests for alert rule CRUD operations.
# Description: Validates create_alert_rule, update_alert_rule, delete_alert_rule.

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


class TestCreateAlertRule:
    """Tests for create_alert_rule tool."""

    @respx.mock
    async def test_create_alert_rule_blocked_by_default(self, client, monkeypatch):
        """create_alert_rule is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alert_rules import create_alert_rule

        result = await create_alert_rule(
            client,
            name="Test Rule",
            priority=100,
            escalation_chain_id=1,
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_alert_rule_succeeds_when_enabled(self, client, monkeypatch):
        """create_alert_rule works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alert_rules import create_alert_rule

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/rules").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 50,
                    "name": "Test Rule",
                    "priority": 100,
                    "escalatingChainId": 1,
                },
            )
        )

        result = await create_alert_rule(
            client,
            name="Test Rule",
            priority=100,
            escalation_chain_id=1,
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["rule_id"] == 50

    @respx.mock
    async def test_create_alert_rule_with_device_groups(self, client, monkeypatch):
        """create_alert_rule includes device groups."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alert_rules import create_alert_rule

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/rules").mock(
            return_value=httpx.Response(
                200,
                json={"id": 51, "name": "Production Rule", "priority": 50},
            )
        )

        await create_alert_rule(
            client,
            name="Production Rule",
            priority=50,
            escalation_chain_id=1,
            device_groups=["Production/*", "Critical/*"],
            level_str="Critical",
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Production Rule"
        assert request_body["priority"] == 50
        assert "deviceGroups" in request_body


class TestUpdateAlertRule:
    """Tests for update_alert_rule tool."""

    @respx.mock
    async def test_update_alert_rule_blocked_by_default(self, client, monkeypatch):
        """update_alert_rule is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alert_rules import update_alert_rule

        result = await update_alert_rule(
            client,
            rule_id=50,
            name="Updated Rule",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_alert_rule_succeeds_when_enabled(self, client, monkeypatch):
        """update_alert_rule works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alert_rules import update_alert_rule

        respx.patch("https://test.logicmonitor.com/santaba/rest/setting/alert/rules/50").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 50,
                    "name": "Updated Rule",
                    "priority": 100,
                },
            )
        )

        result = await update_alert_rule(
            client,
            rule_id=50,
            name="Updated Rule",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True

    @respx.mock
    async def test_update_alert_rule_with_multiple_fields(self, client, monkeypatch):
        """update_alert_rule can update multiple fields."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alert_rules import update_alert_rule

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/alert/rules/50"
        ).mock(return_value=httpx.Response(200, json={"id": 50, "name": "Updated"}))

        await update_alert_rule(
            client,
            rule_id=50,
            name="Updated Rule",
            priority=200,
            escalation_chain_id=2,
            suppress_alert_clear=True,
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Updated Rule"
        assert request_body["priority"] == 200
        assert request_body["escalatingChainId"] == 2
        assert request_body["suppressAlertClear"] is True


class TestDeleteAlertRule:
    """Tests for delete_alert_rule tool."""

    @respx.mock
    async def test_delete_alert_rule_blocked_by_default(self, client, monkeypatch):
        """delete_alert_rule is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alert_rules import delete_alert_rule

        result = await delete_alert_rule(client, rule_id=50)

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_alert_rule_succeeds_when_enabled(self, client, monkeypatch):
        """delete_alert_rule works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alert_rules import delete_alert_rule

        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/alert/rules/50").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_alert_rule(client, rule_id=50)

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestAlertRuleCRUDToolRegistration:
    """Tests for alert rule CRUD tool registration."""

    def test_create_alert_rule_registered_in_registry(self):
        """create_alert_rule is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "create_alert_rule" in tool_names

    def test_update_alert_rule_registered_in_registry(self):
        """update_alert_rule is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "update_alert_rule" in tool_names

    def test_delete_alert_rule_registered_in_registry(self):
        """delete_alert_rule is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "delete_alert_rule" in tool_names

    def test_create_alert_rule_handler_registered(self):
        """create_alert_rule handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("create_alert_rule")
        assert handler is not None

    def test_update_alert_rule_handler_registered(self):
        """update_alert_rule handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("update_alert_rule")
        assert handler is not None

    def test_delete_alert_rule_handler_registered(self):
        """delete_alert_rule handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("delete_alert_rule")
        assert handler is not None
