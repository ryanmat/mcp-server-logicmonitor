# Description: Tests for the universal reference layer (get_reference).
# Description: Validates the Resource mirror tool for clients without the Resource primitive.

import json

import pytest

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient


@pytest.fixture
def client():
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=BearerAuth("test-token"),
        timeout=30,
    )


class TestGetReference:
    """Tests for get_reference handler."""

    async def test_list_returns_all_resources(self, client):
        from lm_mcp.resources.registry import RESOURCES
        from lm_mcp.tools.reference import get_reference

        result = await get_reference(client, list=True)
        data = json.loads(result[0].text)

        assert data["count"] == len(RESOURCES)
        assert data["count"] >= 25
        for entry in data["available"]:
            assert "category" in entry
            assert "name" in entry
            assert "description" in entry
        # Make sure we're returning resources, not tools
        names = {e["name"] for e in data["available"]}
        assert "get_alerts" not in names
        assert "alerts" in names  # schema/alerts, filters/alerts, etc.

    async def test_list_default_when_no_args(self, client):
        """Calling with neither category nor name defaults to list mode."""
        from lm_mcp.tools.reference import get_reference

        result = await get_reference(client)
        data = json.loads(result[0].text)
        assert "available" in data
        assert data["count"] > 0

    async def test_dispatch_schema_alerts(self, client):
        from lm_mcp.tools.reference import get_reference

        result = await get_reference(client, category="schema", name="alerts")
        data = json.loads(result[0].text)

        assert data["uri"] == "lm://schema/alerts"
        assert "content" in data
        assert isinstance(data["content"], dict)

    async def test_dispatch_syntax_operators(self, client):
        from lm_mcp.tools.reference import get_reference

        result = await get_reference(client, category="syntax", name="operators")
        data = json.loads(result[0].text)

        assert data["uri"] == "lm://syntax/operators"
        assert isinstance(data["content"], dict)

    async def test_category_without_name_errors(self, client):
        from lm_mcp.tools.reference import get_reference

        result = await get_reference(client, category="schema")
        text = result[0].text

        assert "Error:" in text
        assert "category" in text and "name" in text
        assert "list=true" in text

    async def test_unknown_reference_returns_clean_error(self, client):
        from lm_mcp.tools.reference import get_reference

        result = await get_reference(client, category="schema", name="bogus_name")
        text = result[0].text

        assert "Error:" in text
        assert "list=true" in text
