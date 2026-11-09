# Description: Tests for analyze_alerts, the one-read analysis of an alert window.
# Description: Covers the window read, statistics, clusters, noise, bursts, changes and selection.

import json
import logging
import time
from unittest.mock import patch

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from tests.alert_pages import alert_lists
from tests.envelope import envelope

# Base epoch for test data (2024-01-15 00:00:00 UTC)
BASE_EPOCH = 1705276800
ALERT_URL = "https://test.logicmonitor.com/santaba/rest/alert/alerts"
GROUP_URL = "https://test.logicmonitor.com/santaba/rest/device/groups/5"
AUDIT_URL = "https://test.logicmonitor.com/santaba/rest/setting/accesslogs"


@pytest.fixture
def client():
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=BearerAuth("test-token"),
        timeout=30,
        max_retries=0,
    )


def _make_alert(
    alert_id,
    device,
    datasource,
    datapoint="value",
    severity=4,
    start_epoch=None,
    end_epoch=0,
    cleared=False,
):
    """An /alert/alerts row in the live shape: cleared is a boolean, endEpoch 0 while open."""
    return {
        "id": f"LMA{alert_id}",
        "severity": severity,
        "monitorObjectName": device,
        "resourceTemplateName": datasource,
        "dataPointName": datapoint,
        "alertValue": f"Alert {alert_id}",
        "startEpoch": start_epoch or BASE_EPOCH,
        "endEpoch": end_epoch,
        "cleared": cleared,
    }


def _cleared(alert_id, device, datasource, datapoint="value", start_epoch=None, **kwargs):
    """A cleared row: it closed 60 seconds after it opened unless end_epoch says otherwise."""
    start = start_epoch or BASE_EPOCH
    kwargs.setdefault("end_epoch", start + 60)
    return _make_alert(
        alert_id, device, datasource, datapoint, start_epoch=start, cleared=True, **kwargs
    )


async def _analyze(client, **kwargs):
    from lm_mcp.tools.analyze_alerts import analyze_alerts

    return await analyze_alerts(client, **kwargs)


def _body(result):
    return json.loads(result[0].text)


