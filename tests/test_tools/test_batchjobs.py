# Description: Tests for Batch Job MCP tools.
# Description: Validates batch job monitoring functions.

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


class TestGetBatchjobs:
    """Tests for get_batchjobs tool."""

    @respx.mock
    async def test_get_batchjobs_returns_list(self, client):
        """get_batchjobs returns properly formatted list."""
        from lm_mcp.tools.batchjobs import get_batchjobs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/batchjobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "DailyBackup",
                            "description": "Daily database backup",
                            "group": "Backups",
                            "schedule": "0 2 * * *",
                            "timeout": 3600,
                            "status": "active",
                            "lastRunTime": 1702400000,
                        },
                        {
                            "id": 2,
                            "name": "LogRotation",
                            "description": "Log file rotation",
                            "group": "Maintenance",
                            "schedule": "0 0 * * *",
                            "timeout": 1800,
                            "status": "active",
                            "lastRunTime": 1702400000,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_batchjobs(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["batchjobs"]) == 2
        assert data["batchjobs"][0]["name"] == "DailyBackup"

    @respx.mock
    async def test_get_batchjobs_with_name_filter(self, client):
        """get_batchjobs passes name filter to API."""
        from lm_mcp.tools.batchjobs import get_batchjobs

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/batchjobs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_batchjobs(client, name_filter="Backup*")

        assert "filter" in route.calls[0].request.url.params
        assert "name~Backup*" in route.calls[0].request.url.params.get("filter", "")


class TestGetBatchjob:
    """Tests for get_batchjob tool."""

    @respx.mock
    async def test_get_batchjob_returns_details(self, client):
        """get_batchjob returns single batch job details."""
        from lm_mcp.tools.batchjobs import get_batchjob

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/batchjobs/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "DailyBackup",
                    "description": "Daily database backup job",
                    "group": "Backups",
                    "schedule": "0 2 * * *",
                    "timeout": 3600,
                    "status": "active",
                    "script": "#!/bin/bash\npg_dump ...",
                    "scriptType": "bash",
                    "appliesTo": "system.hostname =~ 'db-*'",
                },
            )
        )

        result = await get_batchjob(client, batchjob_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 123
        assert data["name"] == "DailyBackup"
        assert data["schedule"] == "0 2 * * *"

    @respx.mock
    async def test_get_batchjob_not_found(self, client):
        """get_batchjob returns error for missing batch job."""
        from lm_mcp.tools.batchjobs import get_batchjob

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/batchjobs/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Batch job not found"})
        )

        result = await get_batchjob(client, batchjob_id=999)

        assert "Error:" in result[0].text


class TestGetDeviceBatchjobs:
    """Tests for get_device_batchjobs tool."""

    @respx.mock
    async def test_get_device_batchjobs_returns_list(self, client):
        """get_device_batchjobs returns batch jobs for device."""
        from lm_mcp.tools.batchjobs import get_device_batchjobs

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/456/batchjobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1001,
                            "batchJobId": 123,
                            "batchJobName": "DailyBackup",
                            "deviceId": 456,
                            "deviceDisplayName": "db-server-01",
                            "status": "active",
                            "lastRunTime": 1702400000,
                            "lastRunStatus": "success",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_device_batchjobs(client, device_id=456)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 456
        assert data["total"] == 1
        assert data["batchjobs"][0]["batchjob_name"] == "DailyBackup"


class TestGetBatchjobHistory:
    """Tests for get_batchjob_history tool."""

    @respx.mock
    async def test_get_batchjob_history_returns_history(self, client):
        """get_batchjob_history returns execution history."""
        from lm_mcp.tools.batchjobs import get_batchjob_history

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/456/batchjobs/123/history"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "runTime": 1702400000,
                            "status": "success",
                            "exitCode": 0,
                            "duration": 300,
                            "output": "Backup completed successfully",
                        },
                        {
                            "id": 2,
                            "runTime": 1702313600,
                            "status": "failed",
                            "exitCode": 1,
                            "duration": 60,
                            "output": "Connection timeout",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_batchjob_history(client, device_id=456, batchjob_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 456
        assert data["batchjob_id"] == 123
        assert data["total"] == 2
        assert data["history"][0]["status"] == "success"
        assert data["history"][1]["status"] == "failed"
