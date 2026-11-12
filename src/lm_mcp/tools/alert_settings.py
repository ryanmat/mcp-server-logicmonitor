# Description: Datapoint alert thresholds at instance, device and group level: read and write.
# Description: Reads name the level a threshold comes from; writes refuse one that does not parse.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
    require_write_permission,
    validation_error,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# One threshold clause as LogicMonitor stores it: an optional time frame "( HH:MM HH:MM )"
# of clock times up to 24:00, an optional comparison method ("delta", "delta|" or "|"), an
# operator, a space, and one to three severity values (warning, error, critical). Clauses
# join with commas. The portal's datasource definitions use these forms and delta is the only
# method they use; the docs name other methods without spelling them, so those are refused.
# The API answered 500 to an operator with no space after it and stored a fourth value as
# written, so neither passes.
_NUMBER = r"-?(?:\d+(?:\.\d+)?|\.\d+)"
_TIME = r"(?:(?:[01]?\d|2[0-3]):[0-5]\d|24:00)"
_CLAUSE = (
    rf"(?:\(\s*{_TIME}\s+{_TIME}\s*\)\s*)?"
    r"(?:delta\|?|\|)?"
    r"(?:>=|<=|!=|>|<|=)"
    rf"\s+{_NUMBER}(?:\s+{_NUMBER}){{0,2}}"
)
_THRESHOLD = re.compile(rf"^\s*{_CLAUSE}(?:\s*,\s*{_CLAUSE})*\s*$")

THRESHOLD_FORM = (
    "an operator (>, >=, <, <=, =, !=), a space and one to three values for warning, error "
    "and critical, such as '> 60 80 90'; an optional method before it ('delta> 5'); time-"
    "framed clauses joined by commas ('( 00:00 12:00 ) > 90 , > 80'); or '' to clear"
)

_LEVEL_IDS = {
    "device": ("device_id",),
    "instance": ("device_id", "device_datasource_id", "instance_id"),
    "group": ("group_id", "datasource_id"),
}


def threshold_parses(expr: str) -> bool:
    """Whether expr is a threshold LogicMonitor takes: empty clears it."""
    return expr == "" or _THRESHOLD.match(expr) is not None


def _missing(level: str, ids: dict[str, int | None]) -> list[TextContent] | None:
    """The refusal for a level outside the three, or one whose path ids were not all
    given, or None."""
    if level not in _LEVEL_IDS:
        return validation_error(
            "INVALID_REQUEST", f"level={level!r} is not one of {', '.join(_LEVEL_IDS)}"
        )
    missing = [name for name in _LEVEL_IDS[level] if ids.get(name) is None]
    if not missing:
        return None
    return validation_error("INVALID_REQUEST", f"level={level!r} needs {', '.join(missing)}")


def _instance_path(device_id: Any, device_datasource_id: Any, instance_id: Any) -> str:
    """The alert settings path of one device datasource instance."""
    return (
        f"/device/devices/{device_id}/devicedatasources/{device_datasource_id}"
        f"/instances/{instance_id}/alertsettings"
    )


def _parents(item: dict) -> list[tuple[str, dict]]:
    """The levels an instance inherits from, highest precedence first, as LogicMonitor
    documents it: instance group, resource datasource, resource groups, then the datasource's
    global definition. The resource groups are taken in the order the API lists them, which
    the swagger gives as highest priority first; the probe saw one group, not an order."""
    groups = [("device_group", group) for group in item.get("parentDeviceGroupAlertExprList") or []]
    return [
        ("instance_group", item.get("parentInstanceGroupAlertExpr") or {}),
        ("device_datasource", item.get("parentResourceDataSourceAlertExpr") or {}),
        *groups,
    ]


def setting_row(item: dict) -> dict:
    """Project one instance or device alert setting: its datapoint, the threshold in force
    and the level that threshold comes from, or None for both when no level sets one."""
    threshold, source, source_group = None, None, None
    if item.get("alertExpr"):
        threshold, source = item["alertExpr"], "instance"
    else:
        for level, parent in _parents(item):
            if parent.get("alertExpr"):
                threshold, source = parent["alertExpr"], level
                source_group = parent.get("groupFullPath") if level == "device_group" else None
                break
        else:
            if item.get("globalAlertExpr"):
                threshold, source = item["globalAlertExpr"], "global"
    return {
        "setting_id": item.get("id"),
        "datapoint": item.get("dataPointName"),
        "datapoint_id": item.get("dataPointId"),
        "instance": item.get("dataSourceInstanceAlias"),
        "instance_id": item.get("dataSourceInstanceId"),
        "threshold": threshold,
        "source": source,
        "source_group": source_group,
        "instance_threshold": item.get("alertExpr"),
        "global_threshold": item.get("globalAlertExpr"),
        "alerting_disabled": item.get("disableAlerting"),
    }


