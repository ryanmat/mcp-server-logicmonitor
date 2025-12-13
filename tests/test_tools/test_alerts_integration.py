# Description: Integration tests for alert tools workflow.
# Description: Tests complete alert management scenarios end-to-end.

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


class TestAlertWorkflow:
    """Integration tests for complete alert workflows."""

    @respx.mock
    async def test_incident_response_flow(self, client, monkeypatch):
        """Test complete incident response: list -> details -> acknowledge."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alerts import acknowledge_alert, get_alert_details, get_alerts

        # Mock: List alerts
        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "LMA100",
                            "severity": 4,
                            "monitorObjectName": "prod-db-01",
                            "alertValue": "Disk usage 95%",
                            "startEpoch": 1702400000,
                        },
                        {
                            "id": "LMA101",
                            "severity": 3,
                            "monitorObjectName": "prod-web-01",
                            "alertValue": "High CPU",
                            "startEpoch": 1702400100,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        # Mock: Get alert details
        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "LMA100",
                    "severity": 4,
                    "monitorObjectName": "prod-db-01",
                    "alertValue": "Disk usage 95%",
                    "resourceTemplateName": "Disk Usage",
                    "instanceName": "/dev/sda1",
                    "startEpoch": 1702400000,
                    "acked": False,
                },
            )
        )

        # Mock: Acknowledge alert
        respx.post("https://test.logicmonitor.com/santaba/rest/alert/alerts/100/ack").mock(
            return_value=httpx.Response(200, json={"success": True})
        )

        # Step 1: List critical alerts
        alerts_result = await get_alerts(client, severity="critical")
        alerts_data = json.loads(alerts_result[0].text)
        assert alerts_data["total"] == 2
        critical_alert_id = alerts_data["alerts"][0]["id"]

        # Step 2: Get details for the critical alert
        details_result = await get_alert_details(client, alert_id=critical_alert_id)
        details_data = json.loads(details_result[0].text)
        assert details_data["severity"] == 4
        assert details_data["acked"] is False

        # Step 3: Acknowledge the alert
        ack_result = await acknowledge_alert(
            client, alert_id=critical_alert_id, note="Investigating disk space issue"
        )
        assert "Error:" not in ack_result[0].text
        ack_data = json.loads(ack_result[0].text)
        assert ack_data["success"] is True

    @respx.mock
    async def test_read_only_mode_blocks_writes(self, client, monkeypatch):
        """Test that read-only mode allows reads but blocks writes."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.alerts import acknowledge_alert, add_alert_note, get_alerts

        # Mock: List alerts (should work)
        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"id": "LMA100", "severity": 4}], "total": 1},
            )
        )

        # Read operation should succeed
        alerts_result = await get_alerts(client)
        assert "Error:" not in alerts_result[0].text

        # Write operations should be blocked
        ack_result = await acknowledge_alert(client, alert_id="100")
        assert "Write operations are disabled" in ack_result[0].text

        note_result = await add_alert_note(client, alert_id="100", note="Test")
        assert "Write operations are disabled" in note_result[0].text

    @respx.mock
    async def test_error_handling_in_workflow(self, client):
        """Test that errors are handled gracefully throughout workflow."""
        from lm_mcp.tools.alerts import get_alert_details, get_alerts

        # Mock: API returns 401
        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=httpx.Response(401, json={"errorMessage": "Invalid token"})
        )

        alerts_result = await get_alerts(client)
        assert "Error:" in alerts_result[0].text
        assert "Invalid token" in alerts_result[0].text

        # Mock: Alert not found
        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Alert not found"})
        )

        details_result = await get_alert_details(client, alert_id="999")
        assert "Error:" in details_result[0].text
        assert "not found" in details_result[0].text.lower()
