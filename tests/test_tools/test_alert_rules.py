# Description: Tests for alert rule MCP tools.
# Description: Validates alert rule query functions.

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


class TestGetAlertRules:
    """Tests for get_alert_rules tool."""

    @respx.mock
    async def test_get_alert_rules_returns_list(self, client):
        """get_alert_rules returns properly formatted rule list."""
        from lm_mcp.tools.alert_rules import get_alert_rules

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/rules").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Critical Alerts",
                            "priority": 1,
                            "escalatingChainId": 100,
                            "escalatingChain": {"name": "Primary On-Call"},
                            "levelStr": "Critical",
                            "devices": ["*"],
                            "deviceGroups": ["Production/*"],
                            "datasource": "*",
                            "suppressAlertClear": False,
                            "suppressAlertAckSdt": False,
                        },
                        {
                            "id": 2,
                            "name": "Warning Alerts",
                            "priority": 2,
                            "escalatingChainId": 101,
                            "escalatingChain": {"name": "Secondary On-Call"},
                            "levelStr": "Warn",
                            "devices": ["*"],
                            "deviceGroups": ["*"],
                            "datasource": "*",
                            "suppressAlertClear": True,
                            "suppressAlertAckSdt": True,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_alert_rules(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["alert_rules"]) == 2
        assert data["alert_rules"][0]["name"] == "Critical Alerts"
        assert data["alert_rules"][0]["priority"] == 1
        assert data["alert_rules"][0]["escalation_chain_name"] == "Primary On-Call"
        assert data["alert_rules"][1]["suppress_alert_clear"] is True

    @respx.mock
    async def test_get_alert_rules_with_name_filter(self, client):
        """get_alert_rules passes name filter to API."""
        from lm_mcp.tools.alert_rules import get_alert_rules

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/rules").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_alert_rules(client, name_filter="Critical*")

        assert "filter" in route.calls[0].request.url.params
        assert "name~Critical*" in route.calls[0].request.url.params["filter"]

    @respx.mock
    async def test_get_alert_rules_with_priority_filter(self, client):
        """get_alert_rules passes priority filter to API."""
        from lm_mcp.tools.alert_rules import get_alert_rules

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/rules").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_alert_rules(client, priority_filter=1)

        assert "filter" in route.calls[0].request.url.params
        assert "priority:1" in route.calls[0].request.url.params["filter"]

    @respx.mock
    async def test_get_alert_rules_handles_error(self, client):
        """get_alert_rules returns error on API failure."""
        from lm_mcp.tools.alert_rules import get_alert_rules

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/rules").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_alert_rules(client)

        assert "Error:" in result[0].text


class TestGetAlertRule:
    """Tests for get_alert_rule tool."""

    @respx.mock
    async def test_get_alert_rule_returns_details(self, client):
        """get_alert_rule returns detailed rule info."""
        from lm_mcp.tools.alert_rules import get_alert_rule

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/rules/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "Critical Production Alerts",
                    "priority": 1,
                    "escalatingChainId": 200,
                    "escalatingChain": {"name": "Primary On-Call", "period": 15},
                    "levelStr": "Critical",
                    "devices": ["prod-*"],
                    "deviceGroups": ["Production/Web"],
                    "datasource": "CPU*",
                    "datapoint": "CPUBusyPercent",
                    "instance": "*",
                    "suppressAlertClear": False,
                    "suppressAlertAckSdt": False,
                    "resourceProperties": [
                        {"name": "system.category", "value": "production"},
                        {"name": "location", "value": "US-East"},
                    ],
                },
            )
        )

        result = await get_alert_rule(client, rule_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 100
        assert data["name"] == "Critical Production Alerts"
        assert data["priority"] == 1
        assert data["escalation_chain_name"] == "Primary On-Call"
        assert data["escalation_interval"] == 15
        assert data["datasource"] == "CPU*"
        assert data["datapoint"] == "CPUBusyPercent"
        assert len(data["resource_properties"]) == 2
        assert data["resource_properties"][0]["name"] == "system.category"

    @respx.mock
    async def test_get_alert_rule_not_found(self, client):
        """get_alert_rule returns error for missing rule."""
        from lm_mcp.tools.alert_rules import get_alert_rule

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/rules/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Alert rule not found"})
        )

        result = await get_alert_rule(client, rule_id=999)

        assert "Error:" in result[0].text
