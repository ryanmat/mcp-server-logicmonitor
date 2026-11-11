# Description: Tests for analyze_metric, the one-fetch analysis of a device instance's series.
# Description: Covers the paged read, each section, section selection and warnings.

import json
import math
import random
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


def _paged(points, page_size=500):
    """(epoch, cpu) pairs as newest-first pages of 500 rows linked by nextPageParams."""
    newest_first = sorted(points, key=lambda p: p[0], reverse=True)
    chunks = [newest_first[i : i + page_size] for i in range(0, len(newest_first), page_size)]
    pages = []
    for n, chunk in enumerate(chunks):
        oldest = chunk[-1][0]
        marker = "" if n == len(chunks) - 1 else f"start={BASE_EPOCH - 86400}&end={oldest - 1}"
        pages.append(httpx.Response(200, json=_series_page(chunk, next_page=marker)))
    return pages


def _every(seconds, values):
    """Values at a fixed interval from BASE_EPOCH, as (epoch, value) pairs."""
    return [(BASE_EPOCH + i * seconds, v) for i, v in enumerate(values)]


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
        """With analyses omitted the response carries every section that needs no argument.

        The baseline needs baseline_hours_ago; the rest run on the window alone.
        """
        from lm_mcp.tools.analyze_metric import SECTIONS

        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours([(0, 1.0), (1, 2.0)])))
        )

        body = _body(await _analyze(client))

        unprompted = [s for s in SECTIONS if s != "baseline"]
        assert body["analyses"] == unprompted
        assert set(unprompted) <= set(body["datapoints"]["cpu"])

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


class TestSeasonality:
    """R2.1 seasonality: detrended autocorrelation table, dominant period, peak hours in UTC."""

    @respx.mock
    async def test_daily_cycle_found_on_the_default_window(self, client):
        """A week of five-minute samples, read whole by default, shows its 24-hour period.

        The default window is 168 hours, so the 24-hour lag fits inside half the series
        (a 24-hour window could not hold it). Every section comes from
        the same five pages.
        """
        week = [50.0 + 20.0 * math.cos(2 * math.pi * i / 288) + 0.01 * i for i in range(2016)]
        route = respx.get(SERIES_URL).mock(side_effect=_paged(_every(300, week)))

        body = _body(await _analyze(client))

        assert route.call_count == 5
        start = int(route.calls[0].request.url.params["start"])
        assert abs(start + 168 * 3600 - int(time.time())) < 60
        seasonality = body["datapoints"]["cpu"]["seasonality"]
        assert set(seasonality["autocorrelation"]) == {"1h", "4h", "12h", "24h"}
        assert seasonality["dominant_period"] == "24h"
        assert seasonality["is_seasonal"] is True

    @respx.mock
    async def test_a_small_cycle_on_a_steep_ramp_is_found(self, client):
        """A daily cycle holding a thousandth of the variance under a steep ramp is still found.

        Detrending removes the ramp and keeps the cycle; only rounding residue is zeroed.
        """
        values = [20.0 * math.cos(2 * math.pi * i / 288) + 1.0 * i for i in range(2016)]
        respx.get(SERIES_URL).mock(side_effect=_paged(_every(300, values)))

        seasonality = _body(await _analyze(client, analyses=["seasonality"]))["datapoints"]["cpu"][
            "seasonality"
        ]

        assert seasonality["dominant_period"] == "24h"
        assert seasonality["is_seasonal"] is True

    @respx.mock
    async def test_detrending_reads_the_hours_between_samples(self, client):
        """An unevenly sampled climb is a straight line in hours: no cycle, no 24-hour echo.

        Samples alternate one and nine minutes apart; a line fitted against the sample
        index instead of the time leaves a zigzag that reads as structure.
        """
        times = []
        t = BASE_EPOCH
        for i in range(2000):
            times.append(t)
            t += 60 if i % 2 == 0 else 540
        values = [100.0 + 0.5 * (ts - BASE_EPOCH) / 3600 for ts in times]
        respx.get(SERIES_URL).mock(side_effect=_paged(list(zip(times, values, strict=True))))

        cpu = _body(await _analyze(client, analyses=["seasonality", "trend"]))["datapoints"]["cpu"]

        assert set(cpu["seasonality"]["autocorrelation"].values()) == {0.0}
        assert cpu["trend"]["autocorrelation_24h"] == 0.0

    @respx.mock
    async def test_a_ramp_is_not_seasonal_once_detrended(self, client):
        """A straight ramp has no cycle: every detrended autocorrelation is 0."""
        ramp = [100.0 + 0.5 * i for i in range(600)]
        respx.get(SERIES_URL).mock(side_effect=_paged(_every(300, ramp)))

        seasonality = _body(await _analyze(client, analyses=["seasonality"]))["datapoints"]["cpu"][
            "seasonality"
        ]

        assert set(seasonality["autocorrelation"].values()) == {0.0}
        assert seasonality["max_autocorrelation"] == 0.0
        assert seasonality["is_seasonal"] is False

    @respx.mock
    async def test_peak_hours_are_utc_hours_above_the_mean(self, client):
        """Two days of hourly samples high from 09:00 to 17:00 UTC peak in exactly those hours."""
        values = [100.0 if 9 <= h % 24 <= 17 else 10.0 for h in range(48)]
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_every(3600, values)))
        )

        seasonality = _body(await _analyze(client, analyses=["seasonality"]))["datapoints"]["cpu"][
            "seasonality"
        ]

        assert seasonality["peak_hours_utc"] == list(range(9, 18))

    @respx.mock
    async def test_trend_label_reads_the_detrended_autocorrelation(self, client):
        """A long ramp is decreasing, not cyclic: its 24-hour autocorrelation is detrended."""
        ramp = [500.0 - 3.0 * k / 60.0 for k in range(2000)]
        respx.get(SERIES_URL).mock(side_effect=_paged(_every(60, ramp)))

        trend = _body(await _analyze(client, analyses=["trend"]))["datapoints"]["cpu"]["trend"]

        assert trend["autocorrelation_24h"] == 0.0
        assert trend["label"] == "decreasing"


