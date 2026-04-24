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
            dev_id, _dev_data = await _resolve_device(client, device_name="web-01")
        assert dev_id == 99

    async def test_not_found_raises(self, client):
        """Raises ValueError when no device matches the name."""
        mock_result = {"devices": []}
        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", mock_result),
            pytest.raises(ValueError, match="No device found"),
        ):
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
                client,
                device_id=1,
                detail_level="summary",
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
                client,
                device_id=1,
                detail_level="full",
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
                client,
                device_id=1,
                detail_level="full",
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
            "get_alerts",
            "get_alert_details",
            "acknowledge_alert",
            "add_alert_note",
            "bulk_acknowledge_alerts",
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
            client,
            query="alert",
            category="nonexistent_cat",
        )
        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert "available_categories" in data


# ---------------------------------------------------------------------------
# TestSiteOutageHelpers (shape compatibility with get_devices formatted output)
# ---------------------------------------------------------------------------


class TestSiteOutageHelpers:
    """Direct tests for _collector_ids_from_devices and _count_dead_devices.

    These helpers receive output from the formatted `get_devices` sub-tool
    (which renames `currentCollectorId` -> `collector_id` and `hostStatus`
    -> `status`). The helpers must handle both shapes.
    """

    def test_collector_ids_from_formatted_shape(self):
        """Formatted get_devices output uses `collector_id`."""
        from lm_mcp.tools.workflows import _collector_ids_from_devices

        devices = [
            {"id": 1, "collector_id": 10},
            {"id": 2, "collector_id": 10},  # duplicate
            {"id": 3, "collector_id": 20},
            {"id": 4, "collector_id": None},  # unassigned
        ]
        assert _collector_ids_from_devices(devices) == [10, 20]

    def test_collector_ids_from_raw_shape(self):
        """Raw LM API items use `currentCollectorId`."""
        from lm_mcp.tools.workflows import _collector_ids_from_devices

        devices = [
            {"id": 1, "currentCollectorId": 11},
            {"id": 2, "preferredCollectorId": 22},
        ]
        assert _collector_ids_from_devices(devices) == [11, 22]

    def test_collector_ids_empty(self):
        """No collector fields present returns empty list."""
        from lm_mcp.tools.workflows import _collector_ids_from_devices

        assert _collector_ids_from_devices([{"id": 1}]) == []

    def test_dead_devices_counts_status_1_and_2(self):
        """Both hostStatus=1 (dead) and hostStatus=2 (dead-collector) count."""
        from lm_mcp.tools.workflows import _count_dead_devices

        devices = [
            {"id": 1, "status": 0},  # normal
            {"id": 2, "status": 1},  # dead
            {"id": 3, "status": 2},  # dead-collector
            {"id": 4, "status": 3},  # unmonitored, not counted
        ]
        assert _count_dead_devices(devices) == 2

    def test_dead_devices_accepts_raw_host_status_field(self):
        """Raw LM API shape uses `hostStatus` not `status`."""
        from lm_mcp.tools.workflows import _count_dead_devices

        devices = [
            {"id": 1, "hostStatus": 1},
            {"id": 2, "hostStatus": 2},
            {"id": 3, "hostStatus": 0},
        ]
        assert _count_dead_devices(devices) == 2

    def test_dead_devices_falls_back_to_alert_status(self):
        """When hostStatus absent, alertStatus strings still flag dead devices."""
        from lm_mcp.tools.workflows import _count_dead_devices

        devices = [
            {"id": 1, "alertStatus": "dead"},
            {"id": 2, "alertStatus": "dead-collector"},
            {"id": 3, "alertStatus": "normal"},
        ]
        assert _count_dead_devices(devices) == 2


# ---------------------------------------------------------------------------
# TestDetectSiteOutage
# ---------------------------------------------------------------------------


