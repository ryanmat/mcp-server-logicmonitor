# Description: Tests for action chain and action rule MCP tools.
# Description: Covers CRUD for /setting/action/chains and /setting/action/rules.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient

BASE = "https://test.logicmonitor.com/santaba/rest"


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


def _chain(**overrides) -> dict:
    item = {
        "id": 1,
        "name": "Precursor Diagnostic_Chain",
        "description": "Migrated from diagnostic rule",
        "stages": [
            {"id": 2, "type": "diagnosticSource", "name": "Precursor Diagnostic"},
            {"id": 3, "type": "diagnosticSource", "name": "IBM_Granite_NL_Summary"},
        ],
    }
    item.update(overrides)
    return item


class TestGetActionChains:
    @respx.mock
    async def test_get_action_chains_returns_list(self, client):
        from lm_mcp.tools.actions import get_action_chains

        respx.get(f"{BASE}/setting/action/chains").mock(
            return_value=httpx.Response(200, json={"items": [_chain()], "total": 1})
        )

        result = await get_action_chains(client)

        data = json.loads(result[0].text)
        assert data["total"] == 1
        chain = data["action_chains"][0]
        assert chain["name"] == "Precursor Diagnostic_Chain"
        assert chain["stage_count"] == 2
        assert chain["stages"][0]["type"] == "diagnosticSource"

    @respx.mock
    async def test_get_action_chains_name_filter_client_side(self, client):
        from lm_mcp.tools.actions import get_action_chains

        respx.get(f"{BASE}/setting/action/chains").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [_chain(), _chain(id=2, name="Disk Cleanup Chain")],
                    "total": 2,
                },
            )
        )

        result = await get_action_chains(client, name_filter="disk")

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["action_chains"][0]["name"] == "Disk Cleanup Chain"


class TestGetActionChain:
    @respx.mock
    async def test_get_action_chain_returns_details(self, client):
        from lm_mcp.tools.actions import get_action_chain

        respx.get(f"{BASE}/setting/action/chains/1").mock(
            return_value=httpx.Response(200, json=_chain())
        )

        result = await get_action_chain(client, chain_id=1)

        data = json.loads(result[0].text)
        assert data["id"] == 1
        assert data["stage_count"] == 2

    @respx.mock
    async def test_get_action_chain_not_found(self, client):
        from lm_mcp.tools.actions import get_action_chain

        respx.get(f"{BASE}/setting/action/chains/99").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await get_action_chain(client, chain_id=99)

        assert "error" in result[0].text.lower()


class TestCreateActionChain:
    async def test_create_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.actions import create_action_chain

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_action_chain(
            client, name="X", stages=[{"id": 1, "type": "diagnosticSource"}]
        )

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_posts_chain(self, client, enable_writes):
        from lm_mcp.tools.actions import create_action_chain

        route = respx.post(f"{BASE}/setting/action/chains").mock(
            return_value=httpx.Response(200, json=_chain(id=5, name="New Chain"))
        )

        stages = [{"id": 2, "type": "diagnosticSource", "name": "Top CPU"}]
        result = await create_action_chain(
            client, name="New Chain", stages=stages, description="desc"
        )

        body = json.loads(route.calls[0].request.content)
        assert body == {"name": "New Chain", "stages": stages, "description": "desc"}
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["action_chain"]["id"] == 5

    async def test_create_validates_stage_type(self, client, enable_writes):
        from lm_mcp.tools.actions import create_action_chain

        result = await create_action_chain(
            client, name="X", stages=[{"id": 1, "type": "bogusSource"}]
        )

        assert "Error" in result[0].text
        assert "diagnosticSource" in result[0].text

    async def test_create_validates_empty_stages(self, client, enable_writes):
        from lm_mcp.tools.actions import create_action_chain

        result = await create_action_chain(client, name="X", stages=[])

        assert "Error" in result[0].text
        assert "non-empty" in result[0].text


class TestUpdateActionChain:
    @respx.mock
    async def test_update_patches_only_provided_fields(self, client, enable_writes):
        from lm_mcp.tools.actions import update_action_chain

        route = respx.patch(f"{BASE}/setting/action/chains/1").mock(
            return_value=httpx.Response(200, json=_chain(description="new desc"))
        )

        result = await update_action_chain(client, chain_id=1, description="new desc")

        body = json.loads(route.calls[0].request.content)
        assert body == {"description": "new desc"}
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_update_no_changes_rejected(self, client, enable_writes):
        from lm_mcp.tools.actions import update_action_chain

        result = await update_action_chain(client, chain_id=1)

        assert "Error" in result[0].text
        assert "at least one" in result[0].text

    async def test_update_validates_stages(self, client, enable_writes):
        from lm_mcp.tools.actions import update_action_chain

        result = await update_action_chain(
            client, chain_id=1, stages=[{"id": "not-int", "type": "diagnosticSource"}]
        )

        assert "Error" in result[0].text
        assert "integer" in result[0].text


