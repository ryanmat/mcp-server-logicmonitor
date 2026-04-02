# Description: Terraform IaC tools for plan, apply, state, and HCL generation.
# Description: Supports any Terraform provider plus LM-specific resource export.

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient
    from lm_mcp.client.terraform import TerraformRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lm_env_vars() -> dict[str, str]:
    """Build LM provider env vars from current config for subprocess.

    Sets both native provider env vars (LM_API_ID, LM_API_KEY, LM_COMPANY)
    and TF_VAR_* equivalents for HCL variable blocks. The native vars are
    what the logicmonitor provider reads directly; TF_VAR_* are for configs
    that use variable blocks for credentials.
    Returns an empty dict if config is unavailable (e.g., in tests).
    """
    try:
        from lm_mcp.config import get_config

        config = get_config()
        env: dict[str, str] = {}
        portal = config.portal if hasattr(config, "portal") else ""
        if portal:
            company = portal.split(".")[0]
            env["LM_COMPANY"] = company
            env["TF_VAR_lm_company"] = company
        if hasattr(config, "access_id") and config.access_id:
            env["LM_API_ID"] = config.access_id
            env["TF_VAR_lm_api_id"] = config.access_id
        if hasattr(config, "access_key") and config.access_key:
            env["LM_API_KEY"] = config.access_key
            env["TF_VAR_lm_api_key"] = config.access_key
        return env
    except Exception:
        return {}


def _parse_plan_exit_code(exit_code: int) -> str:
    """Interpret terraform plan -detailed-exitcode values."""
    if exit_code == 0:
        return "no_changes"
    if exit_code == 2:
        return "changes_pending"
    return "error"


def _safe_name(raw: str) -> str:
    """Convert a display name to a valid Terraform resource name.

    Replaces non-alphanumeric characters with underscores and strips
    leading digits so the result is a valid HCL identifier.
    """
    name = re.sub(r"[^a-zA-Z0-9_]", "_", raw).strip("_").lower()
    name = re.sub(r"_+", "_", name)
    if name and name[0].isdigit():
        name = f"r_{name}"
    return name or "resource"


# ---------------------------------------------------------------------------
# Read-only tools (receive TerraformRunner)
# ---------------------------------------------------------------------------


async def terraform_init(
    runner: TerraformRunner,
    workspace: str,
    backend_config: str | None = None,
) -> list[TextContent]:
    """Initialize a Terraform workspace and download providers.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name (subdirectory of TF_WORKSPACE_DIR).
        backend_config: Optional backend config string (key=value).
    """
    try:
        args = ["init", "-no-color"]
        if backend_config:
            args.extend(["-backend-config", backend_config])
        result = await runner.run(args, workspace, env_extra=_lm_env_vars())
        return format_response(
            {
                "workspace": workspace,
                "exit_code": result.exit_code,
                "success": result.exit_code == 0,
                "output": result.stdout[-4000:] if result.stdout else "",
                "errors": result.stderr[-2000:] if result.stderr else "",
            }
        )
    except Exception as e:
        return handle_error(e)


async def terraform_validate(
    runner: TerraformRunner,
    workspace: str,
) -> list[TextContent]:
    """Validate Terraform configuration syntax.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
    """
    try:
        result = await runner.run(
            ["validate", "-json", "-no-color"], workspace, env_extra=_lm_env_vars()
        )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = {"raw_output": result.stdout[-4000:]}
        return format_response(
            {
                "workspace": workspace,
                "valid": result.exit_code == 0,
                "diagnostics": parsed,
                "errors": result.stderr[-2000:] if result.stderr else "",
            }
        )
    except Exception as e:
        return handle_error(e)


async def terraform_plan(
    runner: TerraformRunner,
    workspace: str,
    var: str | None = None,
    var_file: str | None = None,
    target: str | None = None,
) -> list[TextContent]:
    """Preview Terraform changes without applying.

    Uses -detailed-exitcode: 0=no changes, 1=error, 2=changes pending.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
        var: Variable assignment (key=value).
        var_file: Path to a .tfvars file (relative to workspace).
        target: Target a specific resource address.
    """
    try:
        args = ["plan", "-json", "-no-color", "-detailed-exitcode"]
        if var:
            args.extend(["-var", var])
        if var_file:
            args.extend(["-var-file", var_file])
        if target:
            args.extend(["-target", target])
        result = await runner.run(args, workspace, env_extra=_lm_env_vars())
        status = _parse_plan_exit_code(result.exit_code)

        # Parse JSON lines from plan output for structured summary
        plan_lines = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                try:
                    plan_lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return format_response(
            {
                "workspace": workspace,
                "status": status,
                "exit_code": result.exit_code,
                "has_changes": status == "changes_pending",
                "plan_output": plan_lines[-50:],
                "errors": result.stderr[-2000:] if result.stderr and status == "error" else "",
            }
        )
    except Exception as e:
        return handle_error(e)


