# Description: LogicMonitor MCP Server package.
# Description: Provides MCP tools for interacting with LogicMonitor REST API v3.

from lm_mcp.config import LMConfig
from lm_mcp.exceptions import (
    AuthenticationError,
    ConfigurationError,
    LMConnectionError,
    LMError,
    LMPermissionError,
    NotFoundError,
    RateLimitError,
    ServerError,
)

__version__ = "0.4.0"

__all__ = [
    "LMConfig",
    "LMError",
    "ConfigurationError",
    "AuthenticationError",
    "LMPermissionError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "LMConnectionError",
    "__version__",
]
