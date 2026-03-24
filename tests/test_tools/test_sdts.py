# Description: Tests for SDT (Scheduled Downtime) MCP tools.
# Description: Validates SDT list, create, update, and delete functions.

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


class TestListSdts:
    """Tests for list_sdts tool."""

    @respx.mock
    async def test_list_sdts_returns_formatted_response(self, client):
        """list_sdts returns properly formatted SDT list."""
        from lm_mcp.tools.sdts import list_sdts

        respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "SDT_123",
                            "type": "DeviceSDT",
                            "deviceDisplayName": "server01",
                            "startDateTime": 1702400000,
                            "endDateTime": 1702403600,
                            "comment": "Maintenance window",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await list_sdts(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert len(data["sdts"]) == 1

    @respx.mock
    async def test_list_sdts_with_limit(self, client):
        """list_sdts passes size parameter to API."""
        from lm_mcp.tools.sdts import list_sdts

        route = respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await list_sdts(client, limit=10)

        assert route.calls[0].request.url.params.get("size") == "10"

    @respx.mock
    async def test_list_sdts_with_raw_filter(self, client):
        """list_sdts passes raw filter expression to API."""
        from lm_mcp.tools.sdts import list_sdts

        route = respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await list_sdts(client, filter="type:DeviceSDT,admin~john")

        params = dict(route.calls[0].request.url.params)
        assert "filter" in params
        assert "type:DeviceSDT" in params["filter"]

    @respx.mock
    async def test_list_sdts_with_device_filter(self, client):
        """list_sdts filters by device ID."""
        from lm_mcp.tools.sdts import list_sdts

        route = respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await list_sdts(client, device_id=123)

        params = dict(route.calls[0].request.url.params)
        assert "filter" in params
        assert "deviceId" in params["filter"]

    @respx.mock
    async def test_list_sdts_with_type_filter(self, client):
        """list_sdts filters by SDT type."""
        from lm_mcp.tools.sdts import list_sdts

        route = respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await list_sdts(client, sdt_type="DeviceGroupSDT")

        params = dict(route.calls[0].request.url.params)
        assert "filter" in params
        assert "type" in params["filter"]


class TestCreateSdt:
    """Tests for create_sdt tool."""

    @respx.mock
    async def test_create_sdt_blocked_by_default(self, client, monkeypatch):
        """create_sdt is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import create_sdt

        result = await create_sdt(
            client,
            sdt_type="DeviceSDT",
            device_id=123,
            duration_minutes=60,
            comment="Test",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_sdt_succeeds_when_enabled(self, client, monkeypatch):
        """create_sdt works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import create_sdt

        respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={"id": "SDT_456", "type": "DeviceSDT"},
            )
        )

        result = await create_sdt(
            client,
            sdt_type="DeviceSDT",
            device_id=123,
            duration_minutes=60,
            comment="Maintenance",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True

    @respx.mock
    async def test_create_sdt_handles_api_error(self, client, monkeypatch):
        """create_sdt properly handles API error responses."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import create_sdt

        respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={"errorMessage": "Invalid type", "errorCode": 1400},
            )
        )

        result = await create_sdt(
            client,
            sdt_type="InvalidType",
            device_id=123,
            duration_minutes=60,
        )

        # Error responses are formatted as text, not JSON
        assert "Error:" in result[0].text
        assert "Invalid type" in result[0].text

    @respx.mock
    async def test_create_sdt_datasource_type(self, client, monkeypatch):
        """create_sdt sends correct body for DeviceDataSourceSDT."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import create_sdt

        route = respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={"id": "SDT_789", "type": "DeviceDataSourceSDT"},
            )
        )

        result = await create_sdt(
            client,
            sdt_type="DeviceDataSourceSDT",
            device_id=123,
            datasource_id=456,
            duration_minutes=30,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True

        # Verify the request body included both deviceId and dataSourceId
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["type"] == "ResourceDataSourceSDT"
        assert request_body["deviceId"] == 123
        assert request_body["dataSourceId"] == 456

    @respx.mock
    async def test_create_sdt_maps_device_type_to_resource(self, client, monkeypatch):
        """create_sdt maps DeviceGroupSDT to ResourceGroupSDT in the POST body."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import create_sdt

        route = respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={"id": "SDT_100", "type": "ResourceGroupSDT"},
            )
        )

        result = await create_sdt(
            client,
            sdt_type="DeviceGroupSDT",
            device_group_id=42,
            duration_minutes=30,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["type"] == "ResourceGroupSDT"
        assert request_body["deviceGroupId"] == 42

    @respx.mock
    async def test_create_sdt_passthrough_non_device_type(self, client, monkeypatch):
        """create_sdt passes through non-Device types unchanged."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import create_sdt

        route = respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={"id": "SDT_101", "type": "CollectorSDT"},
            )
        )

        result = await create_sdt(
            client,
            sdt_type="CollectorSDT",
            duration_minutes=15,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["type"] == "CollectorSDT"


class TestBulkCreateDeviceSdt:
    """Tests for bulk_create_device_sdt type mapping."""

    @respx.mock
    async def test_bulk_create_sends_resource_type(self, client, monkeypatch):
        """bulk_create_device_sdt sends ResourceSDT, not DeviceSDT."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import bulk_create_device_sdt

        route = respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={"id": "SDT_200", "type": "ResourceSDT"},
            )
        )

        result = await bulk_create_device_sdt(
            client,
            device_ids=[10, 20],
            duration_minutes=60,
            comment="Bulk test",
        )

        data = json.loads(result[0].text)
        assert data["created"] == 2

        for call in route.calls:
            request_body = json.loads(call.request.content)
            assert request_body["type"] == "ResourceSDT"


class TestDeleteSdt:
    """Tests for delete_sdt tool."""

    @respx.mock
    async def test_delete_sdt_blocked_by_default(self, client, monkeypatch):
        """delete_sdt is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import delete_sdt

        result = await delete_sdt(client, sdt_id="SDT_123")

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_sdt_succeeds_when_enabled(self, client, monkeypatch):
        """delete_sdt works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import delete_sdt

        respx.delete("https://test.logicmonitor.com/santaba/rest/sdt/sdts/SDT_123").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_sdt(client, sdt_id="SDT_123")

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestUpdateSdt:
    """Tests for update_sdt tool."""

    @respx.mock
    async def test_update_sdt_blocked_without_write(self, client, monkeypatch):
        """update_sdt is blocked when write operations disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import update_sdt

        result = await update_sdt(client, sdt_id="SDT_1", comment="Updated")
        assert "Error:" in result[0].text
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_update_sdt_no_changes(self, client, monkeypatch):
        """update_sdt returns error when no updates provided."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import update_sdt

        result = await update_sdt(client, sdt_id="SDT_1")
        assert "No updates provided" in result[0].text

    @respx.mock
    async def test_update_sdt_success(self, client, monkeypatch):
        """update_sdt fetches current SDT and PUTs with modifications."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import update_sdt

        respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts/SDT_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "SDT_1",
                    "type": "ResourceSDT",
                    "deviceId": 42,
                    "startDateTime": 1702400000000,
                    "endDateTime": 1702403600000,
                    "comment": "Original",
                },
            )
        )

        route = respx.put("https://test.logicmonitor.com/santaba/rest/sdt/sdts/SDT_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "SDT_1",
                    "type": "ResourceSDT",
                    "startDateTime": 1702400000000,
                    "endDateTime": 1702500000000,
                    "comment": "Extended",
                },
            )
        )

        result = await update_sdt(
            client,
            sdt_id="SDT_1",
            end_date_time=1702500000000,
            comment="Extended",
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["sdt"]["comment"] == "Extended"
        assert data["sdt"]["end_time"] == 1702500000000

        body = json.loads(route.calls[0].request.content)
        assert body["deviceId"] == 42
        assert body["endDateTime"] == 1702500000000
        assert body["comment"] == "Extended"
        assert body["startDateTime"] == 1702400000000

    @respx.mock
    async def test_update_sdt_not_found(self, client, monkeypatch):
        """update_sdt handles 404 on fetch."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import update_sdt

        respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts/GONE").mock(
            return_value=httpx.Response(404, json={"errorMessage": "SDT not found"})
        )

        result = await update_sdt(client, sdt_id="GONE", comment="Won't work")
        assert "Error:" in result[0].text
