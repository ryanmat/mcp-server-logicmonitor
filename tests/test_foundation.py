# Description: Foundation tests verifying all core modules work together.
# Description: Tests package exports, configuration instantiation, and exception handling.

import pytest


class TestPackageExports:
    """Tests that verify package exports are accessible."""

    def test_version_exported(self):
        """Package version is accessible."""
        from lm_mcp import __version__

        assert __version__ == "0.1.0"

    def test_lm_config_exported(self):
        """LMConfig is exported from package root."""
        from lm_mcp import LMConfig

        assert LMConfig is not None

    def test_all_exceptions_exported(self):
        """All exception classes are exported from package root."""
        from lm_mcp import (
            AuthenticationError,
            ConfigurationError,
            LMConnectionError,
            LMError,
            LMPermissionError,
            NotFoundError,
            RateLimitError,
            ServerError,
        )

        assert LMError is not None
        assert ConfigurationError is not None
        assert AuthenticationError is not None
        assert LMPermissionError is not None
        assert NotFoundError is not None
        assert RateLimitError is not None
        assert ServerError is not None
        assert LMConnectionError is not None


class TestFoundationIntegration:
    """Integration tests for foundation components."""

    def test_config_instantiation_with_env(self, monkeypatch):
        """LMConfig can be instantiated with mock environment variables."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token")

        from lm_mcp import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"
        assert config.base_url == "https://test.logicmonitor.com/santaba/rest"

    def test_exceptions_can_be_raised_and_converted(self):
        """Exceptions can be raised and converted to dict format."""
        from lm_mcp import AuthenticationError, LMError, RateLimitError

        # Test base error
        base_error = LMError("Base error", code="TEST", suggestion="Fix it")
        assert base_error.to_dict() == {
            "error": True,
            "code": "TEST",
            "message": "Base error",
            "suggestion": "Fix it",
        }

        # Test auth error with defaults
        auth_error = AuthenticationError("Auth failed")
        auth_dict = auth_error.to_dict()
        assert auth_dict["code"] == "AUTH_FAILED"
        assert "suggestion" in auth_dict

        # Test rate limit with retry_after
        rate_error = RateLimitError("Rate limited", retry_after=60)
        rate_dict = rate_error.to_dict()
        assert rate_dict["code"] == "RATE_LIMITED"
        assert rate_dict["retry_after"] == 60

    def test_exception_inheritance(self):
        """All custom exceptions inherit from LMError."""
        from lm_mcp import (
            AuthenticationError,
            ConfigurationError,
            LMConnectionError,
            LMError,
            LMPermissionError,
            NotFoundError,
            RateLimitError,
            ServerError,
        )

        exceptions = [
            ConfigurationError("test"),
            AuthenticationError("test"),
            LMPermissionError("test"),
            NotFoundError("test"),
            RateLimitError("test"),
            ServerError("test"),
            LMConnectionError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, LMError), f"{type(exc).__name__} should inherit from LMError"

    def test_config_validation_raises_correct_exception_type(self, monkeypatch):
        """Config validation errors are ValueError not our custom exceptions."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

        from lm_mcp import LMConfig

        with pytest.raises(ValueError, match="bearer_token.*required"):
            LMConfig()
