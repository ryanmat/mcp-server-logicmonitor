# Description: Audit log tools for LogicMonitor MCP server.
# Description: Reads /setting/accesslogs with the filters it honors: all entries or the changes.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    list_tool,
    quote_filter_value,
    sanitize_filter_value,
    validation_error,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# How /setting/accesslogs filters behave, verified against live portals (PR #63):
#   - happenedOn is the epoch-seconds timestamp; happenedOn>:a,happenedOn<:b is honoured as a
#     range. happenedOnLocal is a display string: a filter on it is silently ignored.
#   - username:"a"|"b" is an exact-match OR list. Negation is NOT supported: username!~ returns
#     nothing and username!: behaves like username:, both with HTTP 200. username~ (contains)
#     returns nothing, and a second username clause is ignored.
#   - description~"text" is a contains match. It does not take an OR list, and only one
#     description~ clause is applied.
#   - A filter longer than roughly 1,000 characters returns HTTP 500.
#   - offset + size above 10,000 returns HTTP 413 ("the query limitation of auditLog is 10000").
#   - total is negative when more rows exist (-N reads "at least N"). Rows come newest first.
#   - sessionId is null in practice.
ACCESSLOGS = "/setting/accesslogs"
OFFSET_CEILING = 10000
FILTER_CHAR_LIMIT = 900

# The kinds get_audit_logs reads.
KINDS = ("all", "change")

# System and automation actors. They are most of the feed on busy portals (Active Discovery,
# dynamic group membership, AppliesTo, NetScan, cloud auto-delete, ...). The API cannot exclude
# them server-side, so they are dropped after the fetch. The match is case-sensitive and a
# System actor name holds no "@" or space, so a real user such as system.admin@example.com or
# System.Admin@example.com is not mistaken for one.
SYSTEM_ACTOR = re.compile(
    r"^(System(?::{1,2}|\.)[^@\s]+|LogicMonitor Internal|auto-user-suspend"
    r"|(AZURE|AWS|GCP) auto-delete)$"
)

CHANGE_TYPES = ("create", "update", "delete", "import")

_KV_ACTION = re.compile(r'"Action=([A-Za-z]+)', re.IGNORECASE)
_LEADING_VERB = re.compile(
    r"^\s*(?:\{[^}]*\}\s*)?(add(?:ed)?|creat(?:e|ed)|clon(?:e|ed)|updat(?:e|ed)|edit(?:ed)?|"
    r"chang(?:e|ed)|modif(?:y|ied)|renam(?:e|ed)|delet(?:e|ed)|remov(?:e|ed)|import(?:ed)?|"
    r"enabl(?:e|ed)|disabl(?:e|ed))\b",
    re.IGNORECASE,
)
_NOT_A_CHANGE = re.compile(
    r"signs in via|log in\. 2FA|logged in through|could not log into|signs out|"
    r"^Note \(|API request:|Session timed out|2FA Request",
    re.IGNORECASE,
)

_USERNAME_NOTE = (
    "Wildcard characters were stripped from username; usernames match exactly, so pass "
    "whole names, comma-separated for several."
)


class AuditQueryLimitError(Exception):
    """A request refused before sending: past the offset or the filter-length ceiling."""


def change_type_of(description: str) -> str | None:
    """Classify an audit description as create, update, delete or import; None if no change.

    The verb is read from "Action=..." or the description's leading verb; the API has no
    field for it. Sign-ins, notes, API requests and 2FA requests change nothing, and so do
    Export, Login, Fetch, Acknowledge, Schedule and the like.
    """
    if _NOT_A_CHANGE.search(description):
        return None
    m = _KV_ACTION.search(description) or _LEADING_VERB.search(description)
    if not m:
        return None
    verb = m.group(1).lower()
    if verb.startswith(("add", "creat", "clon")):
        return "create"
    if verb.startswith(("delet", "remov")):
        return "delete"
    if verb.startswith("import"):
        return "import"
    if verb.startswith(("updat", "edit", "chang", "modif", "renam", "enabl", "disabl")):
        return "update"
    return None


def is_change_action(description: str) -> bool:
    """Whether an audit entry's description names a change, by change_type_of."""
    return change_type_of(description) is not None