class TestOneRead:
    """R2.2: one active-plus-cleared read of the window feeds every section."""

    @respx.mock
    async def test_reads_each_page_of_both_lists_once_for_every_section(self, client):
        """2,500 active rows are three pages and 1,200 cleared rows two: five calls in all."""
        active = [_make_alert(i, f"dev-{i % 7}", f"DS-{i % 3}") for i in range(2500)]
        cleared = [_cleared(10_000 + i, f"dev-{i % 7}", "DS-0") for i in range(1200)]
        route = respx.get(ALERT_URL).mock(
            side_effect=alert_lists(active, cleared, lower_bound=True)
        )

        body = _body(await _analyze(client, analyses=["statistics", "clusters", "noise"]))

        assert route.call_count == 5
        assert body["total_alerts"] == 3700
        assert body["truncated"] is False
        assert body["api_total"] == 3700
        assert body["statistics"]["cleared"] == 1200
        assert body["noise"]["total_alerts"] == 3700

    @respx.mock
    async def test_default_runs_every_section(self, client):
        from lm_mcp.tools.analyze_alerts import SECTIONS

        respx.get(ALERT_URL).mock(side_effect=alert_lists([_make_alert(1, "s1", "CPU")]))
        respx.get(AUDIT_URL).mock(return_value=httpx.Response(200, json={"items": []}))

        body = _body(await _analyze(client))

        assert body["hours"] == 24
        assert body["analyses"] == list(SECTIONS)
        assert set(SECTIONS) <= set(body)

    @respx.mock
    async def test_analyses_selects_sections(self, client):
        respx.get(ALERT_URL).mock(side_effect=alert_lists([_make_alert(1, "s1", "CPU")]))

        body = _body(await _analyze(client, analyses=["noise"]))

        assert "noise" in body
        assert "statistics" not in body
        assert "clusters" not in body

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"analyses": ["noise", "bogus"]},
            {"analyses": ["Noise"]},
            {"analyses": []},
            {"severity": "fatal"},
            {"hours": 0},
            {"window_seconds": 0},
            {"min_alerts": 0},
            {"min_devices": 0},
            {"correlation_window_minutes": 0},
        ],
        ids=[
            "unknown-section",
            "wrong-case",
            "empty",
            "unknown-severity",
            "no-hours",
            "no-window",
            "no-min-alerts",
            "no-min-devices",
            "no-correlation-window",
        ],
    )
    @respx.mock
    async def test_bad_argument_is_invalid_request_before_any_read(self, client, kwargs):
        """An unknown section or severity, or a window or threshold under 1, is refused."""
        route = respx.get(ALERT_URL).mock(side_effect=alert_lists([]))

        error = envelope(await _analyze(client, **kwargs))

        assert error["code"] == "INVALID_REQUEST"
        assert route.call_count == 0

    @respx.mock
    async def test_filters_reach_both_reads(self, client):
        """Severity, device, group and datasource narrow the active read; the cleared read
        repeats them, and the audit read opens at the same second."""
        respx.get(GROUP_URL).mock(
            return_value=httpx.Response(200, json={"id": 5, "fullPath": "Sites/East"})
        )
        route = respx.get(ALERT_URL).mock(side_effect=alert_lists([]))
        audit = respx.get(AUDIT_URL).mock(return_value=httpx.Response(200, json={"items": []}))

        before = int(time.time())
        await _analyze(
            client, hours=6, severity="error", device="web", group_id=5, datasource="interface"
        )

        filters = [c.request.url.params["filter"].split(",") for c in route.calls]
        assert len(filters) == 2
        active, cleared = filters
        assert "severity:3" in active
        assert 'monitorObjectName~"web"' in active
        assert 'monitorObjectGroups~"Sites/East"' in active
        assert 'resourceTemplateName~"interface"' in active
        start = int(next(c for c in active if c.startswith("startEpoch>:")).split(":")[1])
        assert before - 6 * 3600 <= start <= int(time.time()) - 6 * 3600
        assert "cleared:true" not in active
        assert cleared == [*active, "cleared:true"]
        assert audit.call_count == 1
        assert audit.calls[0].request.url.params["filter"] == f"happenedOn>:{start}"

    @respx.mock
    async def test_alert_in_both_lists_counts_once_as_cleared(self, client):
        """An alert that clears between the two reads is kept once, as the cleared copy."""
        active = [_make_alert(1, "s1", "CPU")]
        cleared = [_cleared(1, "s1", "CPU", end_epoch=BASE_EPOCH + 600)]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(active, cleared))

        body = _body(await _analyze(client, analyses=["statistics"]))

        assert body["total_alerts"] == 1
        assert body["statistics"]["active"] == 0
        assert body["statistics"]["cleared"] == 1

    @pytest.mark.parametrize(
        ("n_active", "active_lb", "n_cleared", "cleared_lb", "total", "truncated", "api_total"),
        [
            (3, False, 4, False, 7, False, 7),
            (10, False, 6000, True, 5010, True, None),
            (6000, True, 10, False, 5010, True, None),
        ],
        ids=["both-exact", "cleared-capped", "active-capped"],
    )
    @respx.mock
    async def test_truncation_covers_both_reads(
        self, client, n_active, active_lb, n_cleared, cleared_lb, total, truncated, api_total
    ):
        active = [_make_alert(i, f"dev-{i % 5}", "DS") for i in range(n_active)]
        cleared = [_cleared(100_000 + i, f"dev-{i % 5}", "DS") for i in range(n_cleared)]
        respx.get(ALERT_URL).mock(
            side_effect=alert_lists(
                active, cleared, lower_bound=active_lb, cleared_lower_bound=cleared_lb
            )
        )

        body = _body(await _analyze(client, analyses=["statistics"]))

        assert body["total_alerts"] == total
        assert body["truncated"] is truncated
        assert body["api_total"] == api_total

    @respx.mock
    async def test_api_error_is_an_error_result(self, client):
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        error = envelope(await _analyze(client, analyses=["statistics"]))

        assert error["code"] == "UPSTREAM_ERROR"


