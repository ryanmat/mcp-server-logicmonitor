# Description: Tests for escalation chain and recipient group MCP tools.
# Description: Validates escalation chain and recipient group query functions.

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


class TestGetEscalationChains:
    """Tests for get_escalation_chains tool."""

    @respx.mock
    async def test_get_escalation_chains_returns_list(self, client):
        """get_escalation_chains returns properly formatted chain list."""
        from lm_mcp.tools.escalations import get_escalation_chains

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Primary On-Call",
                            "description": "Primary escalation",
                            "enableThrottling": True,
                            "throttlingPeriod": 10,
                            "throttlingAlerts": 5,
                            "inAlerting": False,
                        },
                        {
                            "id": 2,
                            "name": "Secondary On-Call",
                            "description": "Secondary escalation",
                            "enableThrottling": False,
                            "throttlingPeriod": 0,
                            "throttlingAlerts": 0,
                            "inAlerting": True,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_escalation_chains(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["escalation_chains"]) == 2
        assert data["escalation_chains"][0]["name"] == "Primary On-Call"
        assert data["escalation_chains"][1]["in_alerting"] is True

    @respx.mock
    async def test_get_escalation_chains_with_filter(self, client):
        """get_escalation_chains passes name filter to API."""
        from lm_mcp.tools.escalations import get_escalation_chains

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_escalation_chains(client, name_filter="Primary*")

        assert "filter" in route.calls[0].request.url.params


class TestGetEscalationChain:
    """Tests for get_escalation_chain tool."""

    @respx.mock
    async def test_get_escalation_chain_returns_details(self, client):
        """get_escalation_chain returns detailed chain info."""
        from lm_mcp.tools.escalations import get_escalation_chain

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/chains/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "Primary On-Call",
                    "description": "Primary escalation chain",
                    "enableThrottling": True,
                    "throttlingPeriod": 10,
                    "throttlingAlerts": 5,
                    "inAlerting": False,
                    "destinations": [
                        {
                            "type": "single",
                            "period": 15,
                            "stages": [
                                {
                                    "type": "admin",
                                    "addr": "oncall@example.com",
                                    "contact": "On-Call Team",
                                }
                            ],
                        }
                    ],
                    "ccDestinations": [
                        {
                            "type": "ARBITRARY",
                            "method": "email",
                            "addr": "manager@example.com",
                            "contact": "Manager",
                        }
                    ],
                },
            )
        )

        result = await get_escalation_chain(client, chain_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 100
        assert data["name"] == "Primary On-Call"
        assert len(data["destinations"]) == 1
        assert data["destinations"][0]["stages"][0]["address"] == "oncall@example.com"
        assert len(data["cc_destinations"]) == 1

    @respx.mock
    async def test_get_escalation_chain_not_found(self, client):
        """get_escalation_chain returns error for missing chain."""
        from lm_mcp.tools.escalations import get_escalation_chain

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/chains/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Escalation chain not found"})
        )

        result = await get_escalation_chain(client, chain_id=999)

        assert "Error:" in result[0].text


class TestGetRecipientGroups:
    """Tests for get_recipient_groups tool."""

    @respx.mock
    async def test_get_recipient_groups_returns_list(self, client):
        """get_recipient_groups returns group list."""
        from lm_mcp.tools.escalations import get_recipient_groups

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/recipientgroups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "DevOps Team",
                            "description": "DevOps notification group",
                            "groupType": "email",
                        },
                        {
                            "id": 2,
                            "name": "Management",
                            "description": "Management notification group",
                            "groupType": "email",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_recipient_groups(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["recipient_groups"]) == 2
        assert data["recipient_groups"][0]["name"] == "DevOps Team"

    @respx.mock
    async def test_get_recipient_groups_with_filter(self, client):
        """get_recipient_groups passes name filter to API."""
        from lm_mcp.tools.escalations import get_recipient_groups

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/recipientgroups"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_recipient_groups(client, name_filter="DevOps*")

        assert "filter" in route.calls[0].request.url.params


class TestGetRecipientGroup:
    """Tests for get_recipient_group tool."""

    @respx.mock
    async def test_get_recipient_group_returns_details(self, client):
        """get_recipient_group returns detailed group info."""
        from lm_mcp.tools.escalations import get_recipient_group

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/recipientgroups/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "DevOps Team",
                    "description": "DevOps notification group",
                    "groupType": "email",
                    "recipients": [
                        {
                            "type": "admin",
                            "method": "email",
                            "addr": "devops1@example.com",
                            "contact": "DevOps Engineer 1",
                        },
                        {
                            "type": "admin",
                            "method": "email",
                            "addr": "devops2@example.com",
                            "contact": "DevOps Engineer 2",
                        },
                    ],
                },
            )
        )

        result = await get_recipient_group(client, group_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 100
        assert data["name"] == "DevOps Team"
        assert len(data["recipients"]) == 2
        assert data["recipients"][0]["address"] == "devops1@example.com"

    @respx.mock
    async def test_get_recipient_group_not_found(self, client):
        """get_recipient_group returns error for missing group."""
        from lm_mcp.tools.escalations import get_recipient_group

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/recipientgroups/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Recipient group not found"})
        )

        result = await get_recipient_group(client, group_id=999)

        assert "Error:" in result[0].text
