# Description: Tests for the LMConfig configuration module.
# Description: Validates environment loading, credential validation, and URL normalization.

import pytest
from pydantic import ValidationError


class TestLMConfigBearer:
    """Tests for Bearer token configuration."""

    def test_valid_bearer_config(self, monkeypatch):
        """Valid Bearer config loads successfully from environment."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token_123")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.portal == "test.logicmonitor.com"
        assert config.bearer_token == "test_token_123"
        assert config.api_version == 3
        assert config.timeout == 30

    def test_bearer_missing_token_raises_error(self, monkeypatch):
        """Missing bearer token raises ValidationError."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

        from lm_mcp.config import LMConfig

        with pytest.raises(ValueError, match="bearer_token.*required"):
            LMConfig()

    def test_bearer_empty_token_raises_error(self, monkeypatch):
        """Empty bearer token raises ValidationError."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "")

        from lm_mcp.config import LMConfig

        with pytest.raises(ValueError, match="bearer_token.*required"):
            LMConfig()


class TestLMConfigPortalNormalization:
    """Tests for portal URL normalization."""

    def test_portal_strips_https_prefix(self, monkeypatch):
        """Portal URL with https:// prefix is normalized."""
        monkeypatch.setenv("LM_PORTAL", "https://test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"

    def test_portal_strips_http_prefix(self, monkeypatch):
        """Portal URL with http:// prefix is normalized."""
        monkeypatch.setenv("LM_PORTAL", "http://test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"

    def test_portal_strips_trailing_slash(self, monkeypatch):
        """Portal URL with trailing slash is normalized."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com/")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"

    def test_portal_strips_https_and_trailing_slash(self, monkeypatch):
        """Portal URL with https:// and trailing slash is normalized."""
        monkeypatch.setenv("LM_PORTAL", "https://test.logicmonitor.com/")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"


class TestLMConfigBaseUrl:
    """Tests for base_url property."""

    def test_base_url_property(self, monkeypatch):
        """base_url property returns correctly formatted URL."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.base_url == "https://test.logicmonitor.com/santaba/rest"


class TestLMConfigMissingPortal:
    """Tests for missing portal configuration."""

    def test_missing_portal_raises_error(self, monkeypatch):
        """Missing portal raises ValidationError."""
        monkeypatch.delenv("LM_PORTAL", raising=False)
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp.config import LMConfig

        with pytest.raises(ValidationError):
            LMConfig()