def _time_clauses(start_time: int | None, end_time: int | None) -> list[str]:
    filters = []
    if start_time:
        filters.append(f"happenedOn>:{int(start_time)}")
    if end_time:
        filters.append(f"happenedOn<:{int(end_time)}")
    return filters


def _username_clause(username: str) -> tuple[str, bool]:
    """Build username:"a"|"b" from one name or a comma-separated list (exact match)."""
    names, stripped = [], False
    for part in username.split(","):
        clean, modified = sanitize_filter_value(part.strip())
        stripped = stripped or modified
        if clean:
            names.append(quote_filter_value(clean))
    return ("username:" + "|".join(names) if names else ""), stripped


def _row(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "username": item.get("username"),
        "ip_address": item.get("ip"),
        "happened_on": item.get("happenedOn"),
        "timestamp": item.get("happenedOnLocal"),
        "description": item.get("description"),
        "session_id": item.get("sessionId"),
    }


def _contains(item: dict, text: str) -> bool:
    return text.lower() in str(item.get("description") or "").lower()


def _within_ceilings(filters: list[str], size: int, offset: int) -> str:
    """Join the filter clauses, refusing a request the API would answer with 413 or 500."""
    if offset + size > OFFSET_CEILING:
        raise AuditQueryLimitError(
            f"offset + limit must stay within {OFFSET_CEILING} for audit logs "
            "(LogicMonitor returns HTTP 413 beyond it). Narrow the window with "
            "start_time/end_time and page within it instead."
        )
    flt = ",".join(f for f in filters if f)
    if len(flt) > FILTER_CHAR_LIMIT:
        raise AuditQueryLimitError(
            f"filter is {len(flt)} characters; LogicMonitor returns HTTP 500 above about 1,000. "
            "Pass fewer usernames per call."
        )
    return flt


async def _query(
    client: LogicMonitorClient, flt: str, size: int, offset: int
) -> tuple[list[dict], dict]:
    """Read one page of audit rows; a missing or non-integer total is read from the page."""
    params: dict = {"size": size, "offset": offset}
    if flt:
        params["filter"] = flt
    result = await client.get(ACCESSLOGS, params=params)
    items = result.get("items") or []
    total = result.get("total")
    if isinstance(total, bool) or not isinstance(total, int):
        # Read a missing or non-integer total the way the API writes "more exist": a
        # negative lower bound when the page came back full, the exact count otherwise.
        seen = offset + len(items)
        result = {**result, "total": -(seen + 1) if len(items) >= size else seen}
    return items, result


async def _change_logs(
    client: LogicMonitorClient,
    filters: list[str],
    want: str | None,
    drop_system: bool,
    limit: int,
    offset: int,
    notes: list[str],
) -> list[TextContent]:
    """Scan a pool of the newest rows for changes, stopping at limit."""
    # Changes are a small share of the feed, so read a larger pool than requested, as far as
    # the offset ceiling leaves room; only offset + limit past it is refused.
    pool = min(1000, max(limit * 10, 200), max(OFFSET_CEILING - offset, 0))
    flt = _within_ceilings(filters, max(pool, limit), offset)
    items, result = await _query(client, flt, pool, offset)

    logs: list[dict[str, Any]] = []
    scanned = 0
    for item in items:
        if len(logs) >= limit:
            break
        scanned += 1
        if drop_system and SYSTEM_ACTOR.match(str(item.get("username") or "")):
            continue
        ct = change_type_of(str(item.get("description") or ""))
        if not ct or (want and ct != want):
            continue
        logs.append({**_row(item), "change_type": ct})

    # Rows the API holds past this pool (a negative or larger total) were never read.
    older_rows = abs(result["total"]) > offset + len(items)
    has_more = scanned < len(items) or older_rows
    if has_more:
        notes.insert(
            0,
            f"Scanned {scanned} of the newest {len(items)} audit rows from offset {offset}; "
            "more changes may exist. To reach them, narrow start_time/end_time or add "
            "resource_type or username.",
        )
    response: dict[str, Any] = {
        "kind": "change",
        "count": len(logs),
        "scanned": scanned,
        "has_more": has_more,
        "filter": flt or None,
        "change_logs": logs,
    }
    if notes:
        response["note"] = " ".join(notes)
    return format_response(response)


