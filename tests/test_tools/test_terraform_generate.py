# Description: Tests for the terraform_generate tool handler.
# Description: Verifies HCL rendering per resource type against a mocked LM client.

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest


class TestTerraformGenerate:
    @pytest.mark.asyncio
    async def test_device_generation(self):
        from lm_mcp.tools.terraform import terraform_generate

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value={
                "id": 42,
                "name": "192.168.1.1",
                "displayName": "web-server-01",
                "preferredCollectorId": 5,
                "hostGroupIds": "1,2",
                "description": "Primary web server",
                "customProperties": [{"name": "env", "value": "prod"}],
            }
        )
        result = await terraform_generate(mock_client, resource_type="device", resource_id=42)
        data = json.loads(result[0].text)
        assert "hcl" in data
        assert "logicmonitor_device" in data["hcl"]
        assert "web_server_01" in data["hcl"]
        assert "192.168.1.1" in data["hcl"]

    @pytest.mark.asyncio
    async def test_device_group_generation(self):
        from lm_mcp.tools.terraform import terraform_generate

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value={
                "id": 10,
                "name": "Production Servers",
                "parentId": 1,
                "description": "All prod servers",
                "appliesTo": 'system.displayname =~ "prod"',
            }
        )
        result = await terraform_generate(mock_client, resource_type="device_group", resource_id=10)
        data = json.loads(result[0].text)
        assert "logicmonitor_device_group" in data["hcl"]
        assert "Production Servers" in data["hcl"]

    @pytest.mark.asyncio
    async def test_unsupported_type(self):
        from lm_mcp.tools.terraform import terraform_generate

        mock_client = AsyncMock()
        result = await terraform_generate(mock_client, resource_type="invalid_type", resource_id=1)
        assert "unsupported resource type" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_alert_rule_with_list_devices(self):
        """alert_rule renderer handles devices/deviceGroups as lists (API format)."""
        from lm_mcp.tools.terraform import terraform_generate

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value={
                "id": 5,
                "name": "Critical CPU Alert",
                "priority": 100,
                "escalatingChainId": 1,
                "levelStr": "critical",
                "devices": ["server-01", "server-02"],
                "deviceGroups": ["Production", "Web Tier"],
                "datasource": "VMware vSphere Host Performance",
            }
        )
        result = await terraform_generate(mock_client, resource_type="alert_rule", resource_id=5)
        data = json.loads(result[0].text)
        assert "logicmonitor_alert_rule" in data["hcl"]
        assert "server-01,server-02" in data["hcl"]
        assert "Production,Web Tier" in data["hcl"]

    @pytest.mark.asyncio
    async def test_escalation_chain_with_destinations(self):
        """escalation_chain renderer includes destination blocks."""
        from lm_mcp.tools.terraform import terraform_generate

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value={
                "id": 3,
                "name": "Ops Team",
                "enableThrottling": True,
                "throttlingPeriod": 10,
                "throttlingAlerts": 30,
                "destinations": [
                    {"type": "single", "addr": "ops@example.com", "method": "email", "period": 15},
                    {"type": "group", "addr": "NOC", "method": "sms", "period": 30},
                ],
            }
        )
        result = await terraform_generate(
            mock_client, resource_type="escalation_chain", resource_id=3
        )
        data = json.loads(result[0].text)
        hcl = data["hcl"]
        assert "destination {" in hcl
        assert "ops@example.com" in hcl
        assert "NOC" in hcl
        assert hcl.count("destination {") == 2

    @pytest.mark.asyncio
    async def test_generic_renderer_for_sdt(self):
        from lm_mcp.tools.terraform import terraform_generate

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value={
                "id": 99,
                "name": "Weekly maintenance",
                "sdtType": "DeviceSDT",
                "deviceId": 42,
            }
        )
        result = await terraform_generate(mock_client, resource_type="sdt", resource_id=99)
        data = json.loads(result[0].text)
        assert "logicmonitor_sdt" in data["hcl"]
        assert "# Generated from LM API" in data["hcl"]
