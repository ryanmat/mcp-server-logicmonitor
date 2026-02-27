# Description: Tests for action chain MCP tools.
# Description: Validates action chain CRUD functions and registry integration.

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


class TestGetActionChains:
    """Tests for get_action_chains tool."""

    @respx.mock
    async def test_get_action_chains_returns_list(self, client):
        """get_action_chains returns properly formatted chain list."""
        from lm_mcp.tools.action_chains import get_action_chains

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/action/chains").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Disk Diagnostics Chain",
                            "description": "Run disk checks then remediate",
                            "actionchain": [
                                {"type": "diagnosticsource", "diagnosticSourceId": 101},
                                {"type": "remediation", "remediationSourceId": 502},
                            ],
                        },
                        {
                            "id": 2,
                            "name": "CPU Chain",
                            "description": "CPU diagnostics",
                            "actionchain": [
                                {"type": "diagnosticsource", "diagnosticSourceId": 102},
                            ],
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_action_chains(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["action_chains"]) == 2
        assert data["action_chains"][0]["name"] == "Disk Diagnostics Chain"
        assert len(data["action_chains"][0]["actions"]) == 2

    @respx.mock
    async def test_get_action_chains_with_name_filter(self, client):
        """get_action_chains passes name filter to API."""
        from lm_mcp.tools.action_chains import get_action_chains

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/action/chains"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_action_chains(client, name_filter="Disk*")

        assert "filter" in route.calls[0].request.url.params
        assert 'name~"Disk"' in route.calls[0].request.url.params["filter"]

    @respx.mock
    async def test_get_action_chains_handles_error(self, client):
        """get_action_chains returns error on API failure."""
        from lm_mcp.tools.action_chains import get_action_chains

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/action/chains").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_action_chains(client)

        assert "Error:" in result[0].text


class TestGetActionChain:
    """Tests for get_action_chain tool."""

    @respx.mock
    async def test_get_action_chain_returns_details(self, client):
        """get_action_chain returns detailed chain info."""
        from lm_mcp.tools.action_chains import get_action_chain

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/action/chains/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 10,
                    "name": "Full Remediation Chain",
                    "description": "Diagnose then fix",
                    "actionchain": [
                        {"type": "diagnosticsource", "diagnosticSourceId": 101},
                        {"type": "remediation", "remediationSourceId": 502},
                    ],
                },
            )
        )

        result = await get_action_chain(client, chain_id=10)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Full Remediation Chain"
        assert len(data["actions"]) == 2

    @respx.mock
    async def test_get_action_chain_not_found(self, client):
        """get_action_chain returns error for missing chain."""
        from lm_mcp.tools.action_chains import get_action_chain

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/action/chains/999"
        ).mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await get_action_chain(client, chain_id=999)

        assert "Error:" in result[0].text


class TestCreateActionChain:
    """Tests for create_action_chain tool."""

    @respx.mock
    async def test_create_action_chain_blocked_by_default(self, client, monkeypatch):
        """create_action_chain is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import create_action_chain

        result = await create_action_chain(
            client,
            name="Test Chain",
            actions=[{"type": "diagnosticsource", "diagnosticSourceId": 1}],
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_action_chain_succeeds_when_enabled(self, client, monkeypatch):
        """create_action_chain works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import create_action_chain

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/action/chains"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 50,
                    "name": "Test Chain",
                    "actionchain": [
                        {"type": "diagnosticsource", "diagnosticSourceId": 1},
                    ],
                },
            )
        )

        result = await create_action_chain(
            client,
            name="Test Chain",
            actions=[{"type": "diagnosticsource", "diagnosticSourceId": 1}],
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["chain_id"] == 50

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Test Chain"
        assert request_body["actionchain"] == [
            {"type": "diagnosticsource", "diagnosticSourceId": 1}
        ]

    @respx.mock
    async def test_create_action_chain_with_description(self, client, monkeypatch):
        """create_action_chain includes optional description."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import create_action_chain

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/action/chains"
        ).mock(
            return_value=httpx.Response(
                200, json={"id": 51, "name": "Described Chain"}
            )
        )

        await create_action_chain(
            client,
            name="Described Chain",
            description="A chain with diagnostics and remediation",
            actions=[{"type": "diagnosticsource", "diagnosticSourceId": 1}],
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["description"] == "A chain with diagnostics and remediation"


class TestUpdateActionChain:
    """Tests for update_action_chain tool."""

    @respx.mock
    async def test_update_action_chain_blocked_by_default(self, client, monkeypatch):
        """update_action_chain is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import update_action_chain

        result = await update_action_chain(client, chain_id=50, name="Updated Chain")

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_action_chain_succeeds_when_enabled(self, client, monkeypatch):
        """update_action_chain works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import update_action_chain

        respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/action/chains/50"
        ).mock(
            return_value=httpx.Response(
                200, json={"id": 50, "name": "Updated Chain"}
            )
        )

        result = await update_action_chain(client, chain_id=50, name="Updated Chain")

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True

    @respx.mock
    async def test_update_action_chain_no_fields(self, client, monkeypatch):
        """update_action_chain returns error when no fields provided."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import update_action_chain

        result = await update_action_chain(client, chain_id=50)

        assert "Error:" in result[0].text
        assert "No fields provided" in result[0].text

    @respx.mock
    async def test_update_action_chain_with_actions(self, client, monkeypatch):
        """update_action_chain passes actions to API as actionchain."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import update_action_chain

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/action/chains/50"
        ).mock(return_value=httpx.Response(200, json={"id": 50}))

        await update_action_chain(
            client,
            chain_id=50,
            actions=[{"type": "remediation", "remediationSourceId": 99}],
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["actionchain"] == [
            {"type": "remediation", "remediationSourceId": 99}
        ]


class TestDeleteActionChain:
    """Tests for delete_action_chain tool."""

    @respx.mock
    async def test_delete_action_chain_blocked_by_default(self, client, monkeypatch):
        """delete_action_chain is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import delete_action_chain

        result = await delete_action_chain(client, chain_id=50)

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_action_chain_succeeds_when_enabled(self, client, monkeypatch):
        """delete_action_chain works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.action_chains import delete_action_chain

        respx.delete(
            "https://test.logicmonitor.com/santaba/rest/setting/action/chains/50"
        ).mock(return_value=httpx.Response(200, json={}))

        result = await delete_action_chain(client, chain_id=50)

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestActionChainToolRegistration:
    """Tests for action chain tool registration."""

    def test_get_action_chains_registered(self):
        """get_action_chains is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_action_chains" in tool_names

    def test_get_action_chain_registered(self):
        """get_action_chain is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_action_chain" in tool_names

    def test_create_action_chain_registered(self):
        """create_action_chain is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "create_action_chain" in tool_names

    def test_update_action_chain_registered(self):
        """update_action_chain is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "update_action_chain" in tool_names

    def test_delete_action_chain_registered(self):
        """delete_action_chain is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "delete_action_chain" in tool_names

    def test_get_action_chains_handler_registered(self):
        """get_action_chains handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("get_action_chains")
        assert handler is not None

    def test_create_action_chain_handler_registered(self):
        """create_action_chain handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("create_action_chain")
        assert handler is not None

    def test_delete_action_chain_handler_registered(self):
        """delete_action_chain handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("delete_action_chain")
        assert handler is not None
