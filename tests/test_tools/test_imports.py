# Description: Tests for Import/Export MCP tools.
# Description: Validates export functions for LogicModules and configurations.

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


class TestExportDatasource:
    """Tests for export_datasource tool."""

    @respx.mock
    async def test_export_datasource_returns_full_definition(self, client):
        """export_datasource returns complete DataSource JSON."""
        from lm_mcp.tools.imports import export_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "CPU",
                    "displayName": "CPU Stats",
                    "description": "CPU monitoring",
                    "appliesTo": "isLinux()",
                    "collectMethod": "script",
                    "dataPoints": [{"id": 1, "name": "CPUPercent"}],
                },
            )
        )

        result = await export_datasource(client, datasource_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["datasource_id"] == 123
        assert data["name"] == "CPU"
        assert data["format"] == "json"
        assert data["definition"]["collectMethod"] == "script"

    @respx.mock
    async def test_export_datasource_not_found(self, client):
        """export_datasource returns error for missing datasource."""
        from lm_mcp.tools.imports import export_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "DataSource not found"})
        )

        result = await export_datasource(client, datasource_id=999)

        assert "Error:" in result[0].text


class TestExportDashboard:
    """Tests for export_dashboard tool."""

    @respx.mock
    async def test_export_dashboard_with_widgets(self, client):
        """export_dashboard includes widgets when requested."""
        from lm_mcp.tools.imports import export_dashboard

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/456").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 456,
                    "name": "Production Overview",
                    "groupId": 1,
                    "description": "Main dashboard",
                },
            )
        )

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/456/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 1, "name": "CPU Widget", "type": "cgraph"},
                        {"id": 2, "name": "Memory Widget", "type": "cgraph"},
                    ],
                    "total": 2,
                },
            )
        )

        result = await export_dashboard(client, dashboard_id=456, include_widgets=True)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["dashboard_id"] == 456
        assert data["name"] == "Production Overview"
        assert len(data["definition"]["widgets_full"]) == 2


class TestExportAlertRule:
    """Tests for export_alert_rule tool."""

    @respx.mock
    async def test_export_alert_rule_returns_definition(self, client):
        """export_alert_rule returns complete alert rule JSON."""
        from lm_mcp.tools.imports import export_alert_rule

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/rules/789").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 789,
                    "name": "Critical CPU Alert",
                    "priority": 100,
                    "escalatingChainId": 1,
                    "datasource": "CPU",
                },
            )
        )

        result = await export_alert_rule(client, alert_rule_id=789)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["alert_rule_id"] == 789
        assert data["name"] == "Critical CPU Alert"


class TestExportEscalationChain:
    """Tests for export_escalation_chain tool."""

    @respx.mock
    async def test_export_escalation_chain_returns_definition(self, client):
        """export_escalation_chain returns complete chain JSON."""
        from lm_mcp.tools.imports import export_escalation_chain

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/alert/chains/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 101,
                    "name": "On-Call Team",
                    "destinations": [
                        {"type": "single", "period": {"minutes": 15}, "contact": "admin"}
                    ],
                },
            )
        )

        result = await export_escalation_chain(client, escalation_chain_id=101)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["escalation_chain_id"] == 101
        assert data["name"] == "On-Call Team"