class TestStatistics:
    """R2.2 statistics: per-hour volume including cleared, by severity, device and datasource."""

    @respx.mock
    async def test_hourly_volume_counts_cleared_alerts(self, client):
        """Each alert lands in the hour it opened, cleared or not, oldest hour first.

        Alerts sit mid-hour, so the second between the test's clock and the tool's
        cannot move one across a bucket edge.
        """
        now = int(time.time())
        active = [_make_alert(1, "s1", "CPU", start_epoch=now - 1800)]
        cleared = [
            _cleared(2, "s1", "CPU", start_epoch=now - 3 * 3600 - 1800),
            _cleared(3, "s2", "Disk", start_epoch=now - 2 * 3600 - 1800),
            _cleared(4, "s2", "Disk", start_epoch=now - 2 * 3600 - 1200),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(active, cleared))

        stats = _body(await _analyze(client, hours=4, analyses=["statistics"]))["statistics"]

        assert [h["count"] for h in stats["hourly"]] == [1, 2, 0, 1]
        assert stats["active"] == 1
        assert stats["cleared"] == 3
        assert stats["hourly"][1]["start"] - stats["hourly"][0]["start"] == 3600

    @respx.mock
    async def test_alert_stamped_after_the_tool_clock_counts_in_the_last_hour(self, client):
        """A portal clock a little ahead of the server's still counts the alert, not drops it."""
        now = int(time.time())
        active = [
            _make_alert(1, "s1", "CPU", start_epoch=now + 120),
            _make_alert(2, "s1", "CPU", start_epoch=now - 2 * 3600 - 1800),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(active))

        stats = _body(await _analyze(client, hours=3, analyses=["statistics"]))["statistics"]

        assert [h["count"] for h in stats["hourly"]] == [1, 0, 1]

    @respx.mock
    async def test_counts_by_severity_device_and_datasource(self, client):
        alerts = [
            _make_alert(1, "web-01", "CPU", severity=4),
            _make_alert(2, "web-01", "Memory", severity=3),
            _make_alert(3, "web-02", "CPU", severity=2),
        ]
        cleared = [_cleared(4, "web-01", "CPU", severity=4)]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts, cleared))

        stats = _body(await _analyze(client, analyses=["statistics"]))["statistics"]

        assert stats["by_severity"] == {"critical": 2, "error": 1, "warning": 1, "info": 0}
        assert stats["by_device"][0] == {"device": "web-01", "count": 3}
        assert stats["by_datasource"][0] == {"datasource": "CPU", "count": 3}


class TestClusters:
    """R2.2 clusters: alerts grouped by device, datasource and message signature."""

    @respx.mock
    async def test_groups_by_device_datasource_and_signature(self, client):
        """The signature is datasource and datapoint, so it splits a datasource by condition."""
        active = [
            _make_alert(1, "web-01", "CPU", "cpuBusy"),
            _make_alert(2, "web-02", "CPU", "cpuBusy"),
            _make_alert(3, "web-03", "CPU", "loadAvg"),
        ]
        cleared = [_cleared(4, "web-01", "Disk", "used")]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(active, cleared))

        clusters = _body(await _analyze(client, analyses=["clusters"]))["clusters"]

        by_type = {(c["type"], c["key"]): c for c in clusters["clusters"]}
        assert set(by_type) == {
            ("device", "web-01"),
            ("datasource", "CPU"),
            ("signature", "CPU/cpuBusy"),
        }
        assert by_type[("device", "web-01")]["alert_ids"] == ["LMA1", "LMA4"]
        assert by_type[("datasource", "CPU")]["count"] == 3
        assert sorted(by_type[("signature", "CPU/cpuBusy")]["devices"]) == ["web-01", "web-02"]
        assert clusters["cluster_count"] == 3

    @respx.mock
    async def test_single_alerts_form_no_cluster(self, client):
        respx.get(ALERT_URL).mock(
            side_effect=alert_lists([_make_alert(1, "s1", "CPU"), _make_alert(2, "s2", "Disk")])
        )

        clusters = _body(await _analyze(client, analyses=["clusters"]))["clusters"]

        assert clusters == {"cluster_count": 0, "clusters": []}


