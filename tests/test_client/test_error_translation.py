# Description: Tests for Jackson-aware LM error translation in the client.
# Description: Exercises _translate_lm_error and its integration with _raise_for_status.

from __future__ import annotations

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.client.api import _translate_lm_error
from lm_mcp.exceptions import LMError


@pytest.fixture
def client():
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=BearerAuth("test-token"),
        timeout=30,
        api_version=3,
    )


class TestTranslatePureFunction:
    """Unit tests for _translate_lm_error."""

    def test_period_pojo_is_rewritten(self):
        raw = (
            "Invalid json body - Cannot construct instance of "
            "`com.santaba.server.servlet.rest.v3.pojos.setting.alert."
            "RestEscalatingChainV3$Period` (although at least one Creator...)"
        )
        translated, suggestion = _translate_lm_error(raw)
        assert translated is not None
        assert "period must be null" in translated
        assert suggestion is not None
        assert "timebased" in suggestion

    def test_recipient_list_pojo_is_rewritten(self):
        raw = (
            "Cannot deserialize value of type "
            "`java.util.ArrayList<com.santaba.server.servlet.rest.v3.pojos."
            "setting.admin.RestRecipientV3>` from Object value"
        )
        translated, suggestion = _translate_lm_error(raw)
        assert translated is not None
        assert "stages expects a list of Recipient" in translated
        assert "list of lists" in suggestion

    def test_invalid_recipient_keeps_raw_but_attaches_hint(self):
        raw = "invalid recipient for stage 1 : INTEGRATION is invalid"
        translated, suggestion = _translate_lm_error(raw)
        # Raw message preserved (translator returns None for the message).
        assert translated is None
        assert suggestion is not None
        assert "INTEGRATION" in suggestion
        assert "integration-shorthand" in suggestion

    def test_admin_not_found_by_id_rewrites_with_capture(self):
        raw = "admin<3> is not found"
        translated, suggestion = _translate_lm_error(raw)
        assert translated == "admin user id 3 not found"
        assert "username string" in suggestion

    def test_arbitrary_method_error_keeps_raw_adds_hint(self):
        raw = (
            "invalid recipient for stage 1 : invalid method <integration>"
            " for type ARBITRARY, must be email."
        )
        translated, suggestion = _translate_lm_error(raw)
        # The first matching pattern ("invalid recipient for stage") wins and
        # keeps the raw message; its suggestion already explains the fix.
        assert translated is None
        assert "INTEGRATION" in suggestion or "integration" in suggestion.lower()

    def test_unknown_400_returns_none_tuple(self):
        translated, suggestion = _translate_lm_error(
            "Some unrelated validation error about a widget."
        )
        assert translated is None
        assert suggestion is None

    def test_empty_message_returns_none(self):
        assert _translate_lm_error("") == (None, None)


class TestRaiseForStatusIntegration:
    """Tests that _raise_for_status surfaces translations end to end."""

    @respx.mock
    async def test_400_with_period_pojo_raises_translated(self, client):
        respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(
                400,
                json={
                    "errorMessage": (
                        "Invalid json body - Cannot construct instance of "
                        "`com.example.RestEscalatingChainV3$Period`"
                    )
                },
            )
        )

        with pytest.raises(LMError) as exc_info:
            await client.post(
                "/setting/alert/chains",
                json_body={"name": "bad", "destinations": []},
            )

        err = exc_info.value
        assert "period must be null" in err.message
        assert err.suggestion and "timebased" in err.suggestion
        # Raw server message kept under details.
        assert err.details and "RestEscalatingChainV3$Period" in err.details
        assert err.code == "HTTP_400"

    @respx.mock
    async def test_400_with_unknown_message_falls_through(self, client):
        respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(400, json={"errorMessage": "something else broke"})
        )

        with pytest.raises(LMError) as exc_info:
            await client.post("/setting/alert/chains", json_body={"x": 1})

        err = exc_info.value
        assert err.message == "something else broke"
        # Generic fallback suggestion kicks in, no details overlay.
        assert err.suggestion and "HTTP 400" in err.suggestion
        assert err.details is None

    @respx.mock
    async def test_invalid_recipient_keeps_raw_surfaces_hint(self, client):
        respx.post("https://test.logicmonitor.com/santaba/rest/setting/alert/chains").mock(
            return_value=httpx.Response(
                400,
                json={"errorMessage": ("invalid recipient for stage 1 : INTEGRATION is invalid")},
            )
        )

        with pytest.raises(LMError) as exc_info:
            await client.post("/setting/alert/chains", json_body={"x": 1})

        err = exc_info.value
        assert "INTEGRATION is invalid" in err.message
        assert err.suggestion and "integration-shorthand" in err.suggestion
        # Only the suggestion changed, so details carries the (same) raw text.
        assert err.details and "INTEGRATION is invalid" in err.details


class TestLMErrorDetailsField:
    """to_dict() surfaces the details field when present."""

    def test_to_dict_includes_details(self):
        err = LMError(
            message="user-facing",
            code="HTTP_400",
            suggestion="do this",
            details="raw server blob",
        )
        data = err.to_dict()
        assert data["details"] == "raw server blob"
        assert data["message"] == "user-facing"
        assert data["suggestion"] == "do this"

    def test_to_dict_omits_details_when_absent(self):
        err = LMError(message="hi")
        data = err.to_dict()
        assert "details" not in data
