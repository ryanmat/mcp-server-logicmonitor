# Description: Tests for composite workflow tools.
# Description: Validates triage, health_check, capacity_plan, portal_overview, diagnose.

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools.workflows import (
    _resolve_device,
    _trim_detail,
    capacity_plan,
    check_required_tools,
    diagnose,
    health_check,
    portal_overview,
    search_tools,
    triage,
)


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


# ---------------------------------------------------------------------------
# Helpers for building mock sub-tool responses
# ---------------------------------------------------------------------------

def _mock_text(data: dict) -> list:
    """Build a list matching the TextContent return format of tool handlers."""
    from mcp.types import TextContent

    return [TextContent(type="text", text=json.dumps(data))]


def _patch_sub(module_path: str, data: dict) -> patch:
    """Return an AsyncMock patch that returns TextContent wrapping *data*."""
    return patch(module_path, new_callable=AsyncMock, return_value=_mock_text(data))


# ---------------------------------------------------------------------------
# TestCheckRequiredTools
# ---------------------------------------------------------------------------


class TestCheckRequiredTools:
    """Tests for check_required_tools utility."""

    def test_all_tools_pass_returns_none(self, monkeypatch):
        """When no filtering is configured, all tools pass."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = check_required_tools(["get_alerts", "correlate_alerts"])
        assert result is None
        reset_config()

    def test_blocked_with_enabled_tools(self, monkeypatch):
        """Tools not matching LM_ENABLED_TOOLS are blocked."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_alerts,get_devices")
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = check_required_tools(["get_alerts", "correlate_alerts"])
        assert result is not None
        text = result[0].text
        assert "correlate_alerts" in text
        reset_config()

    def test_blocked_with_disabled_tools(self, monkeypatch):
        """Tools matching LM_DISABLED_TOOLS are blocked."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "correlate_*")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = check_required_tools(["get_alerts", "correlate_alerts"])
        assert result is not None
        text = result[0].text
        assert "correlate_alerts" in text
        reset_config()


# ---------------------------------------------------------------------------
# TestResolveDevice
# ---------------------------------------------------------------------------


class TestResolveDevice:
    """Tests for _resolve_device utility."""

    async def test_resolve_by_id(self, client):
        """Resolving by device_id calls get_device."""
        mock_device = {"id": 42, "displayName": "server-01"}
        with _patch_sub("lm_mcp.tools.devices.get_device", mock_device):
            dev_id, dev_data = await _resolve_device(client, device_id=42)
        assert dev_id == 42
        assert dev_data["displayName"] == "server-01"

    async def test_resolve_by_name(self, client):
        """Resolving by device_name calls get_devices and returns first match."""
        mock_result = {"devices": [{"id": 99, "displayName": "web-01"}]}
        with _patch_sub("lm_mcp.tools.devices.get_devices", mock_result):
            dev_id, dev_data = await _resolve_device(client, device_name="web-01")
        assert dev_id == 99

    async def test_not_found_raises(self, client):
        """Raises ValueError when no device matches the name."""
        mock_result = {"devices": []}
        with _patch_sub("lm_mcp.tools.devices.get_devices", mock_result):
            with pytest.raises(ValueError, match="No device found"):
                await _resolve_device(client, device_name="ghost")

    async def test_missing_params_raises(self, client):
        """Raises ValueError when neither device_id nor device_name given."""
        with pytest.raises(ValueError, match="Either device_id or device_name"):
            await _resolve_device(client)


# ---------------------------------------------------------------------------
# TestTrimDetail
# ---------------------------------------------------------------------------


class TestTrimDetail:
    """Tests for _trim_detail utility."""

    def test_summary_strips_keys(self):
        report = {"a": 1, "b": 2, "c": 3}
        trimmed = _trim_detail(report, "summary", {"b", "c"})
        assert trimmed == {"a": 1}

    def test_full_keeps_all(self):
        report = {"a": 1, "b": 2, "c": 3}
        trimmed = _trim_detail(report, "full", {"b", "c"})
        assert trimmed == report


# ---------------------------------------------------------------------------
# TestTriage
# ---------------------------------------------------------------------------


class TestTriage:
    """Tests for the triage composite tool."""

    async def test_happy_path_summary(self, client, monkeypatch):
        """Triage returns a report with expected keys in summary mode."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        stats_data = {"summary": {"total": 5}, "time_buckets": []}
        clusters_data = {"total_alerts": 5, "clusters": [], "cluster_count": 0}
        noise_data = {"noise_score": 10, "total_alerts": 5}
        changes_data = {"correlated_events": [], "total_alerts": 5}

        with (
            _patch_sub("lm_mcp.tools.correlation.get_alert_statistics", stats_data),
            _patch_sub("lm_mcp.tools.correlation.correlate_alerts", clusters_data),
            _patch_sub("lm_mcp.tools.scoring.score_alert_noise", noise_data),
            _patch_sub("lm_mcp.tools.event_correlation.correlate_changes", changes_data),
        ):
            result = await triage(client, detail_level="summary")

        data = json.loads(result[0].text)
        assert "statistics" in data
        assert "noise" in data
        # blast_radius stripped in summary mode
        assert "blast_radius" not in data
        reset_config()

    async def test_happy_path_full(self, client, monkeypatch):
        """Triage full mode includes blast_radius."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        stats_data = {"summary": {"total": 0}, "time_buckets": []}
        clusters_data = {"total_alerts": 0, "clusters": [], "cluster_count": 0}
        noise_data = {"noise_score": 0, "total_alerts": 0}
        changes_data = {"correlated_events": [], "total_alerts": 0}

        with (
            _patch_sub("lm_mcp.tools.correlation.get_alert_statistics", stats_data),
            _patch_sub("lm_mcp.tools.correlation.correlate_alerts", clusters_data),
            _patch_sub("lm_mcp.tools.scoring.score_alert_noise", noise_data),
            _patch_sub("lm_mcp.tools.event_correlation.correlate_changes", changes_data),
        ):
            result = await triage(client, detail_level="full")

        data = json.loads(result[0].text)
        assert "blast_radius" in data
        reset_config()

    async def test_required_tool_blocked(self, client, monkeypatch):
        """Triage returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "correlate_alerts")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = await triage(client)
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or "correlate_alerts" in text
        reset_config()

    async def test_sub_tool_failure_partial_results(self, client, monkeypatch):
        """Triage returns partial results with warnings when a sub-tool fails."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        clusters_data = {"total_alerts": 0, "clusters": [], "cluster_count": 0}
        noise_data = {"noise_score": 0, "total_alerts": 0}
        changes_data = {"correlated_events": [], "total_alerts": 0}

        with (
            patch(
                "lm_mcp.tools.correlation.get_alert_statistics",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API timeout"),
            ),
            _patch_sub("lm_mcp.tools.correlation.correlate_alerts", clusters_data),
            _patch_sub("lm_mcp.tools.scoring.score_alert_noise", noise_data),
            _patch_sub("lm_mcp.tools.event_correlation.correlate_changes", changes_data),
        ):
            result = await triage(client, detail_level="full")

        data = json.loads(result[0].text)
        assert data["statistics"] is None
        assert "warnings" in data
        reset_config()


# ---------------------------------------------------------------------------
# TestHealthCheck
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Tests for the health_check composite tool."""

    async def test_happy_path_summary(self, client, monkeypatch):
        """Health check returns expected keys in summary mode."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        ds_data = {"datasources": [{"id": 10, "name": "CPU"}]}
        inst_data = {"instances": [{"id": 100, "name": "main"}]}
        score_data = {"health_score": 85, "status": "healthy"}
        anomaly_data = {"anomaly_count": 0, "anomalies": []}
        alert_data = {"total": 0, "alerts": []}
        avail_data = {"availability_percent": 99.99}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_datasources", ds_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_instances", inst_data),
            _patch_sub("lm_mcp.tools.scoring.score_device_health", score_data),
            _patch_sub("lm_mcp.tools.correlation.get_metric_anomalies", anomaly_data),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alert_data),
            _patch_sub("lm_mcp.tools.scoring.calculate_availability", avail_data),
        ):
            result = await health_check(client, device_id=1, detail_level="summary")

        data = json.loads(result[0].text)
        assert data["device_id"] == 1
        assert "datasource_count" in data
        # anomalies and health_scores stripped in summary
        assert "anomalies" not in data
        assert "health_scores" not in data
        reset_config()

    async def test_happy_path_full(self, client, monkeypatch):
        """Health check full mode includes anomalies and health_scores."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        ds_data = {"datasources": [{"id": 10, "name": "CPU"}]}
        inst_data = {"instances": [{"id": 100, "name": "main"}]}
        score_data = {"health_score": 85, "status": "healthy"}
        anomaly_data = {"anomaly_count": 0, "anomalies": []}
        alert_data = {"total": 0, "alerts": []}
        avail_data = {"availability_percent": 99.99}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_datasources", ds_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_instances", inst_data),
            _patch_sub("lm_mcp.tools.scoring.score_device_health", score_data),
            _patch_sub("lm_mcp.tools.correlation.get_metric_anomalies", anomaly_data),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alert_data),
            _patch_sub("lm_mcp.tools.scoring.calculate_availability", avail_data),
        ):
            result = await health_check(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert "anomalies" in data
        assert "health_scores" in data
        reset_config()

    async def test_required_tool_blocked(self, client, monkeypatch):
        """Health check returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "get_device_datasources")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = await health_check(client, device_id=1)
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or "get_device_datasources" in text
        reset_config()

    async def test_sub_tool_failure(self, client, monkeypatch):
        """Health check returns partial results with warnings on sub-tool failure."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        alert_data = {"total": 0, "alerts": []}
        avail_data = {"availability_percent": 99.99}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            patch(
                "lm_mcp.tools.metrics.get_device_datasources",
                new_callable=AsyncMock,
                side_effect=RuntimeError("timeout"),
            ),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alert_data),
            _patch_sub("lm_mcp.tools.scoring.calculate_availability", avail_data),
        ):
            result = await health_check(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert data["datasource_count"] == 0
        assert "warnings" in data
        reset_config()


# ---------------------------------------------------------------------------
# TestCapacityPlan
# ---------------------------------------------------------------------------


class TestCapacityPlan:
    """Tests for the capacity_plan composite tool."""

    async def test_happy_path_summary(self, client, monkeypatch):
        """Capacity plan returns expected keys in summary mode."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        ds_data = {"datasources": [{"id": 10, "name": "CPU"}]}
        inst_data = {"instances": [{"id": 100, "name": "main"}]}
        forecast_data = {"forecasts": {"cpu": {"trend": "increasing"}}}
        trend_data = {"classifications": {"cpu": {"classification": "stable"}}}
        season_data = {"seasonality": {"cpu": {"is_seasonal": False}}}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_datasources", ds_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_instances", inst_data),
            _patch_sub("lm_mcp.tools.forecasting.forecast_metric", forecast_data),
            _patch_sub("lm_mcp.tools.forecasting.classify_trend", trend_data),
            _patch_sub("lm_mcp.tools.forecasting.detect_seasonality", season_data),
        ):
            result = await capacity_plan(
                client, device_id=1, detail_level="summary",
            )

        data = json.loads(result[0].text)
        assert data["device_id"] == 1
        # datasources stripped in summary mode
        assert "datasources" not in data
        reset_config()

    async def test_happy_path_full(self, client, monkeypatch):
        """Capacity plan full mode includes datasources."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        ds_data = {"datasources": [{"id": 10, "name": "CPU"}]}
        inst_data = {"instances": [{"id": 100, "name": "main"}]}
        forecast_data = {"forecasts": {"cpu": {"trend": "increasing"}}}
        trend_data = {"classifications": {"cpu": {"classification": "stable"}}}
        season_data = {"seasonality": {"cpu": {"is_seasonal": False}}}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_datasources", ds_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_instances", inst_data),
            _patch_sub("lm_mcp.tools.forecasting.forecast_metric", forecast_data),
            _patch_sub("lm_mcp.tools.forecasting.classify_trend", trend_data),
            _patch_sub("lm_mcp.tools.forecasting.detect_seasonality", season_data),
        ):
            result = await capacity_plan(
                client, device_id=1, detail_level="full",
            )

        data = json.loads(result[0].text)
        assert "datasources" in data
        assert len(data["datasources"]) == 1
        reset_config()

    async def test_required_tool_blocked(self, client, monkeypatch):
        """Capacity plan returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "forecast_metric")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = await capacity_plan(client, device_id=1)
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or "forecast_metric" in text
        reset_config()

    async def test_empty_datasources(self, client, monkeypatch):
        """Capacity plan handles a device with no datasources gracefully."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        ds_data = {"datasources": []}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_datasources", ds_data),
        ):
            result = await capacity_plan(
                client, device_id=1, detail_level="full",
            )

        data = json.loads(result[0].text)
        assert data["datasources"] == []
        reset_config()