def _step(before, after, level_before=100.0, level_after=130.0):
    """A level shift at five-minute samples: `before` samples, then `after` at the new level."""
    return _every(300, [level_before] * before + [level_after] * after)


class TestChangePoints:
    """R2.1 change_points: the windows before and after each sample compared, each shift dated."""

    @respx.mock
    async def test_a_level_shift_is_one_point_at_its_timestamp(self, client):
        """A shift from 100 to 130 is one increase at the first sample of the new level.

        The comparison of the 30 samples after with the 30 before peaks at that sample.
        """
        points = _step(60, 60)
        respx.get(SERIES_URL).mock(return_value=httpx.Response(200, json=_series_page(points)))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert section["window"] == 30
        assert section["points"] == [
            {"timestamp": points[60][0], "direction": "increase", "before": 100.0, "after": 130.0}
        ]

    @respx.mock
    async def test_a_drop_is_a_decrease(self, client):
        """A shift down is reported as a decrease with both levels."""
        points = _step(50, 50, level_after=70.0)
        respx.get(SERIES_URL).mock(return_value=httpx.Response(200, json=_series_page(points)))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert section["points"] == [
            {"timestamp": points[50][0], "direction": "decrease", "before": 100.0, "after": 70.0}
        ]

    @respx.mock
    async def test_noise_around_a_steady_level_has_no_points(self, client):
        """Noise in runs of four around a steady level is no shift."""
        noise = [100.0 + (1.0 if (i // 4) % 2 else -1.0) for i in range(160)]
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_every(300, noise)))
        )

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert section["points"] == []

    @respx.mock
    async def test_a_small_shift_is_dated_to_its_first_sample(self, client):
        """A shift of four in alternating noise of one is dated to its first sample."""
        values = [100.0 + (1.0 if i % 2 else -1.0) + (4.0 if i >= 61 else 0.0) for i in range(130)]
        points = _every(300, values)
        respx.get(SERIES_URL).mock(return_value=httpx.Response(200, json=_series_page(points)))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert [(p["timestamp"], p["direction"]) for p in section["points"]] == [
            (points[61][0], "increase")
        ]
        assert section["points"][0]["before"] == 100.0
        assert section["points"][0]["after"] == 104.0

    @respx.mock
    async def test_a_daily_cycle_on_a_ramp_has_no_points(self, client):
        """A clean daily cycle over a week is a cycle, not a run of level shifts.

        With three days or more the cycle comes out before the windows are compared; left
        in, each half of the cycle reads as a level change against the window before it.
        """
        week = [50.0 + 20.0 * math.cos(2 * math.pi * i / 288) + 0.01 * i for i in range(2016)]
        respx.get(SERIES_URL).mock(side_effect=_paged(_every(300, week)))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert section["deseasonalized"] is True
        assert section["points"] == []

    @respx.mock
    async def test_a_step_inside_a_noisy_daily_cycle_is_one_point(self, client):
        """A step of 8 under a daily cycle of 20 and noise of 3 is one increase where it starts."""
        points = _noisy_week(seed=11, step_at=1000, step=8.0)
        respx.get(SERIES_URL).mock(side_effect=_paged(points))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert len(section["points"]) == 1
        found = section["points"][0]
        assert found["direction"] == "increase"
        assert abs(found["timestamp"] - points[1000][0]) <= 3 * 300
        assert 6.0 < found["after"] - found["before"] < 10.0

    @respx.mock
    async def test_a_noisy_ramp_is_not_a_shift(self, client):
        """A climb of 58 a day under a daily cycle and noise reports no level shift.

        A steady climb moves every window difference by the same amount, the center.
        """
        respx.get(SERIES_URL).mock(side_effect=_paged(_noisy_week(seed=23, slope=0.2)))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert section["points"] == []

    @respx.mock
    async def test_a_steep_short_climb_is_not_a_shift(self, client):
        """A climb of 0.5 a sample in noise of 1 over a day is no shift."""
        rng = random.Random(13)
        values = [100.0 + 0.5 * i + rng.gauss(0, 1.0) for i in range(300)]
        respx.get(SERIES_URL).mock(side_effect=_paged(_every(300, values)))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert section["points"] == []

    @pytest.mark.parametrize(("seed", "at"), [(2047, 1001)])
    def test_the_profile_is_a_median_across_days(self, seed, at):
        """The day a step crosses does not shape the daily profile, so the step stands alone.

        With a mean across days this week gains a decrease 883 samples after the step.
        """
        from lm_mcp.tools.analyze_metric import change_point_stats

        stepped = _noisy_week(seed=seed, step_at=1000, step=8.0)
        points = change_point_stats([v for _, v in stepped], [t for t, _ in stepped])["points"]

        assert [(p["timestamp"], p["direction"]) for p in points] == [(stepped[at][0], "increase")]

    @respx.mock
    async def test_under_three_days_the_cycle_stays_in(self, client):
        """Two and a half days of a noisy cycle are too few to estimate it; it stays in.

        From two days every time of day has a sample to read, but a profile of one or
        two days takes in any step those days hold, so the cut is at three.
        """
        rng = random.Random(3)
        days = [
            50.0 + 20.0 * math.cos(2 * math.pi * i / 288) + rng.gauss(0, 3.0) for i in range(720)
        ]
        respx.get(SERIES_URL).mock(side_effect=_paged(_every(300, days)))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert section["deseasonalized"] is False

    @respx.mock
    async def test_changes_every_ten_hours_leave_no_profile_to_rebuild(self, client):
        """Level changes every 10 hours leave no day to read the cycle from; each is a point.

        The daily profile rebuilt without the day around each change has nothing left to
        read, so the series is analyzed as it is and the section says the cycle stayed in.
        """
        rng = random.Random(5)
        values = [(80.0 if (i // 120) % 2 else 50.0) + rng.gauss(0, 1.0) for i in range(1008)]
        points = _every(300, values)
        respx.get(SERIES_URL).mock(side_effect=_paged(points))

        section = _body(await _analyze(client, analyses=["change_points"]))["datapoints"]["cpu"][
            "change_points"
        ]

        assert section["deseasonalized"] is False
        found = [
            ((p["timestamp"] - points[0][0]) // 300, p["direction"]) for p in section["points"]
        ]
        assert [index for index, _ in found] == [120 * k for k in range(1, 9)]
        assert [direction for _, direction in found] == ["increase", "decrease"] * 4

    @pytest.mark.parametrize("phi", [0.5, 0.8])
    def test_autocorrelated_noise_is_no_shift_and_a_step_is_one(self, phi):
        """Smooth noise wanders without reading as shifts; a step of 15 is one point.

        Eight seeded weeks of a daily cycle and AR(1) noise of sd 3: no point without a
        step, and the step found within one sample. First differences see only the fast
        part of such noise; the spread of the block differences carries the slow part.
        """
        from lm_mcp.tools.analyze_metric import change_point_stats

        for seed in range(6000, 6008):
            quiet = _smooth_week(seed, phi)
            assert change_point_stats([v for _, v in quiet], [t for t, _ in quiet])["points"] == []
            stepped = _smooth_week(seed, phi, step_at=1000, step=15.0)
            points = change_point_stats([v for _, v in stepped], [t for t, _ in stepped])["points"]
            assert len(points) == 1
            assert abs(points[0]["timestamp"] - stepped[1000][0]) <= 300

    @pytest.mark.parametrize("phi", [0.5, 0.8])
    def test_a_day_of_autocorrelated_noise_is_no_shift(self, phi):
        """Forty seeded 24-hour windows of AR(1) noise of sd 3 report no point.

        A day holds nine 30-sample blocks; the spread of their differences, taken every
        six samples, is steady enough to scale by where nine alone are not.
        """
        from lm_mcp.tools.analyze_metric import change_point_stats

        false_points = 0
        for seed in range(7000, 7040):
            rng = random.Random(seed)
            noise = 0.0
            values = []
            for _ in range(288):
                noise = phi * noise + rng.gauss(0, 3.0 * math.sqrt(1 - phi * phi))
                values.append(50.0 + noise)
            timestamps = [BASE_EPOCH + i * 300 for i in range(288)]
            false_points += len(change_point_stats(values, timestamps)["points"])

        assert false_points == 0

    def test_changes_a_day_apart_leave_the_cycle_in(self):
        """Three changes a day apart in four days leave no day to read the cycle from.

        The profile rebuilt without each change's day reaches too few times of day, so
        the series is analyzed as it is, and any point found is one of the changes.
        """
        from lm_mcp.tools.analyze_metric import change_point_stats

        rng = random.Random(1)
        values = [
            50.0
            + 20.0 * math.cos(2 * math.pi * i / 288)
            + (15.0 if i >= 288 else 0.0)
            - (15.0 if i >= 605 else 0.0)
            + (15.0 if i >= 922 else 0.0)
            + rng.gauss(0, 2.0)
            for i in range(1152)
        ]
        timestamps = [BASE_EPOCH + i * 300 for i in range(1152)]

        section = change_point_stats(values, timestamps)

        assert section["deseasonalized"] is False
        changes = [timestamps[i] for i in (288, 605, 922)]
        assert all(min(abs(p["timestamp"] - c) for c in changes) <= 900 for p in section["points"])

    def test_a_profile_reaching_part_of_the_day_is_not_applied(self):
        """Exclusions that leave a fifth of the times of day give no profile to subtract."""
        from lm_mcp.tools.stats_helpers import remove_daily_cycle

        values = [50.0 + 20.0 * math.cos(2 * math.pi * i / 288) for i in range(1152)]
        timestamps = [BASE_EPOCH + i * 300 for i in range(1152)]
        near = [timestamps[i] for i in (288, 605, 922)]

        series, applied = remove_daily_cycle(values, timestamps, exclude_near=near)

        assert applied is False
        assert series == values

    def test_the_profile_is_rebuilt_without_the_day_of_a_step(self):
        """A step of 20 is one point once the profile is rebuilt without the day around it.

        The first profile takes in that day, and read against it this week shows a
        decrease at sample 714 that is not there.
        """
        from lm_mcp.tools.analyze_metric import change_point_stats

        stepped = _noisy_week(seed=2022, step_at=1000, step=20.0)
        points = change_point_stats([v for _, v in stepped], [t for t, _ in stepped])["points"]

        assert [(p["timestamp"], p["direction"]) for p in points] == [
            (stepped[1000][0], "increase")
        ]

    def test_seeded_weeks_have_no_false_points_and_find_every_step(self):
        """Over 20 seeded weeks of cycle and noise: no point without a step, the step with one.

        The step is 8, under three noise units; each found point lies within three
        samples (15 minutes) of where the step starts.
        """
        from lm_mcp.tools.analyze_metric import change_point_stats

        false_points = 0
        found = 0
        for seed in range(2000, 2020):
            quiet = _noisy_week(seed=seed)
            false_points += len(
                change_point_stats([v for _, v in quiet], [t for t, _ in quiet])["points"]
            )
            stepped = _noisy_week(seed=seed, step_at=1000, step=8.0)
            points = change_point_stats([v for _, v in stepped], [t for t, _ in stepped])["points"]
            found += len(points) == 1 and abs(points[0]["timestamp"] - stepped[1000][0]) <= 900

        assert false_points == 0
        assert found == 20


def _noisy_week(seed, step_at=None, step=0.0, slope=0.0):
    """A week of five-minute samples: daily cycle of 20, seeded noise of 3, a step and a slope."""
    rng = random.Random(seed)
    return _every(
        300,
        [
            50.0
            + 20.0 * math.cos(2 * math.pi * i / 288)
            + slope * i
            + rng.gauss(0, 3.0)
            + (step if step_at is not None and i >= step_at else 0.0)
            for i in range(2016)
        ],
    )


def _smooth_week(seed, phi, step_at=None, step=0.0):
    """A week of five-minute samples: a daily cycle of 20 and seeded AR(1) noise of sd 3."""
    rng = random.Random(seed)
    noise = 0.0
    values = []
    for i in range(2016):
        noise = phi * noise + rng.gauss(0, 3.0 * math.sqrt(1 - phi * phi))
        level = step if step_at is not None and i >= step_at else 0.0
        values.append(50.0 + 20.0 * math.cos(2 * math.pi * i / 288) + noise + level)
    return _every(300, values)


def _with_spikes(base_count, spikes):
    """A five-minute series cycling 50 to 54, with {index: value} spikes laid over it."""
    values = [50.0 + (i % 5) for i in range(base_count)]
    for index, value in spikes.items():
        values[index] = value
    return _every(300, values)


class TestAnomalies:
    """R2.1 anomalies: z-score, IQR and MAD hits, each under its method's name."""

    @respx.mock
    async def test_each_method_reports_the_spike(self, client):
        """One spike in a steady cycle is a hit for all three methods, at its timestamp."""
        points = _with_spikes(40, {30: 200.0})
        respx.get(SERIES_URL).mock(return_value=httpx.Response(200, json=_series_page(points)))

        anomalies = _body(await _analyze(client, analyses=["anomalies"]))["datapoints"]["cpu"][
            "anomalies"
        ]

        assert set(anomalies) == {"zscore", "iqr", "mad"}
        assert anomalies["zscore"]["threshold"] == 3.0
        assert anomalies["iqr"]["multiplier"] == 1.5
        assert anomalies["mad"]["threshold"] == 3.5
        for method in ("zscore", "iqr", "mad"):
            assert anomalies[method]["count"] == 1, method
            assert [h["timestamp"] for h in anomalies[method]["hits"]] == [points[30][0]], method
            assert anomalies[method]["hits"][0]["value"] == 200.0, method

    @respx.mock
    async def test_hits_keep_the_most_extreme_in_time_order(self, client):
        """Past the cap the most extreme hits are kept, listed oldest first; count is the total."""
        from lm_mcp.tools.analyze_metric import MAX_ANOMALY_HITS

        spikes = {10 + 5 * k: 100.0 + k for k in range(30)}
        points = _with_spikes(200, spikes)
        respx.get(SERIES_URL).mock(return_value=httpx.Response(200, json=_series_page(points)))

        mad = _body(await _analyze(client, analyses=["anomalies"]))["datapoints"]["cpu"][
            "anomalies"
        ]["mad"]

        assert MAX_ANOMALY_HITS == 20
        assert mad["count"] == 30
        kept = [h["value"] for h in mad["hits"]]
        assert kept == [100.0 + k for k in range(10, 30)]

    @respx.mock
    async def test_the_z_score_fence_is_three(self, client):
        """A sample at |z| between 2 and 3 is not a z-score hit; one between 3 and 4 is."""
        values = [50.0 + (i % 5) for i in range(200)]
        values[50] = 55.5
        values[150] = 57.5
        mean = sum(values) / len(values)
        sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
        assert 2.0 < (values[50] - mean) / sd < 3.0
        assert 3.0 < (values[150] - mean) / sd < 4.0
        points = _every(300, values)
        respx.get(SERIES_URL).mock(return_value=httpx.Response(200, json=_series_page(points)))

        zscore = _body(await _analyze(client, analyses=["anomalies"]))["datapoints"]["cpu"][
            "anomalies"
        ]["zscore"]

        assert [h["timestamp"] for h in zscore["hits"]] == [points[150][0]]

    @respx.mock
    async def test_a_flat_series_has_no_hits(self, client):
        """A constant series has no hits under any method."""
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_every(300, [5.0] * 20)))
        )

        anomalies = _body(await _analyze(client, analyses=["anomalies"]))["datapoints"]["cpu"][
            "anomalies"
        ]

        assert [anomalies[m]["count"] for m in ("zscore", "iqr", "mad")] == [0, 0, 0]


class TestForecast:
    """R2.1 forecast: linear and Holt-Winters to the crossing or a 30-day cap, per hour."""

    @respx.mock
    async def test_linear_crossing_time_and_slope_per_hour(self, client):
        """A climb of 2 an hour from 50 crosses 100 two hours after the latest sample at 96."""
        rows = [(h, 50.0 + 2.0 * h) for h in range(24)]
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours(rows)))
        )

        forecast = _body(await _analyze(client, analyses=["forecast"], threshold=100.0))[
            "datapoints"
        ]["cpu"]["forecast"]

        assert forecast["threshold"] == 100.0
        assert forecast["horizon_days"] == 30
        linear = forecast["linear"]
        assert linear["slope_per_hour"] == 2.0
        assert linear["breach_eta"] == BASE_EPOCH + 25 * 3600
        assert linear["hours_until_breach"] == 2.0
        assert linear["direction"] == "rising"

    @respx.mock
    async def test_linear_crossing_a_lower_threshold_is_falling(self, client):
        """A fall of 2 an hour from 100 reaches 40 seven hours after the latest sample at 54."""
        rows = [(h, 100.0 - 2.0 * h) for h in range(24)]
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours(rows)))
        )

        linear = _body(await _analyze(client, analyses=["forecast"], threshold=40.0))["datapoints"][
            "cpu"
        ]["forecast"]["linear"]

        assert linear["breach_eta"] == BASE_EPOCH + 30 * 3600
        assert linear["hours_until_breach"] == 7.0
        assert linear["direction"] == "falling"

    @respx.mock
    async def test_holt_winters_scans_past_the_old_limits_and_slopes_per_hour(self, client):
        """A daily cycle on a climb of 0.01 a sample crosses 77 some 250 samples ahead.

        The scan reaches it where a 24- or 96-step scan stopped short, and the slope
        is 0.12 an hour (twelve five-minute samples), not 0.01 a sample.
        """
        week = [50.0 + 5.0 * math.cos(2 * math.pi * i / 288) + 0.01 * i for i in range(2016)]
        points = _every(300, week)
        respx.get(SERIES_URL).mock(side_effect=_paged(points))

        forecast = _body(await _analyze(client, analyses=["forecast"], threshold=77.0))[
            "datapoints"
        ]["cpu"]["forecast"]
        hw = forecast["holt_winters"]

        assert forecast["linear"]["hours_until_breach"] == 57.1875
        steps_ahead = (hw["breach_eta"] - points[-1][0]) // 300
        assert 200 < steps_ahead < 320
        assert hw["season_length"] == 288
        assert abs(hw["slope_per_hour"] - 0.12) < 0.03
        assert hw["direction"] == "rising"

    @respx.mock
    async def test_holt_winters_slope_ignores_where_the_window_cuts_the_cycle(self, client):
        """A flat daily cycle over 60 hours has a Holt-Winters slope of about 0 per hour.

        Sixty hours start near a peak and end near a trough; the slope is the fit's own
        trend, not the difference between its first and last values.
        """
        flat = [50.0 + 5.0 * math.cos(2 * math.pi * i / 288) for i in range(720)]
        respx.get(SERIES_URL).mock(side_effect=_paged(_every(300, flat)))

        hw = _body(await _analyze(client, analyses=["forecast"], hours=60))["datapoints"]["cpu"][
            "forecast"
        ]["holt_winters"]

        assert abs(hw["slope_per_hour"]) < 0.01

    @respx.mock
    async def test_holt_winters_crosses_a_lower_threshold_falling(self, client):
        """A daily cycle on a fall of 0.01 a sample reaches 73 some 390 samples ahead."""
        week = [100.0 + 5.0 * math.cos(2 * math.pi * i / 288) - 0.01 * i for i in range(2016)]
        points = _every(300, week)
        respx.get(SERIES_URL).mock(side_effect=_paged(points))

        hw = _body(await _analyze(client, analyses=["forecast"], threshold=73.0))["datapoints"][
            "cpu"
        ]["forecast"]["holt_winters"]

        assert (hw["breach_eta"] - points[-1][0]) // 300 == 390
        assert hw["direction"] == "falling"

    @respx.mock
    async def test_a_flat_series_crosses_nothing_and_says_why(self, client):
        """A constant series reports no crossing from either method, each with its reason."""
        respx.get(SERIES_URL).mock(side_effect=_paged(_every(300, [50.0] * 600)))

        forecast = _body(await _analyze(client, analyses=["forecast"], threshold=80.0))[
            "datapoints"
        ]["cpu"]["forecast"]

        for method in ("linear", "holt_winters"):
            assert forecast[method]["breach_eta"] is None, method
            assert forecast[method]["hours_until_breach"] is None, method
        assert "flat" in forecast["linear"]["reason"]
        assert "30 days" in forecast["holt_winters"]["reason"]

    @respx.mock
    async def test_without_a_threshold_the_forecast_has_slopes_and_no_crossing(self, client):
        """With no threshold named the slopes are reported and the crossing says why not."""
        rows = [(h, 50.0 + 2.0 * h) for h in range(24)]
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours(rows)))
        )

        forecast = _body(await _analyze(client, analyses=["forecast"]))["datapoints"]["cpu"][
            "forecast"
        ]

        assert forecast["threshold"] is None
        assert forecast["linear"]["slope_per_hour"] == 2.0
        assert forecast["linear"]["breach_eta"] is None
        assert "threshold" in forecast["linear"]["reason"]

    @respx.mock
    async def test_holt_winters_needs_two_days(self, client):
        """A day of samples is too short for a daily season; the reason says so."""
        rows = [(h, 50.0 + 2.0 * h) for h in range(24)]
        respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_series_page(_hours(rows)))
        )

        hw = _body(await _analyze(client, analyses=["forecast"], threshold=100.0))["datapoints"][
            "cpu"
        ]["forecast"]["holt_winters"]

        assert hw["breach_eta"] is None
        assert "two days" in hw["reason"]


