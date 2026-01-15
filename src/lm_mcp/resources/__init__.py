# Description: MCP resources module for LogicMonitor schema exposure.
# Description: Provides API field definitions to prevent AI hallucination.

from lm_mcp.resources.registry import RESOURCES, get_resource_content

__all__ = ["RESOURCES", "get_resource_content"]
