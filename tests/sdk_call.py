# Description: Calls a tool the way a client's tools/call reaches it: through the MCP SDK's
# Description: request handlers on lm_mcp.server, which validate input, run it, validate output.

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from mcp import types

from lm_mcp.config import reset_config


async def call_through_sdk(
    monkeypatch: pytest.MonkeyPatch, client: object, name: str, arguments: dict
) -> types.CallToolResult:
    """Call ``name`` through the SDK in single-portal mode with ``client`` as the startup client.

    Lists the tools through the SDK first, as a client does, so the call is validated
    against the definitions the server serves now.
    """
    from lm_mcp.server import server

    for variable in (
        "LM_MULTI_PORTAL",
        "LM_ENABLED_TOOLS",
        "LM_DISABLED_TOOLS",
        "LM_MCP_CATEGORIES",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    reset_config()
    request = types.CallToolRequest(
        params=types.CallToolRequestParams(name=name, arguments=arguments)
    )
    with patch("lm_mcp.server._client", client):
        await server.request_handlers[types.ListToolsRequest](None)
        response = await server.request_handlers[types.CallToolRequest](request)
    return response.root


async def replay_through_sdk(
    monkeypatch: pytest.MonkeyPatch, name: str, arguments: dict, result: list | dict
) -> types.CallToolResult:
    """Send a handler's real ``result`` back through the SDK's call_tool path for ``name``.

    The handler is replaced by one that returns ``result`` (a report a test already parsed
    is formatted again), so a scenario test that ran the real handler can show that its
    output passes the SDK's outputSchema validation.
    """
    from lm_mcp.tools import format_response

    content = format_response(result) if isinstance(result, dict) else result

    async def replay(*args: object, **kwargs: object) -> list:
        return content

    with patch("lm_mcp.server.get_tool_handler", return_value=replay):
        return await call_through_sdk(monkeypatch, object(), name, arguments)


def structured(result: types.CallToolResult) -> dict:
    """The structured content of a successful result, checked against its text twin."""
    assert result.isError is False, result.content[0].text
    assert result.structuredContent == json.loads(result.content[0].text)
    return result.structuredContent
