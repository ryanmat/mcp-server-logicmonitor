# Description: Shared assertions for list tools that page through list_tool.
# Description: Offset declared in the schema and sent; a negative API total read as more rows.

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import respx

from lm_mcp.registry import TOOLS

BASE_URL = "https://test.logicmonitor.com/santaba/rest"


async def assert_offset_declared_and_sent(
    client: Any,
    handler: Callable[..., Awaitable[list]],
    path: str,
    kwargs: dict[str, Any],
) -> None:
    """Assert the tool's schema declares offset and its handler sends it with size.

    Run inside respx.mock. The tool is the registered tool named after the handler.
    """
    (tool,) = [t for t in TOOLS if t.name == handler.__name__]
    assert tool.inputSchema["properties"]["offset"]["type"] == "integer"
    route = respx.get(f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )

    result = await handler(client, limit=10, offset=20, **kwargs)

    params = route.calls[0].request.url.params
    assert (params["size"], params["offset"]) == ("10", "20")
    assert json.loads(result[0].text)["offset"] == 20


async def assert_negative_total_reads_as_more(
    client: Any,
    handler: Callable[..., Awaitable[list]],
    path: str,
    kwargs: dict[str, Any],
) -> None:
    """Assert a page under a negative API total carries has_more and no total.

    Run inside respx.mock. The total is the portal's -(offset + size + 1) for one row.
    """
    respx.get(f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(200, json={"items": [{"id": 1}], "total": -2})
    )

    result = await handler(client, limit=1, **kwargs)

    data = json.loads(result[0].text)
    assert "total" not in data
    assert data["has_more"] is True
