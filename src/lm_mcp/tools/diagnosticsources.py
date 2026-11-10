# Description: Diagnostic source tools for LogicMonitor MCP server.
# Description: CRUD and manual execution for /setting/diagnosticsources REST endpoints.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    normalize_definition_fields,
    paginated_response,
    quote_filter_value,
    require_write_permission,
    sanitize_filter_value,
)
from lm_mcp.tools.diagnostic_remediation import run_pre_execution_checks
from lm_mcp.tools.logicmodules import create_module, delete_module, get_module

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_diagnosticsources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    group_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List DiagnosticSources from LogicMonitor.

    Calls the public REST endpoint ``/setting/diagnosticsources``. Filters
    and pagination are pushed down to the server. The implementation mirrors
    :func:`get_datasources` so consumers get a consistent shape across
    every LogicModule resource family.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by DiagnosticSource name (substring, server-side).
        group_filter: Filter by group (substring, server-side).
        filter: Raw LM filter expression (overrides typed filters).
        limit: Maximum sources to return per page.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with DiagnosticSource data or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}
        wildcards_stripped = False

        if filter:
            params["filter"] = filter
        else:
            filters: list[str] = []
            if name_filter:
                clean_name, was_modified = sanitize_filter_value(name_filter)
                wildcards_stripped = wildcards_stripped or was_modified
                filters.append(f"name~{quote_filter_value(clean_name)}")
            if group_filter:
                clean_group, was_modified = sanitize_filter_value(group_filter)
                wildcards_stripped = wildcards_stripped or was_modified
                filters.append(f"group~{quote_filter_value(clean_group)}")
            if filters:
                params["filter"] = ",".join(filters)

        result = await client.get("/setting/diagnosticsources", params=params)

        sources = []
        for item in result.get("items", []):
            sources.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "display_name": item.get("displayName"),
                    "description": item.get("description"),
                    "applies_to": item.get("appliesTo"),
                    "group": item.get("group"),
                    "collect_method": item.get("collectMethod"),
                    "tags": item.get("tags", []),
                    "technical_notes": item.get("technicalNotes"),
                }
            )

        response = {
            **paginated_response(sources, result, offset),
            "diagnosticsources": sources,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_diagnosticsource(
    client: LogicMonitorClient,
    source_id: int,
    raw: bool = False,
) -> list[TextContent]:
    """Get details for a specific DiagnosticSource.

    Calls ``/setting/diagnosticsources/{id}`` and projects the fields most
    useful to callers (metadata + script content).

    Args:
        client: LogicMonitor API client.
        source_id: DiagnosticSource ID.
        raw: Return the REST object whole instead of the summary.

    Returns:
        List of TextContent with source details or error.
    """
    return await get_module(client, "diagnosticsource", source_id, raw)


@require_write_permission
async def execute_diagnostic(
    client: LogicMonitorClient,
    host_id: int,
    diagnostic_source_id: int,
    alert_id: str | None = None,
) -> list[TextContent]:
    """Execute a DiagnosticSource script on a target device.

    Runs the shared ADR pre-execution checklist (device reachable,
    collector build >= 39.200, appliesTo and script review with
    state-mutation warning) before triggering manual execution via
    POST /setting/diagnosticsources/executemanually.

    Args:
        client: LogicMonitor API client.
        host_id: Device/host ID to execute on.
        diagnostic_source_id: DiagnosticSource ID to execute.
        alert_id: Optional alert ID to associate with the execution.

    Returns:
        Execution result with pre-check details and warnings.
    """
    try:
        error, checks = await run_pre_execution_checks(
            client, host_id, diagnostic_source_id, source_kind="diagnostic"
        )
        if error:
            return format_response(error)

        payload: dict = {
            "hostId": host_id,
            "diagnosticId": diagnostic_source_id,
            "triggerType": "manual",
        }
        if alert_id:
            payload["alertId"] = alert_id

        exec_result = await client.post(
            "/setting/diagnosticsources/executemanually",
            json_body=payload,
        )

        response = {
            "success": True,
            "message": "Diagnostic execution initiated",
            "host_id": host_id,
            "diagnostic_source_id": diagnostic_source_id,
            "alert_id": alert_id,
            "collector_version": checks["collector_version"],
            "applies_to": checks["applies_to"],
            "script_preview": checks["script_preview"],
            "execution_response": exec_result,
            "warnings": checks["warnings"],
            "next_step": (
                "Poll get_diagnostic_remediation_results with this host_id for "
                "execution status and script output."
            ),
        }

        if checks["mutation_warning"]:
            response["mutation_warning"] = checks["mutation_warning"]

        return format_response(response)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_diagnosticsource(
    client: LogicMonitorClient,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create a DiagnosticSource via REST API using a full definition dict.

    Accepts REST API format (the format get_diagnosticsource returns with raw=true).
    For LM Exchange format imports, use import_diagnosticsource instead.

    Args:
        client: LogicMonitor API client.
        definition: Full DiagnosticSource definition dict in REST API format.
        overwrite: If True, replace the DiagnosticSource holding the definition's name in
            place (a PUT to its id); nothing is deleted first.

    Returns:
        List of TextContent with created DiagnosticSource info or error.
    """
    return await create_module(client, "diagnosticsource", definition, overwrite)


@require_write_permission
async def update_diagnosticsource(
    client: LogicMonitorClient,
    diagnosticsource_id: int,
    definition: dict,
    confirm: bool = False,
) -> list[TextContent]:
    """Update an existing DiagnosticSource via REST API (full replace).

    Internal PUT behind update_logicmodule, which reads the current
    definition, merges the caller's changes and passes the merged full
    definition here; the server registers no tool for it. The LM API
    update is full-replace and can blank any field the definition leaves out,
    the Groovy script included.

    Args:
        client: LogicMonitor API client.
        diagnosticsource_id: DiagnosticSource ID to update.
        definition: Full DiagnosticSource definition dict with all fields.
        confirm: Must be True to proceed; update_logicmodule always passes it.
            Without it the call returns INVALID_REQUEST and writes nothing.

    Returns:
        List of TextContent with updated DiagnosticSource info or error.
    """
    if not confirm:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": (
                    "update_diagnosticsource is full-replace -- any field omitted "
                    "from `definition` will be BLANKED, including the script. Set "
                    "confirm=true to proceed, OR use update_logicmodule"
                    "(type='diagnosticsource', id, changes, mode='preview') for a "
                    "safe partial update with diff preview."
                ),
            }
        )
    try:
        payload = normalize_definition_fields(definition)
        payload.pop("id", None)

        result = await client.put(
            f"/setting/diagnosticsources/{diagnosticsource_id}", json_body=payload
        )

        return format_response(
            {
                "success": True,
                "message": f"DiagnosticSource '{result.get('name')}' updated successfully",
                "diagnosticsource": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "display_name": result.get("displayName"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_diagnosticsource(
    client: LogicMonitorClient,
    diagnosticsource_id: int,
) -> list[TextContent]:
    """Delete a DiagnosticSource from LogicMonitor.

    WARNING: This removes the DiagnosticSource definition; any action chains
    referencing it as a stage will lose that stage.

    Args:
        client: LogicMonitor API client.
        diagnosticsource_id: DiagnosticSource ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    return await delete_module(client, "diagnosticsource", diagnosticsource_id)
