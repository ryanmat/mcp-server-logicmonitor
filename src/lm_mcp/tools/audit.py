# Description: Audit log tools for LogicMonitor MCP server.
# Description: Reads /setting/accesslogs as it filters: entries, changes, logins, API tokens.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.exceptions import NotFoundError
from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    list_tool,
    quote_filter_value,
    sanitize_filter_value,
    validation_error,
)
from lm_mcp.tools.api_tokens import find_api_token

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# How /setting/accesslogs filters behave, verified against live portals (PR #63):
#   - happenedOn is the epoch-seconds timestamp; happenedOn>:a,happenedOn<:b is honoured as a
#     range. happenedOnLocal is a display string: a filter on it is silently ignored.
#   - username:"a"|"b" is an exact-match OR list. Negation is NOT supported: username!~ returns
#     nothing and username!: behaves like username:, both with HTTP 200. username~ (contains)
#     returns nothing, and a second username clause is ignored.
#   - description~"text" matches whole words: on the sandbox (2026-11-09) "Throttled" matched
#     and "Throttl" and "hrottled" matched nothing, and the full access ID matched its token's
#     rows where its first six characters matched none. It does not take an OR list, and only
#     one description~ clause is applied.
#   - A filter longer than roughly 1,000 characters returns HTTP 500.
#   - offset + size above 10,000 returns HTTP 413 ("the query limitation of auditLog is 10000").
#   - total is negative when more rows exist (-N reads "at least N"). Rows come newest first.
#   - sessionId is null in practice.
ACCESSLOGS = "/setting/accesslogs"
OFFSET_CEILING = 10000
FILTER_CHAR_LIMIT = 900

# The kinds get_audit_logs reads.
KINDS = ("all", "change", "login", "api_token")

# The portal login wordings, each with the status its rows carry (PR #63). The API takes no
# OR on description, so each wording is one query. A monitored database's "Login failed for
# user" line, which Active Discovery writes, matches none of them.
LOGIN_WORDINGS = (
    ("signs in via", "success"),
    ("log in. 2FA Mode", "success"),
    ("logged in through lmsupport", "success"),
    ("could not log into the system", "failed"),
    ("Session timed out for SSO", "failed"),
    ("signs out", "logout"),
)

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

_TOKEN_IN_DESC = re.compile(r"API token\s+([A-Za-z0-9_\-#*]{4,})", re.IGNORECASE)
_API_PATH = re.compile(r"path\s+'([^']*)'(?:\s+with Method:\s*([A-Z]+))?", re.IGNORECASE)

