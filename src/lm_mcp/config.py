# Description: Configuration module for LogicMonitor MCP Server.
# Description: Handles environment variable loading and validation for LM API credentials.

from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class LMConfig(BaseSettings):
    """Configuration for LogicMonitor MCP Server.

    Loads configuration from environment variables with LM_ prefix.
    Supports both LMv1 (HMAC) and Bearer token authentication methods.
    """

    portal: str
    auth_method: Literal["lmv1", "bearer"] = "lmv1"
    access_id: str | None = None
    access_key: str | None = None
    bearer_token: str | None = None
    api_version: int = 3
    timeout: int = 30

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
    def validate_auth_credentials(self) -> "LMConfig":
        """Validate that required credentials are present for the auth method."""
        if self.auth_method == "lmv1":
            if not self.access_id:
                raise ValueError("access_id is required when auth_method is lmv1")
            if not self.access_key:
                raise ValueError("access_key is required when auth_method is lmv1")
        elif self.auth_method == "bearer":
            if not self.bearer_token:
                raise ValueError("bearer_token is required when auth_method is bearer")
        return self

    @property
    def base_url(self) -> str:
        """Return the base URL for LogicMonitor REST API."""
        return f"https://{self.portal}/santaba/rest"