def _window_page(values, start_epoch):
    """One page of hourly samples from start_epoch, newest first."""
    return _series_page([(start_epoch + h * 3600, v) for h, v in enumerate(values)])


class TestBaseline:
    """R2.1 baseline: the window against a caller-named earlier window, one more read."""

    @respx.mock
    async def test_baseline_reads_the_earlier_window_once_and_compares(self, client):
        """The current window comes from the main read; the earlier one from one more read."""
        route = respx.get(SERIES_URL).mock(
            side_effect=[
                httpx.Response(200, json=_window_page([70.0] * 24, BASE_EPOCH)),
                httpx.Response(200, json=_window_page([50.0] * 24, BASE_EPOCH - 168 * 3600)),
            ]
        )

        body = _body(
            await _analyze(client, analyses=["baseline"], hours=24, baseline_hours_ago=168)
        )

        assert route.call_count == 2
        params = route.calls[1].request.url.params
        now = int(time.time())
        assert abs(int(params["start"]) - (now - (168 + 24) * 3600)) < 60
        assert abs(int(params["end"]) - (now - 168 * 3600)) < 60
        baseline = body["datapoints"]["cpu"]["baseline"]
        assert baseline["baseline"]["mean"] == 50.0
        assert baseline["current"]["mean"] == 70.0
        assert baseline["deviation_percent"] == 40.0
        assert baseline["status"] == "elevated"

    @pytest.mark.parametrize(
        ("current", "status"),
        [(55.0, "normal"), (35.0, "reduced"), (80.0, "anomalous")],
    )
    @respx.mock
    async def test_baseline_status_bands(self, client, current, status):
        """Within 20 percent is normal, within 50 elevated or reduced, past 50 anomalous."""
        respx.get(SERIES_URL).mock(
            side_effect=[
                httpx.Response(200, json=_window_page([current] * 24, BASE_EPOCH)),
                httpx.Response(200, json=_window_page([50.0] * 24, BASE_EPOCH - 24 * 3600)),
            ]
        )

        baseline = _body(
            await _analyze(client, analyses=["baseline"], hours=24, baseline_hours_ago=24)
        )["datapoints"]["cpu"]["baseline"]

        assert baseline["status"] == status

    @respx.mock
    async def test_a_zero_baseline_mean_has_no_percent(self, client):
        """Against a baseline mean of 0 a nonzero window has no percentage and is anomalous."""
        respx.get(SERIES_URL).mock(
            side_effect=[
                httpx.Response(200, json=_window_page([5.0] * 24, BASE_EPOCH)),
                httpx.Response(200, json=_window_page([0.0] * 24, BASE_EPOCH - 24 * 3600)),
            ]
        )

        baseline = _body(
            await _analyze(client, analyses=["baseline"], hours=24, baseline_hours_ago=24)
        )["datapoints"]["cpu"]["baseline"]

        assert baseline["deviation_percent"] is None
        assert baseline["status"] == "anomalous"

    @respx.mock
    async def test_baseline_named_without_a_window_is_refused_before_any_read(self, client):
        """Naming the baseline section without baseline_hours_ago is INVALID_REQUEST."""
        route = respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_window_page([1.0, 2.0], BASE_EPOCH))
        )

        error = envelope(await _analyze(client, analyses=["baseline"]))

        assert error["code"] == "INVALID_REQUEST"
        assert "baseline_hours_ago" in error["message"]
        assert route.call_count == 0

    @respx.mock
    async def test_a_window_named_without_the_section_reads_once(self, client):
        """baseline_hours_ago with the baseline left out of analyses makes no second read."""
        route = respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_window_page([1.0, 2.0, 3.0], BASE_EPOCH))
        )

        body = _body(await _analyze(client, analyses=["summary"], baseline_hours_ago=24))

        assert route.call_count == 1
        assert "baseline" not in body["datapoints"]["cpu"]

    @pytest.mark.parametrize(("ago", "calls"), [(None, 1), (48, 2)])
    @respx.mock
    async def test_the_default_runs_the_baseline_only_with_a_window(self, client, ago, calls):
        """With analyses omitted the baseline runs, and reads, only when a window is named."""
        route = respx.get(SERIES_URL).mock(
            return_value=httpx.Response(200, json=_window_page([1.0, 2.0, 3.0], BASE_EPOCH))
        )
        extra = {} if ago is None else {"baseline_hours_ago": ago}

        body = _body(await _analyze(client, **extra))

        assert route.call_count == calls
        assert ("baseline" in body["analyses"]) is (ago is not None)
        assert ("baseline" in body["datapoints"]["cpu"]) is (ago is not None)


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
        assert tool.inputSchema["properties"]["source"]["enum"] == ["device", "otlp"]
        assert "required" not in tool.inputSchema
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