async def terraform_state_list(
    runner: TerraformRunner,
    workspace: str,
) -> list[TextContent]:
    """List all resources tracked in Terraform state.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
    """
    try:
        result = await runner.run(["state", "list"], workspace)
        if result.exit_code != 0:
            return format_response(
                {
                    "workspace": workspace,
                    "error": True,
                    "message": result.stderr or "No state file found",
                }
            )
        resources = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return format_response(
            {
                "workspace": workspace,
                "resource_count": len(resources),
                "resources": resources,
            }
        )
    except Exception as e:
        return handle_error(e)


async def terraform_state_show(
    runner: TerraformRunner,
    workspace: str,
    address: str,
) -> list[TextContent]:
    """Show detailed state for a specific Terraform resource.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
        address: Resource address (e.g., logicmonitor_device.web01).
    """
    try:
        result = await runner.run(["state", "show", "-json", address], workspace)
        if result.exit_code != 0:
            return format_response(
                {
                    "workspace": workspace,
                    "address": address,
                    "error": True,
                    "message": result.stderr or f"Resource '{address}' not found in state",
                }
            )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = {"raw_output": result.stdout[-4000:]}
        return format_response(
            {
                "workspace": workspace,
                "address": address,
                "resource": parsed,
            }
        )
    except Exception as e:
        return handle_error(e)


async def terraform_output(
    runner: TerraformRunner,
    workspace: str,
) -> list[TextContent]:
    """Show Terraform output values.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
    """
    try:
        result = await runner.run(["output", "-json"], workspace)
        if result.exit_code != 0:
            return format_response(
                {
                    "workspace": workspace,
                    "outputs": {},
                    "message": result.stderr or "No outputs defined or no state",
                }
            )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = {}
        return format_response(
            {
                "workspace": workspace,
                "outputs": parsed,
            }
        )
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# Write-gated tools (receive TerraformRunner)
# ---------------------------------------------------------------------------


