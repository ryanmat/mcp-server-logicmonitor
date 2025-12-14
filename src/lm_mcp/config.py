# Description: Configuration module for LogicMonitor MCP Server.
# Description: Handles environment variable loading and validation for LM API credentials.

import re

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class LMConfig(BaseSettings):
    """Configuration for LogicMonitor MCP Server.

    Loads configuration from environment variables with LM_ prefix.
    Uses Bearer token authentication.

    Environment Variables:
        LM_PORTAL: LogicMonitor portal hostname (e.g., company.logicmonitor.com)
        LM_BEARER_TOKEN: API Bearer token for authentication
        LM_API_VERSION: API version (default: 3)
        LM_TIMEOUT: Request timeout in seconds (default: 30, range: 5-300)
        LM_ENABLE_WRITE_OPERATIONS: Enable write operations (default: false)
        LM_MAX_RETRIES: Max retry attempts for rate limits (default: 3, range: 0-10)
    """

    portal: str
    bearer_token: str | None = None
    api_version: int = 3
    timeout: int = 30
    enable_write_operations: bool = False
    max_retries: int = 3

    model_config = {
        "env_prefix": "LM_",
    }

    @field_validator("portal", mode="before")
    @classmethod
    def normalize_portal(cls, v: str) -> str:
        """Strip protocol prefix and trailing slashes from portal hostname."""
        if v is None:
            return v
        v = str(v)
        if v.startswith("https://"):
            v = v[8:]
        elif v.startswith("http://"):
            v = v[7:]
        v = v.rstrip("/")

        # Validate portal hostname format
        if not v or len(v) < 5:
            raise ValueError("portal must be a valid hostname (e.g., company.logicmonitor.com)")
        if not re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9\-]+)+$", v):
            raise ValueError(
                f"portal '{v}' is not a valid hostname format (expected: company.logicmonitor.com)"
            )
        return v

    @field_validator("timeout", mode="after")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout is within acceptable range."""
        if v < 5:
            raise ValueError("timeout must be at least 5 seconds")
        if v > 300:
            raise ValueError("timeout must not exceed 300 seconds (5 minutes)")
        return v

    @field_validator("max_retries", mode="after")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Validate max_retries is within acceptable range."""
        if v < 0:
            raise ValueError("max_retries must be non-negative")
        if v > 10:
            raise ValueError("max_retries must not exceed 10")
        return v

    @model_validator(mode="after")
    def validate_bearer_token(self) -> "LMConfig":
        """Validate that bearer token is present and has minimum length."""
        if not self.bearer_token:
            raise ValueError("bearer_token is required")
        if len(self.bearer_token) < 10:
            raise ValueError("bearer_token appears invalid (too short)")
        return self

    @property
    def base_url(self) -> str:
        """Return the base URL for LogicMonitor REST API."""
        return f"https://{self.portal}/santaba/rest"
