# Description: Collector management tools for LogicMonitor MCP server.
# Description: Collector and collector group CRUD, health, events, uploaded logs, upgrades.

from __future__ import annotations

import asyncio
import io
import logging
import time
import zipfile
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
    quote_filter_value,
    require_write_permission,
    safe_total,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

logger = logging.getLogger(__name__)


def _collector_row(item: dict) -> dict:
    """Project one /setting/collector/collectors row onto the get_collectors fields.

    status reads 1 whether the collector is up or down, so is_down carries isDown.
    """
    return {
        "id": item.get("id"),
        "hostname": item.get("hostname"),
        "status": item.get("status"),
        "is_down": item.get("isDown"),
        "device_count": item.get("numberOfHosts"),
    }


def _collector_group_row(item: dict) -> dict:
    """Project one /setting/collector/groups row onto the get_collector_groups fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "num_of_collectors": item.get("numOfCollectors"),
        "auto_balance": item.get("autoBalance"),
        "auto_balance_strategy": item.get("autoBalanceStrategy"),
    }


async def get_collectors(
    client: LogicMonitorClient,
    hostname_filter: str | None = None,
    collector_group_id: int | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List collectors from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        hostname_filter: Filter by hostname (supports wildcards).
        collector_group_id: Filter by collector group ID.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "hostname~prod,collectorGroupId:1"
        limit: Maximum number of collectors to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with collector data or error.
    """
    return await list_tool(
        client,
        "/setting/collector/collectors",
        key="collectors",
        project=_collector_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"hostname~": hostname_filter},
        clauses=(
            [f"collectorGroupId:{collector_group_id}"] if collector_group_id is not None else []
        ),
    )


async def get_collector(
    client: LogicMonitorClient,
    collector_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific collector.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID.

    Returns:
        List of TextContent with collector details or error.
    """
    try:
        result = await client.get(f"/setting/collector/collectors/{collector_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


async def get_collector_groups(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List collector groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        filter: Raw filter expression for advanced queries (overrides name_filter).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~prod,autoBalance:true"
        limit: Maximum number of groups to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with collector group data or error.
    """
    return await list_tool(
        client,
        "/setting/collector/groups",
        key="collector_groups",
        project=_collector_group_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"name~": name_filter},
    )


