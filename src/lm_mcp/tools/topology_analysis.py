# Description: Topology-based analysis tools for LogicMonitor.
# Description: Provides blast radius analysis for downstream impact assessment.

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def analyze_blast_radius(
    client: "LogicMonitorClient",
    device_id: int,
    depth: int = 2,
) -> list[TextContent]:
    """Analyze the blast radius of a device failure using topology data.

    Traverses the device's neighbors up to the specified depth to identify
    all potentially affected downstream devices. Checks alert status of
    affected devices and scores the overall blast radius.

    Args:
        client: LogicMonitor API client.
        device_id: ID of the device to analyze.
        depth: Maximum traversal depth (1-3, default: 2).

    Returns:
        Blast radius score, affected devices list, and critical path devices.
    """
    try:
        depth = min(max(depth, 1), 3)

        # BFS traversal of device neighbors
        visited: set[int] = {device_id}
        affected_devices: list[dict] = []
        current_layer = [device_id]
        neighbor_map: dict[int, list[int]] = defaultdict(list)

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
                    # If topology endpoint fails, try device neighbors
                    try:
                        result = await client.get(
                            f"/device/devices/{dev_id}/neighbors",
                            params={"size": 50},
                        )
                        neighbors = result.get("items", [])
                    except Exception:
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
                        affected_devices.append({
                            "device_id": n_id,
                            "device_name": neighbor.get(
                                "displayName",
                                neighbor.get("name", f"device-{n_id}"),
                            ),
                            "depth": current_depth,
                        })

            current_layer = next_layer
            if not current_layer:
                break

        # Check alert status of affected devices (cap at 50)
        devices_to_check = affected_devices[:50]
        critical_alert_count = 0
        for dev in devices_to_check:
            try:
                alert_result = await client.get(
                    "/alert/alerts",
                    params={
                        "filter": (
                            f"monitorObjectId:{dev['device_id']},"
                            "cleared:false"
                        ),
                        "size": 5,
                    },
                )
                dev_alerts = alert_result.get("items", [])
                dev["active_alert_count"] = len(dev_alerts)
                dev["has_critical"] = any(
                    a.get("severity", 0) >= 4 for a in dev_alerts
                )
                if dev["has_critical"]:
                    critical_alert_count += 1
            except Exception:
                dev["active_alert_count"] = 0
                dev["has_critical"] = False

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

        # Blast radius score (0-100)
        affected_count = len(affected_devices)
        blast_radius_score = min(
            100,
            affected_count * 10
            + critical_alert_count * 15
            + len(critical_path_devices) * 20,
        )

        return format_response({
            "device_id": device_id,
            "depth": depth,
            "total_affected_devices": affected_count,
            "blast_radius_score": blast_radius_score,
            "affected_devices": affected_devices,
            "critical_path_devices": critical_path_devices,
            "critical_alert_count": critical_alert_count,
        })
    except Exception as e:
        return handle_error(e)
