# Description: Tests for tool helper functions.
# Description: Validates format_response and handle_error utilities.

import json

from lm_mcp.exceptions import AuthenticationError, LMError, NotFoundError


class TestFormatResponse:
    """Tests for format_response function."""

    def test_format_dict_response(self):
        """Dict data is formatted as JSON text content."""
        from lm_mcp.tools import format_response

        data = {"count": 5, "items": [1, 2, 3]}
        result = format_response(data)

        assert len(result) == 1
        assert result[0].type == "text"
        parsed = json.loads(result[0].text)
        assert parsed["count"] == 5
        assert parsed["items"] == [1, 2, 3]

    def test_format_list_response(self):
        """List data is formatted as JSON text content."""
        from lm_mcp.tools import format_response

        data = [{"id": 1}, {"id": 2}]
        result = format_response(data)

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert len(parsed) == 2
        assert parsed[0]["id"] == 1

    def test_format_string_response(self):
        """String data is returned as-is."""
        from lm_mcp.tools import format_response

        data = "Simple message"
        result = format_response(data)

        assert len(result) == 1
        assert result[0].text == "Simple message"

    def test_format_error_response(self):
        """Error dict includes error message and suggestion."""
        from lm_mcp.tools import format_response

        data = {
            "error": True,
            "code": "TEST_ERROR",
            "message": "Something went wrong",
            "suggestion": "Try again",
        }
        result = format_response(data)

        assert len(result) == 1
        assert "Error: Something went wrong" in result[0].text
        assert "Suggestion: Try again" in result[0].text

    def test_format_error_response_without_suggestion(self):
        """Error dict without suggestion omits suggestion line."""
        from lm_mcp.tools import format_response

        data = {
            "error": True,
            "code": "TEST_ERROR",
            "message": "Something went wrong",
        }
        result = format_response(data)

        assert "Error: Something went wrong" in result[0].text
        assert "Suggestion:" not in result[0].text


class TestHandleError:
    """Tests for handle_error function."""

    def test_handle_lm_error(self):
        """LMError is converted to formatted error response."""
        from lm_mcp.tools import handle_error

        error = LMError("Test error", code="TEST_CODE", suggestion="Fix it")
        result = handle_error(error)

        assert len(result) == 1
        assert "Error: Test error" in result[0].text
        assert "Suggestion: Fix it" in result[0].text

    def test_handle_authentication_error(self):
        """AuthenticationError preserves its code and suggestion."""
        from lm_mcp.tools import handle_error

        error = AuthenticationError("Invalid token")
        result = handle_error(error)

        assert "Error: Invalid token" in result[0].text
        # Should include the default suggestion from AuthenticationError

    def test_handle_not_found_error(self):
        """NotFoundError is handled correctly."""
        from lm_mcp.tools import handle_error

        error = NotFoundError("Device 123 not found")
        result = handle_error(error)

        assert "Error: Device 123 not found" in result[0].text

    def test_handle_generic_exception(self):
        """Generic exceptions are wrapped in UNEXPECTED_ERROR."""
        from lm_mcp.tools import handle_error

        error = ValueError("Something unexpected")
        result = handle_error(error)

        assert "Error: Something unexpected" in result[0].text

    def test_handle_error_returns_text_content(self):
        """handle_error returns list of TextContent."""
        from mcp.types import TextContent

        from lm_mcp.tools import handle_error

        error = LMError("Test")
        result = handle_error(error)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
