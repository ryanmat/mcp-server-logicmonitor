# Description: Tests for the shared execute_tool middleware function.
# Description: Validates tool filtering, write audit, and session recording.

import json
import logging
import tomllib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from mcp.types import CallToolRequest, CallToolRequestParams, CallToolResult, TextContent

from lm_mcp.exceptions import ConfigurationError
from lm_mcp.tools import ErrorContent, is_error_result
from tests.envelope import envelope


class TestExecuteToolMiddleware:
    """Tests for execute_tool applying the full middleware chain."""

    @pytest.fixture
    def mock_handler(self):
        """Create a mock tool handler returning TextContent."""
        return AsyncMock(return_value=[TextContent(type="text", text=json.dumps({"id": 1}))])

    @pytest.fixture
    def mock_client(self):
        """Create a mock LogicMonitor client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_calls_handler_with_client(self, monkeypatch, mock_handler, mock_client):
        """execute_tool passes client and arguments to the handler."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server._client", mock_client),
        ):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_devices", {"limit": 10})

        mock_handler.assert_called_once_with(mock_client, limit=10)
        assert len(result) == 1
        assert json.loads(result[0].text) == {"id": 1}

    @pytest.mark.asyncio
    async def test_session_tool_called_without_client(self, monkeypatch, mock_handler):
        """execute_tool calls session tools without the LM client."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        with patch("lm_mcp.server.get_tool_handler", return_value=mock_handler):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_session_context", {})

        mock_handler.assert_called_once_with()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_rejects_disabled_tool(self, monkeypatch):
        """execute_tool rejects tools matching disabled_tools pattern."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "delete_*")

        from lm_mcp.server import execute_tool

        result = await execute_tool("delete_device", {"device_id": 1})

        assert "disabled" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_rejects_non_enabled_tool(self, monkeypatch):
        """execute_tool rejects tools not in enabled_tools list."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_devices,get_alerts")

        from lm_mcp.server import execute_tool

        result = await execute_tool("delete_device", {"device_id": 1})

        assert "not enabled" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_allows_enabled_tool(self, monkeypatch, mock_handler, mock_client):
        """execute_tool allows tools in the enabled_tools list."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_devices,get_alerts")

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server._client", mock_client),
        ):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_devices", {"limit": 5})

        mock_handler.assert_called_once()
        assert json.loads(result[0].text) == {"id": 1}

    @pytest.mark.asyncio
    async def test_logs_write_operation_on_success(self, monkeypatch, mock_handler, mock_client):
        """execute_tool logs successful write operations."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server._client", mock_client),
            patch("lm_mcp.server.log_write_operation") as mock_log,
        ):
            from lm_mcp.server import execute_tool

            await execute_tool("create_device", {"name": "test"})

        mock_log.assert_called_once_with("create_device", {"name": "test"}, success=True)

    @pytest.mark.asyncio
    async def test_records_result_in_session(self, monkeypatch, mock_handler, mock_client):
        """execute_tool records each non-session tool result in the session."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        mock_session = MagicMock()

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server._client", mock_client),
            patch("lm_mcp.server.get_session", return_value=mock_session),
        ):
            from lm_mcp.server import execute_tool

            await execute_tool("get_devices", {"limit": 10})

        mock_session.record_result.assert_called_once_with(
            "get_devices", {"limit": 10}, {"id": 1}, success=True
        )

    @pytest.mark.asyncio
    async def test_skips_session_for_session_tools(self, monkeypatch, mock_handler):
        """execute_tool does not record session tools in session history."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        mock_session = MagicMock()

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server.get_session", return_value=mock_session),
        ):
            from lm_mcp.server import execute_tool

            await execute_tool("get_session_context", {})

        mock_session.record_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_value_error_returns_error_text(self, monkeypatch, mock_client):
        """execute_tool catches ValueError and returns error message."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        failing_handler = AsyncMock(side_effect=ValueError("bad input"))

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=failing_handler),
            patch("lm_mcp.server._client", mock_client),
        ):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_devices", {"limit": -1})

        assert "bad input" in result[0].text

    @pytest.mark.parametrize(
        ("exc", "arguments"),
        [
            (TypeError("get_devices() got an unexpected keyword argument 'foo'"), {"foo": 1}),
            (ValueError("bad input"), {"limit": -1}),
        ],
    )
    async def test_handler_exception_is_logged_with_traceback(
        self, monkeypatch, mock_client, caplog, exc, arguments
    ):
        """A handler that raises leaves one record with exc_info and an ErrorContent result."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        failing_handler = AsyncMock(side_effect=exc)

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=failing_handler),
            patch("lm_mcp.server._client", mock_client),
            caplog.at_level(logging.ERROR, logger="lm_mcp.server"),
        ):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_devices", arguments)

        assert is_error_result(result)
        assert str(exc) in result[0].text
        records = [r for r in caplog.records if r.name == "lm_mcp.server"]
        assert len(records) == 1
        assert records[0].exc_info is not None
        assert records[0].exc_info[0] is type(exc)
        assert "get_devices" in records[0].getMessage()


class TestCallToolDelegatesToExecuteTool:
    """Tests that the MCP call_tool handler delegates to execute_tool."""

    @pytest.mark.asyncio
    async def test_call_tool_uses_execute_tool(self, monkeypatch):
        """The MCP call_tool handler delegates to execute_tool."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        expected = [TextContent(type="text", text="delegated")]

        with patch("lm_mcp.server.execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = expected
            from lm_mcp.server import call_tool

            result = await call_tool("get_devices", {"limit": 10})

        mock_exec.assert_called_once_with("get_devices", {"limit": 10})
        assert result == expected


class TestPortalToolGating:
    """Portal tools are dispatchable only in multi-portal mode."""

    @pytest.mark.asyncio
    async def test_execute_tool_rejects_portal_tools_in_single_portal_mode(self, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

        from lm_mcp.server import execute_tool

        for name, args in (("use_portal", {"customer": "x"}), ("get_portals", {})):
            result = await execute_tool(name, args)
            assert is_error_result(result)
            assert "multi-portal" in result[0].text


class TestMultiPortalDispatch:
    """execute_tool behavior in multi-portal mode before and around portal selection."""

    def _multi_env(self, monkeypatch, tmp_path):
        p = tmp_path / "portals.json"
        p.write_text(json.dumps({"acme": {"portal": "acme.example.com", "bearer_token": "t"}}))
        monkeypatch.setenv("LM_MULTI_PORTAL", "true")
        monkeypatch.setenv("LM_PORTALS_FILE", str(p))
        monkeypatch.delenv("LM_PORTAL", raising=False)
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

    @pytest.mark.asyncio
    async def test_execute_tool_allows_portal_tools_despite_categories(
        self, monkeypatch, tmp_path, reset_portals
    ):
        self._multi_env(monkeypatch, tmp_path)
        monkeypatch.setenv("LM_MCP_CATEGORIES", "read")

        from lm_mcp.server import execute_tool

        result = await execute_tool("get_current_portal", {})
        data = json.loads(result[0].text)
        assert "active" in data

    @pytest.mark.asyncio
    async def test_search_tools_works_before_use_portal(self, monkeypatch, tmp_path, reset_portals):
        self._multi_env(monkeypatch, tmp_path)

        from lm_mcp.server import execute_tool

        result = await execute_tool("search_tools", {"query": "device"})
        text = result[0].text
        assert "No portal selected" not in text
        assert "device" in text

    @pytest.mark.asyncio
    async def test_get_reference_works_before_use_portal(
        self, monkeypatch, tmp_path, reset_portals
    ):
        self._multi_env(monkeypatch, tmp_path)

        from lm_mcp.server import execute_tool

        result = await execute_tool("get_reference", {"list": True})
        assert "No portal selected" not in result[0].text

    @pytest.mark.asyncio
    async def test_use_portal_recorded_in_session_history(
        self, monkeypatch, tmp_path, reset_portals
    ):
        """A use_portal lands in the history of the portal the call started on."""
        self._multi_env(monkeypatch, tmp_path)

        from lm_mcp import session as session_module
        from lm_mcp.server import execute_tool

        monkeypatch.setattr(session_module, "_sessions", {})
        await execute_tool("use_portal", {"customer": "acme"})
        await execute_tool("use_portal", {"customer": "acme"})
        result = await execute_tool("get_session_history", {})

        history = json.loads(result[0].text)["history"]
        assert [entry["tool"] for entry in history] == ["use_portal"]


DEVICE_URL = "https://test.logicmonitor.com/santaba/rest/device/devices/7"

# Field types copied from a live GET /device/devices read (2026-10-20); the error
# envelope copies the live 404 body shape with the 403 status.
DEVICE_7 = {
    "id": 7,
    "name": "10.0.0.7",
    "displayName": "web-07",
    "deviceType": 0,
    "currentCollectorId": 3,
    "hostGroupIds": "2,14",
    "hostStatus": "normal",
}
FORBIDDEN = {"errorMessage": "Permission denied", "errorCode": 1403, "errorDetail": None}


@pytest.fixture
def write_portal(monkeypatch, reset_portals):
    """Single-portal env with writes on and a real client bound the way stdio binds it."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

    from lm_mcp.auth import validate_auth
    from lm_mcp.client import LogicMonitorClient
    from lm_mcp.config import get_config
    from lm_mcp.server import _set_client

    config = get_config()
    _set_client(
        LogicMonitorClient(
            base_url=config.base_url,
            auth=validate_auth(config.bearer_token, config.access_id, config.access_key),
            timeout=config.timeout,
            max_retries=config.max_retries,
            ingest_url=config.ingest_url,
        )
    )


def _audit_lines(caplog) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "lm_mcp.audit"]


INTEGRATIONS_URL = "https://test.logicmonitor.com/santaba/rest/setting/integrations"
CREDENTIAL_URL = "https://admin:s3cret@10.0.0.5/hook?password=s3cret2"
MASKED_URL = "https://***@10.0.0.5/hook?password=***"
TOPOLOGIES_URL = "https://test.logicmonitor.com/santaba/rest/topology/topologies"


class TestTopologyMapRejectsGroupParameter:
    """R5: passing device_group_id to get_topology_map is an error."""

    @respx.mock
    async def test_passing_it_errors_instead_of_listing_every_map(self, write_portal, caplog):
        route = respx.get(TOPOLOGIES_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        from lm_mcp.server import execute_tool

        with caplog.at_level(logging.ERROR, logger="lm_mcp.server"):
            result = await execute_tool("get_topology_map", {"device_group_id": 6})

        assert isinstance(result[0], ErrorContent)
        assert "device_group_id" in result[0].text
        assert not route.called
        assert "Tool get_topology_map raised" in caplog.text


class TestCredentialsInUrlArguments:
    """R5: the API receives the URL whole; audit and session see it masked."""

    @respx.mock
    async def test_real_write_keeps_the_url_for_the_api_and_masks_the_records(
        self, write_portal, monkeypatch, caplog
    ):
        from lm_mcp.config import reset_config
        from lm_mcp.server import execute_tool
        from lm_mcp.session import get_session

        reset_config()
        get_session().clear()
        route = respx.post(INTEGRATIONS_URL).mock(
            return_value=httpx.Response(200, json={"id": 9, "name": "hook"})
        )
        try:
            with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
                await execute_tool(
                    "create_http_integration", {"name": "hook", "url": CREDENTIAL_URL}
                )
            recorded = get_session().history[-1].arguments
        finally:
            get_session().clear()

        assert json.loads(route.calls[0].request.content)["url"] == CREDENTIAL_URL
        assert recorded == {"name": "hook", "url": MASKED_URL}
        audit = _audit_lines(caplog)
        assert len(audit) == 1
        assert MASKED_URL in audit[0][1]
        assert "s3cret" not in caplog.text

    @pytest.mark.parametrize(
        ("text", "recorded_result"),
        [(json.dumps({"id": 1}), {"id": 1}), ("not json", {})],
        ids=["json_result", "plain_text_result"],
    )
    async def test_session_records_masked_arguments_for_every_result_shape(
        self, monkeypatch, text, recorded_result
    ):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        client = MagicMock()
        handler = AsyncMock(return_value=[TextContent(type="text", text=text)])
        session = MagicMock()

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=handler),
            patch("lm_mcp.server._client", client),
            patch("lm_mcp.server.get_session", return_value=session),
        ):
            from lm_mcp.server import execute_tool

            await execute_tool("get_devices", {"url": CREDENTIAL_URL})

        handler.assert_called_once_with(client, url=CREDENTIAL_URL)
        session.record_result.assert_called_once_with(
            "get_devices", {"url": MASKED_URL}, recorded_result, success=True
        )


class TestWriteOutcomeFromResult:
    """Audit, session and isError derive from the real handler's result (R1.4)."""

    @respx.mock
    async def test_forbidden_delete_audits_failure(self, write_portal, caplog):
        respx.get(DEVICE_URL).mock(return_value=httpx.Response(200, json=DEVICE_7))
        respx.delete(DEVICE_URL).mock(return_value=httpx.Response(403, json=FORBIDDEN))
        from lm_mcp.server import execute_tool

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("delete_device", {"device_id": 7})

        assert isinstance(result[0], ErrorContent)
        assert envelope(result)["message"].startswith("Permission denied")
        assert _audit_lines(caplog) == [
            (logging.WARNING, "Write operation failed: delete_device args={'device_id': 7}")
        ]

    @respx.mock
    async def test_write_disabled_refusal_audits_failure(self, write_portal, monkeypatch, caplog):
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp.config import reset_config
        from lm_mcp.server import execute_tool

        reset_config()
        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("delete_device", {"device_id": 7})

        assert isinstance(result[0], ErrorContent)
        assert envelope(result)["message"].startswith("Write operations are disabled")
        assert not respx.calls
        assert _audit_lines(caplog) == [
            (logging.WARNING, "Write operation failed: delete_device args={'device_id': 7}")
        ]

    @respx.mock
    async def test_collector_debug_refusal_audits_failure(self, write_portal, caplog):
        """R3.9: a collector_debug request the tool refuses is a failed write, before any call."""
        from lm_mcp.server import execute_tool

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool(
                "collector_debug",
                {"command": "ping", "device_id": 7, "args": {"host": "169.254.169.254"}},
            )

        assert envelope(result)["code"] == "REJECTED_BY_TOOL"
        assert not respx.calls
        lines = _audit_lines(caplog)
        assert [level for level, _ in lines] == [logging.WARNING]
        assert lines[0][1].startswith("Write operation failed: collector_debug args=")

    @respx.mock
    async def test_collector_debug_portal_refusal_audits_failure(self, write_portal, caplog):
        """R3.9: a debug POST the portal refuses is an error in the envelope and a failed write."""
        respx.post("https://test.logicmonitor.com/santaba/rest/debug").mock(
            return_value=httpx.Response(403, json=FORBIDDEN)
        )
        from lm_mcp.server import execute_tool

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("collector_debug", {"command": "uptime", "collector_id": 9})

        error = envelope(result)
        assert error["code"] == "AUTH_FAILED" and error["details"]["status"] == "refused"
        lines = _audit_lines(caplog)
        assert [level for level, _ in lines] == [logging.WARNING]
        assert lines[0][1].startswith("Write operation failed: collector_debug args=")

    @respx.mock
    async def test_collector_debug_answer_audits_success(self, write_portal, caplog, monkeypatch):
        """R3.9: an answered collector_debug call is a successful write."""
        from lm_mcp.tools import collector_debug as cd

        monkeypatch.setattr(cd, "POLL_SECONDS", 0.01)
        # Bodies copied from the live exchange in tests/fixtures/collector_debug_exchanges.json.
        respx.post("https://test.logicmonitor.com/santaba/rest/debug").mock(
            return_value=httpx.Response(
                200,
                json={
                    "output": "",
                    "sessionId": "1797233319",
                    "cmdline": "!uptime",
                    "cmdContext": "",
                },
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/debug/1797233319").mock(
            return_value=httpx.Response(
                200,
                json={
                    "output": "uptime=21h 10m 41s, realUptime=21h 10m 41s, confVer=1794483129",
                    "sessionId": "1797233319",
                    "cmdline": None,
                    "cmdContext": "",
                },
            )
        )
        from lm_mcp.server import execute_tool

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("collector_debug", {"command": "uptime", "collector_id": 9})

        assert not is_error_result(result)
        assert json.loads(result[0].text)["status"] == "answered"
        lines = _audit_lines(caplog)
        assert [level for level, _ in lines] == [logging.INFO]
        assert lines[0][1].startswith("Write operation: collector_debug args=")

    @respx.mock
    async def test_successful_delete_audits_success(self, write_portal, caplog):
        respx.get(DEVICE_URL).mock(return_value=httpx.Response(200, json=DEVICE_7))
        respx.delete(DEVICE_URL).mock(return_value=httpx.Response(200, json={}))
        from lm_mcp.server import execute_tool

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("delete_device", {"device_id": 7})

        assert not is_error_result(result)
        assert json.loads(result[0].text)["success"] is True
        assert _audit_lines(caplog) == [
            (logging.INFO, "Write operation: delete_device args={'device_id': 7}")
        ]

    async def test_write_raising_before_handler_audits_failure(self, write_portal, caplog):
        """No client bound: the dispatcher refuses the call and audits the write as failed."""
        from lm_mcp.server import _set_client, execute_tool

        _set_client(None)
        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("delete_device", {"device_id": 7})

        assert envelope(result)["message"] == "Client not initialized"
        assert _audit_lines(caplog) == [
            (logging.WARNING, "Write operation failed: delete_device args={'device_id': 7}")
        ]

    async def test_write_value_error_audits_failure(self, write_portal, caplog):
        """A write tool whose handler rejects its arguments with ValueError audits as failed."""
        from lm_mcp.server import execute_tool

        handler = AsyncMock(side_effect=ValueError("device_id must be positive"))
        with (
            patch("lm_mcp.server.get_tool_handler", return_value=handler),
            caplog.at_level(logging.INFO, logger="lm_mcp.audit"),
        ):
            result = await execute_tool("delete_device", {"device_id": 7})

        assert envelope(result)["code"] == "INVALID_REQUEST"
        assert _audit_lines(caplog) == [
            (logging.WARNING, "Write operation failed: delete_device args={'device_id': 7}")
        ]

    async def test_unregistered_name_leaves_no_audit_line(self, write_portal, caplog):
        """A name no tool answers to runs nothing, so the audit trail stays quiet."""
        from lm_mcp.server import execute_tool

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("delete_no_such_resource", {"id": 7})

        assert is_error_result(result)
        assert envelope(result)["code"] == "INVALID_REQUEST"
        assert _audit_lines(caplog) == []

    @respx.mock
    async def test_forbidden_delete_recorded_as_failure_in_session(self, write_portal, monkeypatch):
        respx.get(DEVICE_URL).mock(return_value=httpx.Response(200, json=DEVICE_7))
        respx.delete(DEVICE_URL).mock(return_value=httpx.Response(403, json=FORBIDDEN))
        from lm_mcp.config import reset_config
        from lm_mcp.server import execute_tool
        from lm_mcp.session import get_session

        reset_config()
        get_session().clear()
        try:
            await execute_tool("delete_device", {"device_id": 7})
            entry = get_session().history[-1]
            assert entry.tool_name == "delete_device"
            assert entry.success is False
        finally:
            get_session().clear()

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (TextContent(type="text", text="plain text, not JSON"), True),
            (ErrorContent(type="text", text='{"error": true, "message": "x"}'), False),
        ],
        ids=["plain-text-success", "json-text-error"],
    )
    async def test_session_outcome_follows_result_type_not_json(
        self, write_portal, monkeypatch, content, expected
    ):
        """Session success comes from the result type, whether or not the text parses."""
        from lm_mcp.config import reset_config
        from lm_mcp.server import execute_tool
        from lm_mcp.session import get_session

        reset_config()
        get_session().clear()
        try:
            with patch(
                "lm_mcp.server.get_tool_handler", return_value=AsyncMock(return_value=[content])
            ):
                await execute_tool("get_devices", {})
            assert get_session().history[-1].success is expected
        finally:
            get_session().clear()

    @respx.mock
    async def test_call_tool_marks_failure_is_error(self, write_portal):
        respx.get(DEVICE_URL).mock(return_value=httpx.Response(200, json=DEVICE_7))
        respx.delete(DEVICE_URL).mock(return_value=httpx.Response(403, json=FORBIDDEN))
        from lm_mcp.server import call_tool

        result = await call_tool("delete_device", {"device_id": 7})

        assert isinstance(result, CallToolResult)
        assert result.isError is True
        error = envelope(result.content)
        assert error["code"] == "AUTH_FAILED"
        assert error["message"].startswith("Permission denied")

    @respx.mock
    async def test_call_tool_success_is_plain_content(self, write_portal):
        respx.get(DEVICE_URL).mock(return_value=httpx.Response(200, json=DEVICE_7))
        respx.delete(DEVICE_URL).mock(return_value=httpx.Response(200, json={}))
        from lm_mcp.server import call_tool

        result = await call_tool("delete_device", {"device_id": 7})

        assert isinstance(result, list)
        assert json.loads(result[0].text)["success"] is True

    @respx.mock
    async def test_sdk_request_handler_reports_is_error(self, write_portal):
        """The registered MCP CallToolRequest handler carries isError to the wire result."""
        respx.get(DEVICE_URL).mock(return_value=httpx.Response(200, json=DEVICE_7))
        respx.delete(DEVICE_URL).mock(return_value=httpx.Response(403, json=FORBIDDEN))
        from lm_mcp.server import server

        handler = server.request_handlers[CallToolRequest]
        response = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="delete_device", arguments={"device_id": 7}),
            )
        )

        wire = response.model_dump(by_alias=True, exclude_none=True)
        assert wire["isError"] is True
        error = json.loads(wire["content"][0]["text"])["error"]
        assert error["code"] == "AUTH_FAILED"
        assert error["message"].startswith("Permission denied")

    def test_mcp_floor_admits_only_passthrough_and_the_body_limit(self):
        """The mcp requirement excludes every release that lacks what the server relies on.

        call_tool returns CallToolResult(isError=True) for an error. mcp 1.19.0 is the first
        lowlevel server that passes one through; 1.18.0 and earlier list() it, fail
        validation, and send a pydantic message in place of the tool's error text. mcp 1.29.0
        added max_request_body_size to StreamableHTTPSessionManager (SDK PR #3101), the limit
        /mcp keeps on a request body; 1.28.1 and earlier have no such limit.
        """
        from packaging.requirements import Requirement
        from packaging.version import Version

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        dependencies = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
        mcp = next(r for r in map(Requirement, dependencies) if r.name == "mcp")

        assert Version("1.18.0") not in mcp.specifier
        assert Version("1.28.1") not in mcp.specifier
        assert Version("1.29.0") in mcp.specifier