def _group_row(entry: dict) -> dict:
    """Project one datapoint of a group's datasource alert config."""
    parent = entry.get("parentDeviceGroupAlertExprList") or {}
    threshold, source, source_group = None, None, None
    if entry.get("alertExpr"):
        threshold, source = entry["alertExpr"], "group"
    elif parent.get("alertExpr"):
        threshold, source = parent["alertExpr"], "device_group"
        source_group = parent.get("groupFullPath")
    elif entry.get("globalAlertExpr"):
        threshold, source = entry["globalAlertExpr"], "global"
    return {
        "datapoint": entry.get("dataPointName"),
        "datapoint_id": entry.get("dataPointId"),
        "threshold": threshold,
        "source": source,
        "source_group": source_group,
        "group_threshold": entry.get("alertExpr"),
        "global_threshold": entry.get("globalAlertExpr"),
        "alerting_disabled": entry.get("disableAlerting"),
    }


async def get_alert_settings(
    client: LogicMonitorClient,
    level: str,
    device_id: int | None = None,
    device_datasource_id: int | None = None,
    instance_id: int | None = None,
    datapoint_id: int | None = None,
    group_id: int | None = None,
    datasource_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Read datapoint alert thresholds at instance, device or group level.

    Args:
        client: LogicMonitor API client.
        level: "device" (every instance's settings on device_id), "instance" (one device
            datasource instance; with datapoint_id, one datapoint) or "group" (a device
            group's settings for datasource_id).
        device_id: Device ID, for device and instance level.
        device_datasource_id: Device datasource ID, for instance level.
        instance_id: Instance ID, for instance level.
        datapoint_id: One datapoint's setting, at instance level.
        group_id: Device group ID, for group level.
        datasource_id: Datasource ID, for group level.
        limit: Maximum settings to return at device and instance level.
        offset: Settings to skip at device and instance level.

    Returns:
        List of TextContent with the settings, or an error envelope.
    """
    ids = {
        "device_id": device_id,
        "device_datasource_id": device_datasource_id,
        "instance_id": instance_id,
        "group_id": group_id,
        "datasource_id": datasource_id,
    }
    refusal = _missing(level, ids)
    if refusal:
        return refusal
    if level == "device":
        return await list_tool(
            client,
            f"/device/devices/{device_id}/alertsettings",
            key="settings",
            project=setting_row,
            limit=limit,
            offset=offset,
        )
    if level == "instance":
        path = _instance_path(device_id, device_datasource_id, instance_id)
        if datapoint_id is None:
            return await list_tool(
                client, path, key="settings", project=setting_row, limit=limit, offset=offset
            )
        try:
            return format_response(
                {"setting": setting_row(await client.get(f"{path}/{datapoint_id}"))}
            )
        except Exception as e:
            return handle_error(e)
    try:
        config = await client.get(
            f"/device/groups/{group_id}/datasources/{datasource_id}/alertsettings"
        )
        return format_response(
            {
                "datasource_type": config.get("datasourceType"),
                "settings": [_group_row(entry) for entry in config.get("dpConfig") or []],
            }
        )
    except Exception as e:
        return handle_error(e)


def _group_entry(config: dict, datapoint_id: int | None) -> dict | None:
    """One datapoint's entry in a group's datasource alert config, or None."""
    return next(
        (e for e in config.get("dpConfig") or [] if e.get("dataPointId") == datapoint_id), None
    )


def _in_force(levels: list[tuple[dict, str]]) -> int:
    """The first interval a level sets (0 or more), highest precedence first; -1 when none
    does, which the API reads as inherit. The resource datasource level sends its intervals
    as strings, and an unset one as an empty string."""
    for values, key in levels:
        value = str(values.get(key) if values.get(key) is not None else "").strip()
        if value.isdigit():
            return int(value)
    return -1


def _instance_intervals(item: dict) -> dict[str, int]:
    """The trigger, clear and no-data intervals in force on an instance datapoint.

    The API refuses a threshold written with the -1 (inherit) a record keeps, so a write
    carries the values in force, taken by the same precedence as the threshold.
    """
    parents = [parent for _, parent in _parents(item)]
    pairs = (
        ("alertTransitionInterval", "alertTransitionInterval", "globalAlertTransitionInterval"),
        (
            "alertClearInterval",
            "alertClearTransitionInterval",
            "globalAlertClearTransitionInterval",
        ),
        ("alertForNoData", "alertForNoData", "globalAlertForNoData"),
    )
    return {
        own: _in_force([(item, own), *[(parent, inherited) for parent in parents], (item, gbl)])
        for own, inherited, gbl in pairs
    }


def _group_intervals(entry: dict) -> dict[str, int]:
    """The trigger, clear and no-data intervals in force on a group datapoint."""
    parent = entry.get("parentDeviceGroupAlertExprList") or {}
    return {
        key: _in_force([(entry, key), (parent, key), (entry, f"global{key[0].upper()}{key[1:]}")])
        for key in ("alertTransitionInterval", "alertClearTransitionInterval", "alertForNoData")
    }


@require_write_permission
async def update_alert_settings(
    client: LogicMonitorClient,
    level: str,
    threshold: str,
    device_id: int | None = None,
    device_datasource_id: int | None = None,
    instance_id: int | None = None,
    datapoint_id: int | None = None,
    group_id: int | None = None,
    datasource_id: int | None = None,
    note: str | None = None,
) -> list[TextContent]:
    """Set or clear one datapoint's alert threshold at instance or group level.

    Args:
        client: LogicMonitor API client.
        level: "instance" or "group"; the device level has no write.
        threshold: The threshold, or "" to clear the level's own and inherit again.
        device_id: Device ID, for instance level.
        device_datasource_id: Device datasource ID, for instance level.
        instance_id: Instance ID, for instance level.
        datapoint_id: The datapoint whose threshold changes.
        group_id: Device group ID, for group level.
        datasource_id: Datasource ID, for group level.
        note: A threshold history note, at instance level.

    Returns:
        List of TextContent with the datapoint's setting after the write (null at group
        level when the API's answer omits the datapoint), or an error envelope.
    """
    if level == "device":
        return validation_error(
            "INVALID_REQUEST",
            "Device-level alert settings are read-only; set the threshold at instance or "
            "group level.",
        )
    if not threshold_parses(threshold):
        return validation_error(
            "INVALID_REQUEST", f"Threshold {threshold!r} does not parse: expected {THRESHOLD_FORM}."
        )
    ids = {
        "device_id": device_id,
        "device_datasource_id": device_datasource_id,
        "instance_id": instance_id,
        "group_id": group_id,
        "datasource_id": datasource_id,
    }
    refusal = _missing(level, ids) or (
        validation_error("INVALID_REQUEST", f"level={level!r} needs datapoint_id")
        if datapoint_id is None
        else None
    )
    if refusal:
        return refusal
    try:
        if level == "instance":
            path = f"{_instance_path(device_id, device_datasource_id, instance_id)}/{datapoint_id}"
            body: dict[str, Any] = {"alertExpr": threshold}
            if note is not None:
                body["alertExprNote"] = note
            if threshold:
                body.update(_instance_intervals(await client.get(path)))
            return format_response(
                {"setting": setting_row(await client.patch(path, json_body=body))}
            )

        path = f"/device/groups/{group_id}/datasources/{datasource_id}/alertsettings"
        entry = _group_entry(await client.get(path), datapoint_id)
        if entry is None:
            return validation_error(
                "NOT_FOUND",
                f"Datapoint {datapoint_id} is not in datasource {datasource_id}'s alert settings "
                f"on group {group_id}.",
            )
        intervals = (
            _group_intervals(entry)
            if threshold
            else dict.fromkeys(
                ("alertTransitionInterval", "alertClearTransitionInterval", "alertForNoData"), -1
            )
        )
        written = await client.patch(
            path,
            json_body={
                "dpConfig": [
                    {
                        "dataPointId": datapoint_id,
                        "dataPointName": entry.get("dataPointName"),
                        "alertExpr": threshold,
                        **intervals,
                    }
                ]
            },
        )
        written_entry = _group_entry(written, datapoint_id)
        return format_response(
            {"setting": _group_row(written_entry) if written_entry is not None else None}
        )
    except Exception as e:
        return handle_error(e)
