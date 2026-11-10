# Description: Tests for shared statistical utility functions.
# Description: Validates the shared statistics and paged reads, and the tools' use of them.

import importlib
import json
import math

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient


@pytest.fixture
def auth():
    """Create a BearerAuth instance for testing."""
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
    )


# Base epoch for test data (2024-01-15 00:00:00 UTC)
BASE_EPOCH = 1705276800


class TestLinearRegression:
    """Tests for linear_regression function."""

    def test_perfect_positive_line(self):
        """Perfect positive linear data yields slope=1, r_squared=1."""
        from lm_mcp.tools.stats_helpers import linear_regression

        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        slope, intercept, r_sq = linear_regression(x, y)
        assert abs(slope - 2.0) < 1e-10
        assert abs(intercept - 0.0) < 1e-10
        assert abs(r_sq - 1.0) < 1e-10

    def test_negative_slope(self):
        """Negative slope data yields negative slope."""
        from lm_mcp.tools.stats_helpers import linear_regression

        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        slope, _intercept, r_sq = linear_regression(x, y)
        assert slope < 0
        assert abs(r_sq - 1.0) < 1e-10

    def test_constant_y(self):
        """Constant y values yield slope=0, r_squared=0."""
        from lm_mcp.tools.stats_helpers import linear_regression

        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 5.0, 5.0, 5.0, 5.0]
        slope, intercept, r_sq = linear_regression(x, y)
        assert abs(slope) < 1e-10
        assert abs(intercept - 5.0) < 1e-10
        assert abs(r_sq) < 1e-10

    def test_two_points(self):
        """Two points produce valid regression."""
        from lm_mcp.tools.stats_helpers import linear_regression

        x = [0.0, 1.0]
        y = [0.0, 1.0]
        slope, intercept, r_sq = linear_regression(x, y)
        assert abs(slope - 1.0) < 1e-10
        assert abs(intercept) < 1e-10
        assert abs(r_sq - 1.0) < 1e-10

    def test_single_point_raises(self):
        """Single point raises ValueError."""
        from lm_mcp.tools.stats_helpers import linear_regression

        with pytest.raises(ValueError, match="At least 2"):
            linear_regression([1.0], [1.0])

    def test_mismatched_lengths_raises(self):
        """Different-length x and y raises ValueError."""
        from lm_mcp.tools.stats_helpers import linear_regression

        with pytest.raises(ValueError, match="same length"):
            linear_regression([1.0, 2.0], [1.0])

    def test_identical_x_values(self):
        """Identical x values (vertical line) returns slope=0."""
        from lm_mcp.tools.stats_helpers import linear_regression

        x = [3.0, 3.0, 3.0]
        y = [1.0, 2.0, 3.0]
        slope, _intercept, _r_sq = linear_regression(x, y)
        assert abs(slope) < 1e-10

    def test_noisy_data_r_squared_less_than_one(self):
        """Noisy data produces r_squared < 1."""
        from lm_mcp.tools.stats_helpers import linear_regression

        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.1, 3.9, 6.2, 7.8, 10.1]
        slope, _intercept, r_sq = linear_regression(x, y)
        assert slope > 0
        assert 0 < r_sq < 1.0


