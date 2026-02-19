# Description: Ansible Automation Platform integration tools for remediation workflows.
# Description: Provides job template management, job execution, and inventory queries.

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client.awx import AwxClient

_JINJA2_PATTERN = re.compile(r"\{\{|\{%|\{#")


def validate_extra_vars(extra_vars: dict) -> None:
    """Reject values containing Jinja2 template syntax.

    Prevents template injection attacks by blocking {{ }}, {% %}, and {# #}
    patterns in extra_vars values passed to job templates.

    Args:
        extra_vars: Dictionary of extra variables to validate.

    Raises:
        ValueError: If any string value contains Jinja2 syntax.
    """
    for key, value in extra_vars.items():
        if isinstance(value, str) and _JINJA2_PATTERN.search(value):
            raise ValueError(
                f"extra_vars['{key}'] contains Jinja2 template syntax "
                "which is rejected for security. Use literal values only."
            )


# -- Connection test -----------------------------------------------------------


async def test_awx_connection(
    client: "AwxClient",
) -> list[TextContent]:
    """Test connectivity to Ansible Automation Platform controller.

    Args:
        client: Automation Controller API client.

    Returns:
        List of TextContent with connection status and version info.
    """
    try:
        data = await client.get("/ping/")
        return format_response(
            {
                "connected": True,
                "version": data.get("version", "unknown"),
                "active_node": data.get("active_node", "unknown"),
            }
        )
    except Exception as e:
        return handle_error(e)


# -- Job template tools --------------------------------------------------------


