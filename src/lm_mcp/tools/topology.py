# Description: Topology mapping tools for LogicMonitor MCP server.
# Description: Provides network topology and relationship data.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_topology_map(
    client: "LogicMonitorClient",
    device_group_id: int | None = None,
    include_connections: bool = True,
    limit: int = 100,
) -> list[TextContent]:
    """Get network topology map data.

    Args:
        client: LogicMonitor API client.
        device_group_id: Filter to specific device group.
        include_connections: Include connection/relationship data.
        limit: Maximum number of nodes to return.

    Returns:
        List of TextContent with topology data or error.
    """
    try:
        params: dict = {"size": limit}

        if device_group_id:
            params["filter"] = f"hostGroupIds~{device_group_id}"

        result = await client.get("/topology/topologies", params=params)

        topologies = []
        for item in result.get("items", []):
            topology = {
                "id": item.get("id"),
                "name": item.get("name"),
                "description": item.get("description"),
                "node_count": item.get("nodeCount"),
                "edge_count": item.get("edgeCount"),
            }
            topologies.append(topology)

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(topologies),
                "topologies": topologies,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_device_neighbors(
    client: "LogicMonitorClient",
    device_id: int,
    depth: int = 1,
) -> list[TextContent]:
    """Get neighboring devices for a specific device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID to find neighbors for.
        depth: How many hops to traverse (1-3).

    Returns:
        List of TextContent with neighbor data or error.
    """
    try:
        params: dict = {"depth": min(depth, 3)}

        result = await client.get(f"/device/devices/{device_id}/neighbors", params=params)

        neighbors = []
        for item in result.get("items", []):
            neighbors.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "display_name": item.get("displayName"),
                    "device_type": item.get("deviceType"),
                    "ip_address": item.get("name"),
                    "connection_type": item.get("connectionType"),
                    "hop_count": item.get("hopCount"),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "depth": depth,
                "total": result.get("total", 0),
                "count": len(neighbors),
                "neighbors": neighbors,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_device_interfaces(
    client: "LogicMonitorClient",
    device_id: int,
    limit: int = 100,
) -> list[TextContent]:
    """Get network interfaces for a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        limit: Maximum number of interfaces to return.

    Returns:
        List of TextContent with interface data or error.
    """
    try:
        params: dict = {"size": limit}

        result = await client.get(
            f"/device/devices/{device_id}/devicedatasources", params=params
        )

        # Filter to interface-related datasources
        interfaces = []
        for item in result.get("items", []):
            ds_name = item.get("dataSourceName", "").lower()
            if any(
                keyword in ds_name
                for keyword in ["interface", "port", "ethernet", "network"]
            ):
                interfaces.append(
                    {
                        "id": item.get("id"),
                        "datasource_id": item.get("dataSourceId"),
                        "datasource_name": item.get("dataSourceName"),
                        "instance_count": item.get("instanceNumber"),
                        "status": item.get("status"),
                    }
                )

        return format_response(
            {
                "device_id": device_id,
                "total": len(interfaces),
                "count": len(interfaces),
                "interfaces": interfaces,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_network_flows(
    client: "LogicMonitorClient",
    device_id: int | None = None,
    source_ip: str | None = None,
    dest_ip: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get network flow data (NetFlow/sFlow).

    Args:
        client: LogicMonitor API client.
        device_id: Filter by exporter device ID.
        source_ip: Filter by source IP address.
        dest_ip: Filter by destination IP address.
        limit: Maximum number of flows to return.

    Returns:
        List of TextContent with flow data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if device_id:
            filters.append(f"exporterDeviceId:{device_id}")
        if source_ip:
            filters.append(f"srcIP:{source_ip}")
        if dest_ip:
            filters.append(f"dstIP:{dest_ip}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/netflow/flows", params=params)

        flows = []
        for item in result.get("items", []):
            flows.append(
                {
                    "id": item.get("id"),
                    "source_ip": item.get("srcIP"),
                    "source_port": item.get("srcPort"),
                    "dest_ip": item.get("dstIP"),
                    "dest_port": item.get("dstPort"),
                    "protocol": item.get("protocol"),
                    "bytes": item.get("bytes"),
                    "packets": item.get("packets"),
                    "exporter_device": item.get("exporterDeviceDisplayName"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(flows),
                "flows": flows,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_device_connections(
    client: "LogicMonitorClient",
    device_id: int,
) -> list[TextContent]:
    """Get all connections/relationships for a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.

    Returns:
        List of TextContent with connection data or error.
    """
    try:
        result = await client.get(f"/device/devices/{device_id}/topologySources")

        connections = []
        for item in result.get("items", []):
            connections.append(
                {
                    "id": item.get("id"),
                    "source_id": item.get("sourceId"),
                    "source_name": item.get("sourceName"),
                    "target_id": item.get("targetId"),
                    "target_name": item.get("targetName"),
                    "connection_type": item.get("type"),
                    "topology_source": item.get("topologySourceName"),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "total": len(connections),
                "count": len(connections),
                "connections": connections,
            }
        )
    except Exception as e:
        return handle_error(e)
