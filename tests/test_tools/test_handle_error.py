# Description: Tests for handle_error in tools/__init__.py.
# Description: Verifies LMError propagation and unexpected-error logging behavior.

from __future__ import annotations

import json
import logging

from lm_mcp.exceptions import AuthenticationError, LMError, NotFoundError
from lm_mcp.tools import handle_error


class TestHandleError:
    """Tests for the handle_error helper."""

    def test_lmerror_propagates_message(self):
        error = LMError("Boom", code="TEST_CODE", suggestion="Try again")
        result = handle_error(error)

        assert len(result) == 1
        text = result[0].text
        assert text.startswith("Error: Boom")
        assert "Suggestion: Try again" in text

    def test_lmerror_subclass_preserves_message(self):
        error = NotFoundError("device 42 not found")
        result = handle_error(error)

        assert "device 42" in result[0].text
        assert result[0].text.startswith("Error:")

    def test_authentication_error_propagates(self):
        error = AuthenticationError("token expired")
        result = handle_error(error)

        assert "token expired" in result[0].text

    def test_unexpected_error_returns_error_text(self):
        error = ValueError("not a string")
        result = handle_error(error)

        assert result[0].text.startswith("Error: not a string")

    def test_unexpected_error_logged_via_logger_exception(self, caplog):
        """JSONDecodeError, KeyError, ValueError etc. must leave a stack trace."""
        with caplog.at_level(logging.ERROR, logger="lm_mcp.tools"):
            error = json.JSONDecodeError("bad json", "doc", 0)
            handle_error(error)

        assert any(
            "unhandled error in tool handler" in record.message for record in caplog.records
        ), "handle_error must log non-LMError exceptions"

        exc_records = [r for r in caplog.records if r.exc_info]
        assert exc_records, "handle_error must include exception info (logger.exception)"

    def test_unexpected_error_logs_keyerror_with_traceback(self, caplog):
        with caplog.at_level(logging.ERROR, logger="lm_mcp.tools"):
            error = KeyError("missing_field")
            handle_error(error)

        assert any(r.exc_info for r in caplog.records)

    def test_unexpected_error_logs_runtime_error_with_traceback(self, caplog):
        with caplog.at_level(logging.ERROR, logger="lm_mcp.tools"):
            error = RuntimeError("something broke")
            handle_error(error)

        assert any(
            r.exc_info and "unhandled error in tool handler" in r.message for r in caplog.records
        )

    def test_lmerror_does_not_log_via_exception(self, caplog):
        """LMError instances should NOT log via logger.exception (they're expected)."""
        with caplog.at_level(logging.ERROR, logger="lm_mcp.tools"):
            handle_error(NotFoundError("expected miss"))

        assert not any(
            "unhandled error in tool handler" in record.message for record in caplog.records
        )
