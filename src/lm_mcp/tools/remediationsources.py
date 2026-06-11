# Description: Remediation source tools for LogicMonitor MCP server.
# Description: Provides read, execution, and history access for remediation sources.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    require_write_permission,
    safe_total,
    sanitize_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

logger = logging.getLogger(__name__)


async def get_remediationsources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    group_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List RemediationSources from LogicMonitor.

    Calls the public REST endpoint ``/setting/remediationsources``. Filters
    and pagination are pushed down to the server. Mirrors :func:`get_datasources`
    so consumers get the same shape across every LogicModule resource family.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by RemediationSource name (substring, server-side).
        group_filter: Filter by group (substring, server-side).
        filter: Raw LM filter expression (overrides typed filters).
        limit: Maximum sources to return per page.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with RemediationSource data or error.
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

        result = await client.get("/setting/remediationsources", params=params)

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

        total = safe_total(result)
        has_more = (offset + len(sources)) < total

        response = {
            "total": total,
            "count": len(sources),
            "offset": offset,
            "has_more": has_more,
            "remediationsources": sources,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_remediationsource(
    client: LogicMonitorClient,
    source_id: int,
) -> list[TextContent]:
    """Get details for a specific RemediationSource.

    Calls ``/setting/remediationsources/{id}`` and projects the fields most
    useful to callers (metadata + script content). The same endpoint is
    already exercised by ``execute_remediation`` for pre-flight checks.

    Args:
        client: LogicMonitor API client.
        source_id: RemediationSource ID.

    Returns:
        List of TextContent with source details or error.
    """
    try:
        result = await client.get(f"/setting/remediationsources/{source_id}")

        detail = {
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

        return format_response(detail)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def execute_remediation(
    client: LogicMonitorClient,
    host_id: int,
    remediation_source_id: int,
    alert_id: str | None = None,
) -> list[TextContent]:
    """Execute a RemediationSource script on a target device.

    Performs an 8-point pre-execution checklist before running:
    1. Collector version >= 39.200
    2. Device reachable (not dead)
    3. Write permission (enforced by decorator)
    4. Audit logging (handled by server middleware)
    5. AppliesTo script included for review
    6. Concurrency warning
    7. Script preview
    8. State mutation warning for dangerous keywords

    Args:
        client: LogicMonitor API client.
        host_id: Device/host ID to execute on.
        remediation_source_id: Remediation source ID to execute.
        alert_id: Optional alert ID to associate with the execution.

    Returns:
        Execution result with pre-check details and warnings.
    """
    try:
        warnings = []

        # Check 1: Get device info and verify reachable
        device = await client.get(f"/device/devices/{host_id}")
        host_status = device.get("hostStatus", -1)
        if host_status == 1:
            return format_response(
                {
                    "error": True,
                    "code": "DEVICE_UNREACHABLE",
                    "message": (
                        f"Device {host_id} is dead (hostStatus=1). Cannot execute remediation."
                    ),
                    "suggestion": "Verify device connectivity before executing remediation.",
                }
            )

        # Check 2: Verify collector version
        collector_id = device.get("preferredCollectorId")
        collector_version = "unknown"
        if collector_id:
            try:
                collector = await client.get(f"/setting/collector/collectors/{collector_id}")
                build = collector.get("build", "0")
                collector_version = str(build)
                # Parse version: build is a string like "39.200" or an int
                try:
                    version_num = float(str(build).replace(",", ""))
                    if version_num < 39.200:
                        return format_response(
                            {
                                "error": True,
                                "code": "COLLECTOR_VERSION_LOW",
                                "message": (
                                    f"Collector {collector_id} build {build} is below "
                                    "minimum 39.200 required for remediation execution."
                                ),
                                "suggestion": (
                                    "Upgrade the collector before executing remediation."
                                ),
                            }
                        )
                except (ValueError, TypeError):
                    warnings.append(
                        f"Could not parse collector build version '{build}'. "
                        "Proceeding with caution."
                    )
            except Exception:
                warnings.append(
                    f"Could not verify collector {collector_id} version. Proceeding with caution."
                )

        # Check 5-8: Get remediation source details
        applies_to = ""
        script_preview = ""
        mutation_warning = None

        try:
            # Try the settings endpoint for remediation source details
            source = await client.get(f"/setting/remediationsources/{remediation_source_id}")
            applies_to = source.get("appliesTo", source.get("appliesToScript", ""))
            script_content = source.get("groovyScript", source.get("script", ""))

            # Script preview (first 500 chars)
            if script_content:
                script_preview = script_content[:500]
                if len(script_content) > 500:
                    script_preview += "... [truncated]"

                # Check for state-mutating keywords
                mutation_keywords = [
                    "restart",
                    "rm ",
                    "rm\t",
                    "delete",
                    "stop",
                    "kill",
                    "reboot",
                    "shutdown",
                ]
                found_keywords = [
                    kw.strip() for kw in mutation_keywords if kw.lower() in script_content.lower()
                ]
                if found_keywords:
                    mutation_warning = (
                        f"This script performs state-mutating operations: "
                        f"{', '.join(found_keywords)}. "
                        "Review carefully before proceeding."
                    )
        except Exception:
            warnings.append(
                "Could not retrieve remediation source details for pre-checks. "
                "Proceeding with execution."
            )

        # Execute the remediation
        payload: dict = {
            "hostId": host_id,
            "remediationId": remediation_source_id,
            "triggerType": "manual",
        }
        if alert_id:
            payload["alertId"] = alert_id

        exec_result = await client.post(
            "/setting/remediationsources/executemanually",
            json_body=payload,
        )

        # Build response
        response = {
            "success": True,
            "message": "Remediation execution initiated",
            "host_id": host_id,
            "remediation_source_id": remediation_source_id,
            "alert_id": alert_id,
            "collector_version": collector_version,
            "applies_to": applies_to,
            "script_preview": script_preview,
            "execution_response": exec_result,
            "warnings": warnings,
            "important_notes": [
                "Cannot pause or cancel once execution starts.",
                "Success does not guarantee resolution -- verify independently.",
            ],
        }

        if mutation_warning:
            response["mutation_warning"] = mutation_warning

        # Concurrency warning
        response["concurrency_note"] = (
            "Concurrent executions not prevented. "
            "Verify no execution is in progress on this device."
        )

        return format_response(response)
    except Exception as e:
        return handle_error(e)
