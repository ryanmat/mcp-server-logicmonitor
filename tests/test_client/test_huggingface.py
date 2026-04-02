# Description: Tests for HuggingFace local Granite model client.
# Description: Verifies interface parity with WatsonxClient using mocked models.

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestHuggingFaceClientForecast:
    """Tests for forecast_ttm method."""

    @pytest.mark.asyncio
    async def test_forecast_returns_correct_shape(self):
        """forecast_ttm returns dict with forecast_values, forecast_count, model."""
        torch = pytest.importorskip("torch")
        from lm_mcp.client.huggingface import HuggingFaceClient

        client = HuggingFaceClient(ttm_model="test/model")

        # Mock the TTM model
        mock_output = MagicMock()
        mock_output.prediction_outputs = torch.randn(1, 96, 1)

        mock_model = MagicMock(return_value=mock_output)
        client._ttm_model = mock_model

        timestamps = list(range(0, 512 * 300, 300))
        values = [float(i) for i in range(512)]

        result = await client.forecast_ttm(timestamps, values, forecast_periods=96)

        assert "forecast_values" in result
        assert "forecast_count" in result
        assert "model" in result
        assert result["forecast_count"] == 96
        assert result["model"] == "test/model"
        assert len(result["forecast_values"]) == 96

    @pytest.mark.asyncio
    async def test_forecast_truncates_to_512(self):
        """forecast_ttm uses last 512 values from longer input."""
        torch = pytest.importorskip("torch")
        from lm_mcp.client.huggingface import HuggingFaceClient

        client = HuggingFaceClient()

        mock_output = MagicMock()
        mock_output.prediction_outputs = torch.randn(1, 96, 1)
        mock_model = MagicMock(return_value=mock_output)
        client._ttm_model = mock_model

        timestamps = list(range(0, 1000 * 300, 300))
        values = [float(i) for i in range(1000)]

        await client.forecast_ttm(timestamps, values)

        # Verify model was called with tensor of shape (1, 512, 1)
        call_args = mock_model.call_args[0][0]
        assert call_args.shape == (1, 512, 1)


class TestHuggingFaceClientSummarize:
    """Tests for summarize method."""

    @pytest.mark.asyncio
    async def test_summarize_returns_string(self):
        """summarize returns a plain string."""
        pytest.importorskip("torch")
        from lm_mcp.client.huggingface import HuggingFaceClient

        client = HuggingFaceClient()

        mock_pipe = MagicMock(return_value=[{"generated_text": "  Summary text here.  "}])
        client._llm_pipeline = mock_pipe

        result = await client.summarize({"alerts": 5}, context="triage")

        assert isinstance(result, str)
        assert result == "Summary text here."

    @pytest.mark.asyncio
    async def test_summarize_truncates_large_data(self):
        """summarize truncates data over 8000 chars."""
        pytest.importorskip("torch")
        from lm_mcp.client.huggingface import HuggingFaceClient

        client = HuggingFaceClient()

        mock_pipe = MagicMock(return_value=[{"generated_text": "Short summary."}])
        client._llm_pipeline = mock_pipe

        large_data = {"big": "x" * 10000}
        await client.summarize(large_data)

        # The prompt passed to the pipeline should be truncated
        call_args = mock_pipe.call_args[0][0]
        assert "truncated" in call_args

    @pytest.mark.asyncio
    async def test_summarize_accepts_string_data(self):
        """summarize accepts raw string input."""
        pytest.importorskip("torch")
        from lm_mcp.client.huggingface import HuggingFaceClient

        client = HuggingFaceClient()

        mock_pipe = MagicMock(return_value=[{"generated_text": "Done."}])
        client._llm_pipeline = mock_pipe

        result = await client.summarize("plain text data", context="test")
        assert result == "Done."


class TestHuggingFaceClientLifecycle:
    """Tests for client lifecycle management."""

    @pytest.mark.asyncio
    async def test_close_clears_models(self):
        """close() sets model references to None."""
        pytest.importorskip("torch")
        from lm_mcp.client.huggingface import HuggingFaceClient

        client = HuggingFaceClient()
        client._ttm_model = MagicMock()
        client._llm_pipeline = MagicMock()

        await client.close()

        assert client._ttm_model is None
        assert client._llm_pipeline is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Client works as async context manager."""
        pytest.importorskip("torch")
        from lm_mcp.client.huggingface import HuggingFaceClient

        async with HuggingFaceClient() as client:
            assert client is not None
        assert client._ttm_model is None

    @pytest.mark.asyncio
    async def test_error_maps_to_lm_error(self):
        """Model inference errors are mapped to LMError."""
        pytest.importorskip("torch")
        from lm_mcp.client.huggingface import HuggingFaceClient
        from lm_mcp.exceptions import LMError

        client = HuggingFaceClient()
        client._ttm_model = MagicMock(side_effect=RuntimeError("out of memory"))

        with pytest.raises(LMError, match="TTM forecast failed"):
            await client.forecast_ttm(list(range(512)), [float(i) for i in range(512)])
