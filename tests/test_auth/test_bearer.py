# Description: Tests for Bearer token authentication provider.
# Description: Validates token handling and header generation.

import pytest


class TestBearerAuth:
    """Tests for BearerAuth provider."""

    def test_bearer_auth_inherits_from_auth_provider(self):
        """BearerAuth implements AuthProvider interface."""
        from lm_mcp.auth import AuthProvider
        from lm_mcp.auth.bearer import BearerAuth

        auth = BearerAuth("test_token")
        assert isinstance(auth, AuthProvider)

    def test_bearer_auth_stores_token(self):
        """BearerAuth stores the token."""
        from lm_mcp.auth.bearer import BearerAuth

        auth = BearerAuth("my_secret_token")
        assert auth.token == "my_secret_token"

    def test_bearer_auth_raises_on_empty_token(self):
        """BearerAuth raises ConfigurationError if token is empty."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="Bearer token"):
            BearerAuth("")

    def test_bearer_auth_raises_on_none_token(self):
        """BearerAuth raises ConfigurationError if token is None."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="Bearer token"):
            BearerAuth(None)

    def test_get_auth_headers_returns_authorization_header(self):
        """get_auth_headers returns correct Authorization header."""
        from lm_mcp.auth.bearer import BearerAuth

        auth = BearerAuth("my_token_123")
        headers = auth.get_auth_headers("GET", "/alert/alerts")

        assert headers == {"Authorization": "Bearer my_token_123"}

    def test_get_auth_headers_ignores_method(self):
        """Bearer auth header is same regardless of HTTP method."""
        from lm_mcp.auth.bearer import BearerAuth

        auth = BearerAuth("test_token")

        get_headers = auth.get_auth_headers("GET", "/path")
        post_headers = auth.get_auth_headers("POST", "/path")
        delete_headers = auth.get_auth_headers("DELETE", "/path")

        assert get_headers == post_headers == delete_headers

    def test_get_auth_headers_ignores_path(self):
        """Bearer auth header is same regardless of path."""
        from lm_mcp.auth.bearer import BearerAuth

        auth = BearerAuth("test_token")

        headers1 = auth.get_auth_headers("GET", "/alert/alerts")
        headers2 = auth.get_auth_headers("GET", "/device/devices")

        assert headers1 == headers2

    def test_get_auth_headers_ignores_body(self):
        """Bearer auth header is same regardless of body."""
        from lm_mcp.auth.bearer import BearerAuth

        auth = BearerAuth("test_token")

        headers1 = auth.get_auth_headers("POST", "/path", "")
        headers2 = auth.get_auth_headers("POST", "/path", '{"key": "value"}')

        assert headers1 == headers2
