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

    def test_cost_optimization_prompt_exists(self):
        """cost_optimization prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "cost_optimization" in names

    def test_audit_review_prompt_exists(self):
        """audit_review prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "audit_review" in names

    def test_alert_correlation_prompt_exists(self):
        """alert_correlation prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "alert_correlation" in names

    def test_collector_health_prompt_exists(self):
        """collector_health prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "collector_health" in names

    def test_troubleshoot_device_prompt_exists(self):
        """troubleshoot_device prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "troubleshoot_device" in names

    def test_top_talkers_prompt_exists(self):
        """top_talkers prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "top_talkers" in names

    def test_rca_workflow_prompt_exists(self):
        """rca_workflow prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "rca_workflow" in names

    def test_capacity_forecast_prompt_exists(self):
        """capacity_forecast prompt is defined."""
        names = [p.name for p in PROMPTS]
        assert "capacity_forecast" in names

    def test_total_prompt_count(self):
        """All 13 prompts are registered."""
        assert len(PROMPTS) == 13


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

    def test_cost_optimization_returns_messages(self):
        """get_prompt_messages returns messages for cost_optimization."""
        result = get_prompt_messages("cost_optimization", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_cost_optimization_includes_time_range(self):
        """cost_optimization includes time_range argument in content."""
        result = get_prompt_messages("cost_optimization", {"time_range": "7d"})
        content = str(result.messages[0].content)
        assert "7d" in content

    def test_audit_review_returns_messages(self):
        """get_prompt_messages returns messages for audit_review."""
        result = get_prompt_messages("audit_review", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_audit_review_includes_username(self):
        """audit_review includes username argument in content."""
        result = get_prompt_messages("audit_review", {"username": "admin"})
        content = str(result.messages[0].content)
        assert "admin" in content

    def test_alert_correlation_returns_messages(self):
        """get_prompt_messages returns messages for alert_correlation."""
        result = get_prompt_messages("alert_correlation", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_collector_health_returns_messages(self):
        """get_prompt_messages returns messages for collector_health."""
        result = get_prompt_messages("collector_health", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_troubleshoot_device_returns_messages(self):
        """get_prompt_messages returns messages for troubleshoot_device."""
        result = get_prompt_messages("troubleshoot_device", {"device_id": "42"})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_troubleshoot_device_includes_device_id(self):
        """troubleshoot_device includes device_id argument in content."""
        result = get_prompt_messages("troubleshoot_device", {"device_id": "42"})
        content = str(result.messages[0].content)
        assert "42" in content

    # Top Talkers prompt tests

    def test_top_talkers_returns_messages(self):
        """get_prompt_messages returns messages for top_talkers."""
        result = get_prompt_messages("top_talkers", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_top_talkers_includes_hours_back(self):
        """top_talkers includes hours_back argument."""
        result = get_prompt_messages("top_talkers", {"hours_back": "12"})
        content = str(result.messages[0].content)
        assert "12" in content

    def test_top_talkers_includes_limit(self):
        """top_talkers includes limit argument."""
        result = get_prompt_messages("top_talkers", {"limit": "5"})
        content = str(result.messages[0].content)
        assert "5" in content

    def test_top_talkers_mentions_get_alert_statistics(self):
        """top_talkers references the get_alert_statistics tool."""
        result = get_prompt_messages("top_talkers", {})
        content = str(result.messages[0].content)
        assert "get_alert_statistics" in content

    # RCA Workflow prompt tests

    def test_rca_workflow_returns_messages(self):
        """get_prompt_messages returns messages for rca_workflow."""
        result = get_prompt_messages("rca_workflow", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_rca_workflow_with_device_id(self):
        """rca_workflow includes device_id argument."""
        result = get_prompt_messages("rca_workflow", {"device_id": "99"})
        content = str(result.messages[0].content)
        assert "99" in content

    def test_rca_workflow_with_alert_id(self):
        """rca_workflow includes alert_id argument."""
        result = get_prompt_messages("rca_workflow", {"alert_id": "LMA555"})
        content = str(result.messages[0].content)
        assert "LMA555" in content

    def test_rca_workflow_mentions_correlate_alerts(self):
        """rca_workflow references the correlate_alerts tool."""
        result = get_prompt_messages("rca_workflow", {})
        content = str(result.messages[0].content)
        assert "correlate_alerts" in content

    def test_rca_workflow_mentions_decision_branches(self):
        """rca_workflow includes decision branches for investigation."""
        result = get_prompt_messages("rca_workflow", {})
        content = str(result.messages[0].content)
        assert "topology" in content.lower() or "config" in content.lower()

    # Capacity Forecast prompt tests

    def test_capacity_forecast_returns_messages(self):
        """get_prompt_messages returns messages for capacity_forecast."""
        result = get_prompt_messages("capacity_forecast", {})
        assert result.messages is not None
        assert len(result.messages) > 0

    def test_capacity_forecast_with_device_id(self):
        """capacity_forecast includes device_id argument."""
        result = get_prompt_messages("capacity_forecast", {"device_id": "77"})
        content = str(result.messages[0].content)
        assert "77" in content

    def test_capacity_forecast_includes_datasource(self):
        """capacity_forecast includes datasource argument."""
        result = get_prompt_messages("capacity_forecast", {"datasource": "Memory"})
        content = str(result.messages[0].content)
        assert "Memory" in content

    def test_capacity_forecast_mentions_get_metric_anomalies(self):
        """capacity_forecast references the get_metric_anomalies tool."""
        result = get_prompt_messages("capacity_forecast", {})
        content = str(result.messages[0].content)
        assert "get_metric_anomalies" in content

    # Enhanced alert_correlation tests

    def test_enhanced_alert_correlation_mentions_correlate_alerts(self):
        """Enhanced alert_correlation references the correlate_alerts tool."""
        result = get_prompt_messages("alert_correlation", {})
        content = str(result.messages[0].content)
        assert "correlate_alerts" in content

    def test_enhanced_alert_correlation_with_device_id(self):
        """alert_correlation includes device_id argument."""
        result = get_prompt_messages("alert_correlation", {"device_id": "33"})
        content = str(result.messages[0].content)
        assert "33" in content

    def test_enhanced_alert_correlation_with_group_id(self):
        """alert_correlation includes group_id argument."""
        result = get_prompt_messages("alert_correlation", {"group_id": "7"})
        content = str(result.messages[0].content)
        assert "7" in content

    def test_enhanced_alert_correlation_mentions_get_alert_statistics(self):
        """Enhanced alert_correlation references the get_alert_statistics tool."""
        result = get_prompt_messages("alert_correlation", {})
        content = str(result.messages[0].content)
        assert "get_alert_statistics" in content
