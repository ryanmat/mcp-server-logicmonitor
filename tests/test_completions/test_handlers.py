# Description: Tests for MCP completion handlers.
# Description: Verifies argument value auto-completion for prompts and resources.

from __future__ import annotations

from lm_mcp.completions import get_completions
from lm_mcp.completions.registry import (
    COMPLETION_SOURCES,
    get_completion_values,
)


class TestCompletionRegistry:
    """Tests for completion source registry."""

    def test_completion_sources_not_empty(self):
        """COMPLETION_SOURCES contains defined argument completions."""
        assert len(COMPLETION_SOURCES) > 0

    def test_completion_sources_have_required_fields(self):
        """Each completion source has argument_name and values."""
        for source in COMPLETION_SOURCES:
            assert "argument_name" in source
            assert "values" in source
            assert len(source["values"]) > 0

    def test_severity_source_exists(self):
        """Severity completion source is defined."""
        severity = next((s for s in COMPLETION_SOURCES if s["argument_name"] == "severity"), None)
        assert severity is not None
        assert "critical" in severity["values"]
        assert "error" in severity["values"]
        assert "warning" in severity["values"]
        assert "info" in severity["values"]

    def test_status_source_exists(self):
        """Device status completion source is defined."""
        status = next((s for s in COMPLETION_SOURCES if s["argument_name"] == "status"), None)
        assert status is not None
        assert "normal" in status["values"]
        assert "dead" in status["values"]

    def test_sdt_type_source_exists(self):
        """SDT type completion source is defined."""
        sdt_type = next((s for s in COMPLETION_SOURCES if s["argument_name"] == "sdt_type"), None)
        assert sdt_type is not None
        assert "DeviceSDT" in sdt_type["values"]
        assert "DeviceGroupSDT" in sdt_type["values"]


class TestGetCompletionValues:
    """Tests for get_completion_values function."""

    def test_get_severity_values(self):
        """get_completion_values returns severity options."""
        values = get_completion_values("severity")
        assert "critical" in values
        assert "error" in values
        assert "warning" in values
        assert "info" in values

    def test_get_status_values(self):
        """get_completion_values returns status options."""
        values = get_completion_values("status")
        assert "normal" in values
        assert "dead" in values

    def test_get_sdt_type_values(self):
        """get_completion_values returns SDT type options."""
        values = get_completion_values("sdt_type")
        assert "DeviceSDT" in values
        assert "DeviceGroupSDT" in values

    def test_unknown_argument_returns_empty(self):
        """get_completion_values returns empty list for unknown argument."""
        values = get_completion_values("unknown_argument")
        assert values == []


class TestGetCompletions:
    """Tests for the main get_completions function."""

    def test_get_completions_severity_empty_prefix(self):
        """get_completions returns all severity values for empty prefix."""
        result = get_completions("severity", "")
        assert len(result.values) == 4
        assert "critical" in result.values
        assert "error" in result.values
        assert "warning" in result.values
        assert "info" in result.values

    def test_get_completions_severity_with_prefix(self):
        """get_completions filters severity values by prefix."""
        result = get_completions("severity", "cr")
        assert "critical" in result.values
        assert "error" not in result.values

    def test_get_completions_severity_case_insensitive(self):
        """get_completions matches case-insensitively."""
        result = get_completions("severity", "CRIT")
        assert "critical" in result.values

    def test_get_completions_status_prefix(self):
        """get_completions filters status values by prefix."""
        result = get_completions("status", "de")
        assert "dead" in result.values
        assert "dead-collector" in result.values
        assert "normal" not in result.values

    def test_get_completions_sdt_type_prefix(self):
        """get_completions filters SDT types by prefix."""
        result = get_completions("sdt_type", "Device")
        assert "DeviceSDT" in result.values
        assert "DeviceGroupSDT" in result.values
        assert "DeviceDataSourceSDT" in result.values

    def test_get_completions_unknown_argument(self):
        """get_completions returns empty completion for unknown argument."""
        result = get_completions("unknown", "test")
        assert len(result.values) == 0
        assert result.total == 0

    def test_get_completions_has_total(self):
        """get_completions includes total count."""
        result = get_completions("severity", "")
        assert result.total == 4

    def test_get_completions_has_more_false(self):
        """get_completions sets hasMore to False when all values returned."""
        result = get_completions("severity", "")
        assert result.hasMore is False

    def test_get_completions_fuzzy_match(self):
        """get_completions supports fuzzy matching with contains."""
        result = get_completions("status", "collect")
        assert "dead-collector" in result.values


class TestCompletionForFilterFields:
    """Tests for filter field completions."""

    def test_cleared_values(self):
        """cleared argument has boolean string values."""
        values = get_completion_values("cleared")
        assert "true" in values
        assert "false" in values

    def test_acked_values(self):
        """acked argument has boolean string values."""
        values = get_completion_values("acked")
        assert "true" in values
        assert "false" in values

    def test_collector_build_values(self):
        """collector_build argument has build type values."""
        values = get_completion_values("collector_build")
        assert "EA" in values
        assert "GD" in values
        assert "MGD" in values