class TestPearsonCorrelation:
    """Tests for pearson_correlation function."""

    def test_perfect_positive(self):
        """Perfectly correlated series returns r=1."""
        from lm_mcp.tools.stats_helpers import pearson_correlation

        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        r = pearson_correlation(x, y)
        assert abs(r - 1.0) < 1e-10

    def test_perfect_negative(self):
        """Perfectly inversely correlated series returns r=-1."""
        from lm_mcp.tools.stats_helpers import pearson_correlation

        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        r = pearson_correlation(x, y)
        assert abs(r - (-1.0)) < 1e-10

    def test_no_correlation(self):
        """Uncorrelated series returns r near 0."""
        from lm_mcp.tools.stats_helpers import pearson_correlation

        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 1.0, 4.0, 2.0, 3.0]
        r = pearson_correlation(x, y)
        assert abs(r) < 0.5

    def test_constant_series_returns_zero(self):
        """Constant series returns r=0."""
        from lm_mcp.tools.stats_helpers import pearson_correlation

        x = [5.0, 5.0, 5.0, 5.0]
        y = [1.0, 2.0, 3.0, 4.0]
        r = pearson_correlation(x, y)
        assert abs(r) < 1e-10

    def test_both_constant_returns_zero(self):
        """Both series constant returns r=0."""
        from lm_mcp.tools.stats_helpers import pearson_correlation

        r = pearson_correlation([5.0, 5.0, 5.0], [3.0, 3.0, 3.0])
        assert abs(r) < 1e-10

    def test_mismatched_lengths_raises(self):
        """Different-length series raises ValueError."""
        from lm_mcp.tools.stats_helpers import pearson_correlation

        with pytest.raises(ValueError, match="same length"):
            pearson_correlation([1.0, 2.0], [1.0])

    def test_fewer_than_two_raises(self):
        """Fewer than 2 points raises ValueError."""
        from lm_mcp.tools.stats_helpers import pearson_correlation

        with pytest.raises(ValueError, match="At least 2"):
            pearson_correlation([1.0], [1.0])


class TestAutocorrelation:
    """Tests for autocorrelation function."""

    def test_sinusoidal_known_period(self):
        """Sinusoidal data has high autocorrelation at its period."""
        from lm_mcp.tools.stats_helpers import autocorrelation

        # 100 points of sin with period 10
        values = [math.sin(2 * math.pi * i / 10) for i in range(100)]
        ac = autocorrelation(values, lag=10)
        assert ac > 0.9

    def test_constant_data_returns_zero(self):
        """Constant data returns autocorrelation=0."""
        from lm_mcp.tools.stats_helpers import autocorrelation

        values = [5.0] * 20
        ac = autocorrelation(values, lag=1)
        assert abs(ac) < 1e-10

    def test_lag_zero_or_negative_returns_zero(self):
        """Lag of zero returns 0."""
        from lm_mcp.tools.stats_helpers import autocorrelation

        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert autocorrelation(values, lag=0) == 0.0
        assert autocorrelation(values, lag=-1) == 0.0

    def test_lag_exceeding_length_returns_zero(self):
        """Lag >= series length returns 0."""
        from lm_mcp.tools.stats_helpers import autocorrelation

        values = [1.0, 2.0, 3.0]
        assert autocorrelation(values, lag=3) == 0.0
        assert autocorrelation(values, lag=10) == 0.0

    def test_short_series(self):
        """Short series (< 2 values) returns 0."""
        from lm_mcp.tools.stats_helpers import autocorrelation

        assert autocorrelation([1.0], lag=1) == 0.0
        assert autocorrelation([], lag=1) == 0.0


class TestShannonEntropy:
    """Tests for shannon_entropy function."""

    def test_uniform_distribution(self):
        """Uniform distribution has maximum entropy."""
        from lm_mcp.tools.stats_helpers import shannon_entropy

        # 4 equally likely events: entropy = log2(4) = 2.0
        probs = [0.25, 0.25, 0.25, 0.25]
        entropy = shannon_entropy(probs)
        assert abs(entropy - 2.0) < 1e-10

    def test_single_event(self):
        """Single certain event has zero entropy."""
        from lm_mcp.tools.stats_helpers import shannon_entropy

        assert shannon_entropy([1.0]) == 0.0

    def test_skewed_distribution(self):
        """Skewed distribution has lower entropy than uniform."""
        from lm_mcp.tools.stats_helpers import shannon_entropy

        # Heavily skewed
        skewed = shannon_entropy([0.9, 0.05, 0.025, 0.025])
        uniform = shannon_entropy([0.25, 0.25, 0.25, 0.25])
        assert skewed < uniform

    def test_empty_returns_zero(self):
        """Empty distribution returns zero entropy."""
        from lm_mcp.tools.stats_helpers import shannon_entropy

        assert shannon_entropy([]) == 0.0


