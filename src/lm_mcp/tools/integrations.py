# Description: Tools for LogicMonitor Integration resources (Custom HTTP Delivery).
# Description: CRUD for /setting/integrations, focused on the type="http" variant.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    require_write_permission,
    sanitize_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# Lifecycle events supported by the LM Custom HTTP Delivery integration.
# `actionNotes` and `updateData` are uncommon but exposed by the real
# server model, so we do not whitelist the subset here -- pass-through.
_LIFECYCLES = ("active", "ack", "clear", "update", "actionNotes", "updateData")


def _normalize_headers(
    headers: dict[str, str] | list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Normalize header input into the shape LogicMonitor stores.

    LM stores each header as a single-key dict ``{HeaderName: value}``
    inside a list. Callers may find that awkward, so this helper also
    accepts two friendlier forms:

    - A plain dict ``{name: value, ...}`` which is projected into the
      one-key-per-entry list form.
    - A list of ``{"name": ..., "value": ...}`` dicts from other tooling
      conventions; each entry is rewritten to ``{name: value}``.

    Returns None if ``headers`` is None so callers can skip the field
    entirely (LM treats absent and empty-list differently on PATCH).
    """
    if headers is None:
        return None
    if isinstance(headers, dict):
        return [{k: v} for k, v in headers.items()]
    result: list[dict[str, Any]] = []
    for entry in headers:
        if not isinstance(entry, dict):
            result.append(entry)
            continue
        if set(entry.keys()) == {"name", "value"}:
            result.append({entry["name"]: entry["value"]})
        else:
            result.append(entry)
    return result


def _summarize_integration(item: dict) -> dict:
    """Project an integration dict into the short list-view shape."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "type": item.get("type"),
        "description": item.get("description"),
    }


