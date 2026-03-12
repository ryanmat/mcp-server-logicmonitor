# Description: Metric type detection and default parameter presets.
# Description: Maps datapoint names to recommended analysis configurations.

from __future__ import annotations

import re
from typing import Any

# Ordered list of (metric_type, regex_pattern, preset_defaults).
# First match wins when classifying a datapoint name.
_METRIC_PRESETS: list[tuple[str, re.Pattern, dict[str, Any]]] = [
    (
        "cpu",
        re.compile(r"cpu|processor|cpubusy", re.IGNORECASE),
        {"hours_back": 24, "anomaly_method": "iqr", "forecast_method": "holt_winters"},
    ),
    (
        "memory",
        re.compile(r"mem|ram|swap|heap", re.IGNORECASE),
        {"hours_back": 168, "anomaly_method": "zscore", "forecast_method": "linear"},
    ),
    (
        "disk",
        re.compile(r"disk|storage|volume|inode", re.IGNORECASE),
        {"hours_back": 168, "anomaly_method": "zscore", "forecast_method": "linear"},
    ),
    (
        "latency",
        re.compile(r"latency|rtt|responsetime", re.IGNORECASE),
        {"hours_back": 24, "anomaly_method": "mad", "forecast_method": "holt_winters"},
    ),
    (
        "error_rate",
        re.compile(r"error|fault|fail|5xx", re.IGNORECASE),
        {"hours_back": 24, "anomaly_method": "iqr", "forecast_method": "auto"},
    ),
    (
        "token_usage",
        re.compile(r"token|apicount", re.IGNORECASE),
        {"hours_back": 168, "anomaly_method": "iqr", "forecast_method": "linear"},
    ),
]


def detect_metric_type(datapoint_name: str) -> str | None:
    """Detect the metric type from a datapoint name.

    Uses regex matching against known patterns. First match wins.

    Args:
        datapoint_name: Name of the datapoint to classify.

    Returns:
        Metric type string or None if no match.
    """
    for metric_type, pattern, _preset in _METRIC_PRESETS:
        if pattern.search(datapoint_name):
            return metric_type
    return None


def get_preset(metric_type: str) -> dict[str, Any] | None:
    """Get analysis defaults for a known metric type.

    Args:
        metric_type: Metric type string (e.g., 'cpu', 'memory').

    Returns:
        Dict with hours_back, anomaly_method, forecast_method, or None.
    """
    for mt, _pattern, preset in _METRIC_PRESETS:
        if mt == metric_type:
            return dict(preset)
    return None


def get_preset_for_datapoint(datapoint_name: str) -> dict[str, Any] | None:
    """Detect metric type and return its preset defaults.

    Convenience function combining detect_metric_type and get_preset.

    Args:
        datapoint_name: Name of the datapoint.

    Returns:
        Preset dict or None if no match.
    """
    metric_type = detect_metric_type(datapoint_name)
    if metric_type is None:
        return None
    return get_preset(metric_type)
