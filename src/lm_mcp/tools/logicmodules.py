# Description: The LogicModule module table: endpoint, id field and projection per module type.
# Description: Generic get, delete and create that the eight per-module tool files delegate to.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    normalize_definition_fields,
    quote_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# LogSource and TopologySource bodies carry collectionMethod, which normalization would
# otherwise rename.
_COLLECTION_METHOD = frozenset({"collectionMethod"})


@dataclass(frozen=True)
class Module:
    """One LogicModule type: where it lives and how its tools report it.

    path is the collection under /setting; id_field is the id argument delete_<module>
    takes and reports; label names the type in messages; project maps the REST object
    onto the get_<module> summary; keep names REST fields normalization leaves alone.
    """

    path: str
    id_field: str
    label: str
    project: Callable[[dict], dict]
    create_reports_display_name: bool = True
    keep: frozenset[str] = field(default_factory=frozenset)


def _project_datasource(result: dict) -> dict:
    """The get_datasource summary of one DataSource."""
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "display_name": result.get("displayName"),
        "description": result.get("description"),
        "applies_to": result.get("appliesTo"),
        "group": result.get("group"),
        "collect_method": result.get("collectMethod"),
        "collect_interval": result.get("collectInterval"),
        "has_multi_instances": result.get("hasMultiInstances"),
        "datapoints": [
            {
                "id": dp.get("id"),
                "name": dp.get("name"),
                "description": dp.get("description"),
                "type": dp.get("type"),
                "alert_expr": dp.get("alertExpr"),
                "post_processor_method": dp.get("postProcessorMethod", ""),
                "post_processor_param": dp.get("postProcessorParam", ""),
            }
            for dp in result.get("dataPoints", [])
        ],
        "graphs": [
            {
                "id": g.get("id"),
                "name": g.get("name"),
                "title": g.get("title"),
            }
            for g in result.get("graphs", [])
        ],
    }


def _project_configsource(result: dict) -> dict:
    """The get_configsource summary of one ConfigSource."""
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "display_name": result.get("displayName"),
        "description": result.get("description"),
        "applies_to": result.get("appliesTo"),
        "technology": result.get("technology"),
        "collect_method": result.get("collectMethod"),
        "collect_interval": result.get("collectInterval"),
        "version": result.get("version"),
        "tags": result.get("tags"),
        "audit_version": result.get("auditVersion"),
        "install_date": result.get("installDate"),
        "config_checks": result.get("configChecks", []),
    }


def _project_eventsource(result: dict) -> dict:
    """The get_eventsource summary of one EventSource."""
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "display_name": result.get("displayName"),
        "description": result.get("description"),
        "applies_to": result.get("appliesTo"),
        "technology": result.get("technology"),
        "group": result.get("group"),
        "version": result.get("version"),
        "tags": result.get("tags"),
        "audit_version": result.get("auditVersion"),
        "install_date": result.get("installDate"),
        "filters": result.get("filters", []),
    }


def _project_propertysource(result: dict) -> dict:
    """The get_propertysource summary of one PropertySource."""
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "display_name": result.get("displayName"),
        "description": result.get("description"),
        "applies_to": result.get("appliesTo"),
        "technology": result.get("technology"),
        "group": result.get("group"),
        "version": result.get("version"),
        "tags": result.get("tags"),
        "audit_version": result.get("auditVersion"),
        "install_date": result.get("installDate"),
    }


def _project_logsource(result: dict) -> dict:
    """The get_logsource summary of one LogSource."""
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "description": result.get("description"),
        "applies_to": result.get("appliesTo"),
        "group": result.get("group"),
        "log_type": result.get("logType"),
        "collect_method": result.get("collectMethod"),
        "version": result.get("version"),
        "filters": result.get("filters", []),
        "log_file_path": result.get("logFilePath"),
        "log_file_format": result.get("logFileFormat"),
        "log_source_type": result.get("logSourceType"),
    }


def _project_topologysource(result: dict) -> dict:
    """The get_topologysource summary of one TopologySource."""
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "display_name": result.get("displayName"),
        "description": result.get("description"),
        "applies_to": result.get("appliesTo"),
        "technology": result.get("technology"),
        "group": result.get("group"),
        "version": result.get("version"),
        "tags": result.get("tags"),
        "audit_version": result.get("auditVersion"),
        "install_date": result.get("installDate"),
    }


def _project_diagnosticsource(result: dict) -> dict:
    """The get_diagnosticsource summary of one DiagnosticSource."""
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "display_name": result.get("displayName"),
        "description": result.get("description"),
        "applies_to": result.get("appliesTo"),
        "group": result.get("group"),
        "collect_method": result.get("collectMethod"),
        "collect_interval": result.get("collectInterval"),
        "tags": result.get("tags", []),
        "technical_notes": result.get("technicalNotes"),
        "datapoints": [
            {
                "id": dp.get("id"),
                "name": dp.get("name"),
                "description": dp.get("description"),
                "type": dp.get("type"),
            }
            for dp in result.get("dataPoints", [])
        ],
    }


