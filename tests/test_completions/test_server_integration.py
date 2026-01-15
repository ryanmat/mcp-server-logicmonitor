# Description: Integration tests for MCP server completion handler.
# Description: Verifies the server.completion() decorator works correctly.

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lm_mcp.server import complete


class TestServerCompletionHandler:
    """Tests for the server completion handler."""

    @pytest.mark.asyncio
    async def test_complete_returns_complete_result(self):
        """complete() returns a CompleteResult."""
        ref = MagicMock()
        argument = MagicMock()
        argument.name = "severity"
        argument.value = ""

        result = await complete(ref, argument)

        assert hasattr(result, "completion")
        assert hasattr(result.completion, "values")

    @pytest.mark.asyncio
    async def test_complete_severity_values(self):
        """complete() returns severity values for severity argument."""
        ref = MagicMock()
        argument = MagicMock()
        argument.name = "severity"
        argument.value = ""

        result = await complete(ref, argument)

        assert "critical" in result.completion.values
        assert "error" in result.completion.values
        assert "warning" in result.completion.values
        assert "info" in result.completion.values

    @pytest.mark.asyncio
    async def test_complete_with_prefix_filters(self):
        """complete() filters values by prefix."""
        ref = MagicMock()
        argument = MagicMock()
        argument.name = "severity"
        argument.value = "cr"

        result = await complete(ref, argument)

        assert "critical" in result.completion.values
        assert "error" not in result.completion.values

    @pytest.mark.asyncio
    async def test_complete_unknown_argument(self):
        """complete() returns empty completion for unknown argument."""
        ref = MagicMock()
        argument = MagicMock()
        argument.name = "unknown_field"
        argument.value = ""

        result = await complete(ref, argument)

        assert len(result.completion.values) == 0
        assert result.completion.total == 0

    @pytest.mark.asyncio
    async def test_complete_status_argument(self):
        """complete() returns status values for status argument."""
        ref = MagicMock()
        argument = MagicMock()
        argument.name = "status"
        argument.value = ""

        result = await complete(ref, argument)

        assert "normal" in result.completion.values
        assert "dead" in result.completion.values

    @pytest.mark.asyncio
    async def test_complete_sdt_type_argument(self):
        """complete() returns SDT types for sdt_type argument."""
        ref = MagicMock()
        argument = MagicMock()
        argument.name = "sdt_type"
        argument.value = ""

        result = await complete(ref, argument)

        assert "DeviceSDT" in result.completion.values
        assert "DeviceGroupSDT" in result.completion.values
