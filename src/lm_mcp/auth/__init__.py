# Description: Authentication module for LogicMonitor MCP Server.
# Description: Provides Bearer token authentication for LogicMonitor API.

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

    Args:
        config: LMConfig instance with bearer token.

    Returns:
        BearerAuth instance.
    """
    from lm_mcp.auth.bearer import BearerAuth

    return BearerAuth(config.bearer_token)


__all__ = [
    "AuthProvider",
    "create_auth_provider",
]
