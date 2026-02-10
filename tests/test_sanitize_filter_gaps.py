# Description: Tests verifying all string filter params use sanitize_filter_value.
# Description: Ensures wildcard characters are stripped from all string filter parameters.

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


class TestAuditSanitizeGaps:
    """Tests for sanitize gaps in audit.py."""

    @respx.mock
    async def test_get_audit_logs_username_wildcard_stripped(self, client):
        """get_audit_logs strips wildcards from username filter."""
        from lm_mcp.tools.audit import get_audit_logs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_audit_logs(client, username="admin*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_audit_logs_username_clean_no_note(self, client):
        """get_audit_logs does not add note for clean username."""
        from lm_mcp.tools.audit import get_audit_logs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_audit_logs(client, username="admin")

        data = json.loads(result[0].text)
        assert "note" not in data

    @respx.mock
    async def test_get_audit_logs_action_wildcard_stripped(self, client):
        """get_audit_logs strips wildcards from action filter."""
        from lm_mcp.tools.audit import get_audit_logs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_audit_logs(client, action="login*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_audit_logs_action_clean_no_note(self, client):
        """get_audit_logs does not add note for clean action."""
        from lm_mcp.tools.audit import get_audit_logs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_audit_logs(client, action="login")

        data = json.loads(result[0].text)
        assert "note" not in data

    @respx.mock
    async def test_get_login_audit_username_wildcard_stripped(self, client):
        """get_login_audit strips wildcards from username filter."""
        from lm_mcp.tools.audit import get_login_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_login_audit(client, username="admin*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_login_audit_username_clean_no_note(self, client):
        """get_login_audit does not add note for clean username."""
        from lm_mcp.tools.audit import get_login_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_login_audit(client, username="admin")

        data = json.loads(result[0].text)
        assert "note" not in data

    @respx.mock
    async def test_get_change_audit_change_type_wildcard_stripped(self, client):
        """get_change_audit strips wildcards from change_type filter."""
        from lm_mcp.tools.audit import get_change_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_change_audit(client, change_type="create*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_change_audit_change_type_clean_no_note(self, client):
        """get_change_audit does not add note for clean change_type."""
        from lm_mcp.tools.audit import get_change_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_change_audit(client, change_type="create")

        data = json.loads(result[0].text)
        assert "note" not in data


class TestCostSanitizeGaps:
    """Tests for sanitize gaps in cost.py."""

    @respx.mock
    async def test_get_cloud_cost_accounts_provider_wildcard_stripped(self, client):
        """get_cloud_cost_accounts strips wildcards from provider filter."""
        from lm_mcp.tools.cost import get_cloud_cost_accounts

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/cloudaccounts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_cloud_cost_accounts(client, provider="aws*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_cloud_cost_accounts_provider_clean_no_note(self, client):
        """get_cloud_cost_accounts does not add note for clean provider."""
        from lm_mcp.tools.cost import get_cloud_cost_accounts

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/cloudaccounts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_cloud_cost_accounts(client, provider="aws")

        data = json.loads(result[0].text)
        assert "note" not in data

    @respx.mock
    async def test_get_cost_recommendations_type_wildcard_stripped(self, client):
        """get_cost_recommendations strips wildcards from recommendation_type filter."""
        from lm_mcp.tools.cost import get_cost_recommendations

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/recommendations").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_cost_recommendations(client, recommendation_type="idle*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_cost_recommendations_type_clean_no_note(self, client):
        """get_cost_recommendations does not add note for clean recommendation_type."""
        from lm_mcp.tools.cost import get_cost_recommendations

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/recommendations").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_cost_recommendations(client, recommendation_type="idle")

        data = json.loads(result[0].text)
        assert "note" not in data

    @respx.mock
    async def test_get_idle_resources_type_wildcard_stripped(self, client):
        """get_idle_resources strips wildcards from resource_type filter."""
        from lm_mcp.tools.cost import get_idle_resources

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/resources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_idle_resources(client, resource_type="ec2*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_idle_resources_type_clean_no_note(self, client):
        """get_idle_resources does not add note for clean resource_type."""
        from lm_mcp.tools.cost import get_idle_resources

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/resources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_idle_resources(client, resource_type="ec2")

        data = json.loads(result[0].text)
        assert "note" not in data


class TestBatchjobsSanitizeGaps:
    """Tests for sanitize gaps in batchjobs.py."""

    @respx.mock
    async def test_get_batchjobs_status_wildcard_stripped(self, client):
        """get_batchjobs strips wildcards from status filter."""
        from lm_mcp.tools.batchjobs import get_batchjobs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/batchjobs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_batchjobs(client, status="active*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_batchjobs_status_clean_no_note(self, client):
        """get_batchjobs does not add note for clean status."""
        from lm_mcp.tools.batchjobs import get_batchjobs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/batchjobs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_batchjobs(client, status="active")

        data = json.loads(result[0].text)
        assert "note" not in data


class TestSdtsSanitizeGaps:
    """Tests for sanitize gaps in sdts.py."""

    @respx.mock
    async def test_list_sdts_sdt_type_wildcard_stripped(self, client):
        """list_sdts strips wildcards from sdt_type filter."""
        from lm_mcp.tools.sdts import list_sdts

        respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await list_sdts(client, sdt_type="Device*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_list_sdts_sdt_type_clean_no_note(self, client):
        """list_sdts does not add note for clean sdt_type."""
        from lm_mcp.tools.sdts import list_sdts

        respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await list_sdts(client, sdt_type="DeviceSDT")

        data = json.loads(result[0].text)
        assert "note" not in data


class TestTopologySanitizeGaps:
    """Tests for sanitize gaps in topology.py."""

    @respx.mock
    async def test_get_network_flows_source_ip_wildcard_stripped(self, client):
        """get_network_flows strips wildcards from source_ip filter."""
        from lm_mcp.tools.topology import get_network_flows

        respx.get("https://test.logicmonitor.com/santaba/rest/netflow/flows").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_network_flows(client, source_ip="192.168.*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_network_flows_source_ip_clean_no_note(self, client):
        """get_network_flows does not add note for clean source_ip."""
        from lm_mcp.tools.topology import get_network_flows

        respx.get("https://test.logicmonitor.com/santaba/rest/netflow/flows").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_network_flows(client, source_ip="192.168.1.1")

        data = json.loads(result[0].text)
        assert "note" not in data

    @respx.mock
    async def test_get_network_flows_dest_ip_wildcard_stripped(self, client):
        """get_network_flows strips wildcards from dest_ip filter."""
        from lm_mcp.tools.topology import get_network_flows

        respx.get("https://test.logicmonitor.com/santaba/rest/netflow/flows").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_network_flows(client, dest_ip="10.0.0.*")

        data = json.loads(result[0].text)
        assert "note" in data
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_get_network_flows_dest_ip_clean_no_note(self, client):
        """get_network_flows does not add note for clean dest_ip."""
        from lm_mcp.tools.topology import get_network_flows

        respx.get("https://test.logicmonitor.com/santaba/rest/netflow/flows").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_network_flows(client, dest_ip="10.0.0.1")

        data = json.loads(result[0].text)
        assert "note" not in data
