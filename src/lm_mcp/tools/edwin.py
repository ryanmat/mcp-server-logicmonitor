# Description: Edwin AI tools: insights, records, alert volume, metadata, agent tools, Ask Edwin.
# Description: Reads Edwin's investigations so the calling model can weigh them beside raw LM data.

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from mcp.types import TextContent
from websockets.exceptions import ConnectionClosedError

from lm_mcp.client.edwin import CREDENTIAL_HINT
from lm_mcp.exceptions import AuthenticationError
from lm_mcp.tools import (
    format_response,
    handle_error,
    require_write_permission,
    validation_error,
)

if TYPE_CHECKING:
    from lm_mcp.client.edwin import EdwinClient

logger = logging.getLogger(__name__)

_MAX_INSIGHTS = 50

# Most characters of rows one list result carries. Claude Code returns no tool result over
# 50,000 characters, and the rest of the result needs room beside the rows.
ROW_BUDGET = 40_000
# What a records page says, after its warning, about fitting more rows into the budget.
_COLUMNS_HINT = ", or name the fields you need in columns so more rows fit"

# Longest ask_edwin waits for Edwin's response_end before returning what it has.
ASK_BUDGET_SECONDS = 120.0
# The LMDiagnosticsAgent route Ask Edwin answers on.
_ASK_ROUTE = "/ws/lm"
# The close code Edwin sends when it refuses the token on the websocket.
_POLICY_VIOLATION = 1008
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


def _offset_field(offset: int) -> dict[str, int]:
    """The request's offset entry: Edwin skips ``offset`` rows, and none without the key."""
    return {"offset": offset} if offset else {}


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


def _check_range(
    hours: int, limit: int | None = None, most: int = 0, offset: int = 0
) -> list[TextContent] | None:
    """The refusal for an hours, limit or offset argument out of range, or None when each is
    in it."""
    if hours < 1:
        return validation_error("INVALID_REQUEST", f"hours must be at least 1, got {hours}")
    if limit is not None and not 1 <= limit <= most:
        return validation_error("INVALID_REQUEST", f"limit must be 1 to {most}, got {limit}")
    if offset < 0:
        return validation_error("INVALID_REQUEST", f"offset must be 0 or more, got {offset}")
    return None


def _page(
    key: str, rows: list[dict[str, Any]], total: int, offset: int, hint: str = ""
) -> dict[str, Any]:
    """The page fields of a list result, with the rows under ``key``.

    Rows are kept whole, in order, while their compact JSON fits ROW_BUDGET; the first
    row is kept whatever its size. ``has_more`` is true when the budget left out rows
    this call read or Edwin counts rows past the ones kept, ``next_offset`` is then the
    offset that reads them, and a ``warning`` says how many rows fit when the budget
    left some out.
    """
    kept: list[dict[str, Any]] = []
    used = 0
    for row in rows:
        used += len(json.dumps(row, separators=(",", ":"), default=str))
        if kept and used > ROW_BUDGET:
            break
        kept.append(row)
    next_offset = offset + len(kept)
    cut = len(kept) < len(rows)
    page: dict[str, Any] = {
        key: kept,
        "count": len(kept),
        "total": total,
        "has_more": cut or total > next_offset,
    }
    if page["has_more"]:
        page["next_offset"] = next_offset
    if cut:
        page["warning"] = (
            f"{len(kept)} of the {len(rows)} rows read fit this result's "
            f"{ROW_BUDGET}-character row budget; call again with offset={next_offset} "
            f"for the rest{hint}."
        )
    return page


