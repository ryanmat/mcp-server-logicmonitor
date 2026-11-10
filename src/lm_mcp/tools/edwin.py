# Description: Edwin AI query tools: insights, records, alert volume, metadata, filter builder.
# Description: Reads Edwin's investigations so the calling model can weigh them beside raw LM data.

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, validation_error

if TYPE_CHECKING:
    from lm_mcp.client.edwin import EdwinClient

logger = logging.getLogger(__name__)

_MAX_INSIGHTS = 50
_MAX_RECORDS = 50

# The field each record source carries its creation time on; events have no
# meta.createdTimestamp, and a window or order on it answers 400.
_TIME_FIELDS = {"alerts": "meta.createdTimestamp", "events": "meta.eventTimestamp"}

# Field-name prefixes a records read leaves out unless named in columns: extra.* mirrors
# the LogicMonitor properties of the CI (2414 fields) and raw.* is the source record.
_BULK_PREFIXES = ("extra.", "raw.")

# The groups entry of each alert-volume grouping.
_VOLUME_GROUPS = {
    "hour": {"field": "meta.createdTimestamp", "type": "HOUR"},
    "state": {"field": "alertDetails.alertState", "type": "COLUMN"},
}

# The fields an insight list row carries (spec R3.1). The genAi fields appear only on
# the insights Edwin analyzed and are passed through verbatim.
_INSIGHT_FIELDS = (
    "_id",
    "meta.displayId",
    "meta.state",
    "insightDetails.workflowState",
    "ml.insightSeverity",
    "ml.causalCI",
    "ml.impactedCIList",
    "meta.totalAlerts",
    "meta.alertKeyList",
    "meta.link",
    "genAi.title",
    "genAi.summary",
    "genAi.rootCause",
    "genAi.impact",
    "genAi.timeline",
    "genAi.remediation",
    "genAi.evidence",
    "genAi.contributing_factors",
    "genAi.similar_incidents",
)

# Epoch-millisecond fields, each returned beside an ISO 8601 twin named <field>_iso.
_TIMESTAMP_FIELDS = (
    "meta.createdTimestamp",
    "meta.updatedTimestamp",
    "meta.firstEventTimestamp",
    "meta.lastEventTimestamp",
)


def filter_condition(*conditions: dict[str, Any]) -> dict[str, Any]:
    """Wrap conditions, ANDed, in the filterCondition v4 envelope Edwin requires.

    No condition gives ``{"AND": []}``, which matches every record; Edwin refuses a
    null filter.
    """
    return {
        "schemaName": "filterCondition",
        "schemaVersion": "4",
        "expression": {"AND": list(conditions)},
    }


def _operand(field: str, type_: str) -> dict[str, str]:
    return {"type": type_, "field": field}


def equals(field: str, value: Any, type_: str = "string") -> dict[str, Any]:
    """An EQUALS condition; numeric fields take type ``long``."""
    return {"EQUALS": [_operand(field, type_), value]}


def in_(field: str, values: Iterable[Any], type_: str = "string") -> dict[str, Any]:
    """An IN condition over a list of values; numeric fields take type ``long``."""
    return {"IN": [_operand(field, type_), list(values)]}


def list_contains(field: str, value: str) -> dict[str, Any]:
    """A LIST_CONTAINS condition, the one that matches inside a list field such as
    ``ml.impactedCIList`` (CONTAINS is refused there)."""
    return {"LIST_CONTAINS": [_operand(field, "string"), value]}


def within(field: str, duration: int, unit: str) -> dict[str, Any]:
    """A WITHIN condition on an epoch-millisecond field: the last ``duration`` units."""
    return {"WITHIN": [_operand(field, "long"), {"duration": duration, "unit": unit}]}


def _with_iso_times(row: dict[str, Any]) -> dict[str, Any]:
    """Add the ISO 8601 twin of each epoch-millisecond field the row carries."""
    out = dict(row)
    for field in _TIMESTAMP_FIELDS:
        value = row.get(field)
        if isinstance(value, int):
            out[f"{field}_iso"] = datetime.fromtimestamp(value / 1000, UTC).isoformat(
                timespec="milliseconds"
            )
    return out


def _project_insight(row: dict[str, Any]) -> dict[str, Any]:
    """Keep the list fields of one insight, verbatim, with the timestamps and their ISO twins."""
    kept = {key: row[key] for key in (*_INSIGHT_FIELDS, *_TIMESTAMP_FIELDS) if key in row}
    return _with_iso_times(kept)


def _check_range(hours: int, limit: int | None = None, most: int = 0) -> list[TextContent] | None:
    """The refusal for an hours or limit argument out of range, or None when each is in it."""
    if hours < 1:
        return validation_error("INVALID_REQUEST", f"hours must be at least 1, got {hours}")
    if limit is not None and not 1 <= limit <= most:
        return validation_error("INVALID_REQUEST", f"limit must be 1 to {most}, got {limit}")
    return None


