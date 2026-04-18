# Description: Tests for the universal reference layer (get_reference, get_workflow).
# Description: Validates Resource/Prompt mirror tools and the _TEMPLATES hoist.

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
        api_version=3,
    )


class TestGetReference:
    """Tests for get_reference handler."""

    async def test_list_returns_all_resources(self, client):
        from lm_mcp.resources.registry import RESOURCES
        from lm_mcp.tools.reference import get_reference

        result = await get_reference(client, list=True)
        data = json.loads(result[0].text)

        assert data["count"] == len(RESOURCES)
        assert data["count"] >= 26
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


class TestGetWorkflow:
    """Tests for get_workflow handler."""

    async def test_list_returns_all_prompts(self, client):
        from lm_mcp.prompts.registry import PROMPTS
        from lm_mcp.tools.reference import get_workflow

        result = await get_workflow(client, list=True)
        data = json.loads(result[0].text)

        assert data["count"] == len(PROMPTS)
        assert data["count"] >= 15
        for entry in data["available"]:
            assert "name" in entry
            assert "description" in entry
            assert "arguments" in entry
            assert isinstance(entry["arguments"], list)

    async def test_incident_triage_returns_text(self, client):
        from lm_mcp.tools.reference import get_workflow

        result = await get_workflow(
            client,
            name="incident_triage",
            arguments={"severity": "critical"},
        )
        data = json.loads(result[0].text)

        assert data["name"] == "incident_triage"
        assert isinstance(data["text"], str)
        assert len(data["text"]) > 0

    async def test_unknown_workflow_returns_clean_error(self, client):
        from lm_mcp.tools.reference import get_workflow

        result = await get_workflow(client, name="bogus_workflow")
        text = result[0].text

        assert "Error:" in text
        assert "bogus_workflow" in text
        assert "list=true" in text

    async def test_list_default_when_no_name(self, client):
        """Calling without name defaults to list mode."""
        from lm_mcp.tools.reference import get_workflow

        result = await get_workflow(client)
        data = json.loads(result[0].text)
        assert "available" in data


class TestTemplatesHoistBackwardsCompat:
    """Guards against drift in the _TEMPLATES hoist."""

    def test_templates_module_level_matches_prompts(self):
        """_TEMPLATES keys must equal PROMPTS names."""
        from lm_mcp.prompts.registry import _TEMPLATES, PROMPTS

        assert set(_TEMPLATES.keys()) == {p.name for p in PROMPTS}

    def test_get_prompt_messages_still_works(self):
        """The existing public API path must continue to work after the hoist."""
        from lm_mcp.prompts.registry import get_prompt_messages

        result = get_prompt_messages("incident_triage", {"severity": "critical"})
        assert result.description == "LogicMonitor incident triage workflow"
        assert len(result.messages) == 1
        text = result.messages[0].content.text
        assert isinstance(text, str)
        assert len(text) > 0

    def test_get_prompt_messages_unknown_still_raises_value_error(self):
        from lm_mcp.prompts.registry import get_prompt_messages

        with pytest.raises(ValueError, match="Unknown prompt"):
            get_prompt_messages("bogus_prompt", {})
