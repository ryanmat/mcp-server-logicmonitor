# Description: Tests for WatsonxClient SDK wrapper.
# Description: Mocks ibm-watsonx-ai SDK classes to test async wrapping and error mapping.

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_client():
    """Create a WatsonxClient with mocked SDK dependencies."""
    mock_credentials = MagicMock()
    mock_api_client = MagicMock()

    with (
        patch("ibm_watsonx_ai.Credentials", return_value=mock_credentials),
        patch("ibm_watsonx_ai.APIClient", return_value=mock_api_client),
    ):
        from lm_mcp.client.watsonx import WatsonxClient

        client = WatsonxClient(
            api_key="test-key",
            url="https://us-south.ml.cloud.ibm.com",
            project_id="proj-123",
        )
    return client


class TestWatsonxClientForecast:
    """Tests for the forecast_ttm method."""

    @pytest.mark.asyncio
    async def test_forecast_ttm_returns_expected_shape(self):
        """forecast_ttm returns dict with forecast_values and model."""
        client = _make_client()
        client._run_ttm_forecast = MagicMock(
            return_value={
                "forecast_values": [45.1, 45.3, 45.5],
                "forecast_count": 3,
                "model": "ibm/granite-ttm-512-96-r2",
            }
        )

        result = await client.forecast_ttm(
            timestamps=[1000, 1300, 1600],
            values=[44.0, 44.5, 45.0],
        )

        assert "forecast_values" in result
        assert result["model"] == "ibm/granite-ttm-512-96-r2"
        assert len(result["forecast_values"]) == 3

    @pytest.mark.asyncio
    async def test_forecast_ttm_maps_auth_error(self):
        """forecast_ttm maps 401 errors to AuthenticationError."""
        from lm_mcp.exceptions import AuthenticationError

        client = _make_client()
        client._run_ttm_forecast = MagicMock(side_effect=Exception("401 Unauthorized"))

        with pytest.raises(AuthenticationError, match="401"):
            await client.forecast_ttm(
                timestamps=[1000, 1300],
                values=[44.0, 44.5],
            )

    @pytest.mark.asyncio
    async def test_forecast_ttm_maps_connection_error(self):
        """forecast_ttm maps connection errors to LMConnectionError."""
        from lm_mcp.exceptions import LMConnectionError

        client = _make_client()
        client._run_ttm_forecast = MagicMock(side_effect=Exception("connection timeout"))

        with pytest.raises(LMConnectionError, match="unreachable"):
            await client.forecast_ttm(
                timestamps=[1000, 1300],
                values=[44.0, 44.5],
            )


class TestWatsonxClientSummarize:
    """Tests for the summarize method."""

    @pytest.mark.asyncio
    async def test_summarize_returns_string(self):
        """summarize returns a plain text string."""
        client = _make_client()
        client._run_llm_generate = MagicMock(
            return_value="3 critical alerts detected on prod-db-01."
        )

        result = await client.summarize(
            data={"alerts": [{"severity": "critical"}]},
            context="triage report",
        )

        assert isinstance(result, str)
        assert "critical" in result

    @pytest.mark.asyncio
    async def test_summarize_truncates_large_input(self):
        """summarize truncates input data exceeding 8000 chars."""
        client = _make_client()

        captured_prompt = None

        def capture_generate(prompt, max_tokens):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "Summary of large data."

        client._run_llm_generate = capture_generate

        large_data = {"key": "x" * 10000}
        await client.summarize(data=large_data)

        assert captured_prompt is not None
        assert "truncated" in captured_prompt

    @pytest.mark.asyncio
    async def test_summarize_handles_string_input(self):
        """summarize accepts plain string data."""
        client = _make_client()
        client._run_llm_generate = MagicMock(return_value="Summary.")

        result = await client.summarize(data="plain text data")

        assert result == "Summary."


class TestBuildSummaryPrompt:
    """Tests for the prompt builder."""

    def test_includes_context(self):
        from lm_mcp.client.watsonx import _build_summary_prompt

        prompt = _build_summary_prompt('{"alerts": []}', "triage report")
        assert "Tool: triage report" in prompt
        assert "shift handoff" in prompt.lower()

    def test_no_context(self):
        from lm_mcp.client.watsonx import _build_summary_prompt

        prompt = _build_summary_prompt('{"alerts": []}', "")
        assert "Tool:" not in prompt
