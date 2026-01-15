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


class TestImportDatasource:
    """Tests for import_datasource tool (v228 JSON import API)."""

    @respx.mock
    async def test_import_datasource_success(self, client, monkeypatch):
        """import_datasource successfully imports a DataSource."""
        from lm_mcp.tools.imports import import_datasource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/importjson"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1001,
                    "name": "ImportedDataSource",
                    "displayName": "Imported DataSource",
                },
            )
        )

        definition = {
            "name": "ImportedDataSource",
            "displayName": "Imported DataSource",
            "appliesTo": "isLinux()",
            "collectMethod": "script",
        }

        result = await import_datasource(client, definition=definition)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["imported_id"] == 1001
        assert data["name"] == "ImportedDataSource"

    async def test_import_datasource_requires_write_permission(self, client, monkeypatch):
        """import_datasource requires write permission."""
        from lm_mcp.tools.imports import import_datasource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await import_datasource(client, definition={"name": "test"})

        assert len(result) == 1
        assert "Write operations are disabled" in result[0].text


class TestImportConfigsource:
    """Tests for import_configsource tool (v228 JSON import API)."""

    @respx.mock
    async def test_import_configsource_success(self, client, monkeypatch):
        """import_configsource successfully imports a ConfigSource."""
        from lm_mcp.tools.imports import import_configsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/configsources/importjson"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 2001,
                    "name": "ImportedConfigSource",
                },
            )
        )

        result = await import_configsource(client, definition={"name": "ImportedConfigSource"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["imported_id"] == 2001


class TestImportEventsource:
    """Tests for import_eventsource tool (v228 JSON import API)."""

    @respx.mock
    async def test_import_eventsource_success(self, client, monkeypatch):
        """import_eventsource successfully imports an EventSource."""
        from lm_mcp.tools.imports import import_eventsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/eventsources/importjson"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 3001,
                    "name": "ImportedEventSource",
                },
            )
        )

        result = await import_eventsource(client, definition={"name": "ImportedEventSource"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["imported_id"] == 3001


class TestImportPropertysource:
    """Tests for import_propertysource tool (v228 JSON import API)."""

    @respx.mock
    async def test_import_propertysource_success(self, client, monkeypatch):
        """import_propertysource successfully imports a PropertySource."""
        from lm_mcp.tools.imports import import_propertysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/propertyrules/importjson"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 4001,
                    "name": "ImportedPropertySource",
                },
            )
        )

        result = await import_propertysource(client, definition={"name": "ImportedPropertySource"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["imported_id"] == 4001


class TestImportLogsource:
    """Tests for import_logsource tool (v228 JSON import API)."""

    @respx.mock
    async def test_import_logsource_success(self, client, monkeypatch):
        """import_logsource successfully imports a LogSource."""
        from lm_mcp.tools.imports import import_logsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/logsources/importjson").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5001,
                    "name": "ImportedLogSource",
                },
            )
        )

        result = await import_logsource(client, definition={"name": "ImportedLogSource"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["imported_id"] == 5001


class TestImportTopologysource:
    """Tests for import_topologysource tool (v228 JSON import API)."""

    @respx.mock
    async def test_import_topologysource_success(self, client, monkeypatch):
        """import_topologysource successfully imports a TopologySource."""
        from lm_mcp.tools.imports import import_topologysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources/importjson"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 6001,
                    "name": "ImportedTopologySource",
                },
            )
        )

        result = await import_topologysource(client, definition={"name": "ImportedTopologySource"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["imported_id"] == 6001


class TestImportJobmonitor:
    """Tests for import_jobmonitor tool (v228 JSON import API)."""

    @respx.mock
    async def test_import_jobmonitor_success(self, client, monkeypatch):
        """import_jobmonitor successfully imports a JobMonitor."""
        from lm_mcp.tools.imports import import_jobmonitor

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/batchjobs/importjson").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 7001,
                    "name": "ImportedJobMonitor",
                },
            )
        )

        result = await import_jobmonitor(client, definition={"name": "ImportedJobMonitor"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["imported_id"] == 7001


class TestImportAppliestoFunction:
    """Tests for import_appliesto_function tool (v228 JSON import API)."""

    @respx.mock
    async def test_import_appliesto_function_success(self, client, monkeypatch):
        """import_appliesto_function successfully imports a function."""
        from lm_mcp.tools.imports import import_appliesto_function

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/functions/importjson").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 8001,
                    "name": "ImportedFunction",
                },
            )
        )

        result = await import_appliesto_function(client, definition={"name": "ImportedFunction"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["imported_id"] == 8001
