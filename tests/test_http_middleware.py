# Description: Tests for HTTP transport applying shared middleware.
# Description: Validates tools/list filtering and tools/call using execute_tool.

import json
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import TextContent


class TestHttpToolsListFiltering:
    """Tests for HTTP /mcp tools/list applying tool filtering."""

    @pytest.mark.asyncio
    async def test_tools_list_filters_by_enabled(self, monkeypatch):
        """HTTP tools/list applies enabled_tools filtering."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_devices,get_alerts")

        from httpx import ASGITransport, AsyncClient

        from lm_mcp.transport.http import create_asgi_app

        app = create_asgi_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            )

        data = resp.json()
        tool_names = {t["name"] for t in data["result"]}
        assert tool_names == {"get_devices", "get_alerts"}

    @pytest.mark.asyncio
    async def test_tools_list_filters_by_disabled(self, monkeypatch):
        """HTTP tools/list applies disabled_tools filtering."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "delete_*")

        from httpx import ASGITransport, AsyncClient

        from lm_mcp.transport.http import create_asgi_app

        app = create_asgi_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            )

        data = resp.json()
        tool_names = {t["name"] for t in data["result"]}
        for name in tool_names:
            assert not name.startswith("delete_"), (
                f"Tool {name} should be hidden by delete_* pattern"
            )

    @pytest.mark.asyncio
    async def test_tools_list_no_filter_returns_all(self, monkeypatch):
        """HTTP tools/list returns all tools when no filter is set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)

        from httpx import ASGITransport, AsyncClient

        from lm_mcp.registry import TOOLS
        from lm_mcp.transport.http import create_asgi_app

        app = create_asgi_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            )

        data = resp.json()
        assert len(data["result"]) == len(TOOLS)


class TestHttpToolsListWithAwx:
    """Tests for HTTP /mcp tools/list including AWX tools."""

    @pytest.mark.asyncio
    async def test_tools_list_includes_awx_when_configured(self, monkeypatch):
        """HTTP tools/list count includes AWX tools when client is set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)

        from unittest.mock import MagicMock

        from lm_mcp.registry import AWX_TOOLS, TOOLS
        from lm_mcp.server import _set_awx_client

        _set_awx_client(MagicMock())

        from httpx import ASGITransport, AsyncClient

        from lm_mcp.transport.http import create_asgi_app

        app = create_asgi_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            )

        data = resp.json()
        assert len(data["result"]) == len(TOOLS) + len(AWX_TOOLS)

        _set_awx_client(None)


class TestHttpToolsCallMiddleware:
    """Tests for HTTP /mcp tools/call going through execute_tool."""

    @pytest.mark.asyncio
    async def test_tools_call_uses_execute_tool(self, monkeypatch):
        """HTTP tools/call delegates to execute_tool for middleware."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        mock_result = [TextContent(type="text", text=json.dumps({"id": 42}))]

        with patch(
            "lm_mcp.server.execute_tool",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_exec:
            from httpx import ASGITransport, AsyncClient

            from lm_mcp.transport.http import create_asgi_app

            app = create_asgi_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": "get_devices", "arguments": {"limit": 5}},
                        "id": 1,
                    },
                )

        mock_exec.assert_called_once_with("get_devices", {"limit": 5})
        data = resp.json()
        assert data["result"] == {"id": 42}

    @pytest.mark.asyncio
    async def test_tools_call_disabled_tool_rejected(self, monkeypatch):
        """HTTP tools/call rejects disabled tools via execute_tool."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "delete_*")

        # execute_tool will handle the rejection, returning an error TextContent
        error_result = [
            TextContent(
                type="text",
                text="Error: Tool 'delete_device' is disabled. Disabled tools: delete_*",
            )
        ]

        with patch(
            "lm_mcp.server.execute_tool",
            new_callable=AsyncMock,
            return_value=error_result,
        ):
            from httpx import ASGITransport, AsyncClient

            from lm_mcp.transport.http import create_asgi_app

            app = create_asgi_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "delete_device",
                            "arguments": {"device_id": 1},
                        },
                        "id": 1,
                    },
                )

        data = resp.json()
        assert "disabled" in str(data["result"]).lower()

    @pytest.mark.asyncio
    async def test_tools_call_missing_name_returns_error(self, monkeypatch):
        """HTTP tools/call with missing tool name returns JSON-RPC error."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from httpx import ASGITransport, AsyncClient

        from lm_mcp.transport.http import create_asgi_app

        app = create_asgi_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"arguments": {}},
                    "id": 1,
                },
            )

        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32602
