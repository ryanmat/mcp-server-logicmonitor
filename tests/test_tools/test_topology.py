# Description: Tests for Topology mapping MCP tools.
# Description: Validates network topology functions.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient


@pytest.fixture
def auth():
    """Create a BearerAuth instance for testing."""
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
        api_version=3,
    )


class TestGetTopologyMap:
    """Tests for get_topology_map tool."""

    @respx.mock
    async def test_get_topology_map_returns_list(self, client):
        """get_topology_map returns topology data."""
        from lm_mcp.tools.topology import get_topology_map

        respx.get("https://test.logicmonitor.com/santaba/rest/topology/topologies").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Network Topology",
                            "description": "Main network map",
                            "nodeCount": 50,
                            "edgeCount": 100,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_topology_map(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["topologies"][0]["name"] == "Network Topology"
        assert data["topologies"][0]["node_count"] == 50


class TestGetDeviceNeighbors:
    """Tests for get_device_neighbors tool."""

    @respx.mock
    async def test_get_device_neighbors_returns_neighbors(self, client):
        """get_device_neighbors returns neighboring devices."""
        from lm_mcp.tools.topology import get_device_neighbors

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/123/neighbors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 456,
                            "name": "192.168.1.2",
                            "displayName": "router-01",
                            "deviceType": "router",
                            "connectionType": "ethernet",
                            "hopCount": 1,
                        },
                        {
                            "id": 789,
                            "name": "192.168.1.3",
                            "displayName": "switch-01",
                            "deviceType": "switch",
                            "connectionType": "ethernet",
                            "hopCount": 1,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_device_neighbors(client, device_id=123, depth=1)

        data = json.loads(result[0].text)
        assert data["device_id"] == 123
        assert data["total"] == 2
        assert len(data["neighbors"]) == 2


class TestGetDeviceInterfaces:
    """Tests for get_device_interfaces tool."""

    @respx.mock
    async def test_get_device_interfaces_filters_interfaces(self, client):
        """get_device_interfaces returns only interface datasources."""
        from lm_mcp.tools.topology import get_device_interfaces

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/123/devicedatasources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "dataSourceId": 100,
                            "dataSourceName": "SNMP_Network_Interfaces",
                            "instanceNumber": 10,
                            "status": "active",
                        },
                        {
                            "id": 2,
                            "dataSourceId": 200,
                            "dataSourceName": "CPU",
                            "instanceNumber": 1,
                            "status": "active",
                        },
                        {
                            "id": 3,
                            "dataSourceId": 300,
                            "dataSourceName": "Ethernet_Ports",
                            "instanceNumber": 24,
                            "status": "active",
                        },
                    ],
                    "total": 3,
                },
            )
        )

        result = await get_device_interfaces(client, device_id=123)

        data = json.loads(result[0].text)
        assert data["device_id"] == 123
        # Should only include interface-related datasources (not CPU)
        assert data["count"] == 2


class TestGetNetworkFlows:
    """Tests for get_network_flows tool."""

    @respx.mock
    async def test_get_network_flows_returns_flows(self, client):
        """get_network_flows returns flow data."""
        from lm_mcp.tools.topology import get_network_flows

        respx.get("https://test.logicmonitor.com/santaba/rest/netflow/flows").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "srcIP": "192.168.1.100",
                            "srcPort": 443,
                            "dstIP": "10.0.0.50",
                            "dstPort": 8080,
                            "protocol": "TCP",
                            "bytes": 1024000,
                            "packets": 1000,
                            "exporterDeviceDisplayName": "router-01",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_network_flows(client)

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["flows"][0]["source_ip"] == "192.168.1.100"
        assert data["flows"][0]["bytes"] == 1024000


class TestGetDeviceConnections:
    """Tests for get_device_connections tool."""

    @respx.mock
    async def test_get_device_connections_returns_connections(self, client):
        """get_device_connections returns device relationships."""
        from lm_mcp.tools.topology import get_device_connections

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/123/topologySources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "sourceId": 123,
                            "sourceName": "server-01",
                            "targetId": 456,
                            "targetName": "switch-01",
                            "type": "physical",
                            "topologySourceName": "LLDP",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_device_connections(client, device_id=123)

        data = json.loads(result[0].text)
        assert data["device_id"] == 123
        assert data["total"] == 1
        assert data["connections"][0]["target_name"] == "switch-01"