class TestNoise:
    """R2.2 noise: entropy, flap pairs and repeats over active and cleared alerts."""

    @respx.mock
    async def test_empty_window_is_quiet(self, client):
        respx.get(ALERT_URL).mock(side_effect=alert_lists([]))

        noise = _body(await _analyze(client, analyses=["noise"]))["noise"]

        assert noise["noise_score"] == 0
        assert noise["total_alerts"] == 0
        assert noise["recommendations"] == ["No alerts in the time window."]

    @respx.mock
    async def test_cleared_alert_and_refire_count_as_a_flap(self, client):
        cleared = [_cleared(1, "s1", "CPU", end_epoch=BASE_EPOCH + 600)]
        active = [_make_alert(2, "s1", "CPU", start_epoch=BASE_EPOCH + 1200)]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(active, cleared))

        noise = _body(await _analyze(client, analyses=["noise"]))["noise"]

        assert noise["total_alerts"] == 2
        assert noise["flap_count"] == 1
        assert noise["flapping_alerts"][0] == {
            "key": "s1:value",
            "gap_seconds": 600,
            "alert_id": "LMA2",
        }

    @pytest.mark.parametrize(
        ("second_start", "flaps"),
        [(BASE_EPOCH + 600, 0), (BASE_EPOCH + 1200, 1)],
        ids=["opens-before-the-clear", "re-fires-as-it-clears"],
    )
    @respx.mock
    async def test_a_flap_needs_the_clear_before_the_refire(self, client, second_start, flaps):
        # An alert that opens while the previous one is still open overlaps it, so
        # nothing cleared and re-fired; a live portal day held 660 such pairs among
        # 4210 counted flaps. A re-fire in the second it cleared is a flap.
        cleared = [
            _cleared(1, "s1", "CPU", start_epoch=BASE_EPOCH, end_epoch=BASE_EPOCH + 1200),
            _cleared(2, "s1", "CPU", start_epoch=second_start, end_epoch=BASE_EPOCH + 2400),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists([], cleared))

        noise = _body(await _analyze(client, analyses=["noise"]))["noise"]

        assert noise["total_alerts"] == 2
        assert noise["flap_count"] == flaps
        assert len(noise["flapping_alerts"]) == flaps

    @respx.mock
    async def test_a_refire_after_thirty_minutes_is_no_flap(self, client):
        cleared = [_cleared(1, "s1", "CPU", end_epoch=BASE_EPOCH + 600)]
        active = [_make_alert(2, "s1", "CPU", start_epoch=BASE_EPOCH + 600 + 1800)]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(active, cleared))

        noise = _body(await _analyze(client, analyses=["noise"]))["noise"]

        assert noise["flap_count"] == 0

    @respx.mock
    async def test_repeats_and_entropy(self, client):
        """Ten rows of one combination and five singles: one repeating combo in six."""
        alerts = [
            _make_alert(i, "s1", "CPU", "value", start_epoch=BASE_EPOCH + i * 60) for i in range(10)
        ] + [_make_alert(10 + i, f"server{i}", f"DS{i}", f"dp{i}") for i in range(5)]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        noise = _body(await _analyze(client, analyses=["noise"]))["noise"]

        assert noise["total_alerts"] == 15
        assert noise["repeat_ratio"] == round(1 / 6, 4)
        # p = 10/15 once and 1/15 five times: H = 1.6923 bits of log2(6) = 2.585.
        assert noise["entropy"] == pytest.approx(1.6923, abs=1e-4)
        assert noise["normalized_entropy"] == pytest.approx(0.6547, abs=1e-4)
        assert noise["top_noisy_devices"][0] == {"device": "s1", "count": 10}
        assert noise["top_noisy_datasources"][0] == {"datasource": "CPU", "count": 10}

    @respx.mock
    async def test_high_noise_carries_the_best_practice(self, client):
        """Flapping on many combinations pushes the score past 50, which adds the guardrails."""
        alerts = []
        for i in range(20):
            alerts.append(
                _cleared(
                    i,
                    f"server{i}",
                    f"DS{i}",
                    start_epoch=BASE_EPOCH,
                    end_epoch=BASE_EPOCH + 30,
                )
            )
            for k in range(1, 4):
                alerts.append(
                    _make_alert(
                        100 * k + i, f"server{i}", f"DS{i}", start_epoch=BASE_EPOCH + 30 + k
                    )
                )
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        noise = _body(await _analyze(client, analyses=["noise"]))["noise"]

        assert noise["noise_score"] > 50
        assert noise["structured_recommendations"]
        assert noise["anti_patterns"]

    @respx.mock
    async def test_low_noise_has_no_anti_patterns(self, client):
        respx.get(ALERT_URL).mock(side_effect=alert_lists([_make_alert(1, "s1", "CPU")]))

        noise = _body(await _analyze(client, analyses=["noise"]))["noise"]

        assert noise["noise_score"] <= 50
        assert "anti_patterns" not in noise


