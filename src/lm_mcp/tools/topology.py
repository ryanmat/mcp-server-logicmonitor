# Description: Topology mapping tools for LogicMonitor MCP server.
# Description: Provides network topology and relationship data.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# DataSources whose name holds one of interface, port, ethernet or network; the device
# DataSource list matches ~ case-insensitively and | between values as OR.
_INTERFACE_DATASOURCE_CLAUSE = 'dataSourceName~"interface"|"port"|"ethernet"|"network"'


def _topology_row(item: dict) -> dict:
    """Project one /topology/topologies row onto the get_topology_map fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "node_count": item.get("nodeCount"),
        "edge_count": item.get("edgeCount"),
    }


async def get_topology_map(
    client: LogicMonitorClient,
    include_connections: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[TextContent]:
    """Get network topology map data.

    Args:
        client: LogicMonitor API client.
        include_connections: Include connection/relationship data.
        limit: Maximum number of nodes to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with topology data or error.
    """
    return await list_tool(
        client,
        "/topology/topologies",
        key="topologies",
        project=_topology_row,
        limit=limit,
        offset=offset,
    )


async def get_device_neighbors(
    client: LogicMonitorClient,
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


def _interface_row(item: dict) -> dict:
    """Project one devicedatasources row onto the get_device_interfaces fields."""
    return {
        "id": item.get("id"),
        "datasource_id": item.get("dataSourceId"),
        "datasource_name": item.get("dataSourceName"),
        "instance_count": item.get("instanceNumber"),
        "status": item.get("status"),
    }


async def get_device_interfaces(
    client: LogicMonitorClient,
    device_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[TextContent]:
    """Get network interfaces for a device.

    The portal returns the device's DataSources whose name contains interface,
    port, ethernet or network, so limit and offset page through those only.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        limit: Maximum number of interfaces to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with interface data or error.
    """
    return await list_tool(
        client,
        f"/device/devices/{device_id}/devicedatasources",
        key="interfaces",
        project=_interface_row,
        limit=limit,
        offset=offset,
        clauses=[_INTERFACE_DATASOURCE_CLAUSE],
        extra={"device_id": device_id},
    )


def _flow_row(item: dict) -> dict:
    """Project one /netflow/flows row onto the get_network_flows fields."""
    return {
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


async def get_network_flows(
    client: LogicMonitorClient,
    device_id: int | None = None,
    source_ip: str | None = None,
    dest_ip: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get network flow data (NetFlow/sFlow).

    Args:
        client: LogicMonitor API client.
        device_id: Filter by exporter device ID.
        source_ip: Filter by source IP address.
        dest_ip: Filter by destination IP address.
        limit: Maximum number of flows to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with flow data or error.
    """
    return await list_tool(
        client,
        "/netflow/flows",
        key="flows",
        project=_flow_row,
        limit=limit,
        offset=offset,
        named={"srcIP:": source_ip, "dstIP:": dest_ip},
        clauses=[f"exporterDeviceId:{device_id}"] if device_id else [],
    )


async def get_device_connections(
    client: LogicMonitorClient,
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
