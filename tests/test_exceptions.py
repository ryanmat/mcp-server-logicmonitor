# Description: Tests for LogicMonitor MCP exception classes.
# Description: Validates exception raising, error codes, and to_dict serialization.

import pytest


class TestLMError:
    """Tests for the base LMError exception."""

    def test_lm_error_can_be_raised(self):
        """LMError can be raised and caught."""
        from lm_mcp.exceptions import LMError

        with pytest.raises(LMError):
            raise LMError("Test error")

    def test_lm_error_message(self):
        """LMError stores the message correctly."""
        from lm_mcp.exceptions import LMError

        error = LMError("Test error message")
        assert error.message == "Test error message"
        assert str(error) == "Test error message"

    def test_lm_error_default_code(self):
        """LMError has default code LM_ERROR."""
        from lm_mcp.exceptions import LMError

        error = LMError("Test error")
        assert error.code == "LM_ERROR"

    def test_lm_error_custom_code(self):
        """LMError accepts custom code."""
        from lm_mcp.exceptions import LMError

        error = LMError("Test error", code="CUSTOM_CODE")
        assert error.code == "CUSTOM_CODE"

    def test_lm_error_suggestion(self):
        """LMError stores suggestion correctly."""
        from lm_mcp.exceptions import LMError

        error = LMError("Test error", suggestion="Try this instead")
        assert error.suggestion == "Try this instead"

    def test_lm_error_to_dict_without_suggestion(self):
        """to_dict returns correct structure without suggestion."""
        from lm_mcp.exceptions import LMError

        error = LMError("Test error", code="TEST_CODE")
        result = error.to_dict()

        assert result == {
            "error": True,
            "code": "TEST_CODE",
            "message": "Test error",
        }

    def test_lm_error_to_dict_with_suggestion(self):
        """to_dict includes suggestion when present."""
        from lm_mcp.exceptions import LMError

        error = LMError("Test error", code="TEST_CODE", suggestion="Fix it")
        result = error.to_dict()

        assert result == {
            "error": True,
            "code": "TEST_CODE",
            "message": "Test error",
            "suggestion": "Fix it",
        }


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_configuration_error_inherits_from_lm_error(self):
        """ConfigurationError is an LMError."""
        from lm_mcp.exceptions import ConfigurationError, LMError

        error = ConfigurationError("Config issue")
        assert isinstance(error, LMError)

    def test_configuration_error_has_correct_code(self):
        """ConfigurationError has CONFIG_ERROR code."""
        from lm_mcp.exceptions import ConfigurationError

        error = ConfigurationError("Config issue")
        assert error.code == "CONFIG_ERROR"

    def test_configuration_error_has_default_suggestion(self):
        """ConfigurationError has a default suggestion."""
        from lm_mcp.exceptions import ConfigurationError

        error = ConfigurationError("Config issue")
        assert error.suggestion is not None


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_authentication_error_has_correct_code(self):
        """AuthenticationError has AUTH_FAILED code."""
        from lm_mcp.exceptions import AuthenticationError, LMError

        error = AuthenticationError("Auth failed")
        assert isinstance(error, LMError)
        assert error.code == "AUTH_FAILED"

    def test_authentication_error_has_default_suggestion(self):
        """AuthenticationError has a default suggestion."""
        from lm_mcp.exceptions import AuthenticationError

        error = AuthenticationError("Auth failed")
        assert error.suggestion is not None


class TestPermissionError:
    """Tests for LMPermissionError."""

    def test_permission_error_has_correct_code(self):
        """LMPermissionError has PERMISSION_DENIED code."""
        from lm_mcp.exceptions import LMError, LMPermissionError

        error = LMPermissionError("Permission denied")
        assert isinstance(error, LMError)
        assert error.code == "PERMISSION_DENIED"

    def test_permission_error_has_default_suggestion(self):
        """LMPermissionError has a default suggestion."""
        from lm_mcp.exceptions import LMPermissionError

        error = LMPermissionError("Permission denied")
        assert error.suggestion is not None


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_not_found_error_has_correct_code(self):
        """NotFoundError has NOT_FOUND code."""
        from lm_mcp.exceptions import LMError, NotFoundError

        error = NotFoundError("Resource not found")
        assert isinstance(error, LMError)
        assert error.code == "NOT_FOUND"

    def test_not_found_error_has_default_suggestion(self):
        """NotFoundError has a default suggestion."""
        from lm_mcp.exceptions import NotFoundError

        error = NotFoundError("Resource not found")
        assert error.suggestion is not None


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_rate_limit_error_has_correct_code(self):
        """RateLimitError has RATE_LIMITED code."""
        from lm_mcp.exceptions import LMError, RateLimitError

        error = RateLimitError("Rate limited")
        assert isinstance(error, LMError)
        assert error.code == "RATE_LIMITED"

    def test_rate_limit_error_stores_retry_after(self):
        """RateLimitError stores retry_after value."""
        from lm_mcp.exceptions import RateLimitError

        error = RateLimitError("Rate limited", retry_after=60)
        assert error.retry_after == 60

    def test_rate_limit_error_default_retry_after(self):
        """RateLimitError has default retry_after of None."""
        from lm_mcp.exceptions import RateLimitError

        error = RateLimitError("Rate limited")
        assert error.retry_after is None

    def test_rate_limit_error_to_dict_includes_retry_after(self):
        """to_dict includes retry_after when present."""
        from lm_mcp.exceptions import RateLimitError

        error = RateLimitError("Rate limited", retry_after=30)
        result = error.to_dict()

        assert result["retry_after"] == 30


class TestServerError:
    """Tests for ServerError."""

    def test_server_error_has_correct_code(self):
        """ServerError has SERVER_ERROR code."""
        from lm_mcp.exceptions import LMError, ServerError

        error = ServerError("Server error")
        assert isinstance(error, LMError)
        assert error.code == "SERVER_ERROR"

    def test_server_error_has_default_suggestion(self):
        """ServerError has a default suggestion."""
        from lm_mcp.exceptions import ServerError

        error = ServerError("Server error")
        assert error.suggestion is not None


class TestConnectionError:
    """Tests for LMConnectionError."""

    def test_connection_error_has_correct_code(self):
        """LMConnectionError has CONNECTION_FAILED code."""
        from lm_mcp.exceptions import LMConnectionError, LMError

        error = LMConnectionError("Connection failed")
        assert isinstance(error, LMError)
        assert error.code == "CONNECTION_FAILED"

    def test_connection_error_has_default_suggestion(self):
        """LMConnectionError has a default suggestion."""
        from lm_mcp.exceptions import LMConnectionError

        error = LMConnectionError("Connection failed")
        assert error.suggestion is not None
