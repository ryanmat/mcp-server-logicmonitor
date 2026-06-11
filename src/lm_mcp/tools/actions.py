# Description: Action chain and action rule tools for LogicMonitor MCP server.
# Description: CRUD for /setting/action/chains and /setting/action/rules (ADR automation).

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    require_write_permission,
    safe_total,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

_STAGE_TYPES = ("diagnosticSource", "remediationSource")


def _project_chain(item: dict) -> dict:
    """Project an ActionChain to snake_case with stage summary."""
    stages = item.get("stages") or []
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "stage_count": len(stages),
        "stages": [
            {"id": s.get("id"), "type": s.get("type"), "name": s.get("name")} for s in stages
        ],
    }


def _validate_stages(stages: list) -> str | None:
    """Validate the create/update stages payload; return an error message or None.

    Each stage is {id: <source id>, type: diagnosticSource|remediationSource,
    name?}. The id references a DiagnosticSource or RemediationSource.
    """
    if not isinstance(stages, list) or not stages:
        return "stages must be a non-empty list of {id, type} objects."
    for i, stage in enumerate(stages):
        if not isinstance(stage, dict):
            return f"stages[{i}] must be an object with id and type."
        if not isinstance(stage.get("id"), int):
            return f"stages[{i}].id must be an integer source ID."
        if stage.get("type") not in _STAGE_TYPES:
            return f"stages[{i}].type must be one of {list(_STAGE_TYPES)}."
    return None


async def get_action_chains(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List action chains (ordered diagnostic/remediation stages).

    Action chains are the ADR automation unit: named sequences of
    DiagnosticSource and RemediationSource stages that action rules bind
    to alerts. The list endpoint declares no filter support, so
    name_filter is applied client-side.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by chain name (substring, client-side).
        limit: Maximum number of chains to return.
        offset: Results to skip for pagination.

    Returns:
        List of TextContent with action chains or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}
        result = await client.get("/setting/action/chains", params=params)

        chains = []
        for item in result.get("items", []):
            if name_filter and name_filter.lower() not in str(item.get("name", "")).lower():
                continue
            chains.append(_project_chain(item))

        return format_response(
            {
                "total": safe_total(result),
                "count": len(chains),
                "action_chains": chains,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_action_chain(
    client: LogicMonitorClient,
    chain_id: int,
) -> list[TextContent]:
    """Get details about a specific action chain including its stages.

    Args:
        client: LogicMonitor API client.
        chain_id: Action chain ID.

    Returns:
        List of TextContent with chain details or error.
    """
    try:
        result = await client.get(f"/setting/action/chains/{chain_id}")
        return format_response(_project_chain(result))
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_action_chain(
    client: LogicMonitorClient,
    name: str,
    stages: list,
    description: str | None = None,
) -> list[TextContent]:
    """Create an action chain from ordered diagnostic/remediation stages.

    Args:
        client: LogicMonitor API client.
        name: Chain name.
        stages: Ordered list of stages, each
            {id: <source id>, type: "diagnosticSource"|"remediationSource",
            name?: <source name>}.
        description: Optional chain description.

    Returns:
        List of TextContent with created chain info or error.
    """
    stage_error = _validate_stages(stages)
    if stage_error:
        return format_response({"error": True, "code": "VALIDATION_ERROR", "message": stage_error})
    try:
        payload: dict = {"name": name, "stages": stages}
        if description is not None:
            payload["description"] = description

        result = await client.post("/setting/action/chains", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"Action chain '{result.get('name', name)}' created",
                "action_chain": _project_chain(result),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_action_chain(
    client: LogicMonitorClient,
    chain_id: int,
    name: str | None = None,
    stages: list | None = None,
    description: str | None = None,
) -> list[TextContent]:
    """Update an action chain (PATCH; only provided fields are sent).

    Args:
        client: LogicMonitor API client.
        chain_id: Action chain ID to update.
        name: New chain name.
        stages: Replacement ordered stage list, each
            {id, type: "diagnosticSource"|"remediationSource", name?}.
        description: New description.

    Returns:
        List of TextContent with updated chain info or error.
    """
    body: dict = {}
    if name is not None:
        body["name"] = name
    if stages is not None:
        stage_error = _validate_stages(stages)
        if stage_error:
            return format_response(
                {"error": True, "code": "VALIDATION_ERROR", "message": stage_error}
            )
        body["stages"] = stages
    if description is not None:
        body["description"] = description

    if not body:
        return format_response(
            {
                "error": True,
                "code": "NO_CHANGES",
                "message": "Provide at least one of name, stages, or description.",
            }
        )
    try:
        result = await client.patch(f"/setting/action/chains/{chain_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Action chain '{result.get('name')}' updated",
                "action_chain": _project_chain(result),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_action_chain(
    client: LogicMonitorClient,
    chain_id: int,
) -> list[TextContent]:
    """Delete an action chain.

    WARNING: Action rules referencing this chain stop triggering it.

    Args:
        client: LogicMonitor API client.
        chain_id: Action chain ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        chain = await client.get(f"/setting/action/chains/{chain_id}")
        chain_name = chain.get("name", f"ID:{chain_id}")

        await client.delete(f"/setting/action/chains/{chain_id}")

        return format_response(
            {
                "success": True,
                "message": f"Action chain '{chain_name}' deleted",
                "chain_id": chain_id,
            }
        )
    except Exception as e:
        return handle_error(e)
