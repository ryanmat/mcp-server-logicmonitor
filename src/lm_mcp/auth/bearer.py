# Description: Bearer token authentication provider for LogicMonitor API.
# Description: Provides simple token-based authentication via Authorization header.

from lm_mcp.auth import AuthProvider
from lm_mcp.exceptions import ConfigurationError


class BearerAuth(AuthProvider):
    """Bearer token authentication provider.

    Uses a static Bearer token for all requests. The token is passed
    in the Authorization header as "Bearer {token}".
    """

    def __init__(self, token: str | None):
        """Initialize with a bearer token.

        Args:
            token: The bearer token for authentication.

        Raises:
            ConfigurationError: If token is empty or None.
        """
        if not token:
            raise ConfigurationError("Bearer token is required")
        self.token = token

    def get_auth_headers(
        self,
        method: str,
        resource_path: str,
        body: str = "",
    ) -> dict[str, str]:
        """Generate Bearer authentication header.

        Args:
            method: HTTP method (unused for Bearer auth)
            resource_path: API path (unused for Bearer auth)
            body: Request body (unused for Bearer auth)

        Returns:
            Dict with Authorization header containing Bearer token.
        """
        return {"Authorization": f"Bearer {self.token}"}