async def get_integrations(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    type_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List LogicMonitor integrations.

    Returns a short summary per integration (id, name, type, description).
    Use :func:`get_integration` for the full definition, which varies by
    integration type.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by integration name (supports wildcards, which
            are sanitized away; the LM ``~`` operator already does
            substring matching).
        type_filter: Exact-match filter on the integration type, e.g.
            ``"http"``, ``"slack-2"``, ``"pagerduty"``. LM's v3 API
            requires exact type values here; wildcards are not
            supported.
        limit: Maximum number of integrations to return.

    Returns:
        List of TextContent with integration summaries or error.
    """
    try:
        params: dict = {"size": limit}
        wildcards_stripped = False
        filter_parts: list[str] = []

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            filter_parts.append(f"name~{quote_filter_value(clean_name)}")
        if type_filter:
            filter_parts.append(f"type:{quote_filter_value(type_filter)}")
        if filter_parts:
            params["filter"] = ",".join(filter_parts)

        result = await client.get("/setting/integrations", params=params)

        integrations = [_summarize_integration(item) for item in result.get("items", [])]

        response: dict[str, Any] = {
            "total": result.get("total", 0),
            "count": len(integrations),
            "integrations": integrations,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_integration(
    client: LogicMonitorClient,
    integration_id: int,
) -> list[TextContent]:
    """Get a specific integration's full definition.

    Returns the raw LM response. The field set depends on the integration
    ``type``: Custom HTTP Delivery (``type="http"``) has flat per-lifecycle
    keys (``url``, ``method``, ``payload``, and their ``ack*``, ``clear*``,
    ``update*``, ``updateData*``, ``actionNotes*`` variants); other
    integrations (Slack, PagerDuty, etc.) expose different fields. Fields
    named ``password`` and ``oAuthClientSecret`` are masked by the server.

    Args:
        client: LogicMonitor API client.
        integration_id: Integration ID.

    Returns:
        List of TextContent with the full integration dict or error.
    """
    try:
        result = await client.get(f"/setting/integrations/{integration_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_http_integration(
    client: LogicMonitorClient,
    name: str,
    url: str,
    description: str | None = None,
    http_method: str = "post",
    headers: dict[str, str] | list[dict[str, Any]] | None = None,
    alert_body: str | None = None,
    alert_body_format: str = "json",
    alert_data_type: str | None = None,
    username: str | None = None,
    password: str | None = None,
    enabled_lifecycles: list[str] | None = None,
    ack_url: str | None = None,
    ack_method: str | None = None,
    ack_body: str | None = None,
    ack_headers: dict[str, str] | list[dict[str, Any]] | None = None,
    clear_url: str | None = None,
    clear_method: str | None = None,
    clear_body: str | None = None,
    clear_headers: dict[str, str] | list[dict[str, Any]] | None = None,
    update_url: str | None = None,
    update_method: str | None = None,
    update_body: str | None = None,
    update_headers: dict[str, str] | list[dict[str, Any]] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> list[TextContent]:
    """Create a Custom HTTP Delivery integration.

    Maps to ``POST /setting/integrations`` with ``type="http"`` injected.
    The per-lifecycle keys (active, ack, clear, update) are flattened
    into the top-level body as LM expects. Rarer lifecycles (``updateData``,
    ``actionNotes``) and OAuth credentials can be passed through
    ``extra_fields``; that dict is merged last and wins on conflict.

    ``headers`` accepts either a plain dict ``{name: value}`` or LM's
    native list-of-single-key-dicts form. When the dict form is used the
    helper converts it. A friendly ``[{"name": ..., "value": ...}]`` form
    is also accepted and converted.

    Args:
        client: LogicMonitor API client.
        name: Integration display name. Shown in the escalation-chain UI
            and used as the Recipient.method value when routing alerts
            to this integration.
        url: Webhook URL for alert lifecycle events. Defaults to the
            same URL for every enabled lifecycle unless overridden by
            ``ack_url`` / ``clear_url`` / ``update_url``.
        description: Optional description.
        http_method: HTTP verb for the active alert post (default ``post``).
        headers: Headers sent on active alerts.
        alert_body: Payload template (supports LM ``##TOKEN##`` substitutions).
        alert_body_format: Payload format (``json`` or ``form``). Default ``json``.
        alert_data_type: LM alert data type, typically ``"raw"`` or ``"formatted"``.
        username: Optional basic-auth username.
        password: Optional basic-auth password (server masks on reads).
        enabled_lifecycles: Subset of ``["active", "ack", "clear", "update",
            "actionNotes", "updateData"]``. Defaults to all four core
            lifecycles.
        ack_url / ack_method / ack_body / ack_headers: Overrides for the
            ack lifecycle. Same pattern for clear and update.
        extra_fields: Dict of raw LM integration fields merged into the
            body last. Use for OAuth credentials, ``updateData*`` fields,
            ``actionNotes*`` fields, ``extra`` UI metadata, etc.

    Returns:
        List of TextContent with success message and new integration ID,
        or error.
    """
    try:
        body: dict[str, Any] = {
            "name": name,
            "type": "http",
            "url": url,
            "method": http_method,
            "payloadFormat": alert_body_format,
            "enabledStatus": enabled_lifecycles or ["active", "ack", "clear", "update"],
        }

        if description is not None:
            body["description"] = description
        if alert_body is not None:
            body["payload"] = alert_body
        if alert_data_type is not None:
            body["alertDataType"] = alert_data_type
        normalized_headers = _normalize_headers(headers)
        if normalized_headers is not None:
            body["headers"] = normalized_headers
        if username is not None:
            body["username"] = username
        if password is not None:
            body["password"] = password

        _apply_lifecycle_overrides(
            body,
            "ack",
            ack_url,
            ack_method,
            ack_body,
            _normalize_headers(ack_headers),
        )
        _apply_lifecycle_overrides(
            body,
            "clear",
            clear_url,
            clear_method,
            clear_body,
            _normalize_headers(clear_headers),
        )
        _apply_lifecycle_overrides(
            body,
            "update",
            update_url,
            update_method,
            update_body,
            _normalize_headers(update_headers),
        )

        if extra_fields:
            body.update(extra_fields)

        result = await client.post("/setting/integrations", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"HTTP Delivery integration '{name}' created",
                "integration_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_http_integration(
    client: LogicMonitorClient,
    integration_id: int,
    name: str | None = None,
    description: str | None = None,
    url: str | None = None,
    http_method: str | None = None,
    headers: dict[str, str] | list[dict[str, Any]] | None = None,
    alert_body: str | None = None,
    alert_body_format: str | None = None,
    alert_data_type: str | None = None,
    username: str | None = None,
    password: str | None = None,
    enabled_lifecycles: list[str] | None = None,
    ack_url: str | None = None,
    ack_method: str | None = None,
    ack_body: str | None = None,
    ack_headers: dict[str, str] | list[dict[str, Any]] | None = None,
    clear_url: str | None = None,
    clear_method: str | None = None,
    clear_body: str | None = None,
    clear_headers: dict[str, str] | list[dict[str, Any]] | None = None,
    update_url: str | None = None,
    update_method: str | None = None,
    update_body: str | None = None,
    update_headers: dict[str, str] | list[dict[str, Any]] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> list[TextContent]:
    """Update a Custom HTTP Delivery integration via PATCH.

    Only fields explicitly provided are sent; omitted fields stay at
    their current server values. LM accepts PATCH on
    ``/setting/integrations/{id}`` as a partial update -- the full-replace
    footgun that hit ``update_datasource`` does not apply here.

    Args mirror :func:`create_http_integration`; all are optional.

    Returns:
        List of TextContent with success message or error.
    """
    try:
        body: dict[str, Any] = {}

        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if url is not None:
            body["url"] = url
        if http_method is not None:
            body["method"] = http_method
        normalized_headers = _normalize_headers(headers)
        if normalized_headers is not None:
            body["headers"] = normalized_headers
        if alert_body is not None:
            body["payload"] = alert_body
        if alert_body_format is not None:
            body["payloadFormat"] = alert_body_format
        if alert_data_type is not None:
            body["alertDataType"] = alert_data_type
        if username is not None:
            body["username"] = username
        if password is not None:
            body["password"] = password
        if enabled_lifecycles is not None:
            body["enabledStatus"] = enabled_lifecycles

        _apply_lifecycle_overrides(
            body,
            "ack",
            ack_url,
            ack_method,
            ack_body,
            _normalize_headers(ack_headers),
        )
        _apply_lifecycle_overrides(
            body,
            "clear",
            clear_url,
            clear_method,
            clear_body,
            _normalize_headers(clear_headers),
        )
        _apply_lifecycle_overrides(
            body,
            "update",
            update_url,
            update_method,
            update_body,
            _normalize_headers(update_headers),
        )

        if extra_fields:
            body.update(extra_fields)

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "VALIDATION_ERROR",
                    "message": "No fields provided to update",
                }
            )

        result = await client.patch(
            f"/setting/integrations/{integration_id}",
            json_body=body,
        )

        return format_response(
            {
                "success": True,
                "message": f"HTTP Delivery integration {integration_id} updated",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_integration(
    client: LogicMonitorClient,
    integration_id: int,
) -> list[TextContent]:
    """Delete an integration by ID. Works for any integration type.

    Args:
        client: LogicMonitor API client.
        integration_id: Integration ID.

    Returns:
        List of TextContent with success message or error.
    """
    try:
        await client.delete(f"/setting/integrations/{integration_id}")
        return format_response(
            {
                "success": True,
                "message": f"Integration {integration_id} deleted",
            }
        )
    except Exception as e:
        return handle_error(e)


def _apply_lifecycle_overrides(
    body: dict[str, Any],
    lifecycle: str,
    url_value: str | None,
    method_value: str | None,
    body_value: str | None,
    headers_value: list[dict[str, Any]] | None,
) -> None:
    """Set per-lifecycle fields on a body dict when provided.

    LM stores overrides as camelCase prefixes: e.g. ``ackUrl``, ``clearMethod``.
    Only fields whose argument is not None are added, which matches both
    create (starts empty) and update (PATCH partial) semantics.
    """
    prefix = lifecycle
    if url_value is not None:
        body[f"{prefix}Url"] = url_value
    if method_value is not None:
        body[f"{prefix}Method"] = method_value
    if body_value is not None:
        body[f"{prefix}Payload"] = body_value
    if headers_value is not None:
        body[f"{prefix}Headers"] = headers_value


__all__ = [
    "create_http_integration",
    "delete_integration",
    "get_integration",
    "get_integrations",
    "update_http_integration",
]