EDWIN_TOOL_NAMES = {
    "get_edwin_insights",
    "get_edwin_insight",
    "get_edwin_records",
    "get_edwin_alert_volume",
    "get_edwin_metadata",
    "get_edwin_tools",
    "edwin_run_tool",
    "ask_edwin",
}
EDWIN_HOST = "https://lmryanmatuszewski.dexda.ai"
# The insight row get_edwin_insights projects, from the 2026-11-10 probe
# (tests/test_tools/test_edwin.py carries the full row).
EDWIN_INSIGHT = {
    "_id": "correlation_36fa3f53-e608-4192-aeca-e0097d2a1e94_1794020047392",
    "meta.displayId": "EDN000029424",
    "meta.state": "cleared",
    "ml.insightSeverity": 0,
    "meta.createdTimestamp": 1794020047392,
}


@pytest.fixture
def edwin_env(monkeypatch, reset_portals):
    """Single-portal env with writes on, both Edwin credentials, and the token exchange answered."""
    monkeypatch.setenv("LM_PORTAL", "lmryanmatuszewski.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "lm-bearer-token-fixture")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)
    monkeypatch.setenv("EDWIN_CLIENT_ID", "edwin-client-id-fixture")
    monkeypatch.setenv("EDWIN_CLIENT_TOKEN", "edwin-secret-fix")
    monkeypatch.delenv("EDWIN_HOST", raising=False)
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{EDWIN_HOST}/auth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "eyJhbGciOiJSUzI1NiJ9.fixture.sig",
                    "token_type": "Bearer",
                    "expires_in": 1799,
                },
            )
        )
        yield monkeypatch, router


