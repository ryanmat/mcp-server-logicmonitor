# Description: Best practices data for LogicMonitor operations.
# Description: Provides scenario-based recommendations and anti-patterns.

from __future__ import annotations

BEST_PRACTICES: dict[str, dict] = {
    "high_alert_noise": {
        "condition": "Alert noise score exceeds 50",
        "recommended_actions": [
            {
                "action": "Review flapping alerts and add hysteresis delay",
                "how": (
                    "Use score_alert_noise to identify flapping alerts, then adjust "
                    "alert thresholds or add trigger_interval in DataSource datapoint "
                    "settings"
                ),
                "priority": "high",
            },
            {
                "action": "Consolidate redundant alert rules",
                "how": (
                    "Use get_alert_rules to list rules, identify overlapping rules "
                    "that cover the same resources, merge into fewer rules with "
                    "appropriate escalation chains"
                ),
                "priority": "medium",
            },
            {
                "action": "Schedule recurring SDTs for known maintenance windows",
                "how": (
                    "Use create_sdt with recurring schedule for devices that produce "
                    "expected alerts during maintenance"
                ),
                "priority": "medium",
            },
        ],
        "anti_patterns": [
            "Do not disable alerting entirely to reduce noise",
            "Do not raise thresholds without understanding baseline behavior",
            "Do not acknowledge alerts in bulk without reviewing each cluster",
        ],
    },
    "device_health_low": {
        "condition": "Device health score below 50",
        "recommended_actions": [
            {
                "action": "Verify collector connectivity and version",
                "how": (
                    "Use get_collectors to check collector status and build version "
                    "for the device's preferred collector"
                ),
                "priority": "high",
            },
            {
                "action": "Check for resource exhaustion",
                "how": (
                    "Use get_device_data for CPU, memory, and disk datasources to "
                    "identify which resource is under pressure"
                ),
                "priority": "high",
            },
            {
                "action": "Review active alerts for root cause indicators",
                "how": (
                    "Use get_alerts filtered to the device to see what is currently "
                    "alerting and correlate with health score contributors"
                ),
                "priority": "medium",
            },
        ],
        "anti_patterns": [
            "Do not restart services without diagnosing the root cause",
            "Do not ignore low health scores on non-production devices",
            "Do not disable monitoring to improve the health score",
        ],
    },
    "availability_low": {
        "condition": "Availability below 99.9%",
        "recommended_actions": [
            {
                "action": "Verify SDT exclusions are applied correctly",
                "how": (
                    "Use get_active_sdts and list_sdts to check if planned downtime "
                    "is excluded from availability calculations"
                ),
                "priority": "high",
            },
            {
                "action": "Review measurement window scope",
                "how": (
                    "Narrow the hours_back parameter or filter by device_id to "
                    "isolate which devices are pulling availability down"
                ),
                "priority": "medium",
            },
            {
                "action": "Investigate longest incidents",
                "how": (
                    "Check the longest_incident_minutes and by_device breakdown "
                    "to find the single biggest contributor to downtime"
                ),
                "priority": "medium",
            },
        ],
        "anti_patterns": [
            "Do not change severity thresholds to hide downtime events",
            "Do not use info-level alerts for availability calculations",
            "Do not compare availability across different time windows without normalization",
        ],
    },
    "remediation_execution": {
        "condition": "Before executing a remediation source",
        "recommended_actions": [
            {
                "action": "Verify the remediation source AppliesTo matches the target device",
                "how": (
                    "Check the appliesTo script in the remediation source definition "
                    "against the device properties"
                ),
                "priority": "high",
            },
            {
                "action": "Review the script content for state-mutating operations",
                "how": (
                    "Check for restart, rm, delete, stop, kill, reboot, shutdown "
                    "keywords in the groovyScript"
                ),
                "priority": "high",
            },
            {
                "action": "Confirm collector version supports execution",
                "how": (
                    "Collector build must be >= 39.200 for remediation execution support"
                ),
                "priority": "high",
            },
        ],
        "anti_patterns": [
            "Do not execute remediation without reviewing the script content",
            "Do not assume AppliesTo is valid without checking",
            "Do not run concurrent remediations on the same device",
        ],
    },
    "genai_monitoring": {
        "condition": "Monitoring GenAI/LLM workloads",
        "recommended_actions": [
            {
                "action": "Track token usage and API call rates",
                "how": (
                    "Use get_device_data with datasources that monitor token "
                    "consumption and API request counts"
                ),
                "priority": "high",
            },
            {
                "action": "Set latency baselines for inference endpoints",
                "how": (
                    "Use save_baseline to capture normal inference latency, then "
                    "compare_to_baseline to detect degradation"
                ),
                "priority": "medium",
            },
            {
                "action": "Monitor error rates and rate limiting",
                "how": (
                    "Use get_metric_anomalies to detect spikes in error rates or "
                    "sudden drops in throughput indicating rate limits"
                ),
                "priority": "medium",
            },
        ],
        "anti_patterns": [
            (
                "Do not use static thresholds for token usage; "
                "it varies by model and prompt complexity"
            ),
            "Do not ignore cost-per-token metrics when scaling up inference workloads",
            "Do not monitor only latency; token throughput and error rates are equally important",
        ],
    },
}


def get_best_practices(scenario: str | None = None) -> dict:
    """Get best practices for a specific scenario or all scenarios.

    Args:
        scenario: Specific scenario name, or None for all.

    Returns:
        Best practices dict (single scenario or all).
    """
    if scenario and scenario in BEST_PRACTICES:
        return {scenario: BEST_PRACTICES[scenario]}
    return BEST_PRACTICES