class TestCoefficientOfVariation:
    """Tests for coefficient_of_variation function."""

    def test_normal_data(self):
        """CV of data with known mean and stddev."""
        from lm_mcp.tools.stats_helpers import coefficient_of_variation

        # Mean = 10, stddev ~= 1.58
        values = [8.0, 9.0, 10.0, 11.0, 12.0]
        cv = coefficient_of_variation(values)
        assert cv > 0
        assert cv < 1.0

    def test_zero_mean_returns_zero(self):
        """Mean of zero returns CV=0."""
        from lm_mcp.tools.stats_helpers import coefficient_of_variation

        values = [-2.0, -1.0, 0.0, 1.0, 2.0]
        cv = coefficient_of_variation(values)
        assert cv == 0.0

    def test_constant_data_returns_zero(self):
        """Constant data returns CV=0."""
        from lm_mcp.tools.stats_helpers import coefficient_of_variation

        values = [5.0, 5.0, 5.0, 5.0]
        cv = coefficient_of_variation(values)
        assert abs(cv) < 1e-10

    def test_single_value_returns_zero(self):
        """Single value returns CV=0."""
        from lm_mcp.tools.stats_helpers import coefficient_of_variation

        assert coefficient_of_variation([5.0]) == 0.0


class TestFetchMetricSeries:
    """Tests for fetch_metric_series function."""

    @respx.mock
    async def test_normal_fetch(self, client):
        """Fetches and transposes metric data correctly."""
        from lm_mcp.tools.stats_helpers import fetch_metric_series

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/1/devicedatasources/10/instances/100/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu", "memory"],
                    "values": [
                        [50.0, 70.0],
                        [55.0, 75.0],
                        [60.0, 80.0],
                    ],
                    "time": [
                        BASE_EPOCH * 1000,
                        (BASE_EPOCH + 300) * 1000,
                        (BASE_EPOCH + 600) * 1000,
                    ],
                },
            )
        )

        series = await fetch_metric_series(
            client, device_id=1, device_datasource_id=10, instance_id=100
        )

        assert "cpu" in series
        assert "memory" in series
        assert series["cpu"]["values"] == [50.0, 55.0, 60.0]
        assert series["memory"]["values"] == [70.0, 75.0, 80.0]
        assert len(series["cpu"]["timestamps"]) == 3

    @respx.mock
    async def test_a_window_ending_now_sends_its_end(self, client):
        """The endpoint answers start alone with its last hour: a read of lmryanmatuszewski
        on 2026-11-09 returned 60 one-minute rows for start=now-24h, on a Linux and a
        Windows host, and 500 rows naming a next page with end=now added."""
        import time

        from lm_mcp.tools.stats_helpers import fetch_metric_series

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/1/devicedatasources/10/instances/100/data"
        ).mock(
            return_value=httpx.Response(
                200, json={"dataPoints": ["cpu"], "values": [], "time": [], "nextPageParams": ""}
            )
        )

        before = int(time.time())
        await fetch_metric_series(
            client, device_id=1, device_datasource_id=10, instance_id=100, hours_back=24
        )
        after = int(time.time())

        params = route.calls[0].request.url.params
        assert before <= int(params["end"]) <= after
        assert int(params["end"]) - int(params["start"]) == 24 * 3600

    @respx.mock
    async def test_no_data_filtering(self, client):
        """'No Data' sentinel values are filtered out."""
        from lm_mcp.tools.stats_helpers import fetch_metric_series

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/1/devicedatasources/10/instances/100/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": [[50.0], ["No Data"], [60.0]],
                    "time": [
                        BASE_EPOCH * 1000,
                        (BASE_EPOCH + 300) * 1000,
                        (BASE_EPOCH + 600) * 1000,
                    ],
                },
            )
        )

        series = await fetch_metric_series(
            client, device_id=1, device_datasource_id=10, instance_id=100
        )

        assert len(series["cpu"]["values"]) == 2
        assert 50.0 in series["cpu"]["values"]
        assert 60.0 in series["cpu"]["values"]

    @respx.mock
    async def test_empty_data(self, client):
        """Empty data returns empty series."""
        from lm_mcp.tools.stats_helpers import fetch_metric_series

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/1/devicedatasources/10/instances/100/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": [],
                    "values": [],
                    "time": [],
                },
            )
        )

        series = await fetch_metric_series(
            client, device_id=1, device_datasource_id=10, instance_id=100
        )

        assert series == {}

    @respx.mock
    async def test_millisecond_timestamps_converted(self, client):
        """Millisecond timestamps are converted to seconds."""
        from lm_mcp.tools.stats_helpers import fetch_metric_series

        ms_ts = BASE_EPOCH * 1000
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/1/devicedatasources/10/instances/100/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": [[50.0]],
                    "time": [ms_ts],
                },
            )
        )

        series = await fetch_metric_series(
            client, device_id=1, device_datasource_id=10, instance_id=100
        )

        assert series["cpu"]["timestamps"][0] == BASE_EPOCH

    @respx.mock
    async def test_datapoints_filter_passed(self, client):
        """datapoints parameter is passed to the API."""
        from lm_mcp.tools.stats_helpers import fetch_metric_series

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/1/devicedatasources/10/instances/100/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": [[50.0]],
                    "time": [BASE_EPOCH * 1000],
                },
            )
        )

        await fetch_metric_series(
            client,
            device_id=1,
            device_datasource_id=10,
            instance_id=100,
            datapoints="cpu,memory",
        )

        params = dict(route.calls[0].request.url.params)
        assert params.get("datapoints") == "cpu,memory"


