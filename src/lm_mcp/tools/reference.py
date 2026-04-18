# Description: Universal reference layer for lm-mcp.
# Description: Exposes Resource and Prompt content as Tools for clients without those primitives.

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
                    "code": "MISSING_ARGS",
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
                    "code": "UNKNOWN_REFERENCE",
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


async def get_workflow(
    client: LogicMonitorClient,
    name: str | None = None,
    list: bool = False,
    arguments: dict | None = None,
) -> list[TextContent]:
    """Return LogicMonitor workflow guidance text.

    Mirrors MCP Prompt content for clients without Prompt support. Prefer the
    composite workflow tools (triage, diagnose, health_check, capacity_plan,
    portal_overview) when they exist -- those execute the procedure rather
    than returning guidance text. Pass `list=True` to discover available
    workflows and their arguments.

    Args:
        client: LogicMonitor API client (unused, required by convention).
        name: Workflow name (e.g., 'incident_triage', 'rca_workflow').
        list: If True, return the list of available workflows instead of text.
        arguments: Optional template arguments passed to the workflow builder.

    Returns:
        TextContent list with workflow text, discovery listing, or error.
    """
    try:
        from lm_mcp.prompts.registry import _TEMPLATES, PROMPTS

        if list or name is None:
            items: list[dict] = []
            for p in PROMPTS:
                args_out = [
                    {
                        "name": a.name,
                        "description": a.description,
                        "required": bool(a.required),
                    }
                    for a in (p.arguments or [])
                ]
                items.append(
                    {
                        "name": p.name,
                        "description": p.description,
                        "arguments": args_out,
                    }
                )
            return format_response({"available": items, "count": len(items)})

        if name not in _TEMPLATES:
            return format_response(
                {
                    "error": True,
                    "code": "UNKNOWN_WORKFLOW",
                    "message": f"unknown workflow '{name}'",
                    "suggestion": "Call get_workflow(list=true) to see available workflows.",
                }
            )

        text = _TEMPLATES[name](arguments or {})
        return format_response({"name": name, "text": text})
    except Exception as e:
        return handle_error(e)
