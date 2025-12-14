# Description: Full integration tests for LogicMonitor MCP server.
# Description: Tests realistic workflows across multiple tools.

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools.alerts import (
    acknowledge_alert,
    add_alert_note,
    get_alert_details,
    get_alerts,
)
from lm_mcp.tools.collectors import get_collector, get_collectors
from lm_mcp.tools.dashboards import (
    create_dashboard,
    get_dashboard,
    get_dashboard_widgets,
    get_dashboards,
)
from lm_mcp.tools.datasources import get_datasource, get_datasources
from lm_mcp.tools.devices import get_device, get_device_groups, get_devices
from lm_mcp.tools.metrics import (
    get_device_data,
    get_device_datasources,
    get_device_instances,
    get_graph_data,
)
from lm_mcp.tools.sdts import create_sdt, delete_sdt, list_sdts


@pytest.fixture
def auth():
    """Create a BearerAuth instance for testing."""
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    """Create test client."""
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


@pytest.fixture
def disable_writes(monkeypatch):
    """Disable write operations for testing."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


class TestIncidentResponseFlow:
    """Test realistic incident response workflow."""

    @respx.mock
    async def test_full_incident_response(self, client, enable_writes):
        """
        Workflow: Alert fires → Get details → Find device → Ack alert → Add note.

        This simulates an operator responding to a critical alert.
        """
        # Mock: Get active critical alerts
        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "LMA12345",
                            "severity": 4,
                            "type": "alert",
                            "monitorObjectName": "prod-web-01",
                            "resourceId": 100,
                            "alertValue": "CPU at 95%",
                            "startEpoch": 1702500000,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        # Mock: Get alert details
        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts/12345").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "LMA12345",
                    "severity": 4,
                    "type": "alert",
                    "monitorObjectName": "prod-web-01",
                    "resourceId": 100,
                    "alertValue": "CPU at 95%",
                    "startEpoch": 1702500000,
                    "acked": False,
                    "ackedBy": "",
                    "rule": "High CPU Usage",
                    "chain": "CPU > 90%",
                },
            )
        )

        # Mock: Get device details
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "displayName": "prod-web-01",
                    "hostGroupIds": "1,2,3",
                    "preferredCollectorId": 1,
                    "systemProperties": [
                        {"name": "system.hostname", "value": "prod-web-01.example.com"}
                    ],
                },
            )
        )

        # Mock: Acknowledge alert
        respx.post("https://test.logicmonitor.com/santaba/rest/alert/alerts/12345/ack").mock(
            return_value=httpx.Response(200, json={"id": "LMA12345", "acked": True})
        )

        # Mock: Add note
        respx.post("https://test.logicmonitor.com/santaba/rest/alert/alerts/12345/note").mock(
            return_value=httpx.Response(
                200, json={"id": "LMA12345", "note": "Investigating high CPU"}
            )
        )

        # Step 1: Get critical alerts
        alerts_result = await get_alerts(client, severity="critical", status="active")
        assert len(alerts_result) == 1
        assert "LMA12345" in alerts_result[0].text

        # Step 2: Get alert details
        details_result = await get_alert_details(client, "LMA12345")
        assert len(details_result) == 1
        assert "prod-web-01" in details_result[0].text
        assert "CPU at 95%" in details_result[0].text

        # Step 3: Get device details
        device_result = await get_device(client, 100)
        assert len(device_result) == 1
        assert "prod-web-01" in device_result[0].text

        # Step 4: Acknowledge alert
        ack_result = await acknowledge_alert(client, "LMA12345")
        assert len(ack_result) == 1

        # Step 5: Add investigation note
        note_result = await add_alert_note(client, "LMA12345", "Investigating high CPU")
        assert len(note_result) == 1


class TestMaintenanceWindowFlow:
    """Test maintenance window (SDT) workflow."""

    @respx.mock
    async def test_scheduled_maintenance(self, client, enable_writes):
        """
        Workflow: Find device → Create SDT → Verify → Delete SDT.

        This simulates scheduling maintenance on a device.
        """
        # Mock: Search for device
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 200,
                            "displayName": "db-server-01",
                            "hostGroupIds": "5",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        # Mock: Create SDT
        respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "SDT_500",
                    "type": "DeviceSDT",
                    "deviceId": 200,
                    "comment": "Database maintenance",
                    "startDateTime": 1702500000,
                    "endDateTime": 1702503600,
                },
            )
        )

        # Mock: List SDTs to verify
        respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "SDT_500",
                            "type": "DeviceSDT",
                            "deviceId": 200,
                            "comment": "Database maintenance",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        # Mock: Delete SDT
        respx.delete("https://test.logicmonitor.com/santaba/rest/sdt/sdts/SDT_500").mock(
            return_value=httpx.Response(200, json={})
        )

        # Step 1: Find the device
        devices_result = await get_devices(client, name_filter="db-server")
        assert len(devices_result) == 1
        assert "db-server-01" in devices_result[0].text

        # Step 2: Create SDT for maintenance
        sdt_result = await create_sdt(
            client,
            sdt_type="device",
            device_id=200,
            duration_minutes=60,
            comment="Database maintenance",
        )
        assert len(sdt_result) == 1

        # Step 3: Verify SDT exists
        list_result = await list_sdts(client)
        assert len(list_result) == 1
        assert "SDT_500" in list_result[0].text

        # Step 4: Delete SDT after maintenance
        delete_result = await delete_sdt(client, "SDT_500")
        assert len(delete_result) == 1


class TestHealthCheckFlow:
    """Test infrastructure health check workflow."""

    @respx.mock
    async def test_infrastructure_health_check(self, client):
        """
        Workflow: Check collectors → Check devices → Review device groups.

        This simulates a daily health check routine.
        """
        # Mock: Get collectors
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "hostname": "collector-01",
                            "status": 0,
                            "numberOfHosts": 50,
                        },
                        {
                            "id": 2,
                            "hostname": "collector-02",
                            "status": 0,
                            "numberOfHosts": 45,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        # Mock: Get specific collector
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "hostname": "collector-01",
                    "status": 0,
                    "numberOfHosts": 50,
                    "build": "34000",
                    "platform": "linux",
                },
            )
        )

        # Mock: Get devices
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 1, "displayName": "server-01", "hostGroupIds": "1"},
                        {"id": 2, "displayName": "server-02", "hostGroupIds": "1"},
                    ],
                    "total": 2,
                },
            )
        )

        # Mock: Get device groups
        respx.get("https://test.logicmonitor.com/santaba/rest/device/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Production",
                            "numOfHosts": 25,
                            "parentId": 0,
                        },
                        {
                            "id": 2,
                            "name": "Development",
                            "numOfHosts": 10,
                            "parentId": 0,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        # Step 1: Check all collectors are healthy
        collectors_result = await get_collectors(client)
        assert len(collectors_result) == 1
        assert "collector-01" in collectors_result[0].text
        assert "collector-02" in collectors_result[0].text

        # Step 2: Get details on primary collector
        collector_result = await get_collector(client, 1)
        assert len(collector_result) == 1
        assert "collector-01" in collector_result[0].text

        # Step 3: Check device count
        devices_result = await get_devices(client)
        assert len(devices_result) == 1
        assert "server-01" in devices_result[0].text

        # Step 4: Review device groups
        groups_result = await get_device_groups(client)
        assert len(groups_result) == 1
        assert "Production" in groups_result[0].text


class TestReadOnlyEnforcement:
    """Test that read-only mode blocks write operations."""

    @respx.mock
    async def test_write_operations_blocked(self, client, disable_writes):
        """Verify all write operations return error in read-only mode."""
        # Try to acknowledge alert - should be blocked
        ack_result = await acknowledge_alert(client, "LMA12345")
        assert len(ack_result) == 1
        assert "error" in ack_result[0].text.lower()
        assert "write" in ack_result[0].text.lower()

        # Try to create SDT - should be blocked
        sdt_result = await create_sdt(
            client,
            sdt_type="device",
            device_id=100,
            duration_minutes=60,
        )
        assert len(sdt_result) == 1
        assert "error" in sdt_result[0].text.lower()

        # Try to add note - should be blocked
        note_result = await add_alert_note(client, "LMA12345", "Test note")
        assert len(note_result) == 1
        assert "error" in note_result[0].text.lower()


class TestErrorRecovery:
    """Test error handling across tools."""

    @respx.mock
    async def test_not_found_handling(self, client):
        """Verify 404 errors are handled gracefully."""
        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts/99999").mock(
            return_value=httpx.Response(
                404, json={"errorMessage": "Alert not found", "errorCode": 1404}
            )
        )

        result = await get_alert_details(client, "99999")
        assert len(result) == 1
        text_lower = result[0].text.lower()
        assert "error" in text_lower or "not found" in text_lower

    @respx.mock
    async def test_permission_denied_handling(self, client):
        """Verify 403 errors are handled gracefully."""
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(
                403, json={"errorMessage": "Permission denied", "errorCode": 1403}
            )
        )

        result = await get_devices(client)
        assert len(result) == 1
        assert "error" in result[0].text.lower()


class TestMetricsInvestigationFlow:
    """Test metrics investigation workflow."""

    @respx.mock
    async def test_cpu_metrics_investigation(self, client):
        """
        Workflow: Find device → List datasources → Get instances → Get metrics.

        This simulates investigating CPU usage on a device.
        """
        # Mock: Get device
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "displayName": "prod-web-01",
                    "hostGroupIds": "1",
                },
            )
        )

        # Mock: Get device datasources
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1001,
                            "dataSourceId": 50,
                            "dataSourceName": "CPU",
                            "instanceNumber": 1,
                            "monitoringInstanceNumber": 1,
                        },
                        {
                            "id": 1002,
                            "dataSourceId": 51,
                            "dataSourceName": "Memory",
                            "instanceNumber": 1,
                            "monitoringInstanceNumber": 1,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        # Mock: Get CPU instances
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 5001,
                            "displayName": "CPU_Total",
                            "description": "Total CPU usage",
                            "groupName": "",
                            "lockDescription": False,
                            "stopMonitoring": False,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        # Mock: Get CPU data
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["CPUBusyPercent", "CPUIdlePercent"],
                    "values": {
                        "CPUBusyPercent": [25.5, 30.2, 28.1, 95.0, 92.5],
                        "CPUIdlePercent": [74.5, 69.8, 71.9, 5.0, 7.5],
                    },
                    "time": [
                        1702500000,
                        1702500060,
                        1702500120,
                        1702500180,
                        1702500240,
                    ],
                },
            )
        )

        # Step 1: Get device details
        device_result = await get_device(client, 100)
        assert len(device_result) == 1
        assert "prod-web-01" in device_result[0].text

        # Step 2: List available datasources
        ds_result = await get_device_datasources(client, device_id=100)
        assert len(ds_result) == 1
        assert "CPU" in ds_result[0].text
        assert "Memory" in ds_result[0].text

        # Step 3: Get CPU instances
        instances_result = await get_device_instances(
            client, device_id=100, device_datasource_id=1001
        )
        assert len(instances_result) == 1
        assert "CPU_Total" in instances_result[0].text

        # Step 4: Get CPU metrics
        data_result = await get_device_data(
            client, device_id=100, device_datasource_id=1001, instance_id=5001
        )
        assert len(data_result) == 1
        assert "CPUBusyPercent" in data_result[0].text

    @respx.mock
    async def test_graph_data_retrieval(self, client):
        """
        Workflow: Get graph data for visualization.

        This simulates retrieving graph data for a dashboard.
        """
        # Mock: Get graph data
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/graphs/200/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "lines": [
                        {"legend": "CPU Usage %", "data": [25.5, 30.2, 28.1]},
                        {"legend": "CPU Idle %", "data": [74.5, 69.8, 71.9]},
                    ],
                    "timestamps": [1702500000, 1702500060, 1702500120],
                },
            )
        )

        # Get graph data
        result = await get_graph_data(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
            graph_id=200,
        )

        assert len(result) == 1
        assert "CPU Usage %" in result[0].text
        assert "timestamps" in result[0].text


class TestDashboardManagementFlow:
    """Test dashboard management workflow."""

    @respx.mock
    async def test_dashboard_exploration(self, client):
        """
        Workflow: List dashboards → Get dashboard details → Get widgets.

        This simulates exploring available dashboards.
        """
        # Mock: List dashboards
        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 100,
                            "name": "Production Overview",
                            "description": "Main production dashboard",
                            "groupId": 1,
                            "groupFullPath": "Dashboards",
                            "owner": "admin",
                            "widgetsConfig": [1, 2, 3, 4, 5],
                        },
                        {
                            "id": 101,
                            "name": "Network Status",
                            "description": "Network monitoring",
                            "groupId": 1,
                            "groupFullPath": "Dashboards",
                            "owner": "admin",
                            "widgetsConfig": [6, 7],
                        },
                    ],
                    "total": 2,
                },
            )
        )

        # Mock: Get dashboard details
        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "Production Overview",
                    "description": "Main production dashboard",
                    "groupId": 1,
                    "owner": "admin",
                },
            )
        )

        # Mock: Get widgets
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/100/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1001,
                            "name": "CPU Overview",
                            "type": "cgraph",
                            "description": "CPU metrics",
                            "columnIdx": 0,
                            "rowSpan": 1,
                            "colSpan": 6,
                        },
                        {
                            "id": 1002,
                            "name": "Memory Overview",
                            "type": "cgraph",
                            "description": "Memory metrics",
                            "columnIdx": 6,
                            "rowSpan": 1,
                            "colSpan": 6,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        # Step 1: List available dashboards
        dashboards_result = await get_dashboards(client)
        assert len(dashboards_result) == 1
        assert "Production Overview" in dashboards_result[0].text
        assert "Network Status" in dashboards_result[0].text

        # Step 2: Get specific dashboard details
        dashboard_result = await get_dashboard(client, dashboard_id=100)
        assert len(dashboard_result) == 1
        assert "Production Overview" in dashboard_result[0].text

        # Step 3: Get widgets on the dashboard
        widgets_result = await get_dashboard_widgets(client, dashboard_id=100)
        assert len(widgets_result) == 1
        assert "CPU Overview" in widgets_result[0].text
        assert "Memory Overview" in widgets_result[0].text

    @respx.mock
    async def test_create_dashboard_workflow(self, client, enable_writes):
        """
        Workflow: Create dashboard → Verify creation.

        This simulates creating a new dashboard.
        """
        # Mock: Create dashboard
        respx.post("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 200,
                    "name": "New Monitoring Dashboard",
                    "groupId": 1,
                    "description": "Created via API",
                },
            )
        )

        # Mock: List dashboards to verify
        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 200,
                            "name": "New Monitoring Dashboard",
                            "description": "Created via API",
                            "groupId": 1,
                            "groupFullPath": "Dashboards",
                            "owner": "admin",
                            "widgetsConfig": [],
                        }
                    ],
                    "total": 1,
                },
            )
        )

        # Step 1: Create new dashboard
        create_result = await create_dashboard(
            client,
            name="New Monitoring Dashboard",
            description="Created via API",
        )
        assert len(create_result) == 1
        assert "success" in create_result[0].text.lower()

        # Step 2: Verify dashboard exists
        list_result = await get_dashboards(client)
        assert len(list_result) == 1
        assert "New Monitoring Dashboard" in list_result[0].text


class TestDatasourceExplorationFlow:
    """Test DataSource exploration workflow."""

    @respx.mock
    async def test_datasource_discovery(self, client):
        """
        Workflow: List datasources → Get details → Check datapoints.

        This simulates exploring available monitoring modules.
        """
        # Mock: List datasources
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 100,
                            "name": "WinCPU",
                            "displayName": "Windows CPU",
                            "description": "Windows CPU monitoring",
                            "appliesTo": "isWindows()",
                            "group": "Core",
                            "collectMethod": "wmi",
                            "hasMultiInstances": True,
                        },
                        {
                            "id": 101,
                            "name": "LinuxCPU",
                            "displayName": "Linux CPU",
                            "description": "Linux CPU monitoring",
                            "appliesTo": "isLinux()",
                            "group": "Core",
                            "collectMethod": "snmp",
                            "hasMultiInstances": True,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        # Mock: Get datasource details
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "WinCPU",
                    "displayName": "Windows CPU",
                    "description": "Windows CPU monitoring",
                    "appliesTo": "isWindows()",
                    "group": "Core",
                    "collectMethod": "wmi",
                    "collectInterval": 60,
                    "hasMultiInstances": True,
                    "dataPoints": [
                        {
                            "id": 1,
                            "name": "CPUBusyPercent",
                            "description": "CPU busy percentage",
                            "type": 0,
                            "alertExpr": "> 90",
                        },
                        {
                            "id": 2,
                            "name": "CPUIdlePercent",
                            "description": "CPU idle percentage",
                            "type": 0,
                            "alertExpr": "",
                        },
                    ],
                    "graphs": [
                        {
                            "id": 10,
                            "name": "CPUGraph",
                            "title": "CPU Usage",
                        }
                    ],
                },
            )
        )

        # Step 1: List available datasources
        ds_list = await get_datasources(client)
        assert len(ds_list) == 1
        assert "WinCPU" in ds_list[0].text
        assert "LinuxCPU" in ds_list[0].text

        # Step 2: Get details on Windows CPU datasource
        ds_detail = await get_datasource(client, datasource_id=100)
        assert len(ds_detail) == 1
        assert "CPUBusyPercent" in ds_detail[0].text
        assert "CPUIdlePercent" in ds_detail[0].text
        assert "CPU Usage" in ds_detail[0].text
