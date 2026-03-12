# Description: Tests for example response resources.
# Description: Validates example data structure and resource resolution.

from __future__ import annotations

import json

from lm_mcp.resources import RESOURCES, get_resource_content
from lm_mcp.resources.examples import get_example_responses
from lm_mcp.resources.registry import get_resource_by_uri

EXPECTED_EXAMPLE_TOOLS = [
    "get_alerts",
    "get_devices",
    "get_device_data",
    "score_device_health",
    "calculate_availability",
    "correlate_alerts",
    "forecast_metric",
]


class TestExampleResponses:
    """Tests for example response data structure."""

    def test_structure_has_all_example_tools(self):
        """Example data includes all 7 expected tools."""
        data = get_example_responses()
        examples = data["examples"]
        for tool_name in EXPECTED_EXAMPLE_TOOLS:
            assert tool_name in examples, f"Missing example for {tool_name}"

    def test_example_count_is_seven(self):
        """Exactly 7 tool examples are present."""
        data = get_example_responses()
        assert len(data["examples"]) == 7

    def test_each_example_has_description_and_example(self):
        """Each tool example has description and example keys."""
        data = get_example_responses()
        for tool_name, tool_data in data["examples"].items():
            assert "description" in tool_data, (
                f"{tool_name} missing description"
            )
            assert "example" in tool_data, (
                f"{tool_name} missing example"
            )

    def test_top_level_has_name_and_description(self):
        """Top-level dict has name and description fields."""
        data = get_example_responses()
        assert data["name"] == "example-responses"
        assert "description" in data

    def test_resource_resolves_at_uri(self):
        """lm://guide/example-responses returns valid JSON."""
        content = get_resource_content("lm://guide/example-responses")
        data = json.loads(content)
        assert data["name"] == "example-responses"
        assert "examples" in data

    def test_alerts_example_has_alerts_list(self):
        """get_alerts example contains an alerts list."""
        data = get_example_responses()
        example = data["examples"]["get_alerts"]["example"]
        assert "alerts" in example
        assert len(example["alerts"]) == 3

    def test_forecast_example_has_forecasts(self):
        """forecast_metric example contains forecasts dict."""
        data = get_example_responses()
        example = data["examples"]["forecast_metric"]["example"]
        assert "forecasts" in example
        assert "UsedPercent" in example["forecasts"]


class TestExampleResourceRegistry:
    """Tests for example-responses resource registration."""

    def test_resource_registered(self):
        """example-responses resource exists in registry."""
        resource = get_resource_by_uri("lm://guide/example-responses")
        assert resource is not None
        assert resource.name == "Example Tool Responses"

    def test_resource_count_is_26(self):
        """Total resource count is 26 after adding example-responses."""
        assert len(RESOURCES) == 26

    def test_all_guide_resources_loadable(self):
        """All guide resources return valid JSON."""
        guide_uris = [str(r.uri) for r in RESOURCES if "/guide/" in str(r.uri)]
        assert len(guide_uris) == 5
        for uri in guide_uris:
            content = get_resource_content(uri)
            data = json.loads(content)
            assert isinstance(data, dict)
