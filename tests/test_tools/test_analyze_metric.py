# Description: Tests for analyze_metric, the one-fetch analysis of a device instance's series.
# Description: Covers the paged read, the summary and trend sections, selection and warnings.

import json
import time
from unittest.mock import patch

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES, coefficient_of_variation
from tests.envelope import envelope

# Base epoch for test data (2024-01-15 00:00:00 UTC)
BASE_EPOCH = 1705276800

SERIES_URL = (
    "https://test.logicmonitor.com/santaba/rest"
    "/device/devices/1/devicedatasources/10/instances/100/data"
)
SERIES_ARGS = {"device_id": 1, "device_datasource_id": 10, "instance_id": 100}


@pytest.fixture
def client():
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=BearerAuth("test-token"),
        timeout=30,
    )


def _data_page(times_sec, rows, next_page=""):
    """Build one data page in the live shape: rows newest first, ms timestamps."""
    return {
        "dataSourceName": "Ping",
        "dataPoints": ["cpu", "memory"],
        "values": rows,
        "time": [t * 1000 for t in times_sec],
        "nextPageParams": next_page,
    }


def _series_page(points, next_page=""):
    """One page from (epoch, cpu) pairs given oldest first; memory is a flat 1.0."""
    newest_first = sorted(points, key=lambda p: p[0], reverse=True)
    return _data_page(
        [t for t, _ in newest_first],
        [[cpu, 1.0] for _, cpu in newest_first],
        next_page=next_page,
    )


def _hours(hours_and_values):
    """(hour offset, value) pairs as (epoch, value) pairs from BASE_EPOCH."""
    return [(BASE_EPOCH + int(h * 3600), v) for h, v in hours_and_values]


async def _analyze(client, **kwargs):
    from lm_mcp.tools.analyze_metric import analyze_metric

    return await analyze_metric(client, **SERIES_ARGS, **kwargs)


def _body(result):
    return json.loads(result[0].text)


class TestOneFetch:
    """R2.1: every section is computed from one paged read of the window."""

    @respx.mock
    async def test_reads_each_page_of_the_window_once_for_both_sections(self, client):
        """Two pages of the window are two calls, with summary and trend both requested."""
        marker = f"start={BASE_EPOCH - 7200}&end={BASE_EPOCH - 1}"
        route = respx.get(SERIES_URL).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json=_series_page(_hours([(0, 10.0), (1, 12.0)]), next_page=marker),
                ),
                httpx.Response(200, json=_series_page(_hours([(-2, 6.0), (-1, 8.0)]))),
            ]
        )

        result = await _analyze(client, analyses=["summary", "trend"])

        assert route.call_count == 2
        cpu = _body(result)["datapoints"]["cpu"]
        assert cpu["sample_count"] == 4
        assert cpu["summary"]["latest"] == 12.0
        assert cpu["summary"]["min"] == 6.0
        assert cpu["trend"]["slope_per_hour"] == 2.0

    @respx.mock
    async def test_default_runs_every_section(self, client):
        """With analyses omitted the response carries every section the tool offers."""
        from lm_mcp.tools.analyze_metric import SECTIONS

        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours([(0, 1.0), (1, 2.0)])))
        )

        body = _body(await _analyze(client))

        assert body["analyses"] == list(SECTIONS)
        assert set(SECTIONS) <= set(body["datapoints"]["cpu"])

    @respx.mock
    async def test_analyses_selects_sections(self, client):
        """Only the named sections are computed and returned."""
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours([(0, 1.0), (1, 2.0)])))
        )

        cpu = _body(await _analyze(client, analyses=["summary"]))["datapoints"]["cpu"]

        assert "summary" in cpu
        assert "trend" not in cpu

    @pytest.mark.parametrize(
        "analyses",
        [["summary", "bogus"], ["Trend"], []],
        ids=["unknown", "wrong-case", "empty"],
    )
    @respx.mock
    async def test_unknown_or_empty_analyses_is_invalid_request_before_any_read(
        self, client, analyses
    ):
        """A section the tool does not offer, or none at all, is refused before the read."""
        route = respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours([(0, 1.0)])))
        )

        error = envelope(await _analyze(client, analyses=analyses))

        assert error["code"] == "INVALID_REQUEST"
        assert "summary" in error["message"] and "trend" in error["message"]
        assert route.call_count == 0