SERIES_URL = (
    "https://test.logicmonitor.com/santaba/rest"
    "/device/devices/1/devicedatasources/10/instances/100/data"
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


class TestFetchMetricSeriesOrderAndPaging:
    """R5: series come out oldest first and every page of the window is read.

    The live data endpoint returns rows newest first, 500 a page, with a
    nextPageParams query string while rows remain (probe 2026-10-30).
    """

    @respx.mock
    async def test_descending_rows_come_out_ascending_and_paired(self, client):
        """A newest-first page is returned oldest first with values kept on their times."""
        from lm_mcp.tools.stats_helpers import fetch_metric_series

        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(
                200,
                json=_data_page(
                    [BASE_EPOCH + 600, BASE_EPOCH + 300, BASE_EPOCH],
                    [[60.0, 80.0], [55.0, 75.0], [50.0, 70.0]],
                ),
            )
        )

        series = await fetch_metric_series(
            client, device_id=1, device_datasource_id=10, instance_id=100
        )

        assert series["cpu"]["timestamps"] == [BASE_EPOCH, BASE_EPOCH + 300, BASE_EPOCH + 600]
        assert series["cpu"]["values"] == [50.0, 55.0, 60.0]
        assert series["memory"]["values"] == [70.0, 75.0, 80.0]
        assert series["cpu"]["truncated"] is False

    @respx.mock
    async def test_latest_is_the_newest_sample(self, client):
        """analyze_metric reports the newest sample as latest on a newest-first page."""
        import json

        from lm_mcp.tools.analyze_metric import analyze_metric

        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(
                200,
                json=_data_page(
                    [BASE_EPOCH + 900, BASE_EPOCH + 600, BASE_EPOCH + 300, BASE_EPOCH],
                    [[90.0, 1.0], [70.0, 1.0], [50.0, 1.0], [30.0, 1.0]],
                ),
            )
        )

        result = await analyze_metric(
            client,
            device_id=1,
            device_datasource_id=10,
            instance_id=100,
            datapoints="cpu",
            hours=24,
            analyses=["summary", "trend"],
        )

        cpu = json.loads(result[0].text)["datapoints"]["cpu"]
        assert cpu["summary"]["latest"] == 90.0
        assert cpu["trend"]["label"] == "increasing"

    @respx.mock
    async def test_next_page_marker_is_followed_until_empty(self, client):
        """Each nextPageParams page is read with its start and end and the datapoints kept."""
        from lm_mcp.tools.stats_helpers import fetch_metric_series

        marker = f"start={BASE_EPOCH - 3600}&end={BASE_EPOCH + 599}"
        route = respx.get(SERIES_URL).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json=_data_page(
                        [BASE_EPOCH + 900, BASE_EPOCH + 600],
                        [[4.0, 40.0], [3.0, 30.0]],
                        next_page=marker,
                    ),
                ),
                httpx.Response(
                    200,
                    json=_data_page(
                        [BASE_EPOCH + 300, BASE_EPOCH],
                        [[2.0, 20.0], [1.0, 10.0]],
                    ),
                ),
            ]
        )

        series = await fetch_metric_series(
            client,
            device_id=1,
            device_datasource_id=10,
            instance_id=100,
            datapoints="cpu,memory",
        )

        assert route.call_count == 2
        second = dict(route.calls[1].request.url.params)
        assert second["start"] == str(BASE_EPOCH - 3600)
        assert second["end"] == str(BASE_EPOCH + 599)
        assert second["datapoints"] == "cpu,memory"
        assert series["cpu"]["values"] == [1.0, 2.0, 3.0, 4.0]
        assert series["memory"]["values"] == [10.0, 20.0, 30.0, 40.0]
        assert series["cpu"]["timestamps"] == [
            BASE_EPOCH,
            BASE_EPOCH + 300,
            BASE_EPOCH + 600,
            BASE_EPOCH + 900,
        ]
        assert series["cpu"]["truncated"] is False

    @respx.mock
    async def test_page_cap_binds_and_reports_truncated(self, client):
        """A window that never runs out stops at the page cap and says it was truncated."""
        from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES, fetch_metric_series

        pages = []
        for i in range(MAX_SERIES_PAGES + 5):
            t = BASE_EPOCH - i * 600
            pages.append(
                httpx.Response(
                    200,
                    json=_data_page(
                        [t, t - 300],
                        [[float(i), 0.0], [float(i), 0.0]],
                        next_page=f"start={BASE_EPOCH - 86400}&end={t - 301}",
                    ),
                )
            )
        route = respx.get(SERIES_URL).mock(side_effect=pages)

        series = await fetch_metric_series(
            client, device_id=1, device_datasource_id=10, instance_id=100
        )

        assert route.call_count == MAX_SERIES_PAGES
        assert series["cpu"]["truncated"] is True
        assert len(series["cpu"]["values"]) == 2 * MAX_SERIES_PAGES
        assert series["cpu"]["timestamps"] == sorted(series["cpu"]["timestamps"])

    @respx.mock
    async def test_page_cap_not_reported_when_last_page_is_final(self, client):
        """Reading exactly the cap's worth of pages, the last with no marker, is not truncated."""
        from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES, fetch_metric_series

        pages = []
        for i in range(MAX_SERIES_PAGES):
            t = BASE_EPOCH - i * 600
            last = i == MAX_SERIES_PAGES - 1
            pages.append(
                httpx.Response(
                    200,
                    json=_data_page(
                        [t],
                        [[float(i), 0.0]],
                        next_page="" if last else f"start={BASE_EPOCH - 86400}&end={t - 1}",
                    ),
                )
            )
        route = respx.get(SERIES_URL).mock(side_effect=pages)

        series = await fetch_metric_series(
            client, device_id=1, device_datasource_id=10, instance_id=100
        )

        assert route.call_count == MAX_SERIES_PAGES
        assert series["cpu"]["truncated"] is False


