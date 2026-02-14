# Description: Tests for shared statistical utility functions.
# Description: Validates linear_regression, pearson_correlation, autocorrelation, cusum, entropy.

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
        api_version=3,
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
        slope, intercept, r_sq = linear_regression(x, y)
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
        slope, intercept, r_sq = linear_regression(x, y)
        assert abs(slope) < 1e-10

    def test_noisy_data_r_squared_less_than_one(self):
        """Noisy data produces r_squared < 1."""
        from lm_mcp.tools.stats_helpers import linear_regression

        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.1, 3.9, 6.2, 7.8, 10.1]
        slope, intercept, r_sq = linear_regression(x, y)
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


class TestCusum:
    """Tests for CUSUM change point detection."""

    def test_upward_shift(self):
        """Detects upward shift in mean."""
        from lm_mcp.tools.stats_helpers import cusum

        # Stable at 10, then shifts to 20
        values = [10.0] * 20 + [20.0] * 20
        points = cusum(values, target=10.0)
        assert len(points) > 0
        assert any(p["direction"] == "increase" for p in points)

    def test_downward_shift(self):
        """Detects downward shift in mean."""
        from lm_mcp.tools.stats_helpers import cusum

        values = [20.0] * 20 + [10.0] * 20
        points = cusum(values, target=20.0)
        assert len(points) > 0
        assert any(p["direction"] == "decrease" for p in points)

    def test_stable_data_no_change_points(self):
        """Stable data produces no change points."""
        from lm_mcp.tools.stats_helpers import cusum

        values = [10.0 + (i % 3) * 0.1 for i in range(40)]
        points = cusum(values)
        # Stable data should produce few or no change points
        assert len(points) <= 1

    def test_constant_data_no_change_points(self):
        """Constant data (stddev=0) produces no change points."""
        from lm_mcp.tools.stats_helpers import cusum

        values = [5.0] * 20
        points = cusum(values)
        assert len(points) == 0

    def test_short_series_returns_empty(self):
        """Fewer than 4 values returns empty list."""
        from lm_mcp.tools.stats_helpers import cusum

        assert cusum([1.0, 2.0, 3.0]) == []
        assert cusum([]) == []

    def test_sensitivity_high_fewer_detections(self):
        """Higher sensitivity threshold detects fewer change points."""
        from lm_mcp.tools.stats_helpers import cusum

        values = [10.0] * 15 + [15.0] * 15
        low_sens = cusum(values, sensitivity=0.5)
        high_sens = cusum(values, sensitivity=3.0)
        assert len(low_sens) >= len(high_sens)

    def test_change_point_has_required_fields(self):
        """Change point dicts have index, direction, magnitude."""
        from lm_mcp.tools.stats_helpers import cusum

        values = [10.0] * 20 + [30.0] * 20
        points = cusum(values, target=10.0)
        assert len(points) > 0
        for p in points:
            assert "index" in p
            assert "direction" in p
            assert "magnitude" in p
            assert p["direction"] in ("increase", "decrease")


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
