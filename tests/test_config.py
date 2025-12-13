# Description: Tests for the LMConfig configuration module.
# Description: Validates environment loading, credential validation, and URL normalization.

import pytest
from pydantic import ValidationError


class TestLMConfigLMv1:
    """Tests for LMv1 authentication configuration."""

    def test_valid_lmv1_config(self, monkeypatch):
        """Valid LMv1 config loads successfully from environment."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_AUTH_METHOD", "lmv1")
        monkeypatch.setenv("LM_ACCESS_ID", "test_id")
        monkeypatch.setenv("LM_ACCESS_KEY", "test_key")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.portal == "test.logicmonitor.com"
        assert config.auth_method == "lmv1"
        assert config.access_id == "test_id"
        assert config.access_key == "test_key"
        assert config.api_version == 3
        assert config.timeout == 30

    def test_lmv1_missing_access_id_raises_error(self, monkeypatch):
        """LMv1 auth without access_id raises ValidationError."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_AUTH_METHOD", "lmv1")
        monkeypatch.setenv("LM_ACCESS_KEY", "test_key")
        monkeypatch.delenv("LM_ACCESS_ID", raising=False)

        from lm_mcp.config import LMConfig

        with pytest.raises(ValueError, match="access_id.*required"):
            LMConfig()

    def test_lmv1_missing_access_key_raises_error(self, monkeypatch):
        """LMv1 auth without access_key raises ValidationError."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_AUTH_METHOD", "lmv1")
        monkeypatch.setenv("LM_ACCESS_ID", "test_id")
        monkeypatch.delenv("LM_ACCESS_KEY", raising=False)

        from lm_mcp.config import LMConfig

        with pytest.raises(ValueError, match="access_key.*required"):
            LMConfig()

    def test_lmv1_is_default_auth_method(self, monkeypatch):
        """Default auth_method is lmv1."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_ACCESS_ID", "test_id")
        monkeypatch.setenv("LM_ACCESS_KEY", "test_key")
        monkeypatch.delenv("LM_AUTH_METHOD", raising=False)

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.auth_method == "lmv1"


class TestLMConfigBearer:
    """Tests for Bearer token authentication configuration."""

    def test_valid_bearer_config(self, monkeypatch):
        """Valid Bearer config loads successfully from environment."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token_123")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.portal == "test.logicmonitor.com"
        assert config.auth_method == "bearer"
        assert config.bearer_token == "test_token_123"

    def test_bearer_missing_token_raises_error(self, monkeypatch):
        """Bearer auth without token raises ValidationError."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

        from lm_mcp.config import LMConfig

        with pytest.raises(ValueError, match="bearer_token.*required"):
            LMConfig()


class TestLMConfigPortalNormalization:
    """Tests for portal URL normalization."""

    def test_portal_strips_https_prefix(self, monkeypatch):
        """Portal URL with https:// prefix is normalized."""
        monkeypatch.setenv("LM_PORTAL", "https://test.logicmonitor.com")
        monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"

    def test_portal_strips_http_prefix(self, monkeypatch):
        """Portal URL with http:// prefix is normalized."""
        monkeypatch.setenv("LM_PORTAL", "http://test.logicmonitor.com")
        monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"

    def test_portal_strips_trailing_slash(self, monkeypatch):
        """Portal URL with trailing slash is normalized."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com/")
        monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"

    def test_portal_strips_https_and_trailing_slash(self, monkeypatch):
        """Portal URL with https:// and trailing slash is normalized."""
        monkeypatch.setenv("LM_PORTAL", "https://test.logicmonitor.com/")
        monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"


class TestLMConfigBaseUrl:
    """Tests for base_url property."""

    def test_base_url_property(self, monkeypatch):
        """base_url property returns correctly formatted URL."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.base_url == "https://test.logicmonitor.com/santaba/rest"


class TestLMConfigMissingPortal:
    """Tests for missing portal configuration."""

    def test_missing_portal_raises_error(self, monkeypatch):
        """Missing portal raises ValidationError."""
        monkeypatch.delenv("LM_PORTAL", raising=False)
        monkeypatch.setenv("LM_AUTH_METHOD", "bearer")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        with pytest.raises(ValidationError):
            LMConfig()