def _project_remediationsource(result: dict) -> dict:
    """The get_remediationsource summary of one RemediationSource."""
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "display_name": result.get("displayName"),
        "description": result.get("description"),
        "applies_to": result.get("appliesTo"),
        "group": result.get("group"),
        "collect_method": result.get("collectMethod"),
        "collect_interval": result.get("collectInterval"),
        "tags": result.get("tags", []),
        "technical_notes": result.get("technicalNotes"),
        "groovy_script": result.get("groovyScript"),
        "datapoints": [
            {
                "id": dp.get("id"),
                "name": dp.get("name"),
                "description": dp.get("description"),
                "type": dp.get("type"),
            }
            for dp in result.get("dataPoints", [])
        ],
    }


MODULES: dict[str, Module] = {
    "datasource": Module(
        path="datasources",
        id_field="datasource_id",
        label="DataSource",
        project=_project_datasource,
    ),
    "configsource": Module(
        path="configsources",
        id_field="configsource_id",
        label="ConfigSource",
        project=_project_configsource,
    ),
    "eventsource": Module(
        path="eventsources",
        id_field="eventsource_id",
        label="EventSource",
        project=_project_eventsource,
    ),
    "propertysource": Module(
        path="propertyrules",
        id_field="propertysource_id",
        label="PropertySource",
        project=_project_propertysource,
        create_reports_display_name=False,
    ),
    "logsource": Module(
        path="logsources",
        id_field="logsource_id",
        label="LogSource",
        project=_project_logsource,
        create_reports_display_name=False,
        keep=_COLLECTION_METHOD,
    ),
    "topologysource": Module(
        path="topologysources",
        id_field="topologysource_id",
        label="TopologySource",
        project=_project_topologysource,
        keep=_COLLECTION_METHOD,
    ),
    "diagnosticsource": Module(
        path="diagnosticsources",
        id_field="diagnosticsource_id",
        label="DiagnosticSource",
        project=_project_diagnosticsource,
    ),
    "remediationsource": Module(
        path="remediationsources",
        id_field="remediationsource_id",
        label="RemediationSource",
        project=_project_remediationsource,
    ),
}


async def get_module(
    client: LogicMonitorClient, module_type: str, module_id: int, raw: bool = False
) -> list[TextContent]:
    """Read one module: its summary, or with raw the REST object whole."""
    module = MODULES[module_type]
    try:
        result = await client.get(f"/setting/{module.path}/{module_id}")
        if raw:
            return format_response(result)
        return format_response(module.project(result))
    except Exception as e:
        return handle_error(e)


async def delete_module(
    client: LogicMonitorClient, module_type: str, module_id: int
) -> list[TextContent]:
    """Delete one module, reading its name first for the confirmation."""
    module = MODULES[module_type]
    item = f"/setting/{module.path}/{module_id}"
    try:
        current = await client.get(item)
        name = current.get("name", f"ID:{module_id}")
        await client.delete(item)
        return format_response(
            {
                "success": True,
                "message": f"{module.label} '{name}' deleted",
                module.id_field: module_id,
            }
        )
    except Exception as e:
        return handle_error(e)


async def create_module(
    client: LogicMonitorClient,
    module_type: str,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create a module from a REST definition; with overwrite, replace one of the same name.

    With overwrite, a module already holding the definition's name is replaced in place by
    a PUT to its id; nothing is deleted first, so a failed write leaves it as it was. A
    name no module holds is created with a POST.
    """
    module = MODULES[module_type]
    collection = f"/setting/{module.path}"
    try:
        payload = normalize_definition_fields(definition, keep=module.keep)
        payload.pop("id", None)

        existing_id = None
        if overwrite and payload.get("name"):
            found = await client.get(
                collection,
                params={"filter": f"name:{quote_filter_value(payload['name'])}", "size": 1},
            )
            items = found.get("items") or []
            if items:
                existing_id = items[0]["id"]

        if existing_id is not None:
            result = await client.put(f"{collection}/{existing_id}", json_body=payload)
            done = "replaced in place"
        else:
            result = await client.post(collection, json_body=payload)
            done = "created successfully"

        created: dict[str, Any] = {"id": result.get("id"), "name": result.get("name")}
        if module.create_reports_display_name:
            created["display_name"] = result.get("displayName")
        return format_response(
            {
                "success": True,
                "message": f"{module.label} '{result.get('name')}' {done}",
                module_type: created,
            }
        )
    except Exception as e:
        return handle_error(e)
