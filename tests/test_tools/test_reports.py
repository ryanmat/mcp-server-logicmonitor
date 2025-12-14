# Description: Tests for report management MCP tools.
# Description: Validates get_reports, get_report, get_report_groups, run_report.

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


class TestGetReports:
    """Tests for get_reports tool."""

    @respx.mock
    async def test_get_reports_returns_list(self, client):
        """get_reports returns properly formatted report list."""
        from lm_mcp.tools.reports import get_reports

        respx.get("https://test.logicmonitor.com/santaba/rest/report/reports").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Daily Alert Report",
                            "description": "Daily summary of alerts",
                            "type": "Alert",
                            "groupId": 1,
                            "groupFullPath": "Reports/Alerts",
                            "format": "PDF",
                            "schedule": "daily",
                            "lastGenerateOn": 1702500000,
                        },
                        {
                            "id": 2,
                            "name": "Weekly Host Metrics",
                            "description": "Weekly host metrics summary",
                            "type": "Host metric",
                            "groupId": 2,
                            "groupFullPath": "Reports/Metrics",
                            "format": "CSV",
                            "schedule": "weekly",
                            "lastGenerateOn": 1702400000,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_reports(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["reports"]) == 2
        assert data["reports"][0]["name"] == "Daily Alert Report"
        assert data["reports"][1]["type"] == "Host metric"

    @respx.mock
    async def test_get_reports_with_filters(self, client):
        """get_reports passes filters to API."""
        from lm_mcp.tools.reports import get_reports

        route = respx.get("https://test.logicmonitor.com/santaba/rest/report/reports").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_reports(client, name_filter="Daily*", group_id=1, report_type="Alert")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_reports_handles_error(self, client):
        """get_reports handles API error gracefully."""
        from lm_mcp.tools.reports import get_reports

        respx.get("https://test.logicmonitor.com/santaba/rest/report/reports").mock(
            return_value=httpx.Response(403, json={"errorMessage": "Permission denied"})
        )

        result = await get_reports(client)

        assert "Error:" in result[0].text


class TestGetReport:
    """Tests for get_report tool."""

    @respx.mock
    async def test_get_report_returns_details(self, client):
        """get_report returns detailed report info."""
        from lm_mcp.tools.reports import get_report

        respx.get("https://test.logicmonitor.com/santaba/rest/report/reports/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "Daily Alert Report",
                    "description": "Daily summary of alerts",
                    "type": "Alert",
                    "groupId": 1,
                    "groupFullPath": "Reports/Alerts",
                    "format": "PDF",
                    "delivery": "email",
                    "schedule": "daily",
                    "dateRange": "last24hours",
                    "recipients": [
                        {"type": "admin", "method": "email", "addr": "admin@example.com"}
                    ],
                    "lastGenerateOn": 1702500000,
                    "lastGenerateSize": 1024,
                    "lastGeneratePages": 5,
                    "lastmodifyUserName": "admin",
                },
            )
        )

        result = await get_report(client, report_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 100
        assert data["name"] == "Daily Alert Report"
        assert len(data["recipients"]) == 1
        assert data["recipients"][0]["address"] == "admin@example.com"

    @respx.mock
    async def test_get_report_not_found(self, client):
        """get_report returns error for missing report."""
        from lm_mcp.tools.reports import get_report

        respx.get("https://test.logicmonitor.com/santaba/rest/report/reports/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Report not found"})
        )

        result = await get_report(client, report_id=999)

        assert "Error:" in result[0].text


class TestGetReportGroups:
    """Tests for get_report_groups tool."""

    @respx.mock
    async def test_get_report_groups_returns_list(self, client):
        """get_report_groups returns group list."""
        from lm_mcp.tools.reports import get_report_groups

        respx.get("https://test.logicmonitor.com/santaba/rest/report/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Alert Reports",
                            "description": "Alert-related reports",
                            "numOfReports": 5,
                        },
                        {
                            "id": 2,
                            "name": "Metric Reports",
                            "description": "Metric-related reports",
                            "numOfReports": 10,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_report_groups(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["groups"]) == 2
        assert data["groups"][0]["name"] == "Alert Reports"
        assert data["groups"][1]["report_count"] == 10

    @respx.mock
    async def test_get_report_groups_with_filter(self, client):
        """get_report_groups passes name filter to API."""
        from lm_mcp.tools.reports import get_report_groups

        route = respx.get("https://test.logicmonitor.com/santaba/rest/report/groups").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_report_groups(client, name_filter="Alert*")

        assert "filter" in route.calls[0].request.url.params


class TestRunReport:
    """Tests for run_report tool."""

    @respx.mock
    async def test_run_report_blocked_by_default(self, client, monkeypatch):
        """run_report blocked when writes disabled."""
        from lm_mcp.tools.reports import run_report

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await run_report(client, report_id=100)

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_run_report_succeeds_when_enabled(self, client, monkeypatch):
        """run_report works when writes enabled."""
        from lm_mcp.tools.reports import run_report

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.post("https://test.logicmonitor.com/santaba/rest/functions").mock(
            return_value=httpx.Response(200, json={"taskId": "task-12345"})
        )

        result = await run_report(client, report_id=100, notify_email="user@example.com")

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["report_id"] == 100
        assert data["task_id"] == "task-12345"