async def get_edwin_insights(
    client: EdwinClient,
    hours: int = 24,
    state: str | None = None,
    severity: list[int] | None = None,
    causal_ci: str | None = None,
    impacted_ci: str | None = None,
    limit: int = 10,
) -> list[TextContent]:
    """List Edwin AI insights (correlated incidents) created in the last ``hours``, newest first.

    Args:
        client: Edwin AI client.
        hours: Window in hours back from now, on the insight's creation time.
        state: Insight state to match exactly; ``active`` and ``cleared`` are observed.
        severity: Edwin severity numbers (``ml.insightSeverity``) to match any of.
        causal_ci: CI Edwin named as the cause, matched exactly.
        impacted_ci: CI that must be in the insight's impacted list.
        limit: Most insights to return, 1 to 50.

    Returns:
        ``insights`` with Edwin's fields verbatim, ``count``, ``total`` (Edwin's count
        of matches) and ``has_more``.
    """
    refusal = _check_range(hours, limit, _MAX_INSIGHTS)
    if refusal is not None:
        return refusal
    conditions = [within("meta.createdTimestamp", hours, "hour")]
    if state:
        conditions.append(equals("meta.state", state))
    if severity:
        conditions.append(in_("ml.insightSeverity", severity, "long"))
    if causal_ci:
        conditions.append(equals("ml.causalCI", causal_ci))
    if impacted_ci:
        conditions.append(list_contains("ml.impactedCIList", impacted_ci))
    try:
        result = await client.post(
            "/ui/query/records",
            json_body={
                "source": "insights",
                "env": {"timezone": "UTC"},
                "filter": filter_condition(*conditions),
                "columns": None,
                "groups": None,
                "order": [{"field": "meta.createdTimestamp", "type": "desc", "size": None}],
                "size": limit,
            },
        )
        insights = [_project_insight(row) for row in result.get("results", [])]
        total = result.get("meta", {}).get("count", len(insights))
        return format_response(
            {
                "insights": insights,
                "count": len(insights),
                "total": total,
                "has_more": total > len(insights),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_edwin_insight(client: EdwinClient, insight_id: str) -> list[TextContent]:
    """Read one Edwin AI insight by its ``_id``, every field Edwin holds for it.

    Args:
        client: Edwin AI client.
        insight_id: The insight's ``_id`` from get_edwin_insights.

    Returns:
        The insight record verbatim, each epoch-millisecond timestamp with an ISO twin.
    """
    try:
        result = await client.get(f"/ui/query/record/insights/{quote(insight_id, safe='')}")
        return format_response(_with_iso_times(result["results"][0]))
    except Exception as e:
        return handle_error(e)


async def get_edwin_records(
    client: EdwinClient,
    source: str,
    hours: int = 24,
    filter: dict[str, Any] | None = None,
    columns: list[str] | None = None,
    order: list[dict[str, Any]] | None = None,
    limit: int = 10,
) -> list[TextContent]:
    """List Edwin AI's alert or event records from the last ``hours``, newest first by default.

    Args:
        client: Edwin AI client.
        source: ``alerts`` or ``events``.
        hours: Window in hours back from now, on ``meta.createdTimestamp`` for alerts and
            ``meta.eventTimestamp`` for events.
        filter: One filterCondition condition, such as
            ``{"EQUALS": [{"type": "string", "field": "cf.eventCI"}, "web01"]}``, ANDed
            with the window.
        columns: Fields to return beside ``_id``. Without it every field is returned
            except the ``extra.*`` and ``raw.*`` ones.
        order: Edwin order entries, ``[{"field", "type": "asc"|"desc", "size": null}]``.
        limit: Most records to return, 1 to 50.

    Returns:
        ``source``, ``records``, ``count``, ``total`` (Edwin's count of matches) and
        ``has_more``, plus a ``note`` when fields were left out.
    """
    if source == "insights":
        return validation_error(
            "INVALID_REQUEST", "Insights are read with get_edwin_insights, not get_edwin_records"
        )
    if source not in _TIME_FIELDS:
        return validation_error(
            "INVALID_REQUEST", f"source must be alerts or events, got {source!r}"
        )
    refusal = _check_range(hours, limit, _MAX_RECORDS)
    if refusal is not None:
        return refusal
    time_field = _TIME_FIELDS[source]
    conditions = [within(time_field, hours, "hour")]
    if filter:
        conditions.append(filter)
    try:
        result = await client.post(
            "/ui/query/records",
            json_body={
                "source": source,
                "env": {"timezone": "UTC"},
                "filter": filter_condition(*conditions),
                "columns": None,
                "groups": None,
                "order": order or [{"field": time_field, "type": "desc", "size": None}],
                "size": limit,
            },
        )
        rows = result.get("results", [])
        if columns:
            wanted = {"_id", *columns}
            records = [{k: v for k, v in row.items() if k in wanted} for row in rows]
        else:
            records = [
                {k: v for k, v in row.items() if not k.startswith(_BULK_PREFIXES)} for row in rows
            ]
        total = result.get("meta", {}).get("count", len(records))
        response: dict[str, Any] = {
            "source": source,
            "records": records,
            "count": len(records),
            "total": total,
            "has_more": total > len(records),
        }
        if not columns:
            response["note"] = (
                "extra.* fields (the CI's LogicMonitor properties) and raw.* fields are "
                "left out; name them in columns to get them, and list them with "
                "get_edwin_metadata."
            )
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_edwin_alert_volume(
    client: EdwinClient, hours: int = 24, group_by: str = "hour"
) -> list[TextContent]:
    """Count the alerts Edwin AI received in the last ``hours``, by hour or by alert state.

    Args:
        client: Edwin AI client.
        hours: Window in hours back from now.
        group_by: ``hour`` (buckets keyed by epoch milliseconds) or ``state``.

    Returns:
        ``buckets`` as ``[key, count]`` pairs, ``total`` (alerts in the window),
        ``bucketed`` (alerts the buckets hold) and ``unreadable`` for a bucket that
        could not be read.
    """
    if group_by not in _VOLUME_GROUPS:
        return validation_error(
            "INVALID_REQUEST", f"group_by must be hour or state, got {group_by!r}"
        )
    refusal = _check_range(hours)
    if refusal is not None:
        return refusal
    try:
        result = await client.post(
            "/ui/query/metrics",
            json_body={
                "source": "alerts",
                "env": {"timezone": "UTC"},
                "filter": filter_condition(within("meta.createdTimestamp", hours, "hour")),
                "columns": [{"field": "meta.rowKey", "type": "COUNT"}],
                "groups": [_VOLUME_GROUPS[group_by]],
                "order": None,
            },
        )
        buckets: list[list[Any]] = []
        unreadable: list[Any] = []
        for bucket in result.get("results", []):
            try:
                key, (count,) = bucket
                buckets.append([key, int(count)])
            except (TypeError, ValueError):
                logger.warning("Edwin alert-volume bucket unreadable: %r", bucket, exc_info=True)
                unreadable.append(bucket)
        response: dict[str, Any] = {
            "group_by": group_by,
            "hours": hours,
            "total": result.get("meta", {}).get("count"),
            "bucketed": sum(count for _, count in buckets),
            "buckets": buckets,
        }
        if unreadable:
            response["unreadable"] = unreadable
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_edwin_metadata(
    client: EdwinClient, record_type: str | None = None, prefix: str | None = None
) -> list[TextContent]:
    """List Edwin AI's record types, or the fields of one, from its data model.

    Args:
        client: Edwin AI client.
        record_type: Record type to describe, such as ``alerts``; omit to list the types.
        prefix: Only fields whose name starts with it, such as ``extra.`` or ``cf.``.

    Returns:
        Without a type: ``record_types`` with each type's ``queryable`` flag and field
        count. With one: its ``attributes`` and ``fields`` as Edwin describes them; the
        ``extra.*`` fields are counted, not listed, unless a prefix is given.
    """
    try:
        records = (await client.get("/metadata")).get("records", [])
        if record_type is None:
            types = [
                {
                    "recordType": r["recordType"],
                    "queryable": bool(r.get("attributes", {}).get("queryable")),
                    "fields": len(r.get("fields", [])),
                }
                for r in records
            ]
            return format_response({"record_types": types, "count": len(types)})
        match = next((r for r in records if r.get("recordType") == record_type), None)
        if match is None:
            return validation_error(
                "INVALID_REQUEST",
                f"Edwin has no record type {record_type!r}",
                "Call get_edwin_metadata without record_type to list them.",
            )
        fields = match.get("fields", [])
        response: dict[str, Any] = {
            "recordType": record_type,
            "attributes": match.get("attributes", {}),
        }
        if prefix:
            response["fields"] = [f for f in fields if f.get("name", "").startswith(prefix)]
        else:
            response["fields"] = [f for f in fields if not f.get("name", "").startswith("extra.")]
            response["extra_fields"] = len(fields) - len(response["fields"])
            response["note"] = (
                "extra.* fields mirror the CI's LogicMonitor properties; pass "
                "prefix='extra.' to list them."
            )
        response["count"] = len(response["fields"])
        return format_response(response)
    except Exception as e:
        return handle_error(e)
