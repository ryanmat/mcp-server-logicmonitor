# Description: Universal reference layer for lm-mcp.
# Description: Exposes Resource content as a Tool for clients without the Resource primitive.

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_reference(
    client: LogicMonitorClient,
    category: str | None = None,
    name: str | None = None,
    list: bool = False,
) -> list[TextContent]:
    """Return LogicMonitor reference content (schemas, enums, filters, syntax, guides).

    Mirrors the content of MCP Resources at `lm://<category>/<name>` for clients
    that do not fully support the Resource primitive (e.g., GitHub Copilot cloud
    agent, OpenAI Codex CLI, Cline). Pass `list=True` -- or omit both arguments --
    to discover the available (category, name) pairs.

    Args:
        client: LogicMonitor API client (unused, required by convention).
        category: Reference category (schema, enums, filters, syntax, guide).
        name: Resource name within the category.
        list: If True, return available (category, name) pairs instead of content.

    Returns:
        TextContent list with reference content, discovery listing, or error.
    """
    try:
        from lm_mcp.resources.registry import RESOURCES, get_resource_content

        if list or (category is None and name is None):
            pairs: list[dict[str, str]] = []
            for r in RESOURCES:
                path = str(r.uri).removeprefix("lm://")
                if "/" in path:
                    cat, nm = path.split("/", 1)
                    pairs.append(
                        {
                            "category": cat,
                            "name": nm,
                            "description": r.description or "",
                        }
                    )
            return format_response({"available": pairs, "count": len(pairs)})

        if category is None or name is None:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": (
                        "Both 'category' and 'name' are required unless list=true. "
                        "Call with list=true to discover available pairs."
                    ),
                }
            )

        uri = f"lm://{category}/{name}"
        try:
            raw = get_resource_content(uri)
        except ValueError as e:
            return format_response(
                {
                    "error": True,
                    "code": "NOT_FOUND",
                    "message": str(e),
                    "suggestion": (
                        "Call get_reference(list=true) to see available (category, name) pairs."
                    ),
                }
            )
        content: Any = json.loads(raw)
        return format_response({"uri": uri, "content": content})
    except Exception as e:
        return handle_error(e)
