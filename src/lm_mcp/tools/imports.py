# Description: Import/Export tools for LogicMonitor MCP server.
# Description: Provides export functionality for LogicModules.

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission


def _ensure_dict(definition: dict | str) -> dict:
    """Parse string definitions back to dict to prevent double-serialization.

    When the MCP transport deserializes the definition parameter, complex nested
    JSON (e.g., Groovy scripts with escape characters) may arrive as a string
    rather than a parsed dict.

    Args:
        definition: Definition as dict or JSON string.

    Returns:
        Definition as dict.
    """
    if isinstance(definition, str):
        return json.loads(definition)
    return definition


def _import_result_response(result: dict, *, extra: dict | None = None) -> list[TextContent]:
    """Format an import result, surfacing the empty/null-id silent-failure case.

    The /importjson endpoints can return HTTP 200 with neither an id nor an
    errorMessage when the definition is in the wrong format (e.g. REST API format
    instead of LM Exchange format). Treat that as a failure rather than a success with
    imported_id=None.
    """
    if result.get("id") is None and result.get("errorMessage") is None:
        return format_response(
            {
                "error": True,
                "code": "IMPORT_SILENT_FAILURE",
                "message": "Import may have silently failed: the API returned no ID and "
                "no error. Verify the definition is in LM Exchange format (not REST API "
                "format); for REST API format use the matching create_* tool.",
            }
        )
    payload: dict = {
        "imported_id": result.get("id"),
        "name": result.get("name"),
    }
    if extra:
        payload.update(extra)
    return format_response(payload)


# LogicModule type -> the REST-format create_* tool that handles an exported definition.
# jobmonitor and appliesto_function have no create_* counterpart.
_CREATE_COUNTERPART: dict[str, str] = {
    "datasource": "create_datasource",
    "configsource": "create_configsource",
    "eventsource": "create_eventsource",
    "propertysource": "create_propertysource",
    "logsource": "create_logsource",
    "topologysource": "create_topologysource",
    "diagnosticsource": "create_diagnosticsource",
}


def _import_error_response(error: Exception, module_type: str) -> list[TextContent]:
    """Redirect a REST-format / wrong-type import failure to the matching create_* tool.

    import_* accepts only LM Exchange JSON. Feeding it a REST API definition (from
    export_<type> or the API) makes the importjson endpoint reject it with "does not
    match the expected module type"; the actionable fix is the create_* tool, so the
    message names it instead of returning the generic HTTP 400.
    """
    if "expected module type" in str(error).lower():
        create_tool = _CREATE_COUNTERPART.get(module_type)
        if create_tool:
            suggestion = (
                f"If this definition came from export_{module_type} or the REST API it is "
                f"REST format -- use {create_tool} with the same definition. "
                f"import_{module_type} accepts only LM Exchange JSON (the portal's "
                "'LM Exchange' export or a community module)."
            )
        else:
            suggestion = (
                f"import_{module_type} accepts only LM Exchange JSON. Verify the definition "
                f"is a valid LM Exchange {module_type} module."
            )
        return format_response(
            {
                "error": True,
                "code": "IMPORT_FORMAT_MISMATCH",
                "message": f"The definition is not a valid LM Exchange {module_type} module.",
                "suggestion": suggestion,
            }
        )
    return handle_error(error)


# LM Exchange "type" field values required by /importjson endpoints.
_IMPORT_TYPE_MAP: dict[str, str] = {
    "datasource": "datasource",
    "configsource": "configsource",
    "eventsource": "eventsource",
    "propertysource": "propertysource",
    "logsource": "logsource",
    "topologysource": "topologysource",
    "jobmonitor": "batchjob",
    "appliesto_function": "function",
    "diagnosticsource": "diagnosticsource",
}


def _ensure_import_envelope(definition: dict, module_type: str) -> dict:
    """Ensure definition has the required LM Exchange 'type' field.

    The /importjson endpoints require a top-level "type" field with the
    LM Exchange module type identifier. If absent, this function injects it.
    If present, it is left as-is so explicit user values are respected.

    Args:
        definition: The definition dict (already parsed from string if needed).
        module_type: Key into _IMPORT_TYPE_MAP (e.g., "datasource").

    Returns:
        Definition dict with "type" field guaranteed present.
    """
    if "type" not in definition:
        definition = dict(definition)
        definition["type"] = _IMPORT_TYPE_MAP[module_type]
    return definition


def _build_import_params(
    handle_conflict: str | None, fields_to_preserve: list[str] | None
) -> dict | None:
    """Build query params dict for import endpoints.

    Args:
        handle_conflict: Conflict resolution strategy.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        Params dict or None if no params specified.
    """
    params: dict = {}
    if handle_conflict:
        params["handleConflict"] = handle_conflict
    if fields_to_preserve:
        params["fieldsToPreserve"] = ",".join(fields_to_preserve)
    return params or None


