# Description: Terraform import discovery for LogicMonitor portal objects.
# Description: Lists one resource type's objects as import blocks for the LogicMonitor provider.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import list_tool, validation_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# The resources of logicmonitor/logicmonitor v2.1.7 whose docs carry an Import section by
# object ID, less the one in _UNIMPORTABLE: the path that lists a type's objects, and the row
# fields that name one, the first present field winning.
IMPORTABLE_TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "alert_rule": ("/setting/alert/rules", ("name",)),
    "collector": ("/setting/collector/collectors", ("description", "hostname")),
    "collector_group": ("/setting/collector/groups", ("name",)),
    "dashboard": ("/dashboard/dashboards", ("name",)),
    "dashboard_group": ("/dashboard/groups", ("name",)),
    "datasource": ("/setting/datasources", ("name",)),
    "device": ("/device/devices", ("displayName", "name")),
    "device_group": ("/device/groups", ("name",)),
    "escalation_chain": ("/setting/alert/chains", ("name",)),
    "report_group": ("/report/groups", ("name",)),
    "role": ("/setting/roles", ("name",)),
    "sdt": ("/sdt/sdts", ("type",)),
    "website": ("/website/websites", ("name",)),
    "website_group": ("/website/groups", ("name",)),
    "widget": ("/dashboard/widgets", ("name",)),
}

# A documented import this tool leaves out, and why. The API answered
# GET /device/groups/0/clusterAlertConf/{id} with 404 on 2026-11-13, and the provider's v2.1.7
# importer reads a cluster alert conf by ID through that path, setting no device group.
_UNIMPORTABLE = {
    "device_group_cluster_alert_conf": (
        "the provider's importer (2.1.7) reads a cluster alert conf by ID without its device "
        "group, and the API answers that read with 404"
    ),
}

NEXT_STEP = (
    "Write the import blocks to a .tf file beside a required_providers entry with "
    'source = "logicmonitor/logicmonitor" and a provider "logicmonitor" block, run '
    "`terraform init`, then `terraform plan -generate-config-out=generated.tf` (Terraform 1.5 or "
    "later) to have Terraform write the matching resource blocks. The provider authenticates with "
    "an LMv1 api_id and api_key (LM_API_ID, LM_API_KEY) and company (LM_COMPANY), not a bearer "
    "token."
)


def _safe_name(raw: str) -> str:
    """Convert a display name to a valid Terraform resource name.

    Replaces non-alphanumeric characters with underscores, folds repeated and
    edge underscores, lowercases, and prefixes r_ to a name that starts with a
    digit, so the result is a valid HCL identifier; an empty result is resource.
    """
    name = re.sub(r"[^a-zA-Z0-9_]", "_", raw).strip("_").lower()
    name = re.sub(r"_+", "_", name)
    if name and name[0].isdigit():
        name = f"r_{name}"
    return name or "resource"


def _import_entry(resource_type: str, fields: tuple[str, ...], row: dict[str, Any]) -> dict:
    """One object as its import block. The object's ID ends the address, so names that two
    objects share, or that differ only in punctuation, still give distinct addresses."""
    name = next((row[field] for field in fields if row.get(field)), None)
    label = f"{name or resource_type} {row['id']}"
    to = f"logicmonitor_{resource_type}.{_safe_name(label)}"
    return {
        "id": row["id"],
        "name": name,
        "to": to,
        "import": f'import {{\n  to = {to}\n  id = "{row["id"]}"\n}}',
    }


async def get_terraform_imports(
    client: LogicMonitorClient,
    resource_type: str,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List a resource type's portal objects as Terraform import blocks.

    Args:
        client: LogicMonitor API client.
        resource_type: One of the 15 provider resource types this tool serves.
        filter: LogicMonitor filter expression, sent as written.
        limit: Page size.
        offset: Rows to skip.

    Returns:
        List of TextContent with one import block per object, or error.
    """
    if resource_type not in IMPORTABLE_TYPES:
        reason = _UNIMPORTABLE.get(resource_type, "it has no Terraform import")
        return validation_error(
            "INVALID_REQUEST",
            f"'{resource_type}' is not served: {reason}. Types: {', '.join(IMPORTABLE_TYPES)}.",
        )
    path, fields = IMPORTABLE_TYPES[resource_type]
    return await list_tool(
        client,
        path,
        key="imports",
        project=lambda row: _import_entry(resource_type, fields, row),
        limit=limit,
        offset=offset,
        filter=filter,
        extra={"resource_type": resource_type, "next_step": NEXT_STEP},
    )