def _burst(n, datasource, devices, start, spacing=3, first_id=0):
    """n alerts on one datasource, spacing seconds apart, cycling over the device count."""
    return [
        _make_alert(
            first_id + i, f"switch-{i % devices}", datasource, start_epoch=start + i * spacing
        )
        for i in range(n)
    ]


class TestBursts:
    """R2.2 bursts: per-datasource windows holding enough alerts on enough devices."""

    @respx.mock
    async def test_detects_a_burst_on_one_datasource(self, client):
        """Twelve alerts on four switches within 36 seconds are one burst."""
        now = int(time.time())
        respx.get(ALERT_URL).mock(
            side_effect=alert_lists(_burst(12, "SNMP_Network_Interfaces", 4, now - 60))
        )

        bursts = _body(
            await _analyze(
                client, analyses=["bursts"], window_seconds=60, min_alerts=10, min_devices=3
            )
        )["bursts"]

        assert bursts["bursts_detected"] == 1
        burst = bursts["bursts"][0]
        assert burst["datasource"] == "SNMP_Network_Interfaces"
        assert burst["alert_count"] == 12
        assert burst["device_count"] == 4
        assert burst["window_start"] == now - 60
        assert burst["window_end"] == now
        assert {d["device"] for d in burst["top_devices"]} == {f"switch-{i}" for i in range(4)}

    @respx.mock
    async def test_too_few_alerts_or_devices_is_no_burst(self, client):
        now = int(time.time())
        alerts = _burst(9, "CPU", 9, now - 60) + _burst(12, "Disk", 2, now - 60, first_id=100)
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        bursts = _body(await _analyze(client, analyses=["bursts"]))["bursts"]

        assert bursts["bursts_detected"] == 0
        assert bursts["bursts"] == []

    @respx.mock
    async def test_alerts_further_apart_than_the_window_are_no_burst(self, client):
        """Ten alerts 10 seconds apart span 90 seconds: a burst in 90, not in 60."""
        now = int(time.time())
        respx.get(ALERT_URL).mock(
            side_effect=alert_lists(_burst(10, "CPU", 5, now - 600, spacing=10))
        )

        narrow = _body(await _analyze(client, analyses=["bursts"], window_seconds=60))
        wide = _body(await _analyze(client, analyses=["bursts"], window_seconds=90))

        assert narrow["bursts"]["bursts_detected"] == 0
        assert wide["bursts"]["bursts_detected"] == 1

    @respx.mock
    async def test_datasources_burst_separately_and_cleared_alerts_count(self, client):
        """Each datasource's alerts form their own windows, cleared alerts included."""
        now = int(time.time())
        active = _burst(10, "Ping", 5, now - 300)
        cleared = [
            _cleared(200 + i, f"host-{i % 3}", "HTTPS", start_epoch=now - 900 + i)
            for i in range(10)
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(active, cleared))

        bursts = _body(await _analyze(client, analyses=["bursts"]))["bursts"]

        assert [b["datasource"] for b in bursts["bursts"]] == ["HTTPS", "Ping"]
        assert bursts["window_seconds"] == 60
        assert bursts["min_alerts"] == 10
        assert bursts["min_devices"] == 3

    @respx.mock
    async def test_empty_window_has_no_bursts(self, client):
        respx.get(ALERT_URL).mock(side_effect=alert_lists([]))

        bursts = _body(await _analyze(client, analyses=["bursts"]))["bursts"]

        assert bursts["bursts_detected"] == 0


