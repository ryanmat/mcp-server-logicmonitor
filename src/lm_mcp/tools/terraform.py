# Description: Terraform HCL export of LogicMonitor portal resources.
# Description: Renders one resource as configuration for the logicmonitor/logicmonitor provider.

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    # devices and deviceGroups come from the API as lists, not strings
    if data.get("devices"):
        devs = data["devices"]
        if isinstance(devs, list):
            devs = ",".join(str(d) for d in devs)
        devs = str(devs).replace('"', '\\"')
        lines.append(f'  devices   = "{devs}"')
    if data.get("deviceGroups"):
        groups = data["deviceGroups"]
        if isinstance(groups, list):
            groups = ",".join(str(g) for g in groups)
        groups = str(groups).replace('"', '\\"')
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
    # destinations is required by the TF provider
    destinations = data.get("destinations", [])
    if destinations:
        for dest in destinations:
            lines.append("")
            lines.append("  destination {")
            if dest.get("type"):
                lines.append(f'    type   = "{dest["type"]}"')
            if dest.get("addr"):
                addr = str(dest["addr"]).replace('"', '\\"')
                lines.append(f'    addr   = "{addr}"')
            if dest.get("method"):
                lines.append(f'    method = "{dest["method"]}"')
            if dest.get("period") is not None:
                lines.append(f"    period = {dest['period']}")
            if dest.get("stages"):
                stages = dest["stages"]
                if isinstance(stages, list):
                    stages_str = ", ".join(str(s) for s in stages)
                    lines.append(f'    stages = "{stages_str}"')
            lines.append("  }")
    else:
        # Provider requires at least one destination block
        lines.append("")
        lines.append("  # WARNING: no destinations found in API response")
        lines.append("  # Add at least one destination block before applying")
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
                    "code": "INVALID_REQUEST",
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
                    "code": "NOT_FOUND",
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
