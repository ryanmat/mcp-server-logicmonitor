# Description: Tests for MCP prompt registry.
# Description: Verifies prompt listing and template generation.

from __future__ import annotations

import pytest

from lm_mcp.prompts import PROMPTS, get_prompt_messages


class TestPromptsRegistry:
    """Tests for the PROMPTS list and registry."""

    def test_prompts_list_not_empty(self):
        """PROMPTS list contains prompt definitions."""
        assert len(PROMPTS) > 0

    def test_prompts_have_required_fields(self):
        """Each prompt has name, description, and arguments."""
        for prompt in PROMPTS:
            assert prompt.name is not None
            assert prompt.description is not None

    def test_prompts_names_are_unique(self):
        """All prompt names are unique."""
        names = [p.name for p in PROMPTS]
        assert len(names) == len(set(names))

    def test_incident_triage_prompt_exists(self):
        """incident_triage prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "incident_triage" in names

    def test_capacity_review_prompt_exists(self):
        """capacity_review prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "capacity_review" in names

    def test_health_check_prompt_exists(self):
        """health_check prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "health_check" in names

    def test_alert_summary_prompt_exists(self):
        """alert_summary prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "alert_summary" in names

    def test_sdt_planning_prompt_exists(self):
        """sdt_planning prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "sdt_planning" in names


class TestGetPromptMessages:
    """Tests for get_prompt_messages function."""

    def test_incident_triage_returns_messages(self):
        """get_prompt_messages returns messages for incident_triage."""
        result = get_prompt_messages("incident_triage", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_incident_triage_with_severity(self):
        """incident_triage includes severity in prompt."""
        result = get_prompt_messages("incident_triage", {"severity": "critical"})
        content = str(result.messages[0].content)
        assert "critical" in content.lower()

    def test_capacity_review_returns_messages(self):
        """get_prompt_messages returns messages for capacity_review."""
        result = get_prompt_messages("capacity_review", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_health_check_returns_messages(self):
        """get_prompt_messages returns messages for health_check."""
        result = get_prompt_messages("health_check", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_alert_summary_returns_messages(self):
        """get_prompt_messages returns messages for alert_summary."""
        result = get_prompt_messages("alert_summary", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_sdt_planning_returns_messages(self):
        """get_prompt_messages returns messages for sdt_planning."""
        result = get_prompt_messages("sdt_planning", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_unknown_prompt_raises_error(self):
        """get_prompt_messages raises error for unknown prompt."""
        with pytest.raises(ValueError, match="Unknown prompt"):
            get_prompt_messages("unknown_prompt", {})

    def test_message_has_role(self):
        """Prompt messages have role attribute."""
        result = get_prompt_messages("health_check", {})
        assert hasattr(result.messages[0], "role")
        assert result.messages[0].role == "user"

    def test_message_has_content(self):
        """Prompt messages have content attribute."""
        result = get_prompt_messages("health_check", {})
        assert hasattr(result.messages[0], "content")
