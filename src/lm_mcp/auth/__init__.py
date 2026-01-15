# Description: Authentication module for LogicMonitor MCP Server.
# Description: Provides Bearer token and LMv1 HMAC authentication for LogicMonitor API.

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lm_mcp.config import LMConfig


class AuthProvider(ABC):
    """Abstract base class for authentication providers.

    Implementations generate the appropriate Authorization headers
    for LogicMonitor API requests.
    """

    @abstractmethod
    def get_auth_headers(
        self,
        method: str,
        resource_path: str,
        body: str = "",
    ) -> dict[str, str]:
        """Generate authentication headers for a request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            resource_path: API path (e.g., /alert/alerts)
            body: Request body as string (for POST/PUT requests)

        Returns:
            Dict of headers to add to the request, typically including
            the Authorization header.
        """
        pass


def create_auth_provider(config: "LMConfig") -> AuthProvider:
    """Create auth provider from configuration.

    Prefers Bearer token authentication when available. Falls back to
    LMv1 HMAC authentication if access_id and access_key are configured.

    Args:
        config: LMConfig instance with authentication credentials.

    Returns:
        BearerAuth or LMv1Auth instance.

    Raises:
        ConfigurationError: If no valid authentication is configured.
    """
    from lm_mcp.exceptions import ConfigurationError

    # Prefer Bearer token authentication
    if config.bearer_token:
        from lm_mcp.auth.bearer import BearerAuth

        return BearerAuth(config.bearer_token)

    # Fall back to LMv1 HMAC authentication
    if config.access_id and config.access_key:
        from lm_mcp.auth.lmv1 import LMv1Auth

        return LMv1Auth(config.access_id, config.access_key)

    # Handle partial LMv1 configuration
    if config.access_id:
        raise ConfigurationError("LMv1 access_key is required when access_id is set")
    if config.access_key:
        raise ConfigurationError("LMv1 access_id is required when access_key is set")

    raise ConfigurationError(
        "No authentication configured. Set LM_BEARER_TOKEN or both LM_ACCESS_ID and LM_ACCESS_KEY"
    )


__all__ = [
    "AuthProvider",
    "create_auth_provider",
]
