# Description: MCP prompts module for LogicMonitor workflow templates.
# Description: Provides pre-built prompts for common operations.

from lm_mcp.prompts.registry import PROMPTS, get_prompt_messages

__all__ = ["PROMPTS", "get_prompt_messages"]
