# Description: Authentication module for LogicMonitor MCP Server.
# Description: Provides Bearer token and LMv1 HMAC authentication for LogicMonitor API.

from abc import ABC, abstractmethod


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


def validate_auth(
    bearer_token: str | None, access_id: str | None, access_key: str | None
) -> AuthProvider:
    """Turn a portal's credentials into the auth provider its client signs with.

    A bearer token wins; otherwise both halves of an LMv1 pair are needed. The
    single-portal config and each multi-portal vault record both come through here.

    Args:
        bearer_token: LM_BEARER_TOKEN or the record's bearer_token.
        access_id: LM_ACCESS_ID or the record's access_id.
        access_key: LM_ACCESS_KEY or the record's access_key.

    Returns:
        BearerAuth or LMv1Auth instance.

    Raises:
        ConfigurationError: If neither a bearer token nor a full LMv1 pair is given.
    """
    from lm_mcp.exceptions import ConfigurationError

    if bearer_token:
        from lm_mcp.auth.bearer import BearerAuth

        return BearerAuth(bearer_token)

    if access_id and access_key:
        from lm_mcp.auth.lmv1 import LMv1Auth

        return LMv1Auth(access_id, access_key)

    raise ConfigurationError(
        "No authentication configured. Set LM_BEARER_TOKEN or both LM_ACCESS_ID and LM_ACCESS_KEY"
    )


__all__ = [
    "AuthProvider",
    "validate_auth",
]