# ---------------------------------------------------------------------------
# TestPortalOverview
# ---------------------------------------------------------------------------


class TestPortalOverview:
    """Tests for the portal_overview composite tool."""

    async def test_happy_path_summary(self, client, monkeypatch):
        """Portal overview returns expected keys in summary mode."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        stats_data = {"summary": {"total": 10}}
        alert_data = {"total": 2, "alerts": []}
        coll_data = {"total": 3, "collectors": []}
        sdt_data = {"active_sdts": []}
        cluster_data = {"clusters": [], "total_alerts": 0}
        noise_data = {"noise_score": 5}
        dead_data = {"devices": [], "total": 0}

        with (
            _patch_sub("lm_mcp.tools.correlation.get_alert_statistics", stats_data),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alert_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", coll_data),
            _patch_sub("lm_mcp.tools.sdts.get_active_sdts", sdt_data),
            _patch_sub("lm_mcp.tools.correlation.correlate_alerts", cluster_data),
            _patch_sub("lm_mcp.tools.scoring.score_alert_noise", noise_data),
            _patch_sub("lm_mcp.tools.devices.get_devices", dead_data),
        ):
            result = await portal_overview(client, detail_level="summary")

        data = json.loads(result[0].text)
        assert "alert_statistics" in data
        assert "noise" in data
        # summary strips detail lists
        assert "critical_alerts" not in data
        assert "dead_devices" not in data
        reset_config()

    async def test_happy_path_full(self, client, monkeypatch):
        """Portal overview full mode includes all keys."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        stats_data = {"summary": {"total": 10}}
        alert_data = {"total": 2, "alerts": []}
        coll_data = {"total": 3, "collectors": []}
        sdt_data = {"active_sdts": []}
        cluster_data = {"clusters": [], "total_alerts": 0}
        noise_data = {"noise_score": 5}
        dead_data = {"devices": [], "total": 0}

        with (
            _patch_sub("lm_mcp.tools.correlation.get_alert_statistics", stats_data),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alert_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", coll_data),
            _patch_sub("lm_mcp.tools.sdts.get_active_sdts", sdt_data),
            _patch_sub("lm_mcp.tools.correlation.correlate_alerts", cluster_data),
            _patch_sub("lm_mcp.tools.scoring.score_alert_noise", noise_data),
            _patch_sub("lm_mcp.tools.devices.get_devices", dead_data),
        ):
            result = await portal_overview(client, detail_level="full")

        data = json.loads(result[0].text)
        assert "critical_alerts" in data
        assert "dead_devices" in data
        reset_config()

    async def test_required_tool_blocked(self, client, monkeypatch):
        """Portal overview returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "get_collectors")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = await portal_overview(client)
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or "get_collectors" in text
        reset_config()


# ---------------------------------------------------------------------------
# TestDiagnose
# ---------------------------------------------------------------------------


class TestDiagnose:
    """Tests for the diagnose composite tool."""

    async def test_happy_path_with_alert_id(self, client, monkeypatch):
        """Diagnose by alert_id returns expected keys."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        alert_detail = {
            "id": "LMA123",
            "severity": 4,
            "monitorObjectId": 42,
            "monitorObjectName": "server-01",
        }
        device_data = {"id": 42, "displayName": "server-01"}
        props_data = {"properties": [{"name": "os", "value": "linux"}]}
        corr_data = {"clusters": [], "total_alerts": 1}
        changes_data = {"correlated_events": []}
        blast_data = {"blast_radius_score": 10, "affected_devices": []}

        with (
            _patch_sub("lm_mcp.tools.alerts.get_alert_details", alert_detail),
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.resources.get_device_properties", props_data),
            _patch_sub("lm_mcp.tools.correlation.correlate_alerts", corr_data),
            _patch_sub("lm_mcp.tools.event_correlation.correlate_changes", changes_data),
            _patch_sub("lm_mcp.tools.topology_analysis.analyze_blast_radius", blast_data),
        ):
            result = await diagnose(client, alert_id="LMA123", detail_level="full")

        data = json.loads(result[0].text)
        assert data.get("alert", {}).get("id") == "LMA123"
        assert "device" in data
        assert "blast_radius" in data
        reset_config()

    async def test_happy_path_with_device_name(self, client, monkeypatch):
        """Diagnose by device_name resolves most recent critical alert."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        alerts_list = {"total": 1, "alerts": [{"id": "LMA456", "severity": 4}]}
        alert_detail = {
            "id": "LMA456",
            "severity": 4,
            "monitorObjectId": 55,
        }
        device_data = {"id": 55, "displayName": "db-01"}
        props_data = {"properties": []}
        corr_data = {"clusters": []}
        changes_data = {"correlated_events": []}
        blast_data = {"blast_radius_score": 0, "affected_devices": []}

        with (
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alerts_list),
            _patch_sub("lm_mcp.tools.alerts.get_alert_details", alert_detail),
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.resources.get_device_properties", props_data),
            _patch_sub("lm_mcp.tools.correlation.correlate_alerts", corr_data),
            _patch_sub("lm_mcp.tools.event_correlation.correlate_changes", changes_data),
            _patch_sub("lm_mcp.tools.topology_analysis.analyze_blast_radius", blast_data),
        ):
            result = await diagnose(client, device_name="db-01", detail_level="full")

        data = json.loads(result[0].text)
        assert data.get("alert", {}).get("id") == "LMA456"
        reset_config()

    async def test_missing_params(self, client, monkeypatch):
        """Diagnose returns error when neither alert_id nor device_name given."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = await diagnose(client)
        text = result[0].text
        assert "MISSING_PARAMS" in text or "alert_id or device_name" in text
        reset_config()

    async def test_required_tool_blocked(self, client, monkeypatch):
        """Diagnose returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "analyze_blast_radius")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config
        reset_config()

        result = await diagnose(client, alert_id="LMA123")
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or "analyze_blast_radius" in text
        reset_config()


# ---------------------------------------------------------------------------
# TestSearchTools
# ---------------------------------------------------------------------------


class TestSearchTools:
    """Tests for the search_tools discovery tool."""

    async def test_keyword_name_match(self, client):
        """Searching for a tool name returns it with high score."""
        result = await search_tools(client, query="get_alerts")
        data = json.loads(result[0].text)
        matches = data["matches"]
        assert len(matches) > 0
        # The exact name match should be first
        assert matches[0]["name"] == "get_alerts"

    async def test_description_match(self, client):
        """Searching for a word in descriptions returns relevant tools."""
        result = await search_tools(client, query="forecast")
        data = json.loads(result[0].text)
        assert data["total"] > 0
        tool_names = [m["name"] for m in data["matches"]]
        assert "forecast_metric" in tool_names

    async def test_category_filter(self, client):
        """Category filter restricts results to that category's tools."""
        result = await search_tools(client, query="alert", category="alerts")
        data = json.loads(result[0].text)
        # All results should be from the alerts category
        alert_tools = {
            "get_alerts", "get_alert_details", "acknowledge_alert",
            "add_alert_note", "bulk_acknowledge_alerts",
        }
        for match in data["matches"]:
            assert match["name"] in alert_tools

    async def test_limit(self, client):
        """Limit parameter caps the number of results."""
        result = await search_tools(client, query="get", limit=3)
        data = json.loads(result[0].text)
        assert len(data["matches"]) <= 3

    async def test_composite_suggestion(self, client):
        """Workflow-related queries suggest composite tools."""
        result = await search_tools(client, query="incident triage")
        data = json.loads(result[0].text)
        suggestions = data.get("suggestions") or []
        assert "triage" in suggestions or "diagnose" in suggestions

    async def test_no_matches(self, client):
        """Non-matching query returns empty results."""
        result = await search_tools(client, query="xyznonexistent123")
        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["matches"] == []

    async def test_invalid_category(self, client):
        """Invalid category returns empty results with available categories."""
        result = await search_tools(
            client, query="alert", category="nonexistent_cat",
        )
        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert "available_categories" in data