async def get_job_templates(
    client: "AwxClient",
    name_filter: str | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List job templates from Ansible Automation Platform.

    Args:
        client: Automation Controller API client.
        name_filter: Search templates by name.
        project_id: Filter by project ID.
        limit: Maximum number of templates to return.

    Returns:
        List of TextContent with template data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter
        if project_id is not None:
            params["project"] = str(project_id)

        data = await client.get("/job_templates/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "templates": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_job_template(
    client: "AwxClient",
    template_id: int,
) -> list[TextContent]:
    """Get details of a specific job template.

    Args:
        client: Automation Controller API client.
        template_id: The job template ID.

    Returns:
        List of TextContent with template details including survey spec.
    """
    try:
        data = await client.get(f"/job_templates/{template_id}/")
        return format_response(data)
    except Exception as e:
        return handle_error(e)


# -- Job execution tools -------------------------------------------------------


@require_write_permission
async def launch_job(
    client: "AwxClient",
    template_id: int,
    extra_vars: dict | None = None,
    inventory_id: int | None = None,
    limit: str | None = None,
    check_mode: bool = False,
) -> list[TextContent]:
    """Launch an Ansible job template.

    Args:
        client: Automation Controller API client.
        template_id: The job template ID to launch.
        extra_vars: Optional dictionary of extra variables for the playbook.
        inventory_id: Override inventory for this run.
        limit: Limit execution to specific hosts (Ansible limit pattern).
        check_mode: Run in check/dry-run mode (no changes applied).

    Returns:
        List of TextContent with job ID and status.
    """
    try:
        body: dict = {}
        if extra_vars:
            validate_extra_vars(extra_vars)
            body["extra_vars"] = extra_vars
        if inventory_id is not None:
            body["inventory"] = inventory_id
        if limit:
            body["limit"] = limit
        if check_mode:
            body["diff_mode"] = True

        data = await client.post(
            f"/job_templates/{template_id}/launch/",
            json_body=body if body else None,
        )
        return format_response(
            {
                "job_id": data.get("job"),
                "status": data.get("status", "pending"),
            }
        )
    except ValueError as e:
        # Jinja2 validation error
        return format_response(
            {
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": str(e),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_job_status(
    client: "AwxClient",
    job_id: int,
) -> list[TextContent]:
    """Get the status of a running or completed job.

    Args:
        client: Automation Controller API client.
        job_id: The job ID to check.

    Returns:
        List of TextContent with job status details.
    """
    try:
        data = await client.get(f"/jobs/{job_id}/")
        return format_response(data)
    except Exception as e:
        return handle_error(e)


async def get_job_output(
    client: "AwxClient",
    job_id: int,
) -> list[TextContent]:
    """Get the stdout output of a job.

    Args:
        client: Automation Controller API client.
        job_id: The job ID to get output from.

    Returns:
        List of TextContent with the job stdout.
    """
    try:
        data = await client.get(
            f"/jobs/{job_id}/stdout/",
            params={"format": "txt"},
        )
        # The response is plain text, not JSON
        if isinstance(data, str):
            return [TextContent(type="text", text=data)]
        return format_response(data)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def cancel_job(
    client: "AwxClient",
    job_id: int,
) -> list[TextContent]:
    """Cancel a running job.

    Args:
        client: Automation Controller API client.
        job_id: The job ID to cancel.

    Returns:
        List of TextContent confirming cancellation.
    """
    try:
        await client.post(f"/jobs/{job_id}/cancel/")
        return format_response({"cancelled": True, "job_id": job_id})
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def relaunch_job(
    client: "AwxClient",
    job_id: int,
    extra_vars: dict | None = None,
) -> list[TextContent]:
    """Relaunch a previously run job.

    Args:
        client: Automation Controller API client.
        job_id: The original job ID to relaunch.
        extra_vars: Optional override variables.

    Returns:
        List of TextContent with new job ID and status.
    """
    try:
        body: dict = {}
        if extra_vars:
            validate_extra_vars(extra_vars)
            body["extra_vars"] = extra_vars

        data = await client.post(
            f"/jobs/{job_id}/relaunch/",
            json_body=body if body else None,
        )
        return format_response(
            {
                "job_id": data.get("job"),
                "status": data.get("status", "pending"),
            }
        )
    except ValueError as e:
        return format_response(
            {
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": str(e),
            }
        )
    except Exception as e:
        return handle_error(e)


# -- Inventory tools -----------------------------------------------------------


async def get_inventories(
    client: "AwxClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List inventories from Ansible Automation Platform.

    Args:
        client: Automation Controller API client.
        name_filter: Search inventories by name.
        limit: Maximum number of inventories to return.

    Returns:
        List of TextContent with inventory data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter

        data = await client.get("/inventories/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "inventories": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_inventory_hosts(
    client: "AwxClient",
    inventory_id: int,
    limit: int = 50,
) -> list[TextContent]:
    """List hosts in a specific inventory.

    Args:
        client: Automation Controller API client.
        inventory_id: The inventory ID.
        limit: Maximum number of hosts to return.

    Returns:
        List of TextContent with host data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        data = await client.get(
            f"/inventories/{inventory_id}/hosts/", params=params
        )
        return format_response(
            {
                "count": data.get("count", 0),
                "hosts": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


# -- Workflow tools ------------------------------------------------------------


@require_write_permission
async def launch_workflow(
    client: "AwxClient",
    template_id: int,
    extra_vars: dict | None = None,
    inventory_id: int | None = None,
    limit: str | None = None,
) -> list[TextContent]:
    """Launch a workflow job template.

    Args:
        client: Automation Controller API client.
        template_id: The workflow template ID to launch.
        extra_vars: Optional dictionary of extra variables.
        inventory_id: Override inventory for this run.
        limit: Limit execution to specific hosts.

    Returns:
        List of TextContent with workflow job ID and status.
    """
    try:
        body: dict = {}
        if extra_vars:
            validate_extra_vars(extra_vars)
            body["extra_vars"] = extra_vars
        if inventory_id is not None:
            body["inventory"] = inventory_id
        if limit:
            body["limit"] = limit

        data = await client.post(
            f"/workflow_job_templates/{template_id}/launch/",
            json_body=body if body else None,
        )
        return format_response(
            {
                "workflow_job_id": data.get("workflow_job"),
                "status": data.get("status", "pending"),
            }
        )
    except ValueError as e:
        return format_response(
            {
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": str(e),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_workflow_status(
    client: "AwxClient",
    job_id: int,
) -> list[TextContent]:
    """Get the status of a workflow job.

    Args:
        client: Automation Controller API client.
        job_id: The workflow job ID.

    Returns:
        List of TextContent with workflow job status.
    """
    try:
        data = await client.get(f"/workflow_jobs/{job_id}/")
        return format_response(data)
    except Exception as e:
        return handle_error(e)


async def get_workflow_templates(
    client: "AwxClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List workflow job templates from Ansible Automation Platform.

    Args:
        client: Automation Controller API client.
        name_filter: Search workflow templates by name.
        limit: Maximum number of templates to return.

    Returns:
        List of TextContent with workflow template data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter

        data = await client.get(
            "/workflow_job_templates/", params=params
        )
        return format_response(
            {
                "count": data.get("count", 0),
                "templates": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


# -- Admin tools ---------------------------------------------------------------


async def get_projects(
    client: "AwxClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List projects from Ansible Automation Platform.

    Args:
        client: Automation Controller API client.
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


async def get_credentials(
    client: "AwxClient",
    name_filter: str | None = None,
    credential_type: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List credentials from Ansible Automation Platform.

    Args:
        client: Automation Controller API client.
        name_filter: Search credentials by name.
        credential_type: Filter by credential type ID.
        limit: Maximum number of credentials to return.

    Returns:
        List of TextContent with credential data (secrets are not exposed).
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter
        if credential_type is not None:
            params["credential_type"] = str(credential_type)

        data = await client.get("/credentials/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "credentials": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_organizations(
    client: "AwxClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List organizations from Ansible Automation Platform.

    Args:
        client: Automation Controller API client.
        name_filter: Search organizations by name.
        limit: Maximum number of organizations to return.

    Returns:
        List of TextContent with organization data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter

        data = await client.get("/organizations/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "organizations": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_job_events(
    client: "AwxClient",
    job_id: int,
    limit: int = 50,
) -> list[TextContent]:
    """Get events from a specific job run.

    Args:
        client: Automation Controller API client.
        job_id: The job ID to get events from.
        limit: Maximum number of events to return.

    Returns:
        List of TextContent with job event data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        data = await client.get(
            f"/jobs/{job_id}/job_events/", params=params
        )
        return format_response(
            {
                "count": data.get("count", 0),
                "events": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_hosts(
    client: "AwxClient",
    name_filter: str | None = None,
    inventory_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List hosts from Ansible Automation Platform.

    Args:
        client: Automation Controller API client.
        name_filter: Search hosts by name.
        inventory_id: Filter by inventory ID.
        limit: Maximum number of hosts to return.

    Returns:
        List of TextContent with host data.
    """
    try:
        params: dict = {"page_size": min(limit, 200)}
        if name_filter:
            params["search"] = name_filter
        if inventory_id is not None:
            params["inventory"] = str(inventory_id)

        data = await client.get("/hosts/", params=params)
        return format_response(
            {
                "count": data.get("count", 0),
                "hosts": data.get("results", []),
            }
        )
    except Exception as e:
        return handle_error(e)