class TestHoltWinters:
    """Tests for holt_winters triple exponential smoothing."""

    def test_known_seasonal_data_produces_forecast(self):
        """Seasonal data produces a forecast of the correct length."""
        from lm_mcp.tools.stats_helpers import holt_winters

        # 4 complete seasons of length 6
        values = [10, 15, 20, 15, 10, 5] * 4
        result = holt_winters(values, season_length=6, forecast_periods=12)
        assert len(result["forecast"]) == 12
        assert len(result["fitted"]) == len(values)
        assert len(result["residuals"]) == len(values)

    def test_insufficient_data_raises(self):
        """Insufficient data for season length raises ValueError."""
        from lm_mcp.tools.stats_helpers import holt_winters

        with pytest.raises(ValueError, match="Need at least"):
            holt_winters([1.0, 2.0, 3.0], season_length=5)

    def test_constant_data_handled(self):
        """Constant data does not raise, produces flat forecast."""
        from lm_mcp.tools.stats_helpers import holt_winters

        values = [50.0] * 20
        result = holt_winters(values, season_length=5)
        # Forecast should be approximately constant
        for fv in result["forecast"]:
            assert abs(fv - 50.0) < 5.0

    def test_forecast_length_matches_parameter(self):
        """Forecast length matches the forecast_periods argument."""
        from lm_mcp.tools.stats_helpers import holt_winters

        values = [float(i % 10) for i in range(40)]
        result = holt_winters(values, season_length=10, forecast_periods=6)
        assert len(result["forecast"]) == 6