if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def export_datasource(
    client: LogicMonitorClient,
    datasource_id: int,
) -> list[TextContent]:
    """Export a DataSource definition as JSON via REST API.

    Returns the REST API representation of the DataSource. This format differs
    from LM Exchange format used by import endpoints. To import into another
    portal, use LM Exchange export from the portal UI instead.

    Args:
        client: LogicMonitor API client.
        datasource_id: DataSource ID to export.

    Returns:
        List of TextContent with full DataSource definition or error.
    """
    try:
        result = await client.get(f"/setting/datasources/{datasource_id}")
        return format_response(
            {
                "datasource_id": datasource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_eventsource(
    client: LogicMonitorClient,
    eventsource_id: int,
) -> list[TextContent]:
    """Export an EventSource definition as JSON via REST API.

    Returns the REST API representation. This format differs from LM Exchange
    format used by import endpoints.

    Args:
        client: LogicMonitor API client.
        eventsource_id: EventSource ID to export.

    Returns:
        List of TextContent with full EventSource definition or error.
    """
    try:
        result = await client.get(f"/setting/eventsources/{eventsource_id}")
        return format_response(
            {
                "eventsource_id": eventsource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_configsource(
    client: LogicMonitorClient,
    configsource_id: int,
) -> list[TextContent]:
    """Export a ConfigSource definition as JSON via REST API.

    Returns the REST API representation. This format differs from LM Exchange
    format used by import endpoints.

    Args:
        client: LogicMonitor API client.
        configsource_id: ConfigSource ID to export.

    Returns:
        List of TextContent with full ConfigSource definition or error.
    """
    try:
        result = await client.get(f"/setting/configsources/{configsource_id}")
        return format_response(
            {
                "configsource_id": configsource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_propertysource(
    client: LogicMonitorClient,
    propertysource_id: int,
) -> list[TextContent]:
    """Export a PropertySource definition as JSON via REST API.

    Returns the REST API representation. This format differs from LM Exchange
    format used by import endpoints.

    Args:
        client: LogicMonitor API client.
        propertysource_id: PropertySource ID to export.

    Returns:
        List of TextContent with full PropertySource definition or error.
    """
    try:
        result = await client.get(f"/setting/propertyrules/{propertysource_id}")
        return format_response(
            {
                "propertysource_id": propertysource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_logsource(
    client: LogicMonitorClient,
    logsource_id: int,
) -> list[TextContent]:
    """Export a LogSource definition as JSON via REST API.

    Returns the REST API representation. This format differs from LM Exchange
    format used by import endpoints.

    Args:
        client: LogicMonitor API client.
        logsource_id: LogSource ID to export.

    Returns:
        List of TextContent with full LogSource definition or error.
    """
    try:
        result = await client.get(f"/setting/logsources/{logsource_id}")
        return format_response(
            {
                "logsource_id": logsource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_dashboard(
    client: LogicMonitorClient,
    dashboard_id: int,
    include_widgets: bool = True,
) -> list[TextContent]:
    """Export a Dashboard definition as JSON including widgets.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID to export.
        include_widgets: Whether to include widget definitions.

    Returns:
        List of TextContent with full Dashboard definition or error.
    """
    try:
        dashboard = await client.get(f"/dashboard/dashboards/{dashboard_id}")

        if include_widgets:
            widgets_result = await client.get(
                f"/dashboard/dashboards/{dashboard_id}/widgets", params={"size": 1000}
            )
            dashboard["widgets_full"] = widgets_result.get("items", [])

        return format_response(
            {
                "dashboard_id": dashboard_id,
                "name": dashboard.get("name"),
                "format": "json",
                "definition": dashboard,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_alert_rule(
    client: LogicMonitorClient,
    alert_rule_id: int,
) -> list[TextContent]:
    """Export an Alert Rule definition as JSON.

    Args:
        client: LogicMonitor API client.
        alert_rule_id: Alert Rule ID to export.

    Returns:
        List of TextContent with full Alert Rule definition or error.
    """
    try:
        result = await client.get(f"/setting/alert/rules/{alert_rule_id}")
        return format_response(
            {
                "alert_rule_id": alert_rule_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_escalation_chain(
    client: LogicMonitorClient,
    escalation_chain_id: int,
) -> list[TextContent]:
    """Export an Escalation Chain definition as JSON.

    Args:
        client: LogicMonitor API client.
        escalation_chain_id: Escalation Chain ID to export.

    Returns:
        List of TextContent with full Escalation Chain definition or error.
    """
    try:
        result = await client.get(f"/setting/alert/chains/{escalation_chain_id}")
        return format_response(
            {
                "escalation_chain_id": escalation_chain_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_datasource(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import a DataSource from LM Exchange JSON definition via multipart upload.

    Expects LM Exchange format (different from REST API format). For REST API
    format definitions (e.g., from export_datasource), use create_datasource instead.

    Args:
        client: LogicMonitor API client.
        definition: DataSource JSON definition in LM Exchange format to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported DataSource info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "datasource")
        result = await client.post_multipart(
            "/setting/datasources/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )

        return _import_result_response(result, extra={"display_name": result.get("displayName")})
    except Exception as e:
        return _import_error_response(e, "datasource")


@require_write_permission
async def import_configsource(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import a ConfigSource from LM Exchange JSON definition via multipart upload.

    Args:
        client: LogicMonitor API client.
        definition: ConfigSource JSON definition to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported ConfigSource info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "configsource")
        result = await client.post_multipart(
            "/setting/configsources/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )
        return _import_result_response(result)
    except Exception as e:
        return _import_error_response(e, "configsource")


@require_write_permission
async def import_eventsource(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import an EventSource from LM Exchange JSON definition via multipart upload.

    Args:
        client: LogicMonitor API client.
        definition: EventSource JSON definition to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported EventSource info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "eventsource")
        result = await client.post_multipart(
            "/setting/eventsources/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )
        return _import_result_response(result)
    except Exception as e:
        return _import_error_response(e, "eventsource")


@require_write_permission
async def import_propertysource(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import a PropertySource from LM Exchange JSON definition via multipart upload.

    Args:
        client: LogicMonitor API client.
        definition: PropertySource JSON definition to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported PropertySource info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "propertysource")
        result = await client.post_multipart(
            "/setting/propertyrules/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )
        return _import_result_response(result)
    except Exception as e:
        return _import_error_response(e, "propertysource")


@require_write_permission
async def import_logsource(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import a LogSource from LM Exchange JSON definition via multipart upload.

    Args:
        client: LogicMonitor API client.
        definition: LogSource JSON definition to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported LogSource info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "logsource")
        result = await client.post_multipart(
            "/setting/logsources/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )
        return _import_result_response(result)
    except Exception as e:
        return _import_error_response(e, "logsource")


@require_write_permission
async def import_topologysource(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import a TopologySource from LM Exchange JSON definition via multipart upload.

    Args:
        client: LogicMonitor API client.
        definition: TopologySource JSON definition to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported TopologySource info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "topologysource")
        result = await client.post_multipart(
            "/setting/topologysources/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )
        return _import_result_response(result)
    except Exception as e:
        return _import_error_response(e, "topologysource")


@require_write_permission
async def import_jobmonitor(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import a JobMonitor from LM Exchange JSON definition via multipart upload.

    Args:
        client: LogicMonitor API client.
        definition: JobMonitor JSON definition to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported JobMonitor info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "jobmonitor")
        result = await client.post_multipart(
            "/setting/batchjobs/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )
        return _import_result_response(result)
    except Exception as e:
        return _import_error_response(e, "jobmonitor")


@require_write_permission
async def import_appliesto_function(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import an AppliesTo function from LM Exchange JSON definition via multipart upload.

    Args:
        client: LogicMonitor API client.
        definition: AppliesTo function JSON definition to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported function info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "appliesto_function")
        result = await client.post_multipart(
            "/setting/functions/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )
        return _import_result_response(result)
    except Exception as e:
        return _import_error_response(e, "appliesto_function")


async def export_diagnosticsource(
    client: LogicMonitorClient,
    diagnosticsource_id: int,
) -> list[TextContent]:
    """Export a DiagnosticSource definition as JSON via REST API.

    Returns the REST API representation. This format differs from LM Exchange
    format used by import endpoints.

    Args:
        client: LogicMonitor API client.
        diagnosticsource_id: DiagnosticSource ID to export.

    Returns:
        List of TextContent with full DiagnosticSource definition or error.
    """
    try:
        result = await client.get(f"/setting/diagnosticsources/{diagnosticsource_id}")
        return format_response(
            {
                "diagnosticsource_id": diagnosticsource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_diagnosticsource(
    client: LogicMonitorClient,
    definition: dict | str,
    handle_conflict: str | None = None,
    fields_to_preserve: list[str] | None = None,
) -> list[TextContent]:
    """Import a DiagnosticSource from LM Exchange JSON definition via multipart upload.

    Args:
        client: LogicMonitor API client.
        definition: DiagnosticSource JSON definition to import.
        handle_conflict: How to handle naming conflicts with existing modules.
        fields_to_preserve: Fields to keep from existing module when overwriting.

    Returns:
        List of TextContent with imported DiagnosticSource info or error.
    """
    try:
        definition = _ensure_dict(definition)
        definition = _ensure_import_envelope(definition, "diagnosticsource")
        result = await client.post_multipart(
            "/setting/diagnosticsources/importjson",
            definition=definition,
            params=_build_import_params(handle_conflict, fields_to_preserve),
        )
        return _import_result_response(result)
    except Exception as e:
        return _import_error_response(e, "diagnosticsource")


async def export_remediationsource(
    client: LogicMonitorClient,
    remediationsource_id: int,
) -> list[TextContent]:
    """Export a RemediationSource definition as JSON via REST API.

    Returns the REST API representation. RemediationSources have no LM
    Exchange import endpoint; use create_remediationsource with this output.

    Args:
        client: LogicMonitor API client.
        remediationsource_id: RemediationSource ID to export.

    Returns:
        List of TextContent with full RemediationSource definition or error.
    """
    try:
        result = await client.get(f"/setting/remediationsources/{remediationsource_id}")
        return format_response(
            {
                "remediationsource_id": remediationsource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)