_USERNAME_NOTE = (
    "Wildcard characters were stripped from username; usernames match exactly, so pass "
    "whole names, comma-separated for several."
)
_ACCESS_ID_NOTE = (
    "Wildcard characters were stripped from access_id; access_id matches the whole access ID."
)
_LOGIN_TOTAL_NOTE = (
    "total counts the login rows read; older rows exist past them, so it is a lower bound."
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


def _login_status(desc: str) -> tuple[str, str | None]:
    """Read a login row's status and sign-in method from its wording."""
    low = desc.lower()
    if "session timed out for sso" in low:
        return "failed", "SSO"
    if "could not log into" in low:
        return "failed", ("2FA" if "two factor" in low else "password")
    if "signs out" in low:
        return "logout", None
    if "logged in through lmsupport" in low:
        return "success", "LM Support"
    m = re.search(r"signs in via\s+(\S+)", desc, re.IGNORECASE)
    if m:
        return "success", m.group(1).rstrip(".").upper()
    m = re.search(r"2FA Mode\s*:\s*(.*)$", desc, re.IGNORECASE)
    if m:
        mode = m.group(1).strip()
        return "success", "Local" + (
            f" + 2FA ({mode})" if mode and mode.lower() not in ("none", "disabled", "off") else ""
        )
    return "unknown", None


async def _login_logs(
    client: LogicMonitorClient,
    filters: list[str],
    wanted: set[str],
    limit: int,
    offset: int,
    notes: list[str],
) -> list[TextContent]:
    """Query each login wording, merge the rows newest first, and cut the page.

    Each wording is read from its newest row to offset + limit, which holds every row of
    the merged list down to that point, so offset pages the merged rows.
    """
    size = offset + limit
    merged: dict[Any, dict] = {}
    older_rows = False
    for wording, status in LOGIN_WORDINGS:
        if status not in wanted:
            continue
        flt = _within_ceilings([*filters, f"description~{quote_filter_value(wording)}"], size, 0)
        items, result = await _query(client, flt, size, 0)
        # A total past the rows read means this wording holds older rows not read.
        older_rows = older_rows or abs(result["total"]) > len(items)
        for item in items:
            merged.setdefault(item.get("id"), item)

    rows = sorted(merged.values(), key=lambda i: i.get("happenedOn") or 0, reverse=True)
    logs = []
    for item in rows[offset:size]:
        status, method = _login_status(str(item.get("description") or ""))
        logs.append({**_row(item), "status": status, "method": method})

    has_more = older_rows or len(rows) > size
    if has_more:
        notes.insert(
            0,
            f"More login rows exist past these {len(logs)}; page on with offset, or narrow "
            "start_time/end_time or username.",
        )
    response: dict[str, Any] = {
        "kind": "login",
        "total": len(rows),
        "count": len(logs),
        "offset": offset,
        "has_more": has_more,
        "login_logs": logs,
    }
    if older_rows:
        response["total_note"] = _LOGIN_TOTAL_NOTE
    if notes:
        response["note"] = " ".join(notes)
    return format_response(response)


def _token_row(item: dict) -> dict:
    """Project an API token row: what happened, the access ID, and the path it called."""
    desc = str(item.get("description") or "")
    low = desc.lower()
    if low.startswith("failed api request"):
        event = "rejected"
    elif low.startswith("throttled api request"):
        event = "throttled"
    else:
        event = "change"
    token = _TOKEN_IN_DESC.search(desc)
    path = _API_PATH.search(desc)
    return {
        **_row(item),
        "event": event,
        "access_id": token.group(1) if token else None,
        "path": path.group(1) if path else None,
        "method": path.group(2) if path else None,
    }


async def _api_token_logs(
    client: LogicMonitorClient,
    filters: list[str],
    access_id: str | None,
    token_id: int | None,
    limit: int,
    offset: int,
    notes: list[str],
) -> list[TextContent]:
    """Page through the rows naming API token <accessId>, keeping that exact id only."""
    if access_id is None and token_id is not None:
        token = await find_api_token(client, token_id)
        access_id = token.get("accessId") or None
        if not access_id:
            raise NotFoundError(f"API token {token_id} not found: the portal sent no access ID")

    needle = f"API token {access_id}" if access_id else "API token"
    flt = _within_ceilings([*filters, f"description~{quote_filter_value(needle)}"], limit, offset)
    extra: dict[str, Any] = {"kind": "api_token", "filter": flt}
    keep = None
    if access_id:
        # A row naming a longer access ID that starts with this one is another token's.
        exact = re.compile(rf"API token {re.escape(access_id)}(?![A-Za-z0-9_\-#*])")

        def keep(item: dict) -> bool:
            return bool(exact.search(str(item.get("description") or "")))

        extra["access_id"] = access_id
    if notes:
        extra["note"] = " ".join(notes)
    return await list_tool(
        client,
        ACCESSLOGS,
        key="api_token_logs",
        project=_token_row,
        limit=limit,
        offset=offset,
        filter=flt,
        extra=extra,
        keep=keep,
    )


def _kind_argument_error(
    kind: str,
    change_type: str | None,
    success_only: bool,
    failed_only: bool,
    access_id: str | None,
    token_id: int | None,
    action: str | None,
    resource_type: str | None,
) -> list[TextContent] | None:
    """Refuse an argument the requested kind does not read."""
    only = {
        "change_type": ("change", change_type is not None),
        "success_only": ("login", success_only),
        "failed_only": ("login", failed_only),
        "access_id": ("api_token", access_id is not None),
        "token_id": ("api_token", token_id is not None),
    }
    for name, (owner, given) in only.items():
        if given and kind != owner:
            return validation_error(
                "INVALID_REQUEST",
                f'{name} applies to kind="{owner}" only.',
                f'Pass kind="{owner}" with it, or leave it out.',
            )
    for name, value in (("action", action), ("resource_type", resource_type)):
        if value and kind in ("login", "api_token"):
            return validation_error(
                "INVALID_REQUEST",
                f'{name} applies to kind "all" or "change"; kind "{kind}" sends the one '
                "description filter the portal applies.",
                'Use kind="all" with it, or leave it out.',
            )
    if success_only and failed_only:
        return validation_error(
            "INVALID_REQUEST",
            "success_only and failed_only cannot both be set.",
            "Set one of them, or neither for every login event.",
        )
    return None


async def get_audit_logs(
    client: LogicMonitorClient,
    kind: str = "all",
    username: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    change_type: str | None = None,
    success_only: bool = False,
    failed_only: bool = False,
    access_id: str | None = None,
    token_id: int | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    exclude_system: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Read the portal audit log: every entry, the changes, the logins, or API token use.

    Args:
        client: LogicMonitor API client.
        kind: "all" for every entry, one page through list_tool; "change" for the
            create, update, delete and import entries in a pool of the newest rows;
            "login" for the portal sign-ins, sign-outs and failed logins, one query per
            login wording; "api_token" for the rows naming an API token.
        username: Exact username, or a comma-separated list (matched as an OR).
        action: Words the description holds, e.g. "Action=Delete"; kinds all and change.
        resource_type: Words the description holds, e.g. "Type=Device"; kinds all and
            change. With action as well, it is matched after the fetch.
        change_type: With kind "change": create, update, delete or import.
        success_only: With kind "login": successful logins only.
        failed_only: With kind "login": failed logins only.
        access_id: With kind "api_token": the token's access ID.
        token_id: With kind "api_token": the token's id, read to its access ID.
        start_time: Only entries at or after this epoch second (happenedOn).
        end_time: Only entries at or before this epoch second (happenedOn).
        exclude_system: Drop System:* and automation actors after the fetch (default
            True), for kinds all and change. Never applied when a username is given.
        limit: Rows to request; changes to return for kind "change".
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
        refused = _kind_argument_error(
            kind,
            change_type,
            success_only,
            failed_only,
            access_id,
            token_id,
            action,
            resource_type,
        )
        if refused:
            return refused

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

        if kind == "login":
            wanted = {"success"} if success_only else {"failed"} if failed_only else None
            return await _login_logs(
                client,
                filters,
                wanted or {"success", "failed", "logout"},
                limit,
                offset,
                notes,
            )
        if kind == "api_token":
            if access_id is not None:
                clean_id, id_stripped = sanitize_filter_value(access_id)
                if not clean_id:
                    return validation_error(
                        "INVALID_REQUEST",
                        f"access_id {access_id!r} is empty once wildcards are stripped.",
                        "Pass the token's whole access ID, or use token_id.",
                    )
                if id_stripped:
                    notes.append(_ACCESS_ID_NOTE)
                access_id = clean_id
            return await _api_token_logs(client, filters, access_id, token_id, limit, offset, notes)

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