@require_write_permission
async def terraform_apply(
    runner: TerraformRunner,
    workspace: str,
    var: str | None = None,
    var_file: str | None = None,
    target: str | None = None,
    confirm: bool = False,
) -> list[TextContent]:
    """Apply Terraform configuration changes.

    Triple-gated: requires LM_ENABLE_WRITE_OPERATIONS=true,
    TF_AUTO_APPROVE_ENABLED=true, and confirm=true parameter.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
        var: Variable assignment (key=value).
        var_file: Path to a .tfvars file (relative to workspace).
        target: Target a specific resource address.
        confirm: Must be True to proceed. Safety gate for destructive operations.
    """
    try:
        if not runner.auto_approve_enabled:
            return format_response(
                {
                    "error": True,
                    "code": "TERRAFORM_APPLY_DISABLED",
                    "message": "Terraform apply is disabled by server configuration",
                    "suggestion": "Set TF_AUTO_APPROVE_ENABLED=true to enable apply operations",
                }
            )
        if not confirm:
            return format_response(
                {
                    "error": True,
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "terraform_apply requires confirm=true parameter",
                    "suggestion": (
                        "Run terraform_plan first to review changes, "
                        "then call terraform_apply with confirm=true"
                    ),
                }
            )

        args = ["apply", "-auto-approve", "-json", "-no-color"]
        if var:
            args.extend(["-var", var])
        if var_file:
            args.extend(["-var-file", var_file])
        if target:
            args.extend(["-target", target])
        result = await runner.run(args, workspace, env_extra=_lm_env_vars())

        apply_lines = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                try:
                    apply_lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return format_response(
            {
                "workspace": workspace,
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "apply_output": apply_lines[-50:],
                "errors": result.stderr[-2000:] if result.stderr and result.exit_code != 0 else "",
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def terraform_destroy(
    runner: TerraformRunner,
    workspace: str,
    target: str | None = None,
    confirm: bool = False,
) -> list[TextContent]:
    """Destroy Terraform-managed infrastructure.

    Triple-gated: requires LM_ENABLE_WRITE_OPERATIONS=true,
    TF_AUTO_APPROVE_ENABLED=true, and confirm=true parameter.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
        target: Target a specific resource address to destroy.
        confirm: Must be True to proceed. Safety gate for destructive operations.
    """
    try:
        if not runner.auto_approve_enabled:
            return format_response(
                {
                    "error": True,
                    "code": "TERRAFORM_DESTROY_DISABLED",
                    "message": "Terraform destroy is disabled by server configuration",
                    "suggestion": "Set TF_AUTO_APPROVE_ENABLED=true to enable destroy operations",
                }
            )
        if not confirm:
            return format_response(
                {
                    "error": True,
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "terraform_destroy requires confirm=true parameter",
                    "suggestion": (
                        "Run terraform_plan first to review what will be destroyed, "
                        "then call terraform_destroy with confirm=true"
                    ),
                }
            )

        args = ["destroy", "-auto-approve", "-json", "-no-color"]
        if target:
            args.extend(["-target", target])
        result = await runner.run(args, workspace, env_extra=_lm_env_vars())

        return format_response(
            {
                "workspace": workspace,
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "output": result.stdout[-4000:] if result.stdout else "",
                "errors": result.stderr[-2000:] if result.stderr and result.exit_code != 0 else "",
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def terraform_import_resource(
    runner: TerraformRunner,
    workspace: str,
    address: str,
    resource_id: str,
) -> list[TextContent]:
    """Import an existing resource into Terraform state.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
        address: Terraform resource address (e.g., logicmonitor_device.web01).
        resource_id: The real-world ID of the resource to import.
    """
    try:
        result = await runner.run(
            ["import", "-no-color", address, str(resource_id)],
            workspace,
            env_extra=_lm_env_vars(),
        )
        return format_response(
            {
                "workspace": workspace,
                "address": address,
                "resource_id": resource_id,
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "output": result.stdout[-4000:] if result.stdout else "",
                "errors": result.stderr[-2000:] if result.stderr and result.exit_code != 0 else "",
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def terraform_write_config(
    runner: TerraformRunner,
    workspace: str,
    filename: str,
    content: str,
) -> list[TextContent]:
    """Write HCL configuration to a file in a Terraform workspace.

    Validates the filename ends with .tf or .tf.json and contains no path
    separators to prevent directory traversal.

    Args:
        runner: TerraformRunner instance.
        workspace: Workspace name.
        filename: Filename to write (must end with .tf or .tf.json).
        content: HCL or JSON content to write.
    """
    try:
        # Validate filename
        if "/" in filename or "\\" in filename:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_FILENAME",
                    "message": "Filename must not contain path separators",
                    "suggestion": "Use a simple filename like 'main.tf' without directory paths",
                }
            )
        if not (filename.endswith(".tf") or filename.endswith(".tf.json")):
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_FILENAME",
                    "message": f"Filename must end with .tf or .tf.json, got '{filename}'",
                    "suggestion": "Use a filename like 'main.tf' or 'config.tf.json'",
                }
            )

        ws_path = runner.workspace_path(workspace)
        ws_path.mkdir(parents=True, exist_ok=True)
        file_path = ws_path / filename
        file_path.write_text(content, encoding="utf-8")

        return format_response(
            {
                "workspace": workspace,
                "filename": filename,
                "written": True,
                "bytes": len(content.encode("utf-8")),
                "path": str(file_path),
            }
        )
    except Exception as e:
        return handle_error(e)


# ---------------------------------------------------------------------------
# terraform_generate — LM-specific (receives LogicMonitorClient)
# ---------------------------------------------------------------------------

# LM API path and Terraform resource type mappings
_RESOURCE_TYPES: dict[str, dict[str, str]] = {
    "device": {"api_path": "/device/devices", "tf_type": "logicmonitor_device"},
    "device_group": {"api_path": "/device/groups", "tf_type": "logicmonitor_device_group"},
    "collector": {
        "api_path": "/setting/collector/collectors",
        "tf_type": "logicmonitor_collector",
    },
    "collector_group": {
        "api_path": "/setting/collector/groups",
        "tf_type": "logicmonitor_collector_group",
    },
    "alert_rule": {"api_path": "/setting/alert/rules", "tf_type": "logicmonitor_alert_rule"},
    "escalation_chain": {
        "api_path": "/setting/alert/chains",
        "tf_type": "logicmonitor_escalation_chain",
    },
    "dashboard": {"api_path": "/dashboard/dashboards", "tf_type": "logicmonitor_dashboard"},
    "dashboard_group": {
        "api_path": "/dashboard/groups",
        "tf_type": "logicmonitor_dashboard_group",
    },
    "datasource": {"api_path": "/setting/datasources", "tf_type": "logicmonitor_datasource"},
    "sdt": {"api_path": "/sdt/sdts", "tf_type": "logicmonitor_sdt"},
    "website": {"api_path": "/website/websites", "tf_type": "logicmonitor_website"},
    "website_group": {"api_path": "/website/groups", "tf_type": "logicmonitor_website_group"},
    "role": {"api_path": "/setting/roles", "tf_type": "logicmonitor_role"},
    "report_group": {"api_path": "/report/groups", "tf_type": "logicmonitor_report_group"},
}


def _render_device(data: dict) -> str:
    """Render a LogicMonitor device as Terraform HCL."""
    name = _safe_name(data.get("displayName", data.get("name", "device")))
    lines = [f'resource "logicmonitor_device" "{name}" {{']
    lines.append(f'  ip_addr              = "{data.get("name", "")}"')
    if data.get("displayName"):
        lines.append(f'  display_name         = "{data["displayName"]}"')
    if data.get("preferredCollectorId"):
        lines.append(f"  preferred_collector_id = {data['preferredCollectorId']}")
    if data.get("hostGroupIds"):
        lines.append(f'  host_group_ids       = "{data["hostGroupIds"]}"')
    if data.get("description"):
        desc = data["description"].replace('"', '\\"')
        lines.append(f'  description          = "{desc}"')
    if data.get("disableAlerting"):
        lines.append("  disable_alerting     = true")
    if data.get("enableNetflow"):
        lines.append("  enable_netflow       = true")
    # Custom properties
    props = data.get("customProperties", [])
    for prop in props:
        lines.append("")
        lines.append("  custom_properties {")
        lines.append(f'    name  = "{prop.get("name", "")}"')
        lines.append(f'    value = "{prop.get("value", "")}"')
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


def _render_device_group(data: dict) -> str:
    """Render a LogicMonitor device group as Terraform HCL."""
    name = _safe_name(data.get("name", "group"))
    lines = [f'resource "logicmonitor_device_group" "{name}" {{']
    lines.append(f'  name        = "{data.get("name", "")}"')
    if data.get("parentId"):
        lines.append(f"  parent_id   = {data['parentId']}")
    if data.get("description"):
        desc = data["description"].replace('"', '\\"')
        lines.append(f'  description = "{desc}"')
    if data.get("appliesTo"):
        applies = data["appliesTo"].replace('"', '\\"')
        lines.append(f'  applies_to  = "{applies}"')
    if data.get("disableAlerting"):
        lines.append("  disable_alerting = true")
    if data.get("defaultCollectorId"):
        lines.append(f"  default_collector_id = {data['defaultCollectorId']}")
    props = data.get("customProperties", [])
    for prop in props:
        lines.append("")
        lines.append("  custom_properties {")
        lines.append(f'    name  = "{prop.get("name", "")}"')
        lines.append(f'    value = "{prop.get("value", "")}"')
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


def _render_alert_rule(data: dict) -> str:
    """Render a LogicMonitor alert rule as Terraform HCL."""
    name = _safe_name(data.get("name", "alert_rule"))
    lines = [f'resource "logicmonitor_alert_rule" "{name}" {{']
    lines.append(f'  name     = "{data.get("name", "")}"')
    if data.get("priority") is not None:
        lines.append(f"  priority = {data['priority']}")
    if data.get("escalatingChainId"):
        lines.append(f"  escalation_chain_id = {data['escalatingChainId']}")
    if data.get("levelStr"):
        lines.append(f'  level_str = "{data["levelStr"]}"')
    if data.get("devices"):
        devs = data["devices"].replace('"', '\\"')
        lines.append(f'  devices   = "{devs}"')
    if data.get("deviceGroups"):
        groups = data["deviceGroups"].replace('"', '\\"')
        lines.append(f'  device_groups = "{groups}"')
    if data.get("datasource"):
        lines.append(f'  datasource = "{data["datasource"]}"')
    lines.append("}")
    return "\n".join(lines)


def _render_escalation_chain(data: dict) -> str:
    """Render a LogicMonitor escalation chain as Terraform HCL."""
    name = _safe_name(data.get("name", "chain"))
    lines = [f'resource "logicmonitor_escalation_chain" "{name}" {{']
    lines.append(f'  name = "{data.get("name", "")}"')
    if data.get("enableThrottling"):
        lines.append("  enable_throttling = true")
    if data.get("throttlingPeriod"):
        lines.append(f"  throttling_period = {data['throttlingPeriod']}")
    if data.get("throttlingAlerts"):
        lines.append(f"  throttling_alerts = {data['throttlingAlerts']}")
    lines.append("}")
    return "\n".join(lines)


def _render_generic(data: dict, tf_type: str) -> str:
    """Render any LM resource as commented Terraform HCL with raw data.

    Used for resource types without a dedicated renderer.
    """
    name = _safe_name(data.get("displayName", data.get("name", data.get("id", "resource"))))
    if isinstance(name, int):
        name = f"r_{name}"
    lines = ["# Generated from LM API -- review and adjust field names"]
    lines.append(f'resource "{tf_type}" "{name}" {{')
    # Output key fields as comments for manual mapping
    skip_keys = {"id", "createdOn", "updatedOn", "createdBy", "updatedBy"}
    for key, value in data.items():
        if key in skip_keys:
            continue
        if isinstance(value, str):
            escaped = value.replace('"', '\\"')[:200]
            lines.append(f'  # {key} = "{escaped}"')
        elif isinstance(value, bool):
            lines.append(f"  # {key} = {str(value).lower()}")
        elif isinstance(value, int | float):
            lines.append(f"  # {key} = {value}")
    lines.append("}")
    return "\n".join(lines)


# Map resource types to their renderer functions
_RENDERERS: dict[str, object] = {
    "device": _render_device,
    "device_group": _render_device_group,
    "alert_rule": _render_alert_rule,
    "escalation_chain": _render_escalation_chain,
}


async def terraform_generate(
    client: LogicMonitorClient,
    resource_type: str,
    resource_id: int,
) -> list[TextContent]:
    """Export a LogicMonitor resource as Terraform HCL configuration.

    Fetches the resource from the LM API and renders it as HCL using the
    logicmonitor/logicmonitor Terraform provider schema.

    Args:
        client: LogicMonitor API client.
        resource_type: Resource type (device, device_group, alert_rule, etc.).
        resource_id: LM resource ID.
    """
    try:
        if resource_type not in _RESOURCE_TYPES:
            supported = ", ".join(sorted(_RESOURCE_TYPES.keys()))
            return format_response(
                {
                    "error": True,
                    "code": "UNSUPPORTED_RESOURCE_TYPE",
                    "message": f"Unsupported resource type: '{resource_type}'",
                    "supported_types": supported,
                }
            )

        type_info = _RESOURCE_TYPES[resource_type]
        api_path = f"{type_info['api_path']}/{resource_id}"
        data = await client.get(api_path)

        if not data or "id" not in data:
            return format_response(
                {
                    "error": True,
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"{resource_type} with ID {resource_id} not found",
                }
            )

        renderer = _RENDERERS.get(resource_type)
        hcl = renderer(data) if renderer else _render_generic(data, type_info["tf_type"])

        # Add provider block for convenience
        provider_block = (
            "# LogicMonitor Terraform Provider\n"
            "# Docs: registry.terraform.io/providers/logicmonitor/logicmonitor/latest\n"
            "terraform {\n"
            "  required_providers {\n"
            "    logicmonitor = {\n"
            '      source  = "logicmonitor/logicmonitor"\n'
            "    }\n"
            "  }\n"
            "}\n\n"
            'provider "logicmonitor" {\n'
            "  api_id  = var.lm_api_id\n"
            "  api_key = var.lm_api_key\n"
            "  company = var.lm_company\n"
            "}\n\n"
            'variable "lm_api_id" {\n'
            "  type      = string\n"
            "  sensitive = true\n"
            "}\n\n"
            'variable "lm_api_key" {\n'
            "  type      = string\n"
            "  sensitive = true\n"
            "}\n\n"
            'variable "lm_company" {\n'
            "  type = string\n"
            "}\n"
        )

        full_hcl = f"{provider_block}\n{hcl}\n"

        return format_response(
            {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "terraform_type": type_info["tf_type"],
                "hcl": full_hcl,
            }
        )
    except Exception as e:
        return handle_error(e)
