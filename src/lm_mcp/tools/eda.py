# Description: Event-Driven Ansible integration tools for automated event response.
# Description: Provides activation management, project sync, rulebook queries, and event streams.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client.eda import EdaClient


# -- Connection test -----------------------------------------------------------


async def test_eda_connection(
    client: "EdaClient",
) -> list[TextContent]:
    """Test connectivity to EDA Controller.

    Args:
        client: EDA Controller API client.

    Returns:
        List of TextContent with connection status.
    """
    try:
        data = await client.get("/status/")
        return format_response(
            {
                "connected": True,
                "status": data.get("status", "unknown"),
                "version": data.get("version", "unknown"),
            }
        )
    except Exception as e:
        return handle_error(e)


# -- Activation tools ----------------------------------------------------------


async def get_eda_activations(
    client: "EdaClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List rulebook activations from EDA Controller.

    Args:
        client: EDA Controller API client.
        name_filter: Search activations by name.
        limit: Maximum number of activations to return.

    Returns:
        List of TextContent with activation data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter

        data = await client.get("/activations/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "activations": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_eda_activation(
    client: "EdaClient",
    activation_id: int,
) -> list[TextContent]:
    """Get details of a specific rulebook activation.

    Args:
        client: EDA Controller API client.
        activation_id: The activation ID.

    Returns:
        List of TextContent with activation details.
    """
    try:
        data = await client.get(f"/activations/{activation_id}/")
        return format_response(data)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_eda_activation(
    client: "EdaClient",
    name: str,
    rulebook_id: int,
    decision_environment_id: int,
    extra_var: str | None = None,
    restart_policy: str = "on-failure",
    is_enabled: bool = True,
    organization_id: int = 1,
) -> list[TextContent]:
    """Create a new rulebook activation.

    Args:
        client: EDA Controller API client.
        name: Activation name.
        rulebook_id: ID of the rulebook to activate.
        decision_environment_id: ID of the decision environment.
        extra_var: Extra variables as YAML string.
        restart_policy: Restart policy (always, never, on-failure).
        is_enabled: Whether to enable the activation immediately.
        organization_id: Organization ID (default 1 = "Default" org).

    Returns:
        List of TextContent with created activation data.
    """
    try:
        body: dict = {
            "name": name,
            "rulebook_id": rulebook_id,
            "decision_environment_id": decision_environment_id,
            "restart_policy": restart_policy,
            "is_enabled": is_enabled,
            "organization_id": organization_id,
        }
        if extra_var is not None:
            body["extra_var"] = extra_var

        data = await client.post("/activations/", json_body=body)
        return format_response(data)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def enable_eda_activation(
    client: "EdaClient",
    activation_id: int,
) -> list[TextContent]:
    """Enable a rulebook activation.

    Args:
        client: EDA Controller API client.
        activation_id: The activation ID to enable.

    Returns:
        List of TextContent confirming activation enabled.
    """
    try:
        await client.post(f"/activations/{activation_id}/enable/")
        return format_response({"enabled": True, "activation_id": activation_id})
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def disable_eda_activation(
    client: "EdaClient",
    activation_id: int,
) -> list[TextContent]:
    """Disable a rulebook activation.

    Args:
        client: EDA Controller API client.
        activation_id: The activation ID to disable.

    Returns:
        List of TextContent confirming activation disabled.
    """
    try:
        await client.post(f"/activations/{activation_id}/disable/")
        return format_response({"disabled": True, "activation_id": activation_id})
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def restart_eda_activation(
    client: "EdaClient",
    activation_id: int,
) -> list[TextContent]:
    """Restart a rulebook activation.

    Args:
        client: EDA Controller API client.
        activation_id: The activation ID to restart.

    Returns:
        List of TextContent confirming activation restarted.
    """
    try:
        await client.post(f"/activations/{activation_id}/restart/")
        return format_response({"restarted": True, "activation_id": activation_id})
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_eda_activation(
    client: "EdaClient",
    activation_id: int,
) -> list[TextContent]:
    """Delete a rulebook activation.

    Args:
        client: EDA Controller API client.
        activation_id: The activation ID to delete.

    Returns:
        List of TextContent confirming deletion.
    """
    try:
        await client.delete(f"/activations/{activation_id}/")
        return format_response({"deleted": True, "activation_id": activation_id})
    except Exception as e:
        return handle_error(e)


async def get_eda_activation_instances(
    client: "EdaClient",
    activation_id: int,
    limit: int = 50,
) -> list[TextContent]:
    """List instances of a rulebook activation.

    Args:
        client: EDA Controller API client.
        activation_id: The activation ID.
        limit: Maximum number of instances to return.

    Returns:
        List of TextContent with instance data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        data = await client.get(
            f"/activations/{activation_id}/instances/", params=params
        )
        return format_response(
            {
                "count": data.get("count", 0),
                "instances": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_eda_activation_instance_logs(
    client: "EdaClient",
    instance_id: int,
    limit: int = 50,
) -> list[TextContent]:
    """Get logs for an activation instance.

    Args:
        client: EDA Controller API client.
        instance_id: The activation instance ID.
        limit: Maximum number of log entries to return.

    Returns:
        List of TextContent with log entries.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        data = await client.get(
            f"/activation-instances/{instance_id}/logs/", params=params
        )
        return format_response(
            {
                "count": data.get("count", 0),
                "logs": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


# -- Project tools -------------------------------------------------------------


async def get_eda_projects(
    client: "EdaClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List projects from EDA Controller.

    Args:
        client: EDA Controller API client.
        name_filter: Search projects by name.
        limit: Maximum number of projects to return.

    Returns:
        List of TextContent with project data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter

        data = await client.get("/projects/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "projects": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_eda_project(
    client: "EdaClient",
    project_id: int,
) -> list[TextContent]:
    """Get details of a specific project.

    Args:
        client: EDA Controller API client.
        project_id: The project ID.

    Returns:
        List of TextContent with project details.
    """
    try:
        data = await client.get(f"/projects/{project_id}/")
        return format_response(data)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_eda_project(
    client: "EdaClient",
    name: str,
    url: str,
    description: str | None = None,
    credential_id: int | None = None,
    organization_id: int = 1,
) -> list[TextContent]:
    """Create a new EDA project from a Git repository.

    Args:
        client: EDA Controller API client.
        name: Project name.
        url: Git repository URL containing rulebooks.
        description: Optional project description.
        credential_id: Optional credential ID for private repos.
        organization_id: Organization ID (default 1 = "Default" org).

    Returns:
        List of TextContent with created project data.
    """
    try:
        body: dict = {
            "name": name,
            "url": url,
            "organization_id": organization_id,
        }
        if description is not None:
            body["description"] = description
        if credential_id is not None:
            body["credential_id"] = credential_id

        data = await client.post("/projects/", json_body=body)
        return format_response(data)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def sync_eda_project(
    client: "EdaClient",
    project_id: int,
) -> list[TextContent]:
    """Sync an EDA project from its Git repository.

    Args:
        client: EDA Controller API client.
        project_id: The project ID to sync.

    Returns:
        List of TextContent confirming sync started.
    """
    try:
        await client.post(f"/projects/{project_id}/sync/")
        return format_response({"synced": True, "project_id": project_id})
    except Exception as e:
        return handle_error(e)


# -- Rulebook tools ------------------------------------------------------------


async def get_eda_rulebooks(
    client: "EdaClient",
    name_filter: str | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List rulebooks from EDA Controller.

    Rulebooks are populated via project sync from Git repositories.

    Args:
        client: EDA Controller API client.
        name_filter: Search rulebooks by name.
        project_id: Filter by project ID.
        limit: Maximum number of rulebooks to return.

    Returns:
        List of TextContent with rulebook data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter
        if project_id is not None:
            params["project_id"] = str(project_id)

        data = await client.get("/rulebooks/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "rulebooks": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_eda_rulebook(
    client: "EdaClient",
    rulebook_id: int,
) -> list[TextContent]:
    """Get details of a specific rulebook.

    Args:
        client: EDA Controller API client.
        rulebook_id: The rulebook ID.

    Returns:
        List of TextContent with rulebook details including rulesets.
    """
    try:
        data = await client.get(f"/rulebooks/{rulebook_id}/")
        return format_response(data)
    except Exception as e:
        return handle_error(e)


# -- Event stream tools --------------------------------------------------------


async def get_eda_event_streams(
    client: "EdaClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List event streams from EDA Controller.

    Event streams provide managed webhook endpoints for receiving events.

    Args:
        client: EDA Controller API client.
        name_filter: Search event streams by name.
        limit: Maximum number of event streams to return.

    Returns:
        List of TextContent with event stream data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter

        data = await client.get("/event-streams/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "event_streams": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_eda_event_stream(
    client: "EdaClient",
    event_stream_id: int,
) -> list[TextContent]:
    """Get details of a specific event stream.

    Args:
        client: EDA Controller API client.
        event_stream_id: The event stream ID.

    Returns:
        List of TextContent with event stream details.
    """
    try:
        data = await client.get(f"/event-streams/{event_stream_id}/")
        return format_response(data)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_eda_event_stream(
    client: "EdaClient",
    name: str,
    eda_credential_id: int,
    event_stream_type: str = "basic",
    organization_id: int = 1,
) -> list[TextContent]:
    """Create a new event stream (webhook endpoint).

    Args:
        client: EDA Controller API client.
        name: Event stream name.
        eda_credential_id: ID of the EDA credential for authentication.
        event_stream_type: Type of event stream (basic, hmac, etc.).
        organization_id: Organization ID (default 1 = "Default" org).

    Returns:
        List of TextContent with created event stream data.
    """
    try:
        body: dict = {
            "name": name,
            "eda_credential_id": eda_credential_id,
            "event_stream_type": event_stream_type,
            "organization_id": organization_id,
        }
        data = await client.post("/event-streams/", json_body=body)
        return format_response(data)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_eda_event_stream(
    client: "EdaClient",
    event_stream_id: int,
) -> list[TextContent]:
    """Delete an event stream.

    Args:
        client: EDA Controller API client.
        event_stream_id: The event stream ID to delete.

    Returns:
        List of TextContent confirming deletion.
    """
    try:
        await client.delete(f"/event-streams/{event_stream_id}/")
        return format_response({"deleted": True, "event_stream_id": event_stream_id})
    except Exception as e:
        return handle_error(e)
