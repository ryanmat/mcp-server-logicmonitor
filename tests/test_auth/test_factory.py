# Description: Tests for authentication provider factory.
# Description: Validates factory creates correct auth provider from config.


class TestAuthFactory:
    """Tests for create_auth_provider factory function."""

    def test_factory_creates_bearer_auth(self, monkeypatch):
        """Factory creates BearerAuth from config."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token_12345")

        from lm_mcp.auth import create_auth_provider
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.config import LMConfig

        config = LMConfig()
        auth = create_auth_provider(config)

        assert isinstance(auth, BearerAuth)
        assert auth.token == "test_token_12345"

    def test_factory_created_bearer_works(self, monkeypatch):
        """Factory-created BearerAuth generates correct headers."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "my_token_12345")

        from lm_mcp.auth import create_auth_provider
        from lm_mcp.config import LMConfig

        config = LMConfig()
        auth = create_auth_provider(config)
        headers = auth.get_auth_headers("GET", "/alert/alerts")

        assert headers["Authorization"] == "Bearer my_token_12345"
