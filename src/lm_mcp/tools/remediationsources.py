# Description: Remediation source tools for LogicMonitor MCP server.
# Description: Provides read, execution, and history access for remediation sources.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_remediationsources(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    group_filter: str | None = None,
) -> list[TextContent]:
    """List remediation sources from LogicMonitor Exchange Toolbox.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by source name (client-side substring match).
        group_filter: Filter by group (client-side substring match).

    Returns:
        List of TextContent with remediation source data or error.
    """
    try:
        result = await client.post(
            "/exchange/toolbox/exchangeRemediationSources", json_body={}
        )

        # Unwrap Exchange Toolbox envelope
        data = result.get("data", {})
        by_id = data.get("byId", {})
        sources = list(by_id.values())

        # Apply client-side filters
        if name_filter:
            name_lower = name_filter.lower()
            sources = [s for s in sources if name_lower in s.get("name", "").lower()]
        if group_filter:
            group_lower = group_filter.lower()
            sources = [s for s in sources if group_lower in s.get("group", "").lower()]

        formatted = []
        for src in sources:
            formatted.append(
                {
                    "id": src.get("id"),
                    "name": src.get("name"),
                    "description": src.get("description"),
                    "group": src.get("group"),
                    "tags": src.get("tags", []),
                    "technical_notes": src.get("technicalNotes"),
                }
            )

        return format_response(
            {
                "count": len(formatted),
                "remediationsources": formatted,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_remediationsource(
    client: "LogicMonitorClient",
    source_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific remediation source.

    Args:
        client: LogicMonitor API client.
        source_id: Remediation source ID.

    Returns:
        List of TextContent with source details or error.
    """
    try:
        result = await client.post(
            f"/exchange/toolbox/exchangeRemediationSources/{source_id}", json_body={}
        )

        # Handle envelope or direct response
        if "data" in result and "byId" in result.get("data", {}):
            by_id = result["data"]["byId"]
            source = by_id.get(str(source_id), {})
        else:
            source = result

        detail = {
            "id": source.get("id"),
            "name": source.get("name"),
            "description": source.get("description"),
            "group": source.get("group"),
            "tags": source.get("tags", []),
            "technical_notes": source.get("technicalNotes"),
            "applies_to": source.get("appliesToScript"),
            "script": source.get("script"),
        }

        return format_response(detail)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def execute_remediation(
    client: "LogicMonitorClient",
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
            return format_response({
                "error": True,
                "code": "DEVICE_UNREACHABLE",
                "message": (
                    f"Device {host_id} is dead (hostStatus=1). "
                    "Cannot execute remediation."
                ),
                "suggestion": "Verify device connectivity before executing remediation.",
            })

        # Check 2: Verify collector version
        collector_id = device.get("preferredCollectorId")
        collector_version = "unknown"
        if collector_id:
            try:
                collector = await client.get(
                    f"/setting/collector/collectors/{collector_id}"
                )
                build = collector.get("build", "0")
                collector_version = str(build)
                # Parse version: build is a string like "39.200" or an int
                try:
                    version_num = float(str(build).replace(",", ""))
                    if version_num < 39.200:
                        return format_response({
                            "error": True,
                            "code": "COLLECTOR_VERSION_LOW",
                            "message": (
                                f"Collector {collector_id} build {build} is below "
                                "minimum 39.200 required for remediation execution."
                            ),
                            "suggestion": (
                                "Upgrade the collector before executing remediation."
                            ),
                        })
                except (ValueError, TypeError):
                    warnings.append(
                        f"Could not parse collector build version '{build}'. "
                        "Proceeding with caution."
                    )
            except Exception:
                warnings.append(
                    f"Could not verify collector {collector_id} version. "
                    "Proceeding with caution."
                )

        # Check 5-8: Get remediation source details
        applies_to = ""
        script_preview = ""
        mutation_warning = None

        try:
            # Try the settings endpoint for remediation source details
            source = await client.get(
                f"/setting/remediationsources/{remediation_source_id}"
            )
            applies_to = source.get("appliesTo", source.get("appliesToScript", ""))
            script_content = source.get("groovyScript", source.get("script", ""))

            # Script preview (first 500 chars)
            if script_content:
                script_preview = script_content[:500]
                if len(script_content) > 500:
                    script_preview += "... [truncated]"

                # Check for state-mutating keywords
                mutation_keywords = [
                    "restart", "rm ", "rm\t", "delete", "stop",
                    "kill", "reboot", "shutdown",
                ]
                found_keywords = [
                    kw.strip() for kw in mutation_keywords
                    if kw.lower() in script_content.lower()
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


async def get_remediation_status(
    client: "LogicMonitorClient",
    host_id: int,
    remediation_source_id: int,
) -> list[TextContent]:
    """Get the current status of a remediation source on a device.

    Queries available endpoints to determine execution state.

    Args:
        client: LogicMonitor API client.
        host_id: Device/host ID.
        remediation_source_id: Remediation source ID.

    Returns:
        Current remediation status with human-readable descriptions.
    """
    try:
        # Query device datasources for remediation-related data
        status_info: dict = {
            "host_id": host_id,
            "remediation_source_id": remediation_source_id,
        }

        # Try to get the remediation source details
        try:
            source = await client.get(
                f"/setting/remediationsources/{remediation_source_id}"
            )
            status_info["source_name"] = source.get("name", "unknown")
            status_info["source_group"] = source.get("group", "unknown")
        except Exception:
            status_info["source_name"] = "unknown"
            status_info["note"] = (
                "Could not retrieve remediation source details. "
                "The source may not exist or you may lack permissions."
            )

        # Try to get device status to verify it is still reachable
        try:
            device = await client.get(f"/device/devices/{host_id}")
            status_info["device_name"] = device.get("displayName", "unknown")
            status_info["device_status"] = (
                "normal" if device.get("hostStatus", 0) == 0 else "dead"
            )
        except Exception:
            status_info["device_name"] = "unknown"
            status_info["device_status"] = "unknown"

        status_info["status_note"] = (
            "The LM API does not provide a dedicated execution status endpoint. "
            "Check device alerts and metrics to verify remediation effect. "
            "Use get_remediation_history for past execution records."
        )

        return format_response(status_info)
    except Exception as e:
        return handle_error(e)


async def get_remediation_history(
    client: "LogicMonitorClient",
    host_id: int,
    remediation_source_id: int | None = None,
    hours_back: int = 24,
) -> list[TextContent]:
    """List past remediation executions for a device.

    Args:
        client: LogicMonitor API client.
        host_id: Device/host ID.
        remediation_source_id: Optional filter to a specific remediation source.
        hours_back: Hours to look back (default: 24).

    Returns:
        List of past executions with timestamps and results.
        Output truncated at 32KB with truncated flag.
    """
    try:
        import json as _json
        import time as _time

        now_epoch = int(_time.time())
        start_epoch = now_epoch - (hours_back * 3600)

        # Query audit logs for remediation executions
        params = {
            "size": 100,
            "filter": f"happenedOn>:{start_epoch}",
        }

        try:
            result = await client.get("/setting/accesslogs", params=params)
            items = result.get("items", [])
        except Exception:
            items = []

        # Filter for remediation-related entries
        remediation_entries = []
        for item in items:
            description = str(item.get("description", "")).lower()
            if "remediation" not in description and "executemanually" not in description:
                continue
            entry = {
                "timestamp": item.get("happenedOn"),
                "user": item.get("username", "unknown"),
                "description": item.get("description", ""),
                "ip": item.get("ip", ""),
            }
            # Filter by remediation_source_id if specified
            if remediation_source_id is not None:
                if str(remediation_source_id) in str(item.get("description", "")):
                    remediation_entries.append(entry)
            else:
                remediation_entries.append(entry)

        # Check output size and truncate if needed
        response: dict = {
            "host_id": host_id,
            "remediation_source_id": remediation_source_id,
            "hours_back": hours_back,
            "total_entries": len(remediation_entries),
            "entries": remediation_entries,
            "truncated": False,
        }

        # Truncate at 32KB
        serialized = _json.dumps(response, indent=2, default=str)
        if len(serialized) > 32768:
            # Reduce entries until under limit
            while len(remediation_entries) > 0:
                remediation_entries.pop()
                response["entries"] = remediation_entries
                response["truncated"] = True
                serialized = _json.dumps(response, indent=2, default=str)
                if len(serialized) <= 32768:
                    break

        if not remediation_entries:
            response["note"] = (
                "No remediation execution records found in the audit log. "
                "Entries may have aged out or remediation may not have been executed "
                "in the specified time window."
            )

        return format_response(response)
    except Exception as e:
        return handle_error(e)
