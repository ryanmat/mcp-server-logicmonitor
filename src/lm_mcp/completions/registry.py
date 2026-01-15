# Description: Registry of completion sources for tool arguments.
# Description: Defines valid values for arguments like severity, status, sdt_type.

from __future__ import annotations

# Completion sources define valid values for specific argument names.
# These are used by the completion handler to provide auto-complete suggestions.
COMPLETION_SOURCES: list[dict] = [
    {
        "argument_name": "severity",
        "description": "Alert severity levels",
        "values": ["critical", "error", "warning", "info"],
    },
    {
        "argument_name": "status",
        "description": "Device status values",
        "values": [
            "normal",
            "dead",
            "dead-collector",
            "unmonitored",
            "disabled",
            "disabled-none",
            "disabled-stop-alerting",
        ],
    },
    {
        "argument_name": "sdt_type",
        "description": "Scheduled Downtime type values",
        "values": [
            "DeviceSDT",
            "DeviceGroupSDT",
            "DeviceDataSourceSDT",
            "DeviceDataSourceInstanceSDT",
            "DeviceDataSourceInstanceGroupSDT",
            "DeviceEventSourceSDT",
            "DeviceBatchJobSDT",
            "CollectorSDT",
            "WebsiteSDT",
            "WebsiteGroupSDT",
            "WebsiteCheckpointSDT",
            "ServiceSDT",
            "ServiceGroupSDT",
            "ResourceGroupSDT",
        ],
    },
    {
        "argument_name": "cleared",
        "description": "Alert cleared status",
        "values": ["true", "false"],
    },
    {
        "argument_name": "acked",
        "description": "Alert acknowledged status",
        "values": ["true", "false"],
    },
    {
        "argument_name": "collector_build",
        "description": "Collector build type",
        "values": ["EA", "GD", "MGD"],
    },
    {
        "argument_name": "sdted",
        "description": "Resource SDT status",
        "values": ["true", "false"],
    },
    {
        "argument_name": "host_status",
        "description": "Device host status values",
        "values": [
            "normal",
            "dead",
            "dead-collector",
            "unmonitored",
            "disabled",
        ],
    },
    {
        "argument_name": "device_type",
        "description": "Device type values",
        "values": ["0", "2", "4", "6"],  # Regular, AWS, Azure, GCP
    },
]


def get_completion_values(argument_name: str) -> list[str]:
    """Get all valid completion values for an argument.

    Args:
        argument_name: The name of the argument to get values for.

    Returns:
        List of valid values, or empty list if argument is not recognized.
    """
    for source in COMPLETION_SOURCES:
        if source["argument_name"] == argument_name:
            return source["values"]
    return []
