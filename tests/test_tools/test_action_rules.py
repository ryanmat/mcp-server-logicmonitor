# Description: Tests for action rule MCP tools.
# Description: Validates action rule CRUD functions and registry integration.

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


class TestGetActionRules:
    """Tests for get_action_rules tool."""

    @respx.mock
    async def test_get_action_rules_returns_list(self, client):
        """get_action_rules returns properly formatted rule list."""
        from lm_mcp.tools.action_rules import get_action_rules

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/action/rules").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Critical CPU Rule",
                            "actionChainId": 10,
                            "deviceGroups": ["Production/*"],
                            "devices": ["*"],
                            "datasource": "CPU",
                            "datapoint": "CPUBusyPercent",
                            "instance": "*",
                            "severity": "critical",
                        },
                        {
                            "id": 2,
                            "name": "Disk Space Rule",
                            "actionChainId": 11,
                            "deviceGroups": ["*"],
                            "devices": ["*"],
                            "datasource": "WinVolumeUsage",
                            "datapoint": "PercentUsed",
                            "instance": "*",
                            "severity": "error",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_action_rules(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["action_rules"]) == 2
        assert data["action_rules"][0]["name"] == "Critical CPU Rule"
        assert data["action_rules"][0]["action_chain_id"] == 10

    @respx.mock
    async def test_get_action_rules_with_name_filter(self, client):
        """get_action_rules passes name filter to API."""
        from lm_mcp.tools.action_rules import get_action_rules

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/action/rules"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_action_rules(client, name_filter="CPU*")

        assert "filter" in route.calls[0].request.url.params
        assert 'name~"CPU"' in route.calls[0].request.url.params["filter"]

    @respx.mock
    async def test_get_action_rules_handles_error(self, client):
        """get_action_rules returns error on API failure."""
        from lm_mcp.tools.action_rules import get_action_rules

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/action/rules").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_action_rules(client)

        assert "Error:" in result[0].text


class TestGetActionRule:
    """Tests for get_action_rule tool."""

    @respx.mock
    async def test_get_action_rule_returns_details(self, client):
        """get_action_rule returns detailed rule info."""
        from lm_mcp.tools.action_rules import get_action_rule

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/action/rules/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 10,
                    "name": "Critical CPU Rule",
                    "actionChainId": 20,
                    "deviceGroups": ["Production/*"],
                    "devices": ["web-*"],
                    "datasource": "CPU",
                    "datapoint": "CPUBusyPercent",
                    "instance": "*",
                    "severity": "critical",
                    "hostname": "*.example.com",
                    "resourceProperty": "system.category=server",
                },
            )
        )

        result = await get_action_rule(client, rule_id=10)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Critical CPU Rule"
        assert data["action_chain_id"] == 20
        assert data["severity"] == "critical"
        assert data["hostname"] == "*.example.com"

    @respx.mock
    async def test_get_action_rule_not_found(self, client):
        """get_action_rule returns error for missing rule."""
        from lm_mcp.tools.action_rules import get_action_rule

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/action/rules/999"
        ).mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await get_action_rule(client, rule_id=999)

        assert "Error:" in result[0].text


class TestCreateActionRule:
    """Tests for create_action_rule tool."""

    @respx.mock
    async def test_create_action_rule_blocked_by_default(self, client, monkeypatch):
        """create_action_rule is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import create_action_rule

        result = await create_action_rule(
            client,
            name="Test Rule",
            action_chain_id=10,
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_action_rule_succeeds_when_enabled(self, client, monkeypatch):
        """create_action_rule works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import create_action_rule

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/action/rules"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 50,
                    "name": "Test Rule",
                    "actionChainId": 10,
                },
            )
        )

        result = await create_action_rule(
            client,
            name="Test Rule",
            action_chain_id=10,
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["rule_id"] == 50

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Test Rule"
        assert request_body["actionChainId"] == 10

    @respx.mock
    async def test_create_action_rule_with_all_fields(self, client, monkeypatch):
        """create_action_rule passes all optional fields to API."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import create_action_rule

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/action/rules"
        ).mock(
            return_value=httpx.Response(200, json={"id": 51, "name": "Full Rule"})
        )

        await create_action_rule(
            client,
            name="Full Rule",
            action_chain_id=10,
            device_groups=["Production/*"],
            devices=["web-*"],
            datasource="CPU",
            datapoint="CPUBusyPercent",
            instance="*",
            severity="critical",
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Full Rule"
        assert request_body["deviceGroups"] == ["Production/*"]
        assert request_body["devices"] == ["web-*"]
        assert request_body["datasource"] == "CPU"
        assert request_body["datapoint"] == "CPUBusyPercent"
        assert request_body["instance"] == "*"
        assert request_body["severity"] == "critical"


class TestUpdateActionRule:
    """Tests for update_action_rule tool."""

    @respx.mock
    async def test_update_action_rule_blocked_by_default(self, client, monkeypatch):
        """update_action_rule is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import update_action_rule

        result = await update_action_rule(client, rule_id=50, name="Updated Rule")

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_action_rule_succeeds_when_enabled(self, client, monkeypatch):
        """update_action_rule works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import update_action_rule

        respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/action/rules/50"
        ).mock(
            return_value=httpx.Response(200, json={"id": 50, "name": "Updated Rule"})
        )

        result = await update_action_rule(client, rule_id=50, name="Updated Rule")

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True

    @respx.mock
    async def test_update_action_rule_no_fields(self, client, monkeypatch):
        """update_action_rule returns error when no fields provided."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import update_action_rule

        result = await update_action_rule(client, rule_id=50)

        assert "Error:" in result[0].text
        assert "No fields provided" in result[0].text

    @respx.mock
    async def test_update_action_rule_with_severity(self, client, monkeypatch):
        """update_action_rule passes severity to API."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import update_action_rule

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/action/rules/50"
        ).mock(return_value=httpx.Response(200, json={"id": 50}))

        await update_action_rule(client, rule_id=50, severity="error")

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["severity"] == "error"


class TestDeleteActionRule:
    """Tests for delete_action_rule tool."""

    @respx.mock
    async def test_delete_action_rule_blocked_by_default(self, client, monkeypatch):
        """delete_action_rule is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import delete_action_rule

        result = await delete_action_rule(client, rule_id=50)

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_action_rule_succeeds_when_enabled(self, client, monkeypatch):
        """delete_action_rule works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_rules import delete_action_rule

        respx.delete(
            "https://test.logicmonitor.com/santaba/rest/setting/action/rules/50"
        ).mock(return_value=httpx.Response(200, json={}))

        result = await delete_action_rule(client, rule_id=50)

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestActionRuleToolRegistration:
    """Tests for action rule tool registration."""

    def test_get_action_rules_registered(self):
        """get_action_rules is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_action_rules" in tool_names

    def test_get_action_rule_registered(self):
        """get_action_rule is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_action_rule" in tool_names

    def test_create_action_rule_registered(self):
        """create_action_rule is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "create_action_rule" in tool_names

    def test_update_action_rule_registered(self):
        """update_action_rule is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "update_action_rule" in tool_names

    def test_delete_action_rule_registered(self):
        """delete_action_rule is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "delete_action_rule" in tool_names

    def test_get_action_rules_handler_registered(self):
        """get_action_rules handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("get_action_rules")
        assert handler is not None

    def test_create_action_rule_handler_registered(self):
        """create_action_rule handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("create_action_rule")
        assert handler is not None

    def test_delete_action_rule_handler_registered(self):
        """delete_action_rule handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("delete_action_rule")
        assert handler is not None