async def get_edwin_insights(
    client: EdwinClient,
    hours: int = 24,
    state: str | None = None,
    severity: list[int] | None = None,
    causal_ci: str | None = None,
    impacted_ci: str | None = None,
    limit: int = 10,
    offset: int = 0,
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
        offset: Insights to skip, for the page after an earlier call's.

    Returns:
        ``insights`` with Edwin's fields verbatim, as many whole rows as fit ROW_BUDGET,
        ``count``, ``total`` (Edwin's count of matches), ``has_more``, ``next_offset``
        while rows remain, and a ``warning`` when the budget left out rows.
    """
    refusal = _check_range(hours, limit, _MAX_INSIGHTS, offset)
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
                **_offset_field(offset),
            },
        )
        insights = [_project_insight(row) for row in result.get("results", [])]
        total = result.get("meta", {}).get("count", offset + len(insights))
        return format_response(_page("insights", insights, total, offset))
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
    offset: int = 0,
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
        offset: Records to skip, for the page after an earlier call's.

    Returns:
        ``source``, ``records`` (as many whole rows as fit ROW_BUDGET), ``count``,
        ``total`` (Edwin's count of matches), ``has_more``, ``next_offset`` while rows
        remain, a ``warning`` when the budget left out rows, and a ``note`` when fields
        were left out.
    """
    if source == "insights":
        return validation_error(
            "INVALID_REQUEST", "Insights are read with get_edwin_insights, not get_edwin_records"
        )
    if source not in _TIME_FIELDS:
        return validation_error(
            "INVALID_REQUEST", f"source must be alerts or events, got {source!r}"
        )
    refusal = _check_range(hours, limit, _MAX_RECORDS, offset)
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
                **_offset_field(offset),
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
        total = result.get("meta", {}).get("count", offset + len(records))
        response: dict[str, Any] = {
            "source": source,
            **_page("records", records, total, offset, _COLUMNS_HINT),
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


# The fields of an agent and of a tool that get_edwin_tools returns; the agent's route,
# the MCP endpoint (an address inside Edwin) and the timestamps are left out.
_AGENT_FIELDS = ("name", "display_name", "customer_facing_description", "is_active")
_TOOL_FIELDS = ("name", "display_name", "short_description")


async def get_edwin_tools(client: EdwinClient, agent: str | None = None) -> list[TextContent]:
    """List Edwin AI's agents, or one agent's MCP servers and the active tools on each.

    Args:
        client: Edwin AI client.
        agent: Agent name, such as ``LMDiagnosticsAgent``; omit to list the agents.

    Returns:
        Without an agent: ``agents`` with name, display name, description and
        ``is_active``. With one: ``mcps``, each with ``mcp_name``, ``display_name``,
        ``is_enabled`` and its ``tools``, plus ``tool_count``. The ``mcp_name`` and tool
        ``name`` pairs are what edwin_run_tool takes.
    """
    try:
        if agent is None:
            result = await client.get("/api/agents", params={"active_only": "false"})
            agents = [
                {key: row.get(key) for key in _AGENT_FIELDS} for row in result.get("agents", [])
            ]
            return format_response({"agents": agents, "count": len(agents)})
        name = quote(agent, safe="")
        listed = await client.get(f"/api/org/agents/{name}/mcps")
        mcps = []
        for mcp in listed.get("mcps", []):
            tools = await client.get(
                f"/api/mcp-servers/{quote(mcp['mcp_name'], safe='')}/tools",
                params={"active_only": "true", "agent_name": agent},
            )
            mcps.append(
                {
                    "mcp_name": mcp["mcp_name"],
                    "display_name": mcp.get("display_name"),
                    "is_enabled": mcp.get("is_enabled"),
                    "tools": [
                        {key: tool.get(key) for key in _TOOL_FIELDS}
                        for tool in tools.get("tools", [])
                    ],
                }
            )
        return format_response(
            {
                "agent": agent,
                "mcps": mcps,
                "tool_count": sum(len(mcp["tools"]) for mcp in mcps),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def edwin_run_tool(
    client: EdwinClient, mcp_name: str, tool_name: str, parameters: dict[str, Any]
) -> list[TextContent]:
    """Run one tool of one of Edwin AI's MCP servers, with the parameters passed unchanged.

    Args:
        client: Edwin AI client.
        mcp_name: Edwin MCP server, from get_edwin_tools.
        tool_name: Tool on that server, from get_edwin_tools.
        parameters: The tool's arguments, sent to Edwin as given.

    Returns:
        ``mcp_name``, ``tool_name`` and the tool's ``content`` as Edwin returns it;
        ``REJECTED_BY_TOOL`` with Edwin's error when the tool reports failure.
    """
    try:
        result = await client.post(
            "/api/run-tool",
            json_body={"mcp_name": mcp_name, "tool_name": tool_name, "parameters": parameters},
        )
        if not result.get("success"):
            return format_response(
                {
                    "error": True,
                    "code": "REJECTED_BY_TOOL",
                    "message": f"Edwin AI tool {mcp_name}/{tool_name} reported failure: "
                    f"{result.get('error')}",
                    "details": {"edwin_error": result.get("error")},
                }
            )
        return format_response(
            {"mcp_name": mcp_name, "tool_name": tool_name, "content": result.get("content")}
        )
    except Exception as e:
        return handle_error(e)


async def ask_edwin(
    client: EdwinClient, question: str, conversation_id: str | None = None
) -> list[TextContent]:
    """Ask Edwin AI a question in an Ask Edwin conversation and wait for its answer.

    Args:
        client: Edwin AI client.
        question: The question, in plain words.
        conversation_id: A conversation to continue; omit to start one.

    Returns:
        ``answer`` (Edwin's final text), ``reasoning`` (its tool-call narration and
        interim text), ``conversation_id``, ``langfuseTraceId`` and ``truncated``, true
        when the answer stopped before Edwin's end frame (an early close or the
        ``ASK_BUDGET_SECONDS`` budget); ``unreadable`` lists frames that could not be read.
    """
    try:
        if conversation_id is None:
            created = await client.post("/api/conversations", json_body={})
            conversation_id = str(created["conversationId"])
        answer: list[str] = []
        reasoning: list[str] = []
        unreadable: list[Any] = []
        trace_id = None
        truncated = True
        async with client.websocket(_ASK_ROUTE) as ws:
            await ws.send(json.dumps({"conversationId": conversation_id, "message": question}))
            try:
                async with asyncio.timeout(ASK_BUDGET_SECONDS):
                    async for raw in ws:
                        try:
                            frame = json.loads(raw)
                            kind = frame["type"]
                        except (ValueError, TypeError, KeyError):
                            logger.warning("Edwin frame unreadable: %r", raw, exc_info=True)
                            unreadable.append(raw)
                            continue
                        trace_id = frame.get("langfuseTraceId") or trace_id
                        if kind == "response_end":
                            truncated = False
                            break
                        if kind == "answer_token":
                            answer.append(frame.get("message") or "")
                        elif kind == "answer_thought":
                            reasoning.append(frame.get("message") or "")
                    else:
                        logger.warning(
                            "Edwin closed the conversation with %s before response_end",
                            ws.close_code,
                        )
            except TimeoutError:
                logger.warning(
                    "ask_edwin stopped at its %s s budget", ASK_BUDGET_SECONDS, exc_info=True
                )
            except ConnectionClosedError as e:
                code = e.rcvd.code if e.rcvd is not None else None
                if code == _POLICY_VIOLATION:
                    raise AuthenticationError(
                        f"Edwin AI closed the conversation with {code} (policy violation): "
                        "it refused the token",
                        suggestion=CREDENTIAL_HINT,
                    ) from e
                logger.warning("Edwin closed the conversation early: %s", e, exc_info=True)
        result: dict[str, Any] = {
            "answer": "".join(answer),
            "reasoning": "".join(reasoning),
            "conversation_id": conversation_id,
            "langfuseTraceId": trace_id,
            "truncated": truncated,
        }
        if unreadable:
            result["unreadable"] = unreadable
        return format_response(result)
    except Exception as e:
        return handle_error(e)