class TestSummary:
    """R2.1 summary: latest, mean, standard deviation, min, max, z-score of latest."""

    @respx.mock
    async def test_summary_statistics(self, client):
        """Sample standard deviation, and the latest sample's z-score against the window."""
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(
                200,
                json=_series_page(_hours([(0, 10.0), (1, 20.0), (2, 30.0), (3, 40.0), (4, 100.0)])),
            )
        )

        summary = _body(await _analyze(client, analyses=["summary"]))["datapoints"]["cpu"][
            "summary"
        ]

        assert summary == {
            "latest": 100.0,
            "mean": 40.0,
            "stddev": 35.3553,
            "min": 10.0,
            "max": 100.0,
            "z_score": 1.6971,
        }

    @respx.mock
    async def test_z_score_is_signed(self, client):
        """A latest sample below the mean has a negative z-score."""
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(
                200,
                json=_series_page(_hours([(0, 100.0), (1, 40.0), (2, 30.0), (3, 20.0), (4, 10.0)])),
            )
        )

        summary = _body(await _analyze(client, analyses=["summary"]))["datapoints"]["cpu"][
            "summary"
        ]

        assert summary["latest"] == 10.0
        assert summary["z_score"] == -0.8485

    @respx.mock
    async def test_flat_series_has_zero_deviation_and_zero_z(self, client):
        """A constant series has standard deviation 0 and z-score 0, not a division error."""
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(
                200, json=_series_page(_hours([(0, 5.0), (1, 5.0), (2, 5.0)]))
            )
        )

        summary = _body(await _analyze(client, analyses=["summary"]))["datapoints"]["cpu"][
            "summary"
        ]

        assert summary["stddev"] == 0.0
        assert summary["z_score"] == 0.0


class TestTrend:
    """R2.1 trend: OLS and Theil-Sen slope per hour, r-squared, CV and the label."""

    @respx.mock
    async def test_slopes_are_per_hour_across_a_gap(self, client):
        """A ten-hour gap in the samples leaves the slope at 5 per hour, not per sample."""
        points = _hours([(0, 1000.0), (1, 1005.0), (2, 1010.0), (10, 1050.0), (11, 1055.0)])
        respx.get(SERIES_URL).mock(return_value=httpx.Response(200, json=_series_page(points)))

        trend = _body(await _analyze(client, analyses=["trend"]))["datapoints"]["cpu"]["trend"]

        assert trend["slope_per_hour"] == 5.0
        assert trend["theil_sen_slope_per_hour"] == 5.0
        assert trend["r_squared"] == 1.0
        values = [v for _, v in points]
        assert trend["coefficient_of_variation"] == round(coefficient_of_variation(values), 4)
        assert trend["label"] == "increasing"

    @respx.mock
    async def test_theil_sen_ignores_a_spike_that_moves_ols(self, client):
        """One spike pulls the least-squares slope; the median of pairwise slopes stays at 2."""
        rows = [(h, 1000.0 + 2.0 * h) for h in range(9)]
        rows[7] = (7, 2000.0)
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours(rows)))
        )

        trend = _body(await _analyze(client, analyses=["trend"]))["datapoints"]["cpu"]["trend"]

        assert trend["theil_sen_slope_per_hour"] == 2.0
        assert trend["slope_per_hour"] > 2.5

    @respx.mock
    async def test_theil_sen_subsample_spans_a_long_series(self, client):
        """Past the pairwise cap the subsample spans the window, not its first or last samples.

        The series is flat for its first 1,000 minutes and falls 3 per hour for the next
        1,000; a subsample of either half alone would give exactly 0 or exactly -3.
        """
        from lm_mcp.tools.stats_helpers import THEIL_SEN_MAX_SAMPLES

        rows = [(k / 60.0, 500.0 - 3.0 * max(0, k - 1000) / 60.0) for k in range(2000)]
        assert len(rows) > 2 * THEIL_SEN_MAX_SAMPLES
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours(rows)))
        )

        trend = _body(await _analyze(client, analyses=["trend"]))["datapoints"]["cpu"]["trend"]

        assert -3.0 < trend["theil_sen_slope_per_hour"] < 0.0

    @respx.mock
    async def test_trend_matches_classify_trend_on_the_same_page(self, client):
        """The trend math is classify_trend's, moved: the shared figures agree on one page."""
        from lm_mcp.tools.forecasting import classify_trend

        rows = [(h * 0.5, 50.0 + (h % 7) * 3.0 + h * 0.2) for h in range(120)]
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours(rows)))
        )

        trend = _body(await _analyze(client, analyses=["trend"]))["datapoints"]["cpu"]["trend"]
        old = _body(await classify_trend(client, **SERIES_ARGS, datapoints="cpu"))[
            "classifications"
        ]["cpu"]

        assert trend["slope_per_hour"] == old["slope_per_hour"]
        assert trend["r_squared"] == old["r_squared"]
        assert trend["coefficient_of_variation"] == old["volatility_index"]
        assert trend["autocorrelation_24h"] == old["autocorrelation_24h"]
        assert trend["label"] == old["classification"]
        assert trend["confidence"] == old["confidence"]


