# Description: Edwin AI query tools: insights, one insight, and the filterCondition builder.
# Description: Reads Edwin's investigations so the calling model can weigh them beside raw LM data.

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, validation_error

if TYPE_CHECKING:
    from lm_mcp.client.edwin import EdwinClient

_MAX_INSIGHTS = 50

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
    if hours < 1:
        return validation_error("INVALID_REQUEST", f"hours must be at least 1, got {hours}")
    if not 1 <= limit <= _MAX_INSIGHTS:
        return validation_error(
            "INVALID_REQUEST", f"limit must be 1 to {_MAX_INSIGHTS}, got {limit}"
        )
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