@pytest.fixture
async def edwin_server(edwin_env):
    """The server with its backends bootstrapped the way both transports build them."""
    from lm_mcp.config import get_config
    from lm_mcp.transport.bootstrap import bootstrap_backends

    backends = bootstrap_backends(get_config())
    yield edwin_env[1]
    await backends.close()


class TestEdwinBackend:
    """R3.1: the Edwin tools are served, dispatched and gated only when Edwin is configured."""

    @pytest.mark.parametrize(
        ("client_id", "client_token", "listed"),
        [
            ("edwin-client-id-fixture", "edwin-secret-fix", True),
            ("edwin-client-id-fixture", None, False),
            (None, "edwin-secret-fix", False),
            (None, None, False),
        ],
        ids=["both", "id_only", "token_only", "neither"],
    )
    async def test_the_edwin_tools_are_listed_only_with_both_credentials(
        self, edwin_env, client_id, client_token, listed
    ):
        from lm_mcp.config import get_config
        from lm_mcp.server import list_tools
        from lm_mcp.transport.bootstrap import bootstrap_backends

        monkeypatch = edwin_env[0]
        for name, value in (("EDWIN_CLIENT_ID", client_id), ("EDWIN_CLIENT_TOKEN", client_token)):
            if value is None:
                monkeypatch.delenv(name, raising=False)
        backends = bootstrap_backends(get_config())
        try:
            names = {tool.name for tool in await list_tools()}
        finally:
            await backends.close()

        assert (names & EDWIN_TOOL_NAMES) == (EDWIN_TOOL_NAMES if listed else set())
        assert "get_devices" in names

    async def test_closing_the_backends_withdraws_the_edwin_tools(self, edwin_server):
        from lm_mcp.config import get_config
        from lm_mcp.server import list_tools
        from lm_mcp.transport.bootstrap import bootstrap_backends

        backends = bootstrap_backends(get_config())
        await backends.close()

        assert not {tool.name for tool in await list_tools()} & EDWIN_TOOL_NAMES

    async def test_an_edwin_tool_reads_through_the_bound_edwin_client(self, edwin_server):
        """The call reaches Edwin with no LogicMonitor client bound at all."""
        from lm_mcp.server import execute_tool

        route = edwin_server.post(f"{EDWIN_HOST}/ui/query/records").mock(
            return_value=httpx.Response(
                200,
                json={"meta": {"count": 1, "recordType": "insights"}, "results": [EDWIN_INSIGHT]},
            )
        )

        result = await execute_tool("get_edwin_insights", {"hours": 6, "limit": 5})

        assert not is_error_result(result)
        assert json.loads(result[0].text)["insights"][0]["meta.displayId"] == "EDN000029424"
        body = json.loads(route.calls.last.request.content)
        assert body["size"] == 5
        assert route.calls.last.request.headers["authorization"] == (
            "Bearer eyJhbGciOiJSUzI1NiJ9.fixture.sig"
        )

    async def test_without_edwin_an_edwin_tool_is_refused_as_disabled(self, edwin_env, caplog):
        from lm_mcp.config import get_config
        from lm_mcp.server import execute_tool
        from lm_mcp.transport.bootstrap import bootstrap_backends

        for name in ("EDWIN_CLIENT_ID", "EDWIN_CLIENT_TOKEN"):
            edwin_env[0].delenv(name)
        backends = bootstrap_backends(get_config())

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            read = await execute_tool("get_edwin_insights", {})
            run = await execute_tool(
                "edwin_run_tool", {"mcp_name": "query-mcp", "tool_name": "t", "parameters": {}}
            )
        await backends.close()

        for result in (read, run):
            assert is_error_result(result)
            error = json.loads(result[0].text)["error"]
            assert error["code"] == "FEATURE_DISABLED"
            assert "EDWIN_CLIENT_ID" in error["message"]
        assert [level for level, _ in _audit_lines(caplog)] == [logging.WARNING]

    async def test_bootstrap_with_no_host_to_derive_logs_and_serves_without_edwin(
        self, edwin_env, tmp_path, caplog
    ):
        """Multi-portal mode has no LM_PORTAL to derive the Edwin host from."""
        from lm_mcp.config import get_config
        from lm_mcp.server import list_tools
        from lm_mcp.transport.bootstrap import bootstrap_backends

        monkeypatch = edwin_env[0]
        portals_file = tmp_path / "portals.json"
        portals_file.write_text(
            json.dumps({"acme": {"portal": "acme.example.com", "bearer_token": "t"}})
        )
        monkeypatch.setenv("LM_MULTI_PORTAL", "true")
        monkeypatch.setenv("LM_PORTALS_FILE", str(portals_file))
        monkeypatch.delenv("LM_PORTAL")
        monkeypatch.delenv("LM_BEARER_TOKEN")

        with caplog.at_level(logging.WARNING, logger="lm_mcp.transport.bootstrap"):
            backends = bootstrap_backends(get_config())
        names = {tool.name for tool in await list_tools()}
        await backends.close()

        assert backends.edwin is None
        assert not names & EDWIN_TOOL_NAMES
        records = [r for r in caplog.records if r.name == "lm_mcp.transport.bootstrap"]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert records[0].exc_info and records[0].exc_info[0] is ConfigurationError
        assert "EDWIN_HOST" in records[0].getMessage()

    async def test_multi_portal_reads_edwin_before_a_portal_is_selected(
        self, edwin_env, tmp_path, reset_portals
    ):
        """Edwin is one tenant for the server: EDWIN_HOST names it, no use_portal needed."""
        from lm_mcp.config import get_config
        from lm_mcp.server import execute_tool
        from lm_mcp.transport.bootstrap import bootstrap_backends

        monkeypatch, router = edwin_env
        portals_file = tmp_path / "portals.json"
        portals_file.write_text(
            json.dumps({"acme": {"portal": "acme.example.com", "bearer_token": "t"}})
        )
        monkeypatch.setenv("LM_MULTI_PORTAL", "true")
        monkeypatch.setenv("LM_PORTALS_FILE", str(portals_file))
        monkeypatch.setenv("EDWIN_HOST", EDWIN_HOST)
        monkeypatch.delenv("LM_PORTAL")
        monkeypatch.delenv("LM_BEARER_TOKEN")
        route = router.get(f"{EDWIN_HOST}/api/agents").mock(
            return_value=httpx.Response(200, json={"agents": [], "total": 0})
        )

        backends = bootstrap_backends(get_config())
        result = await execute_tool("get_edwin_tools", {})
        await backends.close()

        assert not is_error_result(result)
        assert route.called

    async def test_multi_portal_withholds_edwin_run_tool_and_keeps_the_reads(
        self, edwin_env, tmp_path, reset_portals, caplog
    ):
        """Edwin is one tenant for every portal, so no portal's write flag can vouch for a run
        that may change it: the run is unlisted and refused, even on a writable portal."""
        from lm_mcp.config import get_config
        from lm_mcp.server import execute_tool, list_tools
        from lm_mcp.transport.bootstrap import bootstrap_backends

        monkeypatch, router = edwin_env
        portals_file = tmp_path / "portals.json"
        portals_file.write_text(
            json.dumps(
                {"acme": {"portal": "acme.example.com", "bearer_token": "t", "writable": True}}
            )
        )
        monkeypatch.setenv("LM_MULTI_PORTAL", "true")
        monkeypatch.setenv("LM_PORTALS_FILE", str(portals_file))
        monkeypatch.setenv("EDWIN_HOST", EDWIN_HOST)
        monkeypatch.delenv("LM_PORTAL")
        monkeypatch.delenv("LM_BEARER_TOKEN")
        run = router.post(f"{EDWIN_HOST}/api/run-tool")

        backends = bootstrap_backends(get_config())
        await execute_tool("use_portal", {"customer": "acme"})
        names = {tool.name for tool in await list_tools()}
        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool(
                "edwin_run_tool", {"mcp_name": "query-mcp", "tool_name": "t", "parameters": {}}
            )
        await backends.close()

        assert "edwin_run_tool" not in names
        assert names >= EDWIN_TOOL_NAMES - {"edwin_run_tool"}
        error = json.loads(result[0].text)["error"]
        assert error["code"] == "FEATURE_DISABLED"
        assert "multi-portal" in error["message"]
        assert not run.called
        assert [level for level, _ in _audit_lines(caplog)] == [logging.WARNING]

    async def test_edwin_run_tool_audits_with_credential_parameter_keys_masked(
        self, edwin_server, caplog
    ):
        from lm_mcp.server import execute_tool

        route = edwin_server.post(f"{EDWIN_HOST}/api/run-tool").mock(
            return_value=httpx.Response(200, json={"success": True, "content": "{}", "error": None})
        )
        arguments = {
            "mcp_name": "query-mcp",
            "tool_name": "fetch_insight_by_id",
            "parameters": {"api_key": "key-value-fixture", "host": "web01"},
        }

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("edwin_run_tool", arguments)

        assert not is_error_result(result)
        assert json.loads(route.calls.last.request.content)["parameters"]["api_key"] == (
            "key-value-fixture"
        )
        audit = _audit_lines(caplog)
        assert len(audit) == 1
        assert audit[0][0] == logging.INFO
        assert "edwin_run_tool" in audit[0][1] and "web01" in audit[0][1]
        assert "key-value-fixture" not in caplog.text

    async def test_search_tools_ranks_get_edwin_insights_first_for_what_edwin_found(
        self, edwin_server
    ):
        from lm_mcp.server import execute_tool

        result = await execute_tool("search_tools", {"query": "what did Edwin find"})

        first, second = json.loads(result[0].text)["matches"][:2]
        assert first["name"] == "get_edwin_insights"
        assert first["score"] > second["score"]

    async def test_search_tools_names_no_edwin_tool_without_edwin(self, edwin_env):
        from lm_mcp.config import get_config
        from lm_mcp.server import execute_tool
        from lm_mcp.transport.bootstrap import bootstrap_backends

        for name in ("EDWIN_CLIENT_ID", "EDWIN_CLIENT_TOKEN"):
            edwin_env[0].delenv(name)
        backends = bootstrap_backends(get_config())
        result = await execute_tool("search_tools", {"query": "what did Edwin find"})
        await backends.close()

        names = {match["name"] for match in json.loads(result[0].text)["matches"]}
        assert not names & EDWIN_TOOL_NAMES