def _aligned_spike_time(now):
    """A five-minute bucket boundary an hour back, so a spike's bucket starts on it."""
    return (now // 300) * 300 - 3600


def _spike_with_background(spike_ts, now):
    """Ten alerts in one bucket and five single alerts in earlier buckets."""
    alerts = [_make_alert(i, f"server{i}", "Ping", start_epoch=spike_ts) for i in range(10)]
    alerts += [
        _make_alert(100 + i, f"bg{i}", "Ping", start_epoch=now - 7200 + i * 600) for i in range(5)
    ]
    return alerts


class TestChanges:
    """R2.2 changes: audit write actions in the window paired to alert spikes."""

    @respx.mock
    async def test_write_action_before_a_spike_is_paired(self, client):
        now = int(time.time())
        spike_ts = _aligned_spike_time(now)
        respx.get(ALERT_URL).mock(side_effect=alert_lists(_spike_with_background(spike_ts, now)))
        audit = respx.get(AUDIT_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "happenedOn": spike_ts - 600,
                            "username": "admin",
                            "description": '"Action=Update"; "Type=Device"; "Device=web-01"',
                        }
                    ]
                },
            )
        )

        changes = _body(await _analyze(client, analyses=["changes"]))["changes"]

        assert audit.call_count == 1
        assert changes["total_changes"] == 1
        assert changes["total_spikes"] == 1
        event = changes["correlated_events"][0]
        assert event["change"]["user"] == "admin"
        assert event["spike"] == {"timestamp": spike_ts, "alert_count": 10}
        assert event["time_gap_minutes"] == 10.0
        assert event["confidence"] == 0.83
        assert changes["uncorrelated_changes"] == []

    @respx.mock
    async def test_a_read_or_login_entry_is_not_a_change(self, client):
        now = int(time.time())
        spike_ts = _aligned_spike_time(now)
        respx.get(ALERT_URL).mock(side_effect=alert_lists(_spike_with_background(spike_ts, now)))
        respx.get(AUDIT_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "happenedOn": spike_ts - 60,
                            "username": "admin",
                            "description": "admin signs in (adminLogin)",
                        }
                    ]
                },
            )
        )

        changes = _body(await _analyze(client, analyses=["changes"]))["changes"]

        assert changes["total_changes"] == 0
        assert changes["correlated_events"] == []
        assert changes["uncorrelated_spikes"] == [{"timestamp": spike_ts, "alert_count": 10}]

    @pytest.mark.parametrize(("window", "paired"), [(30, 0), (60, 1)])
    @respx.mock
    async def test_the_correlation_window_bounds_the_pairing(self, client, window, paired):
        """A change 40 minutes before the spike pairs in a 60-minute window, not a 30."""
        now = int(time.time())
        spike_ts = _aligned_spike_time(now)
        respx.get(ALERT_URL).mock(side_effect=alert_lists(_spike_with_background(spike_ts, now)))
        respx.get(AUDIT_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "happenedOn": spike_ts - 2400,
                            "username": "admin",
                            "description": "Updated firewall rule",
                        }
                    ]
                },
            )
        )

        changes = _body(
            await _analyze(client, analyses=["changes"], correlation_window_minutes=window)
        )["changes"]

        assert len(changes["correlated_events"]) == paired
        assert changes["correlation_window_minutes"] == window

    @respx.mock
    async def test_unpaired_change_reports_its_time_in_seconds(self, client):
        """An audit time in milliseconds is read as seconds, paired or not."""
        now = int(time.time())
        respx.get(ALERT_URL).mock(side_effect=alert_lists([_make_alert(1, "s1", "CPU")]))
        respx.get(AUDIT_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "happenedOn": (now - 36000) * 1000,
                            "username": "admin",
                            "description": "Updated config",
                        }
                    ]
                },
            )
        )

        changes = _body(await _analyze(client, analyses=["changes"]))["changes"]

        assert changes["total_changes"] == 1
        assert changes["uncorrelated_changes"] == [
            {"timestamp": now - 36000, "user": "admin", "description": "Updated config"}
        ]

    @respx.mock
    async def test_failed_audit_read_is_flagged_not_silent(self, client, caplog):
        """A failed audit read leaves the other sections whole and says changes are unknown."""
        respx.get(ALERT_URL).mock(side_effect=alert_lists([_make_alert(1, "s1", "CPU")]))
        respx.get(AUDIT_URL).mock(return_value=httpx.Response(403, json={"errorMessage": "no"}))

        with caplog.at_level(logging.WARNING, logger="lm_mcp.tools.analyze_alerts"):
            body = _body(await _analyze(client, analyses=["statistics", "changes"]))

        assert body["statistics"]["active"] == 1
        changes = body["changes"]
        assert changes["audit_read_failed"] is True
        assert "unavailable" in changes["warning"]
        assert changes["total_changes"] == 0
        records = [r for r in caplog.records if r.name == "lm_mcp.tools.analyze_alerts"]
        assert len(records) == 1
        assert records[0].exc_info is not None

    @respx.mock
    async def test_no_audit_read_without_the_changes_section(self, client):
        respx.get(ALERT_URL).mock(side_effect=alert_lists([]))
        audit = respx.get(AUDIT_URL).mock(return_value=httpx.Response(200, json={"items": []}))

        await _analyze(client, analyses=["statistics", "clusters", "noise", "bursts"])

        assert audit.call_count == 0