class TestDetectSiteOutage:
    """Tests for the detect_site_outage composite."""

    @pytest.fixture(autouse=True)
    def _reset_config(self, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_MCP_CATEGORIES", raising=False)
        from lm_mcp.config import reset_config

        reset_config()
        yield
        reset_config()

    async def test_all_signals_trigger_site_outage_detected(self, client):
        """CollectorDown + burst + power + silence → verdict = site_outage_detected.

        Uses the formatted `get_devices` shape (`status`, `collector_id`) that
        the composite actually receives from the sub-tool dispatch.
        """
        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {"devices": [{"id": i, "status": 1, "collector_id": 1} for i in range(10)]}
        collector_data = {
            "total_collectors": 1,
            "collectors_down": 1,
            "collectors": [{"id": 1, "hostname": "col-01", "is_down": True}],
        }
        burst_data = {
            "bursts_detected": 1,
            "bursts": [{"datasource": "SNMP_Network_Interfaces", "alert_count": 20}],
        }
        power_data = {
            "total_power_events": 3,
            "events": [
                {"id": 1, "datasource": "APC_UPS_Battery"},
                {"id": 2, "datasource": "APC_UPS_Battery"},
                {"id": 3, "datasource": "Liebert_UPS"},
            ],
        }

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collector_health", collector_data),
            _patch_sub("lm_mcp.tools.networking.detect_alert_burst", burst_data),
            _patch_sub("lm_mcp.tools.networking.get_power_events", power_data),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["verdict"] == "site_outage_detected"
        assert data["confidence"] == 100
        assert data["signals"]["collector_down"]["triggered"] is True
        assert data["signals"]["interface_burst"]["triggered"] is True
        assert data["signals"]["power_events"]["triggered"] is True

    async def test_no_signals_returns_no_outage(self, client):
        """Clean state → verdict = no_outage_signature."""
        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {"devices": [{"id": 1, "status": 0, "collector_id": 1}]}
        collector_data = {
            "total_collectors": 1,
            "collectors_down": 0,
            "collectors": [{"id": 1, "hostname": "col-01", "is_down": False}],
        }
        burst_data = {"bursts_detected": 0, "bursts": []}
        power_data = {"total_power_events": 0, "events": []}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collector_health", collector_data),
            _patch_sub("lm_mcp.tools.networking.detect_alert_burst", burst_data),
            _patch_sub("lm_mcp.tools.networking.get_power_events", power_data),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["verdict"] == "no_outage_signature"
        assert data["confidence"] == 0

    async def test_possible_outage_at_boundary(self, client):
        """Burst + power (no collector down) → 50 confidence → possible_site_outage."""
        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {"devices": [{"id": 1, "status": 0, "collector_id": 1}]}
        collector_data = {
            "total_collectors": 1,
            "collectors_down": 0,
            "collectors": [{"id": 1, "hostname": "col-01", "is_down": False}],
        }
        burst_data = {"bursts_detected": 1, "bursts": []}
        power_data = {"total_power_events": 2, "events": []}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collector_health", collector_data),
            _patch_sub("lm_mcp.tools.networking.detect_alert_burst", burst_data),
            _patch_sub("lm_mcp.tools.networking.get_power_events", power_data),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["verdict"] == "possible_site_outage"
        assert data["confidence"] == 50

    async def test_sub_tool_failure_appends_warning(self, client):
        """Failure in one sub-tool is captured as warning, composite continues."""
        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {"devices": [{"id": 1, "status": 1, "collector_id": 1}]}

        async def failing_mock(*args, **kwargs):
            raise RuntimeError("sub-tool exploded")

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            patch(
                "lm_mcp.tools.collectors.get_collector_health",
                new_callable=AsyncMock,
                side_effect=failing_mock,
            ),
            _patch_sub(
                "lm_mcp.tools.networking.detect_alert_burst",
                {"bursts_detected": 0, "bursts": []},
            ),
            _patch_sub(
                "lm_mcp.tools.networking.get_power_events",
                {"total_power_events": 0, "events": []},
            ),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert len(data["warnings"]) >= 1
        assert any("Collector health" in w for w in data["warnings"])
        # No CollectorDown signal → collector_down triggered is False
        assert data["signals"]["collector_down"]["triggered"] is False

    async def test_required_tools_disabled_blocks_composite(self, client, monkeypatch):
        """LM_DISABLED_TOOLS matching a required sub-tool blocks execution."""
        from lm_mcp.config import reset_config
        from lm_mcp.tools.workflows import detect_site_outage

        monkeypatch.setenv("LM_DISABLED_TOOLS", "detect_alert_burst")
        reset_config()

        result = await detect_site_outage(client, group_id=42)
        assert "requires disabled tools" in result[0].text
        assert "detect_alert_burst" in result[0].text
        reset_config()


# ---------------------------------------------------------------------------
# TestAuditNetworkMonitoringCoverage
# ---------------------------------------------------------------------------


class TestAuditNetworkMonitoringCoverage:
    """Tests for the audit_network_monitoring_coverage composite."""

    @pytest.fixture(autouse=True)
    def _reset_config(self, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_MCP_CATEGORIES", raising=False)
        from lm_mcp.config import reset_config

        reset_config()
        yield
        reset_config()

    async def test_reports_power_gap_when_no_ups_devices(self, client):
        """No UPS/PDU → high-severity power gap."""
        from lm_mcp.tools.workflows import audit_network_monitoring_coverage

        devices_data = {
            "devices": [
                {
                    "id": 1,
                    "displayName": "core-switch-01",
                    "systemCategories": "switch,network",
                    "customProperties": [{"name": "snmp.version", "value": "v2c"}],
                },
                {
                    "id": 2,
                    "displayName": "core-switch-02",
                    "systemCategories": "switch,network",
                    "customProperties": [{"name": "snmp.version", "value": "v2c"}],
                },
            ]
        }
        collectors_data = {"collectors": [{"id": 1, "hostname": "col-01", "status": "normal"}]}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", collectors_data),
        ):
            result = await audit_network_monitoring_coverage(client, group_id=1)

        data = json.loads(result[0].text)
        power_gaps = [g for g in data["gaps"] if g["category"] == "power"]
        assert len(power_gaps) == 1
        assert power_gaps[0]["severity"] == "high"
        assert data["inventory"]["total_devices"] == 2
        assert data["coverage_counts"]["snmp_credentialed"] == 2

    async def test_flags_missing_netflow_exporters(self, client):
        """No NetFlow exporters on network gear → medium netflow gap."""
        from lm_mcp.tools.workflows import audit_network_monitoring_coverage

        devices_data = {
            "devices": [
                {
                    "id": 1,
                    "displayName": "router-01",
                    "systemCategories": "router",
                    "customProperties": [{"name": "snmp.version", "value": "v2c"}],
                }
            ]
        }
        collectors_data = {"collectors": [{"id": 1, "status": "normal"}]}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", collectors_data),
        ):
            result = await audit_network_monitoring_coverage(client)

        data = json.loads(result[0].text)
        netflow_gaps = [g for g in data["gaps"] if g["category"] == "netflow"]
        assert len(netflow_gaps) == 1

    async def test_power_coverage_healthy_when_ups_present(self, client):
        """UPS device present → no power gap."""
        from lm_mcp.tools.workflows import audit_network_monitoring_coverage

        devices_data = {
            "devices": [
                {
                    "id": 1,
                    "displayName": "ups-01",
                    "systemCategories": "ups",
                    "customProperties": [],
                }
            ]
        }
        collectors_data = {"collectors": [{"id": 1, "status": "normal"}]}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", collectors_data),
        ):
            result = await audit_network_monitoring_coverage(client)

        data = json.loads(result[0].text)
        assert data["coverage_counts"]["power_monitored_devices"] == 1
        power_gaps = [g for g in data["gaps"] if g["category"] == "power"]
        assert power_gaps == []

    async def test_critical_when_no_collectors(self, client):
        """Zero collectors → critical gap."""
        from lm_mcp.tools.workflows import audit_network_monitoring_coverage

        devices_data = {"devices": []}
        collectors_data = {"collectors": []}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", collectors_data),
        ):
            result = await audit_network_monitoring_coverage(client)

        data = json.loads(result[0].text)
        critical = [g for g in data["gaps"] if g["severity"] == "critical"]
        assert len(critical) == 1
        assert critical[0]["category"] == "collectors"