class TestIQRAnomalies:
    """Tests for iqr_anomalies function."""

    def test_known_outlier_detected(self):
        """Known outlier is flagged as anomaly."""
        from lm_mcp.tools.stats_helpers import iqr_anomalies

        values = [10, 11, 12, 10, 11, 12, 10, 11, 100]
        result = iqr_anomalies(values)
        assert 8 in result["anomaly_indices"]

    def test_no_outliers_in_uniform_data(self):
        """Uniform data has no anomalies."""
        from lm_mcp.tools.stats_helpers import iqr_anomalies

        values = [10.0, 11.0, 10.5, 10.8, 11.2, 10.3, 10.9, 11.1]
        result = iqr_anomalies(values)
        assert len(result["anomaly_indices"]) == 0

    def test_fewer_than_four_returns_empty(self):
        """Fewer than 4 values returns empty anomaly list."""
        from lm_mcp.tools.stats_helpers import iqr_anomalies

        result = iqr_anomalies([1.0, 2.0, 3.0])
        assert result["anomaly_indices"] == []
        assert result["q1"] == 0.0

    def test_fences_computed(self):
        """Q1, Q3, IQR, and fences are computed correctly."""
        from lm_mcp.tools.stats_helpers import iqr_anomalies

        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        result = iqr_anomalies(values)
        assert result["q1"] > 0
        assert result["q3"] > result["q1"]
        assert result["iqr"] > 0
        assert result["lower_fence"] < result["q1"]
        assert result["upper_fence"] > result["q3"]


class TestMADAnomalies:
    """Tests for mad_anomalies function."""

    def test_known_outlier_detected(self):
        """Known outlier is flagged as anomaly."""
        from lm_mcp.tools.stats_helpers import mad_anomalies

        # Data with variation so MAD is nonzero, plus an extreme outlier
        values = [10.0, 12.0, 11.0, 13.0, 10.0, 12.0, 11.0, 13.0, 200.0]
        result = mad_anomalies(values, threshold=3.0)
        assert 8 in result["anomaly_indices"]

    def test_constant_data_returns_zero_mad(self):
        """Constant data returns MAD=0 with no anomalies."""
        from lm_mcp.tools.stats_helpers import mad_anomalies

        values = [5.0, 5.0, 5.0, 5.0, 5.0]
        result = mad_anomalies(values)
        assert result["mad"] == 0.0
        assert result["anomaly_indices"] == []

    def test_fewer_than_three_returns_empty(self):
        """Fewer than 3 values returns empty results."""
        from lm_mcp.tools.stats_helpers import mad_anomalies

        result = mad_anomalies([1.0, 2.0])
        assert result["anomaly_indices"] == []
        assert result["modified_z_scores"] == []

    def test_modified_z_scores_present(self):
        """Modified z-scores are computed for all values."""
        from lm_mcp.tools.stats_helpers import mad_anomalies

        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        result = mad_anomalies(values)
        assert len(result["modified_z_scores"]) == len(values)