OTLP_URL = "https://test.logicmonitor.com/santaba/rest/metrics/query-range"
OTLP_QUERY = 'sum by (code) (rate(apiserver_request_total{cluster_name="rm-aro-cluster"}[5m]))'


def _otlp_body(*series):
    """A query-range body in the live shape: each series (labels or None, [(epoch, text)]).

    An aggregate with no grouping carries no metric key at all, as
    sum(rate(apiserver_request_total[5m])) answered on 2026-11-11.
    """
    data = []
    for labels, points in series:
        entry = {"values": [{"value": v, "timestamp": t} for t, v in points]}
        if labels is not None:
            entry["metric"] = labels
        data.append(entry)
    return {"data": data, "meta": {"accessible": True, "queryTimeMs": 236, "resultType": "matrix"}}


def _texts(points):
    return [(t, repr(v)) for t, v in points]


class TestOtlpSource:
    """R3.2: analyze_metric(source="otlp") reads one PromQL range query and runs every section."""

    @respx.mock
    async def test_one_range_read_feeds_every_section_per_series(self, client):
        from lm_mcp.tools.analyze_metric import SECTIONS, analyze_metric

        rising = _texts(_every(300, [100.0 + i for i in range(60)]))
        flat = _texts(_every(300, [5.0] * 60))
        route = respx.post(OTLP_URL).mock(
            return_value=httpx.Response(
                200, json=_otlp_body(({"code": "200"}, rising), ({"code": "0"}, flat))
            )
        )

        before = int(time.time())
        result = await analyze_metric(client, source="otlp", query=OTLP_QUERY, hours=6, step="5m")
        after = int(time.time())

        assert route.call_count == 1
        sent = json.loads(route.calls[0].request.content)
        assert sent["query"] == OTLP_QUERY and sent["step"] == "5m"
        assert before <= sent["end"] <= after
        assert sent["end"] - sent["start"] == 6 * 3600
        body = _body(result)
        assert body["source"] == "otlp"
        assert list(body["series"]) == ['{code="200"}', '{code="0"}']
        entry = body["series"]['{code="200"}']
        assert entry["sample_count"] == 60
        assert set(entry) >= {s for s in SECTIONS if s != "baseline"}
        assert entry["summary"]["latest"] == 159.0
        assert entry["trend"]["label"] == "increasing"
        assert body["series"]['{code="0"}']["summary"]["stddev"] == 0.0

    @respx.mock
    async def test_series_keys_name_labels_and_an_unlabeled_aggregate(self, client):
        from lm_mcp.tools.analyze_metric import analyze_metric

        points = _texts(_every(300, [1.0, 2.0, 3.0]))
        respx.post(OTLP_URL).mock(
            return_value=httpx.Response(
                200,
                json=_otlp_body(
                    ({"__name__": "up", "job": "kubelet", "cluster_name": "rm-aks"}, points),
                    (None, points),
                ),
            )
        )

        body = _body(await analyze_metric(client, source="otlp", query="up", analyses=["summary"]))

        assert list(body["series"]) == ['up{cluster_name="rm-aks",job="kubelet"}', "up"]

    @respx.mock
    async def test_nan_and_infinite_samples_are_left_out(self, client):
        from lm_mcp.tools.analyze_metric import analyze_metric

        points = [
            (BASE_EPOCH, "NaN"),
            (BASE_EPOCH + 300, "4"),
            (BASE_EPOCH + 600, "+Inf"),
            (BASE_EPOCH + 900, "6"),
        ]
        respx.post(OTLP_URL).mock(
            return_value=httpx.Response(200, json=_otlp_body(({"code": "500"}, points)))
        )

        body = _body(await analyze_metric(client, source="otlp", query="q", analyses=["summary"]))

        entry = body["series"]['{code="500"}']
        assert entry["sample_count"] == 2
        assert entry["summary"]["mean"] == 5.0

    @respx.mock
    async def test_more_series_than_the_cap_analyzes_the_first_and_warns(self, client):
        from lm_mcp.tools.analyze_metric import analyze_metric
        from lm_mcp.tools.otlp_metrics import MAX_SERIES

        points = _texts(_every(300, [1.0, 2.0]))
        series = [({"pod": f"p{i:02d}"}, points) for i in range(MAX_SERIES + 5)]
        respx.post(OTLP_URL).mock(return_value=httpx.Response(200, json=_otlp_body(*series)))

        body = _body(await analyze_metric(client, source="otlp", query="q", analyses=["summary"]))

        assert len(body["series"]) == MAX_SERIES
        assert body["series_count_total"] == MAX_SERIES + 5
        assert any(str(MAX_SERIES + 5) in w for w in body["warnings"])

    @respx.mock
    async def test_no_series_is_an_empty_result_with_a_warning(self, client):
        from lm_mcp.tools.analyze_metric import analyze_metric

        respx.post(OTLP_URL).mock(return_value=httpx.Response(200, json=_otlp_body()))

        result = await analyze_metric(client, source="otlp", query="q")

        body = _body(result)
        assert body["series"] == {}
        assert body["series_count_total"] == 0
        assert body["warnings"]

    @respx.mock
    async def test_baseline_reads_the_earlier_window_with_a_second_range_query(self, client):
        from lm_mcp.tools.analyze_metric import analyze_metric

        now_points = _texts(_every(300, [12.0] * 10))
        then_points = _texts(_every(300, [10.0] * 10))
        route = respx.post(OTLP_URL).mock(
            side_effect=[
                httpx.Response(200, json=_otlp_body(({"code": "200"}, now_points))),
                httpx.Response(200, json=_otlp_body(({"code": "200"}, then_points))),
            ]
        )

        body = _body(
            await analyze_metric(
                client,
                source="otlp",
                query="q",
                hours=2,
                analyses=["baseline"],
                baseline_hours_ago=168,
            )
        )

        first, second = (json.loads(c.request.content) for c in route.calls)
        assert first["end"] - second["end"] == 168 * 3600
        assert second["end"] - second["start"] == 2 * 3600
        baseline = body["series"]['{code="200"}']["baseline"]
        assert baseline["deviation_percent"] == 20.0
        assert baseline["status"] == "normal"

    @respx.mock
    async def test_a_200_with_an_errors_array_is_an_upstream_error(self, client):
        from lm_mcp.tools.analyze_metric import analyze_metric

        respx.post(OTLP_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "meta": {"accessible": True},
                    "errors": [{"type": "INTERNAL_ERROR", "message": "storage timed out"}],
                },
            )
        )

        result = await analyze_metric(client, source="otlp", query="q")

        assert envelope(result)["code"] == "UPSTREAM_ERROR"
        assert "storage timed out" in envelope(result)["message"]

    @respx.mock
    async def test_a_portal_without_otlp_gets_the_unavailable_notice(self, client):
        from lm_mcp.tools.analyze_metric import analyze_metric

        respx.post(OTLP_URL).mock(
            return_value=httpx.Response(
                404, json={"errorMessage": "HTTP 404 Not Found", "errorCode": 1400}
            )
        )

        body = _body(await analyze_metric(client, source="otlp", query="q"))

        assert body["available"] is False

    @pytest.mark.parametrize(
        ("kwargs", "named"),
        [
            ({"source": "otlp"}, "query"),
            ({"source": "otlp", "query": "q", "device_id": 1}, "device_id"),
            ({"source": "otlp", "query": "q", "datapoints": "cpu"}, "datapoints"),
            ({"source": "device", "query": "q", **SERIES_ARGS}, "query"),
            ({"source": "device", "step": "5m", **SERIES_ARGS}, "step"),
            ({"source": "device", "device_id": 1}, "device_datasource_id"),
            ({"source": "prometheus", "query": "q"}, "source"),
        ],
        ids=[
            "otlp_no_query",
            "otlp_device_id",
            "otlp_datapoints",
            "device_query",
            "device_step",
            "device_missing_ids",
            "unknown_source",
        ],
    )
    @respx.mock
    async def test_arguments_of_the_other_source_are_refused(self, client, kwargs, named):
        from lm_mcp.tools.analyze_metric import analyze_metric

        route = respx.route(url__startswith="https://test.logicmonitor.com/")

        result = await analyze_metric(client, **kwargs)

        assert envelope(result)["code"] == "INVALID_REQUEST"
        assert named in envelope(result)["message"]
        assert not route.called