async def get_collector_group(
    client: LogicMonitorClient,
    group_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific collector group.

    Args:
        client: LogicMonitor API client.
        group_id: Collector group ID.

    Returns:
        List of TextContent with collector group details or error.
    """
    try:
        result = await client.get(f"/setting/collector/groups/{group_id}")

        group = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "num_of_collectors": result.get("numOfCollectors"),
            "auto_balance": result.get("autoBalance"),
            "auto_balance_strategy": result.get("autoBalanceStrategy"),
            "auto_balance_instance_count_threshold": result.get(
                "autoBalanceInstanceCountThreshold"
            ),
            "custom_properties": [
                {"name": p.get("name"), "value": p.get("value")}
                for p in result.get("customProperties", [])
            ],
        }

        return format_response(group)
    except Exception as e:
        return handle_error(e)


async def get_collector_health(
    client: LogicMonitorClient,
    collector_id: int | None = None,
    collector_group_id: int | None = None,
    include_history: bool = False,
    history_days: int = 7,
) -> list[TextContent]:
    """Enriched collector status with down state, device count and optional alert history.

    Reports collector health signals critical for detecting site-level events
    (power outages, network partitions). Status is enriched with whether the
    collector is currently down, from the isDown field on its record, how many
    devices it monitors, and optionally alerts on a device named for its hostname.
    The collector asked for by collector_id, and in a list each collector not known to
    be up, carries evidence: its latest status check and its five latest events.

    Args:
        client: LogicMonitor API client.
        collector_id: Single collector ID. If set, other scope args are ignored.
        collector_group_id: Restrict to collectors in this group.
        include_history: Include recent alerts on a device named for the collector's
            hostname (default: False). A collector with no such device returns an empty
            list, which does not show it stayed up. The API cannot narrow rows to
            CollectorDown.
        history_days: History lookback in days (default: 7).

    Returns:
        List of TextContent with enriched collector records.
    """
    try:
        if collector_id is not None:
            collectors = [await client.get(f"/setting/collector/collectors/{collector_id}")]
        else:
            params: dict = {"size": 100}
            if collector_group_id is not None:
                params["filter"] = f"collectorGroupId:{collector_group_id}"
            list_result = await client.get("/setting/collector/collectors", params=params)
            collectors = list_result.get("items", [])

        enriched: list[dict] = []
        for col in collectors:
            with_evidence = collector_id is not None or col.get("isDown") is not False
            enriched.append(
                await _enrich_collector(client, col, include_history, history_days, with_evidence)
            )

        down_count = sum(1 for c in enriched if c["is_down"])
        unknown_signal = sum(1 for c in enriched if c.get("down_signal_unavailable"))

        response: dict = {
            "total_collectors": len(enriched),
            "collectors_down": down_count,
            "include_history": include_history,
            "history_days": history_days if include_history else None,
            "collectors": enriched,
        }
        if unknown_signal:
            response["collectors_down_signal_unavailable"] = unknown_signal
            response["warning"] = (
                f"{unknown_signal} of {len(enriched)} collector record(s) carry no isDown "
                "field; collectors_down may be undercounted."
            )
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def _enrich_collector(
    client: LogicMonitorClient,
    col: dict,
    include_history: bool,
    history_days: int,
    with_evidence: bool,
) -> dict:
    """Attach the down state, downstream device count and, when asked, the evidence."""
    cid = col.get("id")
    hostname = col.get("hostname") or ""
    num_hosts_reported = col.get("numberOfHosts") or 0

    downstream_count = num_hosts_reported
    try:
        device_result = await client.get(
            "/device/devices",
            params={
                "size": 1,
                "filter": f"currentCollectorId:{cid}",
            },
        )
        downstream_count = safe_total(device_result)
    except Exception:
        # Fall back to numberOfHosts from the collector record when the
        # devices filter is not supported.
        logger.warning(
            "collector %s: downstream device count query failed; using reported "
            "numberOfHosts as fallback",
            cid,
            exc_info=True,
        )
        downstream_count = num_hosts_reported

    history: list[dict] | None = []
    history_warning: str | None = None
    if include_history and hostname:
        history, history_warning = await _collector_down_history(client, hostname, history_days)

    # isDown is the down signal. status is 1 whether the collector is up or down, so a
    # record with no isDown leaves the state unknown.
    is_down: bool | None = col.get("isDown")

    record: dict = {
        "id": cid,
        "hostname": hostname,
        "collector_group_id": col.get("collectorGroupId"),
        "collector_group_name": col.get("collectorGroupName"),
        "platform": col.get("platform"),
        "status": col.get("status"),
        "is_down": is_down,
        "downstream_device_count": downstream_count,
        "reported_numberOfHosts": num_hosts_reported,
        "up_time_seconds": col.get("upTime"),
    }
    if is_down is None:
        record["down_signal_unavailable"] = True
    if include_history:
        record["collector_down_history"] = history
    if history_warning:
        record["history_warning"] = history_warning
    if with_evidence:
        record["evidence"], evidence_warning = await _collector_evidence(client, cid)
        if evidence_warning:
            record["evidence_warning"] = evidence_warning
    return record


# Events cited as a collector's evidence, newest first.
_EVIDENCE_EVENTS = 5


def _status_check(body: dict) -> dict:
    """Project a services/getStatusCheck answer: its progress and the checks not OK."""
    points = body.get("checkPoints") or []
    return {
        "finished": body.get("finished"),
        "aborted": body.get("aborted"),
        "last_triggered": body.get("lastTriggeredMills"),
        "last_updated": body.get("lastUpdateMills"),
        "scripts_total": body.get("totalScriptCount"),
        "scripts_finished": body.get("finishedScriptCount"),
        "scripts_skipped": body.get("skippedScriptCount"),
        "checks_ok": sum(1 for point in points if point.get("status") == "OK"),
        "problems": [
            {
                "name": point.get("name"),
                "status": point.get("status"),
                "detail": point.get("detail"),
            }
            for point in points
            if point.get("status") != "OK"
        ],
    }


async def _collector_evidence(
    client: LogicMonitorClient, collector_id: int | None
) -> tuple[dict, str | None]:
    """Read a collector's latest status check and recent events, once each.

    A failed read leaves its part null, which does not mean the collector has no check
    or events, and names the failure in the warning.
    """
    path = f"/setting/collector/collectors/{collector_id}"
    evidence: dict = {"status_check": None, "recent_events": None}
    warnings: list[str] = []
    try:
        evidence["status_check"] = _status_check(
            await client.get(f"{path}/services/getStatusCheck")
        )
    except Exception as exc:
        logger.warning("collector %s: status check read failed", collector_id, exc_info=True)
        warnings.append(f"Status check read failed: {exc}")
    try:
        events = await client.get(f"{path}/events", params={"size": _EVIDENCE_EVENTS})
        evidence["recent_events"] = [_event_row(item) for item in events.get("items", [])]
    except Exception as exc:
        logger.warning("collector %s: events read failed", collector_id, exc_info=True)
        warnings.append(f"Events read failed: {exc}")
    return evidence, "; ".join(warnings) or None


async def _collector_down_history(
    client: LogicMonitorClient,
    hostname: str,
    history_days: int,
) -> tuple[list[dict] | None, str | None]:
    """Fetch recent alerts on a device named for a collector hostname.

    A probe of 2026-11-06 (probes-2026-10.md section f) found no alert type that marks a
    collector going down, so rows are not limited to one; each row's alert_type names
    what it is.
    A failed read is unknown, not an empty history: it returns None and a warning.
    """
    start_epoch = int(time.time()) - (history_days * 86400)
    try:
        result = await client.get(
            "/alert/alerts",
            params={
                "size": 100,
                "filter": (
                    f"monitorObjectName:{quote_filter_value(hostname)},startEpoch>:{start_epoch}"
                ),
            },
        )
    except Exception as exc:
        logger.warning("collector history query failed for hostname=%s", hostname, exc_info=True)
        return None, (
            f"Alert history read failed: {exc}. null history does not mean the collector stayed up."
        )

    history: list[dict] = []
    for item in result.get("items", []):
        history.append(
            {
                "alert_id": item.get("id"),
                "severity": item.get("severity"),
                "start_epoch": item.get("startEpoch"),
                "end_epoch": item.get("endEpoch"),
                "cleared": item.get("cleared", False),
                "alert_type": item.get("type"),
            }
        )
    return history, None


def _event_row(item: dict) -> dict:
    """Project one /setting/collector/collectors/{id}/events row onto the event fields."""
    return {
        "id": item.get("id"),
        "reported_on": item.get("reportedOn"),
        "event_code": item.get("eCode"),
        "message": item.get("eventMsg"),
        "collector_build": item.get("collectorBuild"),
        "collector_platform": item.get("collectorPlatform"),
    }


async def get_collector_events(
    client: LogicMonitorClient,
    collector_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List a collector's events (agent restarts, credential rotation, down), newest first.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID.
        limit: Maximum number of events to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the page of events, or an error envelope.
    """
    return await list_tool(
        client,
        f"/setting/collector/collectors/{collector_id}/events",
        key="events",
        project=_event_row,
        limit=limit,
        offset=offset,
    )


def _log_file_row(item: dict) -> dict:
    """Project one /setting/collector/collectors/{id}/logs row onto the log file fields."""
    return {
        "file_name": item.get("fileName"),
        "size": item.get("size"),
        "last_modified": item.get("lastModified"),
        "uploaded": item.get("uploaded"),
    }


async def get_collector_log_files(
    client: LogicMonitorClient,
    collector_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List the log files a collector has uploaded to the portal, as zip files.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID.
        limit: Maximum number of files to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the page of log_files, or an error envelope.
    """
    return await list_tool(
        client,
        f"/setting/collector/collectors/{collector_id}/logs",
        key="log_files",
        project=_log_file_row,
        limit=limit,
        offset=offset,
    )


# Bytes read from a zip member at a time; only the last max_bytes + 1 are kept.
_LOG_CHUNK = 65536


def _member_tail(archive: zipfile.ZipFile, name: str, max_bytes: int) -> tuple[bytes, int]:
    """Read a zip member and return its last max_bytes bytes and its full size.

    The bytes are cut to start on a whole line when the member is longer than max_bytes;
    a last line longer than max_bytes keeps its end.
    """
    window = bytearray()
    size = 0
    with archive.open(name) as member:
        while chunk := member.read(_LOG_CHUNK):
            size += len(chunk)
            window += chunk
            del window[: -(max_bytes + 1)]
    if size <= max_bytes:
        return bytes(window), size
    # The window holds the byte before the cap; a newline there or later, short of the
    # one that ends the last line, marks where the first whole line starts.
    cut = window.find(b"\n", 0, len(window) - 1)
    return bytes(window[cut + 1 :] if cut != -1 else window[1:]), size


async def get_collector_log_file(
    client: LogicMonitorClient,
    collector_id: int,
    file_name: str,
    max_bytes: int = 20000,
) -> list[TextContent]:
    """Read one uploaded collector log file and return the end of its text.

    The portal sends the file as a zip archive; the tool reads its first file and returns
    at most max_bytes bytes from its end, starting on a whole line.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID.
        file_name: The file's name as get_collector_log_files lists it.
        max_bytes: Most bytes of the log's end to return.

    Returns:
        List of TextContent with member, size, truncated, text and other_members, or an
        error envelope.
    """
    try:
        content = await client.get_bytes(
            f"/setting/collector/collectors/{collector_id}/logs/{file_name}",
            params={"format": "zip"},
        )
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            tail, size = _member_tail(archive, names[0], max_bytes)
        return format_response(
            {
                "collector_id": collector_id,
                "file_name": file_name,
                "member": names[0],
                "size": size,
                "truncated": size > max_bytes,
                "text": tail.decode("utf-8", errors="replace"),
                "other_members": names[1:],
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_collector_upgrade_history(
    client: LogicMonitorClient,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List the portal's collector upgrade history, each row as the API returns it.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of rows to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the page of upgrades, or an error envelope.
    """
    return await list_tool(
        client,
        "/setting/collector/collectors/upgradeHistory",
        key="upgrades",
        project=dict,
        limit=limit,
        offset=offset,
    )


# Seconds between status check reads, and the longest run_collector_status_check waits
# for the check it triggered to finish.
STATUS_CHECK_POLL_SECONDS = 5
STATUS_CHECK_BUDGET_SECONDS = 45

STATUS_CHECK_RUNNING_NOTE = (
    "The status check is still running; get_collector_health with this collector_id reads "
    "its latest result."
)


@require_write_permission
async def run_collector_status_check(
    client: LogicMonitorClient,
    collector_id: int,
) -> list[TextContent]:
    """Trigger a collector status check and read its result.

    The check that was last triggered is read first; after the trigger the tool reads
    until a check triggered later finishes or STATUS_CHECK_BUDGET_SECONDS pass, and a
    check still running then is returned with finished false and a note.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID.

    Returns:
        List of TextContent with the trigger's answer and the status check, or an error
        envelope.
    """
    try:
        path = f"/setting/collector/collectors/{collector_id}/services"
        before = (await client.get(f"{path}/getStatusCheck")).get("lastTriggeredMills")
        triggered = await client.post(f"{path}/triggerStatusCheck")
        deadline = time.monotonic() + STATUS_CHECK_BUDGET_SECONDS
        while True:
            check = await client.get(f"{path}/getStatusCheck")
            newer = check.get("lastTriggeredMills") != before
            if (newer and (check.get("finished") or check.get("aborted"))) or (
                time.monotonic() >= deadline
            ):
                break
            await asyncio.sleep(STATUS_CHECK_POLL_SECONDS)
        result: dict = {
            "collector_id": collector_id,
            "triggered": triggered,
            **_status_check(check),
        }
        if not (newer and result["finished"]):
            result["note"] = STATUS_CHECK_RUNNING_NOTE
        return format_response(result)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def restart_collector(
    client: LogicMonitorClient,
    collector_id: int,
) -> list[TextContent]:
    """Restart a collector, with no configuration overrides.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID.

    Returns:
        List of TextContent with the restart's async job id, or an error envelope.
    """
    try:
        job = await client.post(
            f"/setting/collector/collectors/{collector_id}/services/restart", json_body={}
        )
        return format_response({"collector_id": collector_id, "restart_job_id": job})
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def acknowledge_collector_down(
    client: LogicMonitorClient,
    collector_id: int,
    comment: str,
) -> list[TextContent]:
    """Acknowledge a down collector's alert with a comment.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID.
        comment: The acknowledgement comment.

    Returns:
        List of TextContent confirming the acknowledgement, or an error envelope.
    """
    try:
        await client.post(
            f"/setting/collector/collectors/{collector_id}/ackdown",
            json_body={"comment": comment},
        )
        return format_response(
            {"collector_id": collector_id, "acknowledged": True, "comment": comment}
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_collector(
    client: LogicMonitorClient,
    collector_id: int,
    description: str | None = None,
    collector_group_id: int | None = None,
    enable_failback: bool | None = None,
    escalation_chain_id: int | None = None,
) -> list[TextContent]:
    """Update a collector in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID to update.
        description: New description.
        collector_group_id: New collector group ID.
        enable_failback: Enable automatic failback.
        escalation_chain_id: Escalation chain ID for collector down alerts.

    Returns:
        List of TextContent with updated collector details or error.
    """
    try:
        body: dict = {}

        if description is not None:
            body["description"] = description
        if collector_group_id is not None:
            body["collectorGroupId"] = collector_group_id
        if enable_failback is not None:
            body["enableFailBack"] = enable_failback
        if escalation_chain_id is not None:
            body["escalatingChainId"] = escalation_chain_id

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "No updates provided",
                }
            )

        result = await client.patch(f"/setting/collector/collectors/{collector_id}", json_body=body)

        return format_response(
            {
                "message": "Collector updated successfully",
                "collector": {
                    "id": result.get("id"),
                    "hostname": result.get("hostname"),
                    "collector_group_id": result.get("collectorGroupId"),
                    "collector_group_name": result.get("collectorGroupName"),
                    "description": result.get("description"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_collector(
    client: LogicMonitorClient,
    collector_id: int,
) -> list[TextContent]:
    """Delete a collector from LogicMonitor.

    Blocks deletion if the collector still has devices assigned to prevent
    orphaning monitored resources.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        collector = await client.get(f"/setting/collector/collectors/{collector_id}")
        hostname = collector.get("hostname", f"ID:{collector_id}")
        device_count = collector.get("numberOfHosts", 0)

        if device_count > 0:
            return format_response(
                {
                    "error": True,
                    "code": "REJECTED_BY_TOOL",
                    "message": f"Collector '{hostname}' has {device_count} devices assigned. "
                    "Move or delete devices before removing the collector.",
                    "collector_id": collector_id,
                    "device_count": device_count,
                }
            )

        await client.delete(f"/setting/collector/collectors/{collector_id}")

        return format_response(
            {
                "success": True,
                "message": f"Collector '{hostname}' deleted",
                "collector_id": collector_id,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_collector_group(
    client: LogicMonitorClient,
    name: str,
    description: str | None = None,
    auto_balance: bool | None = None,
    auto_balance_strategy: str | None = None,
    custom_properties: dict[str, str] | None = None,
) -> list[TextContent]:
    """Create a collector group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Name of the collector group.
        description: Optional description.
        auto_balance: Enable auto-balancing of devices across collectors.
        auto_balance_strategy: Strategy for auto-balance (e.g., roundRobin).
        custom_properties: Optional custom properties as key-value pairs.

    Returns:
        List of TextContent with created group info or error.
    """
    try:
        body: dict = {"name": name}

        if description is not None:
            body["description"] = description
        if auto_balance is not None:
            body["autoBalance"] = auto_balance
        if auto_balance_strategy is not None:
            body["autoBalanceStrategy"] = auto_balance_strategy
        if custom_properties is not None:
            body["customProperties"] = [
                {"name": k, "value": v} for k, v in custom_properties.items()
            ]

        result = await client.post("/setting/collector/groups", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Collector group '{name}' created",
                "group_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_collector_group(
    client: LogicMonitorClient,
    group_id: int,
    name: str | None = None,
    description: str | None = None,
    auto_balance: bool | None = None,
    auto_balance_strategy: str | None = None,
    custom_properties: dict[str, str] | None = None,
) -> list[TextContent]:
    """Update a collector group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: Collector group ID to update.
        name: New group name.
        description: New description.
        auto_balance: Enable/disable auto-balancing.
        auto_balance_strategy: New auto-balance strategy.
        custom_properties: Custom properties to merge (adds/updates, does not remove).

    Returns:
        List of TextContent with updated group info or error.
    """
    try:
        body: dict = {}

        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if auto_balance is not None:
            body["autoBalance"] = auto_balance
        if auto_balance_strategy is not None:
            body["autoBalanceStrategy"] = auto_balance_strategy
        if custom_properties is not None:
            existing = await client.get(f"/setting/collector/groups/{group_id}")
            existing_props = {p["name"]: p["value"] for p in existing.get("customProperties", [])}
            existing_props.update(custom_properties)
            body["customProperties"] = [{"name": k, "value": v} for k, v in existing_props.items()]

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "No updates provided",
                }
            )

        result = await client.patch(f"/setting/collector/groups/{group_id}", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Collector group {group_id} updated",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_collector_group(
    client: LogicMonitorClient,
    group_id: int,
) -> list[TextContent]:
    """Delete a collector group from LogicMonitor.

    Blocks deletion if collectors are still assigned to the group.

    Args:
        client: LogicMonitor API client.
        group_id: Collector group ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        group = await client.get(f"/setting/collector/groups/{group_id}")
        group_name = group.get("name", f"ID:{group_id}")
        collector_count = group.get("numOfCollectors", 0)

        if collector_count > 0:
            return format_response(
                {
                    "error": True,
                    "code": "REJECTED_BY_TOOL",
                    "message": (
                        f"Collector group '{group_name}' has {collector_count} "
                        "collectors assigned. Move collectors before deleting the group."
                    ),
                    "group_id": group_id,
                    "collector_count": collector_count,
                }
            )

        await client.delete(f"/setting/collector/groups/{group_id}")

        return format_response(
            {
                "success": True,
                "message": f"Collector group '{group_name}' deleted",
                "group_id": group_id,
            }
        )
    except Exception as e:
        return handle_error(e)