SERIES_ARGS = {"device_id": 1, "device_datasource_id": 10, "instance_id": 100}
SECOND_SERIES_ARGS = {"device_id": 2, "device_datasource_id": 10, "instance_id": 100}
SECOND_SERIES_URL = SERIES_URL.replace("/devices/1/", "/devices/2/")

# The fetch_metric_series consumers that analyze every datapoint of one instance;
# correlate_metrics reads one datapoint per source and has its own tests.
INSTANCE_CONSUMERS = [
    pytest.param("analyze_metric", "analyze_metric", {}, id="analyze_metric"),
]


def _capped_pages():
    """MAX_SERIES_PAGES newest-first pages, the last still naming a next page."""
    from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES

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
    return pages


def _complete_page():
    """One final page: the read saw the whole window."""
    return httpx.Response(
        200,
        json=_data_page(
            [BASE_EPOCH + 600, BASE_EPOCH + 300, BASE_EPOCH],
            [[60.0, 80.0], [55.0, 75.0], [50.0, 70.0]],
        ),
    )


def _complete_page_before_base():
    """One final page over the capped read's newest three samples, so the two join."""
    return httpx.Response(
        200,
        json=_data_page(
            [BASE_EPOCH, BASE_EPOCH - 300, BASE_EPOCH - 600],
            [[60.0, 80.0], [55.0, 75.0], [50.0, 70.0]],
        ),
    )


class TestTruncatedSeriesWarnings:
    """R5 follow-up: every consumer reports a series the page cap cut short."""

    @respx.mock
    @pytest.mark.parametrize(("module", "tool", "extra"), INSTANCE_CONSUMERS)
    async def test_capped_series_warns_naming_datapoint_and_cap(self, client, module, tool, extra):
        from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES

        route = respx.get(SERIES_URL).mock(side_effect=_capped_pages())
        handler = getattr(importlib.import_module(f"lm_mcp.tools.{module}"), tool)

        result = await handler(client, **SERIES_ARGS, **extra)

        assert route.call_count == MAX_SERIES_PAGES
        data = json.loads(result[0].text)
        assert data["device_id"] == 1
        warnings = data["warnings"]
        assert len(warnings) == 2
        for datapoint, warning in zip(("cpu", "memory"), warnings, strict=True):
            assert warning.startswith(f"{datapoint}: ")
            assert f"{MAX_SERIES_PAGES}-page cap" in warning

    @respx.mock
    @pytest.mark.parametrize(("module", "tool", "extra"), INSTANCE_CONSUMERS)
    async def test_complete_series_carries_no_warnings(self, client, module, tool, extra):
        respx.get(SERIES_URL).mock(return_value=_complete_page())
        handler = getattr(importlib.import_module(f"lm_mcp.tools.{module}"), tool)

        result = await handler(client, **SERIES_ARGS, **extra)

        data = json.loads(result[0].text)
        assert data["device_id"] == 1
        assert "warnings" not in data

    @respx.mock
    @pytest.mark.parametrize(
        ("capped_device", "complete_url"),
        [(1, SECOND_SERIES_URL), (2, SERIES_URL)],
        ids=["first_source_capped", "second_source_capped"],
    )
    @pytest.mark.parametrize(
        "datapoint", [{"datapoint": "cpu"}, {}], ids=["named_datapoint", "first_available"]
    )
    async def test_correlate_metrics_warns_only_for_the_capped_source(
        self, client, capped_device, complete_url, datapoint
    ):
        from lm_mcp.tools.correlation import correlate_metrics
        from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES

        capped_url = SERIES_URL if capped_device == 1 else SECOND_SERIES_URL
        respx.get(capped_url).mock(side_effect=_capped_pages())
        respx.get(complete_url).mock(return_value=_complete_page_before_base())

        result = await correlate_metrics(
            client,
            sources=[{**SERIES_ARGS, **datapoint}, {**SECOND_SERIES_ARGS, **datapoint}],
        )

        data = json.loads(result[0].text)
        assert data["labels"] == ["d1:cpu", "d2:cpu"]
        warnings = data["warnings"]
        assert len(warnings) == 1
        assert warnings[0].startswith(f"d{capped_device}:cpu: ")
        assert f"{MAX_SERIES_PAGES}-page cap" in warnings[0]

    @respx.mock
    async def test_correlate_metrics_complete_sources_carry_no_warnings(self, client):
        from lm_mcp.tools.correlation import correlate_metrics

        respx.get(SERIES_URL).mock(return_value=_complete_page())
        respx.get(SECOND_SERIES_URL).mock(return_value=_complete_page())

        result = await correlate_metrics(
            client,
            sources=[
                {**SERIES_ARGS, "datapoint": "cpu"},
                {**SECOND_SERIES_ARGS, "datapoint": "cpu"},
            ],
        )

        data = json.loads(result[0].text)
        assert data["shared_samples"] == 3
        assert "warnings" not in data


