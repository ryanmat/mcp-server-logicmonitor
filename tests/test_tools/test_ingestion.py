# Description: Tests for log and metric ingestion tools.
# Description: Validates LMv1-authenticated push API functionality.

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from lm_mcp.tools.ingestion import ingest_logs, push_metrics


class TestIngestLogs:
    """Tests for ingest_logs tool."""

    @pytest.fixture
    def lmv1_client(self, monkeypatch):
        """Create client with LMv1 authentication and write operations enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_ACCESS_ID", "test_access_id")
        monkeypatch.setenv("LM_ACCESS_KEY", "test_access_key")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.auth import create_auth_provider
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.config import LMConfig

        config = LMConfig()
        auth = create_auth_provider(config)
        return LogicMonitorClient(
            base_url=config.base_url,
            auth=auth,
            timeout=config.timeout,
            api_version=config.api_version,
            ingest_url=config.ingest_url,
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_ingest_logs_success(self, lmv1_client):
        """ingest_logs sends logs to ingestion endpoint."""
        respx.post("https://test.logicmonitor.com/rest/log/ingest").mock(
            return_value=Response(202, json={"success": True, "message": "Accepted"})
        )

        logs = [
            {"message": "Test log 1", "_lm.resourceId": {"system.hostname": "server1"}},
            {"message": "Test log 2", "_lm.resourceId": {"system.hostname": "server1"}},
        ]

        result = await ingest_logs(lmv1_client, logs=logs)

        assert len(result) == 1
        assert "success" in result[0].text.lower() or "accepted" in result[0].text.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_ingest_logs_uses_lmv1_auth(self, lmv1_client):
        """ingest_logs uses LMv1 authentication headers."""
        route = respx.post("https://test.logicmonitor.com/rest/log/ingest").mock(
            return_value=Response(202, json={"success": True})
        )

        logs = [{"message": "Test log"}]
        await ingest_logs(lmv1_client, logs=logs)

        assert route.called
        request = route.calls[0].request
        auth_header = request.headers.get("Authorization", "")
        assert auth_header.startswith("LMv1 ")

    @respx.mock
    @pytest.mark.asyncio
    async def test_ingest_logs_empty_list(self, lmv1_client):
        """ingest_logs returns error for empty log list."""
        result = await ingest_logs(lmv1_client, logs=[])

        assert len(result) == 1
        assert "error" in result[0].text.lower() or "empty" in result[0].text.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_ingest_logs_with_resource_mapping(self, lmv1_client):
        """ingest_logs includes resource mapping in payload."""
        route = respx.post("https://test.logicmonitor.com/rest/log/ingest").mock(
            return_value=Response(202, json={"success": True})
        )

        logs = [
            {
                "message": "Application started",
                "_lm.resourceId": {"system.hostname": "webserver1"},
            }
        ]
        await ingest_logs(lmv1_client, logs=logs)

        request = route.calls[0].request
        body = json.loads(request.content)
        assert "_lm.resourceId" in body[0]


class TestPushMetrics:
    """Tests for push_metrics tool."""

    @pytest.fixture
    def lmv1_client(self, monkeypatch):
        """Create client with LMv1 authentication and write operations enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_ACCESS_ID", "test_access_id")
        monkeypatch.setenv("LM_ACCESS_KEY", "test_access_key")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.auth import create_auth_provider
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.config import LMConfig

        config = LMConfig()
        auth = create_auth_provider(config)
        return LogicMonitorClient(
            base_url=config.base_url,
            auth=auth,
            timeout=config.timeout,
            api_version=config.api_version,
            ingest_url=config.ingest_url,
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_push_metrics_success(self, lmv1_client):
        """push_metrics sends metrics to ingestion endpoint."""
        respx.post("https://test.logicmonitor.com/rest/metric/ingest?create=true").mock(
            return_value=Response(202, json={"success": True, "message": "Accepted"})
        )

        metrics = {
            "resourceIds": {"system.hostname": "server1"},
            "dataSource": "CustomMetrics",
            "dataSourceGroup": "MyGroup",
            "instances": [
                {
                    "instanceName": "instance1",
                    "dataPoints": [{"dataPointName": "cpu", "values": [50, 60, 70]}],
                }
            ],
        }

        result = await push_metrics(lmv1_client, metrics=metrics)

        assert len(result) == 1
        assert "success" in result[0].text.lower() or "accepted" in result[0].text.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_push_metrics_uses_lmv1_auth(self, lmv1_client):
        """push_metrics uses LMv1 authentication headers."""
        route = respx.post("https://test.logicmonitor.com/rest/metric/ingest?create=true").mock(
            return_value=Response(202, json={"success": True})
        )

        metrics = {
            "resourceIds": {"system.hostname": "server1"},
            "dataSource": "CustomMetrics",
            "instances": [],
        }
        await push_metrics(lmv1_client, metrics=metrics)

        assert route.called
        request = route.calls[0].request
        auth_header = request.headers.get("Authorization", "")
        assert auth_header.startswith("LMv1 ")

    @respx.mock
    @pytest.mark.asyncio
    async def test_push_metrics_empty_dict(self, lmv1_client):
        """push_metrics returns error for empty metrics."""
        result = await push_metrics(lmv1_client, metrics={})

        assert len(result) == 1
        assert "error" in result[0].text.lower() or "empty" in result[0].text.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_push_metrics_validates_required_fields(self, lmv1_client):
        """push_metrics validates required fields in payload."""
        metrics = {"instances": []}  # Missing resourceIds and dataSource

        result = await push_metrics(lmv1_client, metrics=metrics)

        assert len(result) == 1
        assert "error" in result[0].text.lower() or "required" in result[0].text.lower()


class TestIngestionWriteGate:
    """Verify ingest_logs and push_metrics honor LM_ENABLE_WRITE_OPERATIONS.

    Both tools push data to the portal -- the audit flagged them as
    write-permission bypasses because the @require_write_permission
    decorator was missing in versions <= 3.8.2. These tests guard the
    decorator does its job and the error envelope shape is canonical.
    """

    @pytest.fixture
    def write_disabled_client(self, monkeypatch):
        """Create client with LMv1 auth and write operations explicitly disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_ACCESS_ID", "test_access_id")
        monkeypatch.setenv("LM_ACCESS_KEY", "test_access_key")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.auth import create_auth_provider
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.config import LMConfig

        config = LMConfig()
        auth = create_auth_provider(config)
        return LogicMonitorClient(
            base_url=config.base_url,
            auth=auth,
            timeout=config.timeout,
            api_version=config.api_version,
            ingest_url=config.ingest_url,
        )

    @pytest.mark.asyncio
    async def test_ingest_logs_blocked_when_write_disabled(self, write_disabled_client):
        """ingest_logs returns WRITE_DISABLED envelope when writes are off."""
        result = await ingest_logs(
            write_disabled_client,
            logs=[{"message": "hi", "_lm.resourceId": {"system.hostname": "h"}}],
        )
        text = result[0].text
        assert "Write operations are disabled" in text
        assert "LM_ENABLE_WRITE_OPERATIONS" in text

    @pytest.mark.asyncio
    async def test_push_metrics_blocked_when_write_disabled(self, write_disabled_client):
        """push_metrics returns WRITE_DISABLED envelope when writes are off."""
        result = await push_metrics(
            write_disabled_client,
            metrics={
                "resourceIds": {"system.hostname": "h"},
                "dataSource": "X",
                "instances": [],
            },
        )
        text = result[0].text
        assert "Write operations are disabled" in text


class TestIngestionValidationErrors:
    """Verify validation failures produce the canonical error envelope."""

    @pytest.fixture
    def lmv1_client(self, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_ACCESS_ID", "test_access_id")
        monkeypatch.setenv("LM_ACCESS_KEY", "test_access_key")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.auth import create_auth_provider
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.config import LMConfig

        config = LMConfig()
        auth = create_auth_provider(config)
        return LogicMonitorClient(
            base_url=config.base_url,
            auth=auth,
            timeout=config.timeout,
            api_version=config.api_version,
            ingest_url=config.ingest_url,
        )

    @pytest.mark.asyncio
    async def test_empty_logs_returns_structured_envelope(self, lmv1_client):
        result = await ingest_logs(lmv1_client, logs=[])
        text = result[0].text
        assert text.startswith("Error: logs list cannot be empty")
        assert "Suggestion:" in text

    @pytest.mark.asyncio
    async def test_empty_metrics_returns_structured_envelope(self, lmv1_client):
        result = await push_metrics(lmv1_client, metrics={})
        text = result[0].text
        assert text.startswith("Error: metrics payload cannot be empty")
        assert "Suggestion:" in text

    @pytest.mark.asyncio
    async def test_missing_resource_ids_returns_structured_envelope(self, lmv1_client):
        result = await push_metrics(lmv1_client, metrics={"dataSource": "X"})
        text = result[0].text
        assert "resourceIds is required" in text
        assert "Suggestion:" in text

    @pytest.mark.asyncio
    async def test_missing_data_source_returns_structured_envelope(self, lmv1_client):
        result = await push_metrics(
            lmv1_client,
            metrics={"resourceIds": {"system.hostname": "h"}},
        )
        text = result[0].text
        assert "dataSource is required" in text
        assert "Suggestion:" in text


class TestIngestionToolRegistration:
    """Tests for ingestion tool registration."""

    def test_ingest_logs_registered_in_registry(self):
        """ingest_logs is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "ingest_logs" in tool_names

    def test_push_metrics_registered_in_registry(self):
        """push_metrics is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "push_metrics" in tool_names

    def test_ingest_logs_handler_registered(self):
        """ingest_logs handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("ingest_logs")
        assert handler is not None

    def test_push_metrics_handler_registered(self):
        """push_metrics handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("push_metrics")
        assert handler is not None