class TestRegistration:
    """analyze_alerts is a registered, read-only tool dispatched through execute_tool."""

    def test_schema_offers_exactly_the_sections_and_severities(self):
        from lm_mcp.registry import TOOLS
        from lm_mcp.tools import SEVERITY_MAP
        from lm_mcp.tools.analyze_alerts import SECTIONS

        tool = next(t for t in TOOLS if t.name == "analyze_alerts")
        props = tool.inputSchema["properties"]

        assert props["analyses"]["items"]["enum"] == list(SECTIONS)
        assert props["severity"]["enum"] == list(SEVERITY_MAP)
        assert set(props) == {
            "hours",
            "severity",
            "device",
            "group_id",
            "datasource",
            "analyses",
            "window_seconds",
            "min_alerts",
            "min_devices",
            "correlation_window_minutes",
        }
        assert "required" not in tool.inputSchema
        assert tool.annotations.readOnlyHint is True

    @respx.mock
    async def test_execute_tool_dispatches_to_analyze_alerts(self, client, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        respx.get(ALERT_URL).mock(side_effect=alert_lists([_make_alert(1, "s1", "CPU")]))

        with patch("lm_mcp.server._client", client):
            from lm_mcp.server import execute_tool

            result = await execute_tool("analyze_alerts", {"analyses": ["statistics"]})

        assert _body(result)["statistics"]["active"] == 1
