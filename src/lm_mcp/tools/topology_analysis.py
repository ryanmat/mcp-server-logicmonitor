# Description: Topology-based analysis tools for LogicMonitor.
# Description: Provides blast radius analysis for downstream impact assessment.

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

logger = logging.getLogger(__name__)

# The report analyze_blast_radius returns, as a JSON Schema.
ANALYZE_BLAST_RADIUS_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "device_id": {"type": "integer"},
        "depth": {"type": "integer"},
        "total_affected_devices": {"type": "integer"},
        "neighbor_count": {"type": "integer"},
        "dependent_count": {"type": "integer"},
        "affected_devices": {"type": "array", "items": {"type": "object"}},
        "critical_path_devices": {"type": "array", "items": {"type": "object"}},
        "critical_alert_count": {"type": "integer"},
        "unreadable": {"type": "array"},
        "warning": {"type": "string"},
        "degraded": {"type": "boolean"},
        "degraded_detail": {"type": "string"},
    },
    "required": [
        "device_id",
        "depth",
        "total_affected_devices",
        "neighbor_count",
        "dependent_count",
        "affected_devices",
        "critical_path_devices",
        "critical_alert_count",
        "unreadable",
    ],
    "additionalProperties": False,
}


async def analyze_blast_radius(
    client: LogicMonitorClient,
    device_id: int,
    depth: int = 2,
) -> list[TextContent]:
    """Count the devices a device failure could reach through its topology neighbors.

    Traverses the device's neighbors up to the specified depth, reading each
    device's neighbors from /topology/devices/{id}/neighbors and then
    /device/devices/{id}/neighbors. A device neither path answers is logged and
    listed under unreadable, so a failed read is never a count of zero; a
    read-only probe of the sandbox portal on 2026-11-09 found neither route.
    Checks the alert status of the devices reached.

    Args:
        client: LogicMonitor API client.
        device_id: ID of the device to analyze.
        depth: Maximum traversal depth (1-3, default: 2).

    Returns:
        neighbor_count (depth 1) and dependent_count (depth 2 and beyond), the
        devices reached with their depth and alert status, critical path devices,
        the critical alert count, and unreadable with a warning when a read failed.
    """
    try:
        depth = min(max(depth, 1), 3)

        # BFS traversal of device neighbors
        visited: set[int] = {device_id}
        affected_devices: list[dict] = []
        current_layer = [device_id]
        neighbor_map: dict[int, list[int]] = defaultdict(list)
        unreadable: list[int] = []

        for current_depth in range(1, depth + 1):
            next_layer = []
            for dev_id in current_layer:
                if len(visited) >= 100:
                    break

                try:
                    result = await client.get(
                        f"/topology/devices/{dev_id}/neighbors",
                        params={"size": 50},
                    )
                    neighbors = result.get("items", [])
                except Exception:
                    logger.debug(
                        "blast radius: topology neighbors read failed for device %s",
                        dev_id,
                        exc_info=True,
                    )
                    try:
                        result = await client.get(
                            f"/device/devices/{dev_id}/neighbors",
                            params={"size": 50},
                        )
                        neighbors = result.get("items", [])
                    except Exception:
                        logger.warning(
                            "blast radius: neighbors of device %s unreadable on both paths",
                            dev_id,
                            exc_info=True,
                        )
                        unreadable.append(dev_id)
                        neighbors = []

                for neighbor in neighbors:
                    n_id = neighbor.get("id", neighbor.get("deviceId"))
                    if n_id is None:
                        continue
                    n_id = int(n_id)

                    neighbor_map[dev_id].append(n_id)

                    if n_id not in visited:
                        visited.add(n_id)
                        next_layer.append(n_id)
                        affected_devices.append(
                            {
                                "device_id": n_id,
                                "device_name": neighbor.get(
                                    "displayName",
                                    neighbor.get("name", f"device-{n_id}"),
                                ),
                                "depth": current_depth,
                            }
                        )

            current_layer = next_layer
            if not current_layer:
                break

        # Check alert status of affected devices (cap at 50)
        devices_to_check = affected_devices[:50]
        critical_alert_count = 0
        alert_check_failures = 0
        for dev in devices_to_check:
            try:
                # Each device's own alert list: /alert/alerts ignores a device id filter.
                alert_result = await client.get(
                    f"/device/devices/{dev['device_id']}/alerts",
                    params={"filter": "cleared:false", "size": 5},
                )
                dev_alerts = alert_result.get("items", [])
                dev["active_alert_count"] = len(dev_alerts)
                dev["has_critical"] = any(a.get("severity", 0) >= 4 for a in dev_alerts)
                if dev["has_critical"]:
                    critical_alert_count += 1
            except Exception:
                logger.exception(
                    "blast radius: alert lookup failed for device %s", dev["device_id"]
                )
                alert_check_failures += 1
                dev["active_alert_count"] = None
                dev["has_critical"] = None
                dev["alert_status_unavailable"] = True

        # Identify critical path devices (appear as neighbors of multiple devices)
        path_counts: dict[int, int] = defaultdict(int)
        for neighbors in neighbor_map.values():
            for n_id in neighbors:
                path_counts[n_id] += 1

        critical_path_devices = [
            {
                "device_id": dev["device_id"],
                "device_name": dev["device_name"],
                "connection_count": path_counts.get(dev["device_id"], 0),
            }
            for dev in affected_devices
            if path_counts.get(dev["device_id"], 0) >= 2
        ]

        neighbor_count = sum(1 for dev in affected_devices if dev["depth"] == 1)

        response: dict = {
            "device_id": device_id,
            "depth": depth,
            "total_affected_devices": len(affected_devices),
            "neighbor_count": neighbor_count,
            "dependent_count": len(affected_devices) - neighbor_count,
            "affected_devices": affected_devices,
            "critical_path_devices": critical_path_devices,
            "critical_alert_count": critical_alert_count,
            "unreadable": unreadable,
        }
        if unreadable:
            response["warning"] = (
                f"Neighbors of {len(unreadable)} device(s) could not be read on either "
                "topology path; the counts cover only the devices read."
            )
        if alert_check_failures:
            response["degraded"] = True
            response["degraded_detail"] = (
                f"{alert_check_failures} alert lookup(s) failed; the critical counts may be "
                "understated."
            )
        return format_response(response)
    except Exception as e:
        return handle_error(e)