# Identical at every shared time, so correctly paired series correlate at exactly 1.0.
SHARED_CPU = [10.0, 80.0, 20.0, 90.0, 30.0, 70.0, 15.0, 85.0]
SHARED_TIMES = [BASE_EPOCH + 300 * i for i in range(1, len(SHARED_CPU) + 1)]


def _cpu_page(times_sec, values):
    """One final page in the live shape, newest first, from oldest-first times and values."""
    pairs = list(zip(times_sec, values, strict=True))[::-1]
    return httpx.Response(
        200,
        json=_data_page([t for t, _ in pairs], [[v, 0.0] for _, v in pairs]),
    )


class TestCorrelateMetricsAlignment:
    """R2.3: series of different lengths join on the timestamp buckets both hold."""

    @staticmethod
    async def _correlate(client):
        from lm_mcp.tools.correlation import correlate_metrics

        result = await correlate_metrics(
            client,
            sources=[
                {**SERIES_ARGS, "datapoint": "cpu"},
                {**SECOND_SERIES_ARGS, "datapoint": "cpu"},
            ],
        )
        return json.loads(result[0].text)

    @respx.mock
    @pytest.mark.parametrize(
        ("longer_url", "shorter_url"),
        [(SERIES_URL, SECOND_SERIES_URL), (SECOND_SERIES_URL, SERIES_URL)],
        ids=["first_source_longer", "second_source_longer"],
    )
    async def test_extra_older_sample_does_not_shift_the_pairs(
        self, client, longer_url, shorter_url
    ):
        """One source with an older sample still pairs every shared time with itself."""
        respx.get(longer_url).mock(
            return_value=_cpu_page([BASE_EPOCH, *SHARED_TIMES], [55.0, *SHARED_CPU])
        )
        respx.get(shorter_url).mock(return_value=_cpu_page(SHARED_TIMES, SHARED_CPU))

        data = await self._correlate(client)

        assert data["correlation_matrix"][0][1] == 1.0
        assert data["shared_samples"] == len(SHARED_CPU)

    @respx.mock
    async def test_a_newer_sample_without_a_partner_is_left_out(self, client):
        """A sample in a bucket the other source lacks is left out; the shared times pair.

        Paired by position from the newest, the extra sample shifted every pair and r
        fell below 1.
        """
        newest = SHARED_TIMES[-1] + 300
        respx.get(SERIES_URL).mock(
            return_value=_cpu_page([*SHARED_TIMES, newest], [*SHARED_CPU, 40.0])
        )
        respx.get(SECOND_SERIES_URL).mock(return_value=_cpu_page(SHARED_TIMES, SHARED_CPU))

        data = await self._correlate(client)

        assert data["correlation_matrix"][0][1] == 1.0
        assert data["shared_samples"] == len(SHARED_CPU)
