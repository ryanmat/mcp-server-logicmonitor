# Description: Dashboard tools for LogicMonitor MCP server.
# Description: Provides dashboard and widget management tools.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_dashboards(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    group_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List dashboards from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by dashboard name (supports wildcards).
        group_id: Filter by dashboard group ID.
        limit: Maximum number of dashboards to return.

    Returns:
        List of TextContent with dashboard data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if name_filter:
            filters.append(f"name~{name_filter}")
        if group_id is not None:
            filters.append(f"groupId:{group_id}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/dashboard/dashboards", params=params)

        dashboards = []
        for item in result.get("items", []):
            dashboards.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "group_id": item.get("groupId"),
                    "group_name": item.get("groupFullPath"),
                    "widget_count": item.get("widgetsConfig", {}).get("count", 0)
                    if isinstance(item.get("widgetsConfig"), dict)
                    else len(item.get("widgetsConfig", [])),
                    "owner": item.get("owner"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(dashboards),
                "dashboards": dashboards,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_dashboard(
    client: "LogicMonitorClient",
    dashboard_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific dashboard.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID.

    Returns:
        List of TextContent with dashboard details or error.
    """
    try:
        result = await client.get(f"/dashboard/dashboards/{dashboard_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


async def get_dashboard_widgets(
    client: "LogicMonitorClient",
    dashboard_id: int,
    limit: int = 100,
) -> list[TextContent]:
    """Get widgets for a specific dashboard.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID.
        limit: Maximum number of widgets to return.

    Returns:
        List of TextContent with widget data or error.
    """
    try:
        params: dict = {"size": limit}

        result = await client.get(f"/dashboard/dashboards/{dashboard_id}/widgets", params=params)

        widgets = []
        for item in result.get("items", []):
            widgets.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "description": item.get("description"),
                    "column": item.get("columnIdx"),
                    "row_span": item.get("rowSpan"),
                    "col_span": item.get("colSpan"),
                }
            )

        return format_response(
            {
                "dashboard_id": dashboard_id,
                "total": result.get("total", 0),
                "count": len(widgets),
                "widgets": widgets,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_dashboard(
    client: "LogicMonitorClient",
    name: str,
    group_id: int = 1,
    description: str | None = None,
    sharable: bool = True,
) -> list[TextContent]:
    """Create a new dashboard.

    Args:
        client: LogicMonitor API client.
        name: Dashboard name.
        group_id: Dashboard group ID (default: 1 for root).
        description: Dashboard description.
        sharable: Whether dashboard is sharable (default: True).

    Returns:
        List of TextContent with created dashboard details or error.
    """
    try:
        payload: dict = {
            "name": name,
            "groupId": group_id,
            "sharable": sharable,
        }

        if description:
            payload["description"] = description

        result = await client.post("/dashboard/dashboards", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"Dashboard '{name}' created successfully",
                "dashboard": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "group_id": result.get("groupId"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_dashboard(
    client: "LogicMonitorClient",
    dashboard_id: int,
    name: str | None = None,
    description: str | None = None,
    group_id: int | None = None,
    sharable: bool | None = None,
) -> list[TextContent]:
    """Update an existing dashboard.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID to update.
        name: New dashboard name.
        description: New dashboard description.
        group_id: New dashboard group ID.
        sharable: Whether dashboard is sharable.

    Returns:
        List of TextContent with updated dashboard details or error.
    """
    try:
        # Get current dashboard to preserve unmodified fields
        current = await client.get(f"/dashboard/dashboards/{dashboard_id}")

        payload = dict(current)
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if group_id is not None:
            payload["groupId"] = group_id
        if sharable is not None:
            payload["sharable"] = sharable

        result = await client.put(f"/dashboard/dashboards/{dashboard_id}", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"Dashboard {dashboard_id} updated",
                "dashboard": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "group_id": result.get("groupId"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_dashboard(
    client: "LogicMonitorClient",
    dashboard_id: int,
) -> list[TextContent]:
    """Delete a dashboard.

    WARNING: This permanently deletes the dashboard and all its widgets.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID to delete.

    Returns:
        List of TextContent with deletion result or error.
    """
    try:
        # Get dashboard info first for confirmation message
        dashboard = await client.get(f"/dashboard/dashboards/{dashboard_id}")
        dashboard_name = dashboard.get("name", f"ID:{dashboard_id}")
        widget_count = len(dashboard.get("widgetsConfig", []))

        await client.delete(f"/dashboard/dashboards/{dashboard_id}")

        return format_response(
            {
                "success": True,
                "message": f"Dashboard '{dashboard_name}' deleted",
                "details": {
                    "dashboard_id": dashboard_id,
                    "widgets_removed": widget_count,
                },
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_widget(
    client: "LogicMonitorClient",
    dashboard_id: int,
    widget_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific widget.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID containing the widget.
        widget_id: Widget ID.

    Returns:
        List of TextContent with widget details or error.
    """
    try:
        result = await client.get(f"/dashboard/dashboards/{dashboard_id}/widgets/{widget_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def add_widget(
    client: "LogicMonitorClient",
    dashboard_id: int,
    name: str,
    widget_type: str,
    column_index: int = 0,
    row_span: int = 1,
    col_span: int = 6,
    description: str | None = None,
    config: dict | None = None,
) -> list[TextContent]:
    """Add a widget to a dashboard.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID to add widget to.
        name: Widget name.
        widget_type: Widget type (e.g., cgraph, sgraph, text, html, alert, etc.).
        column_index: Column position (0-11).
        row_span: Number of rows to span.
        col_span: Number of columns to span (1-12).
        description: Widget description.
        config: Additional widget configuration (type-specific).

    Returns:
        List of TextContent with created widget details or error.
    """
    try:
        payload: dict = {
            "name": name,
            "type": widget_type,
            "dashboardId": dashboard_id,
            "columnIdx": column_index,
            "rowSpan": row_span,
            "colSpan": col_span,
        }

        if description:
            payload["description"] = description

        # Merge additional config
        if config:
            payload.update(config)

        result = await client.post(
            f"/dashboard/dashboards/{dashboard_id}/widgets",
            json_body=payload,
        )

        return format_response(
            {
                "success": True,
                "message": f"Widget '{name}' added to dashboard {dashboard_id}",
                "widget": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "type": result.get("type"),
                    "dashboard_id": dashboard_id,
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_widget(
    client: "LogicMonitorClient",
    dashboard_id: int,
    widget_id: int,
    name: str | None = None,
    description: str | None = None,
    column_index: int | None = None,
    row_span: int | None = None,
    col_span: int | None = None,
    config: dict | None = None,
) -> list[TextContent]:
    """Update an existing widget.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID containing the widget.
        widget_id: Widget ID to update.
        name: New widget name.
        description: New widget description.
        column_index: New column position.
        row_span: New row span.
        col_span: New column span.
        config: Additional configuration to update.

    Returns:
        List of TextContent with updated widget details or error.
    """
    try:
        # First get the current widget to preserve unmodified fields
        current = await client.get(f"/dashboard/dashboards/{dashboard_id}/widgets/{widget_id}")

        payload = dict(current)
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if column_index is not None:
            payload["columnIdx"] = column_index
        if row_span is not None:
            payload["rowSpan"] = row_span
        if col_span is not None:
            payload["colSpan"] = col_span
        if config:
            payload.update(config)

        result = await client.put(
            f"/dashboard/dashboards/{dashboard_id}/widgets/{widget_id}",
            json_body=payload,
        )

        return format_response(
            {
                "success": True,
                "message": f"Widget {widget_id} updated",
                "widget": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "type": result.get("type"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_widget(
    client: "LogicMonitorClient",
    dashboard_id: int,
    widget_id: int,
) -> list[TextContent]:
    """Delete a widget from a dashboard.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID containing the widget.
        widget_id: Widget ID to delete.

    Returns:
        List of TextContent with deletion result or error.
    """
    try:
        await client.delete(f"/dashboard/dashboards/{dashboard_id}/widgets/{widget_id}")

        return format_response(
            {
                "success": True,
                "message": f"Widget {widget_id} deleted from dashboard {dashboard_id}",
            }
        )
    except Exception as e:
        return handle_error(e)
