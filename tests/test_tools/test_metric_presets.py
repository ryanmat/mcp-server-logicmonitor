# Description: Tests for metric type detection and preset defaults.
# Description: Validates regex matching and preset parameter retrieval.

from __future__ import annotations

from lm_mcp.tools.metric_presets import (
    detect_metric_type,
    get_preset,
    get_preset_for_datapoint,
)


class TestDetectMetricType:
    """Tests for detect_metric_type regex matching."""

    def test_cpu_match(self):
        """CPUBusyPercent matches cpu type."""
        assert detect_metric_type("CPUBusyPercent") == "cpu"

    def test_cpu_match_processor(self):
        """ProcessorQueueLength matches cpu type."""
        assert detect_metric_type("ProcessorQueueLength") == "cpu"

    def test_memory_match(self):
        """MemUsedPercent matches memory type."""
        assert detect_metric_type("MemUsedPercent") == "memory"

    def test_memory_match_swap(self):
        """SwapUsedPercent matches memory type."""
        assert detect_metric_type("SwapUsedPercent") == "memory"

    def test_memory_match_heap(self):
        """HeapUsedMB matches memory type."""
        assert detect_metric_type("HeapUsedMB") == "memory"

    def test_disk_match(self):
        """DiskUsedPercent matches disk type."""
        assert detect_metric_type("DiskUsedPercent") == "disk"

    def test_disk_match_storage(self):
        """StorageFreeGB matches disk type."""
        assert detect_metric_type("StorageFreeGB") == "disk"

    def test_disk_match_volume(self):
        """VolumeUsedPercent matches disk type."""
        assert detect_metric_type("VolumeUsedPercent") == "disk"

    def test_disk_match_inode(self):
        """InodeUsedPercent matches disk type."""
        assert detect_metric_type("InodeUsedPercent") == "disk"

    def test_latency_match(self):
        """ResponseTime matches latency type."""
        assert detect_metric_type("ResponseTime") == "latency"

    def test_latency_match_rtt(self):
        """RTTavg matches latency type."""
        assert detect_metric_type("RTTavg") == "latency"

    def test_error_rate_match(self):
        """ErrorCount matches error_rate type."""
        assert detect_metric_type("ErrorCount") == "error_rate"

    def test_error_rate_match_5xx(self):
        """Http5xxCount matches error_rate type."""
        assert detect_metric_type("Http5xxCount") == "error_rate"

    def test_error_rate_match_fault(self):
        """FaultRate matches error_rate type."""
        assert detect_metric_type("FaultRate") == "error_rate"

    def test_token_usage_match(self):
        """TokenUsage matches token_usage type."""
        assert detect_metric_type("TokenUsage") == "token_usage"

    def test_token_usage_match_apicount(self):
        """ApiCountTotal matches token_usage type."""
        assert detect_metric_type("ApiCountTotal") == "token_usage"

    def test_unknown_returns_none(self):
        """RandomMetric returns None for unknown types."""
        assert detect_metric_type("RandomMetric") is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert detect_metric_type("") is None

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        assert detect_metric_type("cpubusypercent") == "cpu"
        assert detect_metric_type("CPUBUSYPERCENT") == "cpu"


class TestGetPreset:
    """Tests for get_preset by metric type string."""

    def test_known_type_returns_dict(self):
        """Known metric type returns a preset dict."""
        preset = get_preset("cpu")
        assert preset is not None
        assert isinstance(preset, dict)

    def test_unknown_type_returns_none(self):
        """Unknown metric type returns None."""
        assert get_preset("unknown_type") is None

    def test_preset_has_expected_keys(self):
        """Preset dict contains hours_back, anomaly_method, forecast_method."""
        preset = get_preset("cpu")
        assert preset is not None
        assert "hours_back" in preset
        assert "anomaly_method" in preset
        assert "forecast_method" in preset

    def test_cpu_preset_values(self):
        """CPU preset has correct default values."""
        preset = get_preset("cpu")
        assert preset is not None
        assert preset["hours_back"] == 24
        assert preset["anomaly_method"] == "iqr"
        assert preset["forecast_method"] == "holt_winters"

    def test_memory_preset_values(self):
        """Memory preset has correct default values."""
        preset = get_preset("memory")
        assert preset is not None
        assert preset["hours_back"] == 168
        assert preset["anomaly_method"] == "zscore"

    def test_latency_preset_values(self):
        """Latency preset uses MAD anomaly method."""
        preset = get_preset("latency")
        assert preset is not None
        assert preset["anomaly_method"] == "mad"

    def test_preset_returns_copy(self):
        """get_preset returns a copy, not a reference to the internal dict."""
        preset1 = get_preset("cpu")
        preset2 = get_preset("cpu")
        assert preset1 is not preset2


class TestGetPresetForDatapoint:
    """Tests for the convenience function combining detect + get."""

    def test_matching_datapoint_returns_preset(self):
        """Known datapoint name returns a preset dict."""
        preset = get_preset_for_datapoint("CPUBusyPercent")
        assert preset is not None
        assert preset["hours_back"] == 24

    def test_unknown_datapoint_returns_none(self):
        """Unknown datapoint name returns None."""
        assert get_preset_for_datapoint("RandomMetric") is None

    def test_disk_datapoint_returns_disk_preset(self):
        """DiskUsedPercent returns disk preset values."""
        preset = get_preset_for_datapoint("DiskUsedPercent")
        assert preset is not None
        assert preset["hours_back"] == 168
        assert preset["anomaly_method"] == "zscore"
        assert preset["forecast_method"] == "linear"

    def test_error_datapoint_returns_error_preset(self):
        """ErrorCount returns error_rate preset values."""
        preset = get_preset_for_datapoint("ErrorCount")
        assert preset is not None
        assert preset["forecast_method"] == "auto"