class TestSeriesEdges:
    """Short series, truncation and warnings carry through from the paged reader."""

    @respx.mock
    async def test_fewer_than_two_samples_is_insufficient_data(self, client):
        """One sample reports insufficient_data in each section with the count."""
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours([(0, 7.0)])))
        )

        cpu = _body(await _analyze(client))["datapoints"]["cpu"]

        assert cpu["sample_count"] == 1
        assert cpu["summary"] == {"status": "insufficient_data"}
        assert cpu["trend"] == {"status": "insufficient_data"}

    @respx.mock
    async def test_capped_read_is_truncated_and_warns(self, client):
        """A read stopped by the page cap marks the datapoint truncated and warns by name."""
        pages = []
        for i in range(MAX_SERIES_PAGES):
            t = BASE_EPOCH - i * 600
            pages.append(
                httpx.Response(
                    200,
                    json=_data_page(
                        [t, t - 300],
                        [[50.0 + i, 70.0 - i], [51.0 + i, 71.0 - i]],
                        next_page=f"start={BASE_EPOCH - 86400}&end={t - 301}",
                    ),
                )
            )
        route = respx.get(SERIES_URL).mock(side_effect=pages)

        body = _body(await _analyze(client))

        assert route.call_count == MAX_SERIES_PAGES
        assert body["datapoints"]["cpu"]["truncated"] is True
        assert any(w.startswith("cpu:") and "page cap" in w for w in body["warnings"])
        assert any(w.startswith("memory:") for w in body["warnings"])

    @respx.mock
    async def test_complete_read_has_no_warnings(self, client):
        """A read that reached the end of the window is not truncated and carries no warnings."""
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours([(0, 1.0), (1, 2.0)])))
        )

        body = _body(await _analyze(client))

        assert body["datapoints"]["cpu"]["truncated"] is False
        assert "warnings" not in body

    @respx.mock
    async def test_datapoints_and_hours_reach_the_read(self, client):
        """The datapoint list is sent on the read and the window is echoed in the response."""
        route = respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours([(0, 1.0), (1, 2.0)])))
        )

        body = _body(await _analyze(client, datapoints="cpu", hours=48))

        assert route.calls[0].request.url.params["datapoints"] == "cpu"
        start = int(route.calls[0].request.url.params["start"])
        end_of_window = start + 48 * 3600
        assert abs(end_of_window - int(time.time())) < 60
        assert body["hours"] == 48


class TestRegistration:
    """analyze_metric is a registered, read-only tool dispatched through execute_tool."""

    def test_schema_offers_exactly_the_sections(self):
        """The schema's analyses enum is the module's section list, so the two cannot drift."""
        from lm_mcp.registry import TOOLS
        from lm_mcp.tools.analyze_metric import SECTIONS

        tool = next(t for t in TOOLS if t.name == "analyze_metric")

        assert tool.inputSchema["properties"]["analyses"]["items"]["enum"] == list(SECTIONS)
        assert tool.inputSchema["required"] == [
            "device_id",
            "device_datasource_id",
            "instance_id",
        ]
        assert tool.annotations.readOnlyHint is True

    @respx.mock
    async def test_execute_tool_dispatches_to_analyze_metric(self, client, monkeypatch):
        """A tools/call for analyze_metric reaches the handler and returns its sections."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours([(0, 3.0), (1, 4.0)])))
        )

        with patch("lm_mcp.server._client", client):
            from lm_mcp.server import execute_tool

            result = await execute_tool("analyze_metric", {**SERIES_ARGS, "analyses": ["summary"]})

        assert _body(result)["datapoints"]["cpu"]["summary"]["latest"] == 4.0
