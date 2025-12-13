# Description: Configuration module for LogicMonitor MCP Server.
# Description: Handles environment variable loading and validation for LM API credentials.

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class LMConfig(BaseSettings):
    """Configuration for LogicMonitor MCP Server.

    Loads configuration from environment variables with LM_ prefix.
    Uses Bearer token authentication.
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
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_bearer_token(self) -> "LMConfig":
        """Validate that bearer token is present."""
        if not self.bearer_token:
            raise ValueError("bearer_token is required")
        return self

    @property
    def base_url(self) -> str:
        """Return the base URL for LogicMonitor REST API."""
        return f"https://{self.portal}/santaba/rest"