async def get_audit_logs(
    client: LogicMonitorClient,
    kind: str = "all",
    username: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    change_type: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    exclude_system: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Read the portal audit log: every entry, or the configuration changes.

    Args:
        client: LogicMonitor API client.
        kind: "all" for every entry, one page through list_tool; "change" for the
            create, update, delete and import entries in a pool of the newest rows.
        username: Exact username, or a comma-separated list (matched as an OR).
        action: Text the description must contain, e.g. "Action=Delete", "signs in".
        resource_type: Text the description must contain, e.g. "dashboard", "Type=Device";
            with action as well, it is matched after the fetch.
        change_type: With kind "change": create, update, delete or import.
        start_time: Only entries at or after this epoch second (happenedOn).
        end_time: Only entries at or before this epoch second (happenedOn).
        exclude_system: Drop System:* and automation actors after the fetch (default
            True). Never applied when a username is given.
        limit: Rows to request for kind "all"; changes to return for kind "change".
        offset: Rows to skip; offset plus the rows read must stay within 10,000.

    Returns:
        List of TextContent with the audit rows or error.
    """
    try:
        if kind not in KINDS:
            return validation_error(
                "INVALID_REQUEST",
                f"kind must be one of {', '.join(KINDS)}; got {kind!r}.",
            )
        if change_type is not None and kind != "change":
            return validation_error(
                "INVALID_REQUEST",
                'change_type applies to kind="change" only.',
                'Pass kind="change" with it, or leave it out.',
            )

        filters: list[str] = []
        notes: list[str] = []
        wildcards_stripped = False
        user_clause = ""
        if username is not None:
            user_clause, username_stripped = _username_clause(username)
            if not user_clause:
                return validation_error(
                    "INVALID_REQUEST",
                    f"username {username!r} names nobody once wildcards are stripped.",
                    "Pass whole usernames, comma-separated for several, or leave it out.",
                )
            if username_stripped:
                notes.append(_USERNAME_NOTE)
            filters.append(user_clause)

        texts = []
        for value in (action, resource_type):
            if value:
                clean, modified = sanitize_filter_value(value)
                wildcards_stripped = wildcards_stripped or modified
                if clean:
                    texts.append(clean)
        # Only one description~ clause is applied server-side; any second one runs here.
        if texts:
            filters.append(f"description~{quote_filter_value(texts[0])}")
        filters.extend(_time_clauses(start_time, end_time))

        # A named user is queried as asked, system actor or not.
        drop_system = exclude_system and not user_clause

        if kind == "change":
            want = None
            if change_type is not None:
                clean, modified = sanitize_filter_value(change_type)
                wildcards_stripped = wildcards_stripped or modified
                want = (clean or "").strip().lower() or None
                if want not in CHANGE_TYPES:
                    # An unknown type would match nothing and read as "no changes".
                    return validation_error(
                        "INVALID_REQUEST",
                        f"change_type must be one of {', '.join(CHANGE_TYPES)}; "
                        f"got {change_type!r}.",
                    )
            if wildcards_stripped:
                notes.append(WILDCARD_STRIP_NOTE)
            return await _change_logs(client, filters, want, drop_system, limit, offset, notes)

        flt = _within_ceilings(filters, limit, offset)
        second = texts[1] if len(texts) > 1 else None
        if second:
            notes.append(
                f"'{second}' was matched after the fetch (one description filter per call)."
            )
        if wildcards_stripped:
            notes.append(WILDCARD_STRIP_NOTE)

        def keep(item: dict) -> bool:
            if second and not _contains(item, second):
                return False
            return not (drop_system and SYSTEM_ACTOR.match(str(item.get("username") or "")))

        extra: dict[str, Any] = {"kind": "all", "filter": flt or None}
        if notes:
            extra["note"] = " ".join(notes)
        return await list_tool(
            client,
            ACCESSLOGS,
            key="audit_logs",
            project=_row,
            limit=limit,
            offset=offset,
            filter=flt or None,
            extra=extra,
            keep=keep,
        )
    except AuditQueryLimitError as e:
        return validation_error("INVALID_REQUEST", str(e))
    except Exception as e:
        return handle_error(e)


async def get_api_token_audit(
    client: LogicMonitorClient,
    token_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get API token usage audit logs.

    Args:
        client: LogicMonitor API client.
        token_id: Filter by specific API token ID.
        limit: Maximum number of logs to return.

    Returns:
        List of TextContent with API token audit data or error.
    """
    try:
        params: dict = {"size": limit}

        if token_id:
            params["filter"] = f"apiTokenId:{token_id}"

        result = await client.get("/setting/accesslogs", params=params)

        # Filter to API token related entries
        logs = []
        for item in result.get("items", []):
            desc = item.get("description", "").lower()
            if "api" in desc or "token" in desc or item.get("username", "").startswith("api."):
                logs.append(
                    {
                        "id": item.get("id"),
                        "username": item.get("username"),
                        "ip_address": item.get("ip"),
                        "action": item.get("happenedOn"),
                        "description": item.get("description"),
                        "timestamp": item.get("happenedOnLocal"),
                    }
                )

        return format_response(
            {
                "total": len(logs),
                "count": len(logs),
                "api_token_logs": logs,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_login_audit(
    client: LogicMonitorClient,
    username: str | None = None,
    success_only: bool = False,
    failed_only: bool = False,
    limit: int = 50,
) -> list[TextContent]:
    """Get login/authentication audit logs.

    Args:
        client: LogicMonitor API client.
        username: Filter by specific username.
        success_only: Only show successful logins.
        failed_only: Only show failed login attempts.
        limit: Maximum number of logs to return.

    Returns:
        List of TextContent with login audit data or error.
    """
    try:
        params: dict = {"size": limit}

        wildcards_stripped = False

        filters = [f"happenedOn:{quote_filter_value('login')}"]
        if username:
            clean_username, was_modified = sanitize_filter_value(username)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f"username:{quote_filter_value(clean_username)}")

        params["filter"] = ",".join(filters)

        result = await client.get("/setting/accesslogs", params=params)

        logs = []
        for item in result.get("items", []):
            desc = item.get("description", "").lower()
            is_success = "success" in desc or "logged in" in desc
            is_failed = "fail" in desc or "invalid" in desc

            if success_only and not is_success:
                continue
            if failed_only and not is_failed:
                continue

            logs.append(
                {
                    "id": item.get("id"),
                    "username": item.get("username"),
                    "ip_address": item.get("ip"),
                    "status": "success" if is_success else "failed" if is_failed else "unknown",
                    "description": item.get("description"),
                    "timestamp": item.get("happenedOnLocal"),
                }
            )

        response = {
            "total": len(logs),
            "count": len(logs),
            "login_logs": logs,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_change_audit(
    client: LogicMonitorClient,
    resource_type: str | None = None,
    change_type: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get configuration change audit logs.

    Args:
        client: LogicMonitor API client.
        resource_type: Filter by resource type (device, dashboard, user, etc.).
        change_type: Filter by change type (create, update, delete).
        limit: Maximum number of logs to return.

    Returns:
        List of TextContent with change audit data or error.
    """
    try:
        params: dict = {"size": limit}
        wildcards_stripped = False

        filters = []
        if change_type:
            clean_type, was_modified = sanitize_filter_value(change_type)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f"happenedOn:{quote_filter_value(clean_type)}")
        if resource_type:
            clean_type, was_modified = sanitize_filter_value(resource_type)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f"description~{quote_filter_value(clean_type)}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/setting/accesslogs", params=params)

        logs = []
        for item in result.get("items", []):
            if is_change_action(str(item.get("description", ""))):
                logs.append(
                    {
                        "id": item.get("id"),
                        "username": item.get("username"),
                        "action": item.get("happenedOn"),
                        "description": item.get("description"),
                        "timestamp": item.get("happenedOnLocal"),
                        "ip_address": item.get("ip"),
                    }
                )

        response = {
            "total": len(logs),
            "count": len(logs),
            "change_logs": logs,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)
