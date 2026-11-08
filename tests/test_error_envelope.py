# Description: Tests for the one error envelope (spec R2.7) every tool failure carries.
# Description: Covers each handle_error path, the dispatcher's refusals and handler errors.

from __future__ import annotations

import httpx
import pytest

from lm_mcp.exceptions import (
    AuthenticationError,
    LMError,
    LMPermissionError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from lm_mcp.tools import (
    format_response,
    handle_error,
    validation_error,
    write_disabled_response,
)
from tests.envelope import client_raised, envelope

HANDLE_ERROR_PATHS = [
    pytest.param(NotFoundError("Device 7 not found"), "NOT_FOUND", "validation", False, id="404"),
    pytest.param(
        ValidationError("filter value has a bare comma"),
        "INVALID_REQUEST",
        "validation",
        False,
        id="validation",
    ),
    pytest.param(
        LMError("Bad field", code="HTTP_400", suggestion="Fix it", details="raw jackson text"),
        "INVALID_REQUEST",
        "validation",
        False,
        id="other-4xx",
    ),
    pytest.param(
        RateLimitError("Too many requests", retry_after=30),
        "RATE_LIMITED",
        "transient",
        True,
        id="429",
    ),
    pytest.param(ServerError("Internal error"), "UPSTREAM_ERROR", "transient", True, id="5xx"),
    pytest.param(
        LMError("body error", code="API_ERROR_1007"),
        "INVALID_REQUEST",
        "validation",
        False,
        id="200-with-errorCode",
    ),
    pytest.param(
        LMError("body error", code="API_ERROR"),
        "INVALID_REQUEST",
        "validation",
        False,
        id="200-with-errorMessage",
    ),
    pytest.param(
        LMError("ingest rejected records", code="INGEST_PARTIAL_FAILURE"),
        "UPSTREAM_ERROR",
        "transient",
        True,
        id="other-lm-code",
    ),
    pytest.param(
        httpx.ReadTimeout("read timed out"), "TIMEOUT", "transient", True, id="raw-timeout"
    ),
    pytest.param(
        client_raised(httpx.ReadTimeout("")), "TIMEOUT", "transient", True, id="client-timeout"
    ),
    pytest.param(
        client_raised(httpx.ConnectError("refused")),
        "UPSTREAM_ERROR",
        "transient",
        True,
        id="connect-failed",
    ),
    pytest.param(
        AuthenticationError("Invalid token"), "AUTH_FAILED", "permission", False, id="401"
    ),
    pytest.param(
        LMPermissionError("Permission denied"), "AUTH_FAILED", "permission", False, id="403"
    ),
    pytest.param(RuntimeError("boom"), "UPSTREAM_ERROR", "transient", True, id="unknown"),
]


class TestHandleErrorEnvelope:
    @pytest.mark.parametrize(("error", "code", "category", "retryable"), HANDLE_ERROR_PATHS)
    def test_every_path_yields_a_documented_envelope(self, error, code, category, retryable):
        error_dict = envelope(handle_error(error))

        assert error_dict["code"] == code
        assert error_dict["errorCategory"] == category
        assert error_dict["isRetryable"] is retryable

    def test_rate_limit_carries_retry_after(self):
        error_dict = envelope(handle_error(RateLimitError("slow down", retry_after=30)))

        assert error_dict["retry_after"] == 30
        assert "Wait 30 seconds" in error_dict["message"]

    def test_lm_code_and_server_message_go_in_details(self):
        error = LMError("Bad field", code="HTTP_400", suggestion="Fix it", details="raw text")

        error_dict = envelope(handle_error(error))

        assert error_dict["message"] == "Bad field. Fix it"
        assert error_dict["details"] == {"lm_code": "HTTP_400", "lm_message": "raw text"}

    def test_403_keeps_its_own_code_in_details(self):
        error_dict = envelope(handle_error(LMPermissionError("Permission denied")))

        assert error_dict["details"] == {"lm_code": "PERMISSION_DENIED"}

    def test_documented_lm_code_adds_no_details(self):
        error_dict = envelope(handle_error(NotFoundError("Device 7 not found")))

        assert error_dict["details"] is None
        assert error_dict["message"].startswith("Device 7 not found")

    def test_unknown_exception_names_its_class(self):
        error_dict = envelope(handle_error(KeyError("missing_field")))

        assert error_dict["details"] == {"exception": "KeyError"}
        assert error_dict["message"] == "'missing_field'"

    def test_unknown_exception_with_empty_text_names_its_class(self):
        error_dict = envelope(handle_error(RuntimeError()))

        assert error_dict["message"] == "RuntimeError"


class TestHandlerErrors:
    def test_unknown_code_is_refused(self):
        with pytest.raises(KeyError):
            validation_error("NO_CHANGES", "nothing to do")

    def test_validation_error_folds_the_suggestion_into_the_message(self):
        error_dict = envelope(validation_error("INVALID_REQUEST", "No updates provided", "Pass x"))

        assert error_dict["code"] == "INVALID_REQUEST"
        assert error_dict["message"] == "No updates provided. Pass x"

    def test_message_ending_in_punctuation_is_not_doubled(self):
        error_dict = envelope(validation_error("INVALID_REQUEST", "Nothing given.", "Pass x"))

        assert error_dict["message"] == "Nothing given. Pass x"

    def test_handler_dict_extra_keys_become_details(self):
        result = format_response(
            {
                "error": True,
                "code": "REJECTED_BY_TOOL",
                "message": "Collector 'c1' has 3 devices assigned.",
                "suggestion": "Move them first.",
                "collector_id": 9,
                "device_count": 3,
            }
        )

        error_dict = envelope(result)
        assert error_dict["details"] == {"collector_id": 9, "device_count": 3}
        assert error_dict["isRetryable"] is False
        assert error_dict["errorCategory"] == "business"

    def test_write_disabled(self):
        error_dict = envelope(write_disabled_response())

        assert error_dict["code"] == "WRITE_DISABLED"
        assert error_dict["errorCategory"] == "permission"
        assert "LM_ENABLE_WRITE_OPERATIONS=true" in error_dict["message"]