class TestDeleteActionChain:
    @respx.mock
    async def test_delete_success(self, client, enable_writes):
        from lm_mcp.tools.actions import delete_action_chain

        respx.get(f"{BASE}/setting/action/chains/1").mock(
            return_value=httpx.Response(200, json=_chain())
        )
        respx.delete(f"{BASE}/setting/action/chains/1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_action_chain(client, chain_id=1)

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "Precursor Diagnostic_Chain" in data["message"]

    async def test_delete_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.actions import delete_action_chain

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_action_chain(client, chain_id=1)

        assert "Write operations are disabled" in result[0].text


def _rule(**overrides) -> dict:
    item = {
        "id": 1,
        "name": "Precursor Diagnostic Action Rule",
        "levelStr": "Error",
        "deviceGroups": ["*"],
        "devices": ["*"],
        "datasource": "Precursor Predictive",
        "instance": "*",
        "datapoint": "ClusterId",
        "resourceProperties": [{"name": "precursor.enabled", "value": "true"}],
        "actionChainId": 1,
        "actionChain": {"id": 1, "name": "Precursor Diagnostic_Chain"},
        "enabled": True,
    }
    item.update(overrides)
    return item


class TestGetActionRules:
    @respx.mock
    async def test_get_action_rules_returns_list(self, client):
        from lm_mcp.tools.actions import get_action_rules

        respx.get(f"{BASE}/setting/action/rules").mock(
            return_value=httpx.Response(200, json={"items": [_rule()], "total": 1})
        )

        result = await get_action_rules(client)

        data = json.loads(result[0].text)
        assert data["total"] == 1
        rule = data["action_rules"][0]
        assert rule["level"] == "Error"
        assert rule["action_chain_name"] == "Precursor Diagnostic_Chain"
        assert rule["resource_properties"] == [{"name": "precursor.enabled", "value": "true"}]

    @respx.mock
    async def test_get_action_rules_name_filter(self, client):
        from lm_mcp.tools.actions import get_action_rules

        respx.get(f"{BASE}/setting/action/rules").mock(
            return_value=httpx.Response(
                200, json={"items": [_rule(), _rule(id=2, name="Other Rule")], "total": 2}
            )
        )

        result = await get_action_rules(client, name_filter="precursor")

        data = json.loads(result[0].text)
        assert data["count"] == 1


class TestGetActionRule:
    @respx.mock
    async def test_get_action_rule_returns_details(self, client):
        from lm_mcp.tools.actions import get_action_rule

        respx.get(f"{BASE}/setting/action/rules/1").mock(
            return_value=httpx.Response(200, json=_rule())
        )

        result = await get_action_rule(client, rule_id=1)

        data = json.loads(result[0].text)
        assert data["id"] == 1
        assert data["enabled"] is True


class TestCreateActionRule:
    async def test_create_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.actions import create_action_rule

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_action_rule(
            client, name="X", level="Error", device_groups=["*"], action_chain_id=1
        )

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_posts_rule_body(self, client, enable_writes):
        from lm_mcp.tools.actions import create_action_rule

        route = respx.post(f"{BASE}/setting/action/rules").mock(
            return_value=httpx.Response(200, json=_rule(id=7, name="New Rule"))
        )

        result = await create_action_rule(
            client,
            name="New Rule",
            level="Critical",
            device_groups=["lm-mcp-test-nothing"],
            action_chain_id=1,
            enabled=False,
        )

        body = json.loads(route.calls[0].request.content)
        assert body == {
            "name": "New Rule",
            "levelStr": "Critical",
            "deviceGroups": ["lm-mcp-test-nothing"],
            "actionChainId": 1,
            "enabled": False,
        }
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestUpdateActionRule:
    @respx.mock
    async def test_update_patches_only_provided_fields(self, client, enable_writes):
        from lm_mcp.tools.actions import update_action_rule

        route = respx.patch(f"{BASE}/setting/action/rules/1").mock(
            return_value=httpx.Response(200, json=_rule(datapoint="NewDP"))
        )

        result = await update_action_rule(client, rule_id=1, datapoint="NewDP")

        body = json.loads(route.calls[0].request.content)
        assert body == {"datapoint": "NewDP"}
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_update_no_changes_rejected(self, client, enable_writes):
        from lm_mcp.tools.actions import update_action_rule

        result = await update_action_rule(client, rule_id=1)

        assert "Error" in result[0].text


class TestDeleteActionRule:
    @respx.mock
    async def test_delete_success(self, client, enable_writes):
        from lm_mcp.tools.actions import delete_action_rule

        respx.get(f"{BASE}/setting/action/rules/1").mock(
            return_value=httpx.Response(200, json=_rule())
        )
        respx.delete(f"{BASE}/setting/action/rules/1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_action_rule(client, rule_id=1)

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "Precursor Diagnostic Action Rule" in data["message"]


class TestSetActionRuleStatus:
    @respx.mock
    async def test_status_toggle_puts_enabled(self, client, enable_writes):
        from lm_mcp.tools.actions import set_action_rule_status

        route = respx.put(f"{BASE}/setting/action/rules/1/status").mock(
            return_value=httpx.Response(200, json={"enabled": False})
        )

        result = await set_action_rule_status(client, rule_id=1, enabled=False)

        body = json.loads(route.calls[0].request.content)
        assert body == {"enabled": False}
        data = json.loads(result[0].text)
        assert data["enabled"] is False
        assert "disabled" in data["message"]

    async def test_status_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.actions import set_action_rule_status

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await set_action_rule_status(client, rule_id=1, enabled=True)

        assert "Write operations are disabled" in result[0].text

    def test_set_action_rule_status_classified_as_write(self):
        """The precise prefix keeps session tools read-classified."""
        from lm_mcp.logging import is_write_tool

        assert is_write_tool("set_action_rule_status") is True
        assert is_write_tool("set_session_variable") is False
