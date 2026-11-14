# Description: Tests for collector MCP tools.
# Description: Validates collector read, update, and delete functions.

import io
import json
import re
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result
from tests.envelope import envelope
from tests.list_paging import assert_negative_total_reads_as_more, assert_offset_declared_and_sent


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


class TestGetCollectors:
    """Tests for get_collectors tool."""

    @respx.mock
    async def test_get_collectors_returns_formatted_response(self, client):
        """get_collectors returns properly formatted collector list."""
        from lm_mcp.tools.collectors import get_collectors

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "hostname": "collector01.example.com",
                            "status": 1,
                            "numberOfHosts": 50,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_collectors(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["collectors"][0]["hostname"] == "collector01.example.com"

    @respx.mock
    async def test_get_collectors_with_limit(self, client):
        """get_collectors passes size parameter to API."""
        from lm_mcp.tools.collectors import get_collectors

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collectors(client, limit=10)

        assert route.calls[0].request.url.params.get("size") == "10"


class TestGetCollector:
    """Tests for get_collector tool."""

    @respx.mock
    async def test_get_collector_returns_details(self, client):
        """get_collector returns single collector details."""
        from lm_mcp.tools.collectors import get_collector

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/5").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5,
                    "hostname": "collector05.example.com",
                    "status": 1,
                    "numberOfHosts": 100,
                    "platform": "linux",
                },
            )
        )

        result = await get_collector(client, collector_id=5)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 5

    @respx.mock
    async def test_get_collector_not_found(self, client):
        """get_collector returns error for missing collector."""
        from lm_mcp.tools.collectors import get_collector

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/999"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Collector not found"}))

        result = await get_collector(client, collector_id=999)

        assert is_error_result(result)


class TestGetCollectorsFilters:
    """Tests for get_collectors filter parameters."""

    @respx.mock
    async def test_get_collectors_with_hostname_filter(self, client):
        """get_collectors filters by hostname."""
        from lm_mcp.tools.collectors import get_collectors

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collectors(client, hostname_filter="prod")

        params = dict(route.calls[0].request.url.params)
        assert "filter" in params
        assert 'hostname~"prod"' in params["filter"]

    @respx.mock
    async def test_get_collectors_with_group_id(self, client):
        """get_collectors filters by collector group ID."""
        from lm_mcp.tools.collectors import get_collectors

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collectors(client, collector_group_id=5)

        params = dict(route.calls[0].request.url.params)
        assert "filter" in params
        assert "collectorGroupId:5" in params["filter"]

    @respx.mock
    async def test_get_collectors_with_raw_filter(self, client):
        """get_collectors passes raw filter expression to API."""
        from lm_mcp.tools.collectors import get_collectors

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collectors(client, filter="hostname~prod,collectorGroupId:1")

        params = dict(route.calls[0].request.url.params)
        assert params["filter"] == "hostname~prod,collectorGroupId:1"

    @respx.mock
    async def test_get_collectors_with_offset(self, client):
        """get_collectors passes offset for pagination."""
        from lm_mcp.tools.collectors import get_collectors

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collectors(client, offset=50)

        params = dict(route.calls[0].request.url.params)
        assert params["offset"] == "50"

    @respx.mock
    async def test_get_collectors_pagination_info(self, client):
        """get_collectors returns pagination info."""
        from lm_mcp.tools.collectors import get_collectors

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": 1, "hostname": "collector01"}],
                    "total": 100,
                },
            )
        )

        result = await get_collectors(client, limit=10, offset=0)

        data = json.loads(result[0].text)
        assert data["total"] == 100
        assert data["has_more"] is True
        assert data["offset"] == 0


class TestGetCollectorGroupsFilters:
    """Tests for get_collector_groups filter parameters."""

    @respx.mock
    async def test_get_collector_groups_with_raw_filter(self, client):
        """get_collector_groups passes raw filter expression to API."""
        from lm_mcp.tools.collectors import get_collector_groups

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/groups"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collector_groups(client, filter="name~prod,autoBalance:true")

        params = dict(route.calls[0].request.url.params)
        assert params["filter"] == "name~prod,autoBalance:true"

    @respx.mock
    async def test_get_collector_groups_with_offset(self, client):
        """get_collector_groups passes offset for pagination."""
        from lm_mcp.tools.collectors import get_collector_groups

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/groups"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collector_groups(client, offset=25)

        params = dict(route.calls[0].request.url.params)
        assert params["offset"] == "25"


class TestUpdateCollector:
    """Tests for update_collector tool."""

    @respx.mock
    async def test_update_collector_group(self, client, monkeypatch):
        """update_collector sends correct PATCH body for group change."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import update_collector

        respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/121"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 121,
                    "hostname": "argus-0",
                    "collectorGroupId": 34,
                    "collectorGroupName": "AKS Cluster",
                    "description": "",
                },
            )
        )

        result = await update_collector(client, collector_id=121, collector_group_id=34)
        data = json.loads(result[0].text)
        assert data["message"] == "Collector updated successfully"
        assert data["collector"]["collector_group_id"] == 34

    @respx.mock
    async def test_update_collector_no_changes(self, client, monkeypatch):
        """update_collector returns error when no updates provided."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import update_collector

        result = await update_collector(client, collector_id=121)
        assert "No updates provided" in result[0].text


class TestDeleteCollector:
    """Tests for delete_collector tool."""

    @respx.mock
    async def test_delete_collector_blocked_with_devices(self, client, monkeypatch):
        """delete_collector blocks when collector has devices."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import delete_collector

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/121"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 121, "hostname": "argus-0", "numberOfHosts": 50},
            )
        )

        result = await delete_collector(client, collector_id=121)
        assert "50 devices assigned" in result[0].text
        assert "Move or delete devices" in result[0].text

    @respx.mock
    async def test_delete_collector_succeeds_empty(self, client, monkeypatch):
        """delete_collector succeeds when collector has no devices."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import delete_collector

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/121"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 121, "hostname": "argus-0", "numberOfHosts": 0},
            )
        )
        respx.delete(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/121"
        ).mock(return_value=httpx.Response(200, json={}))

        result = await delete_collector(client, collector_id=121)
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestGetCollectorHealth:
    """Tests for get_collector_health tool."""

    @respx.mock
    async def test_reports_healthy_collector(self, client):
        """R5: isDown false is an up collector; status is 1 whether the collector is up or down."""
        from lm_mcp.tools.collectors import get_collector_health

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "hostname": "col-01",
                    "status": 1,
                    "isDown": False,
                    "numberOfHosts": 42,
                    "collectorGroupId": 5,
                    "collectorGroupName": "prod",
                    "platform": "linux",
                    "upTime": 86400,
                },
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 42})
        )

        _mock_evidence()
        result = await get_collector_health(client, collector_id=1)
        data = json.loads(result[0].text)

        assert data["total_collectors"] == 1
        assert data["collectors_down"] == 0
        assert "collectors_down_signal_unavailable" not in data
        assert "warning" not in data
        col = data["collectors"][0]
        assert col["hostname"] == "col-01"
        assert col["is_down"] is False
        assert col["downstream_device_count"] == 42
        assert "down_signal_unavailable" not in col

    @respx.mock
    async def test_flags_collector_the_record_marks_down(self, client):
        """R5: isDown true is a down collector, with status 1 as a live portal returns it."""
        from lm_mcp.tools.collectors import get_collector_health

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 2,
                    "hostname": "col-02",
                    "status": 1,
                    "isDown": True,
                    "numberOfHosts": 30,
                },
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 30})
        )

        _mock_evidence()
        result = await get_collector_health(client, collector_id=2)
        data = json.loads(result[0].text)

        assert data["collectors_down"] == 1
        assert data["collectors"][0]["is_down"] is True
        assert "collectors_down_signal_unavailable" not in data

    @respx.mock
    async def test_sends_no_alert_read_for_the_down_signal(self, client):
        """R5: the API rejects type:alert and ignores alertType, so the state reads no alerts."""
        from lm_mcp.tools.collectors import get_collector_health

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/1").mock(
            return_value=httpx.Response(
                200, json={"id": 1, "hostname": "col-01", "status": 1, "isDown": False}
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        alerts = respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": []})
        )

        _mock_evidence()
        result = await get_collector_health(client, collector_id=1)
        data = json.loads(result[0].text)

        assert not alerts.called
        assert "active_collector_down_alerts" not in data["collectors"][0]

    @respx.mock
    async def test_record_without_is_down_leaves_the_state_unknown(self, client):
        """R4.4: no isDown is unknown, whatever status says, and neither counts as down."""
        from lm_mcp.tools.collectors import get_collector_health

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 1, "hostname": "col-a", "status": "dead", "numberOfHosts": 4},
                        {"id": 2, "hostname": "col-b", "status": 1, "numberOfHosts": 6},
                    ]
                },
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 5})
        )

        _mock_evidence()
        result = await get_collector_health(client)
        data = json.loads(result[0].text)

        for col in data["collectors"]:
            assert col["is_down"] is None
            assert col["down_signal_unavailable"] is True
        assert data["collectors_down"] == 0
        assert data["collectors_down_signal_unavailable"] == 2
        assert "undercounted" in data["warning"]

    @respx.mock
    async def test_lists_all_collectors_when_no_scope(self, client):
        from lm_mcp.tools.collectors import get_collector_health

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 1, "hostname": "col-a", "status": 1, "isDown": False},
                        {"id": 2, "hostname": "col-b", "status": 1, "isDown": True},
                    ]
                },
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        _mock_evidence()
        result = await get_collector_health(client)
        data = json.loads(result[0].text)
        assert data["total_collectors"] == 2
        assert data["collectors_down"] == 1
        assert [c["is_down"] for c in data["collectors"]] == [False, True]

    @respx.mock
    async def test_includes_history_when_requested(self, client):
        """R5: history rows name the alert's own type, the field a live alert carries."""
        from lm_mcp.tools.collectors import get_collector_health

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/3").mock(
            return_value=httpx.Response(
                200,
                json={"id": 3, "hostname": "col-03", "status": 1, "isDown": False},
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        alerts = respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 500,
                            "type": "dataSourceAlert",
                            "monitorObjectName": "col-03",
                            "startEpoch": 1700000000,
                            "severity": 4,
                            "cleared": True,
                        }
                    ]
                },
            )
        )

        _mock_evidence()
        result = await get_collector_health(
            client, collector_id=3, include_history=True, history_days=3
        )
        data = json.loads(result[0].text)
        assert data["include_history"] is True
        assert alerts.call_count == 1
        sent_filter = alerts.calls.last.request.url.params["filter"]
        assert 'monitorObjectName:"col-03"' in sent_filter
        assert "startEpoch>:" in sent_filter
        history = data["collectors"][0]["collector_down_history"]
        assert len(history) == 1
        assert history[0]["alert_type"] == "dataSourceAlert"

    @respx.mock
    async def test_a_failed_history_read_is_null_with_a_warning(self, client):
        """R2.10: a failed alert read is unknown, not an empty history; the alertType
        clause the API ignores is not sent."""
        from lm_mcp.tools.collectors import get_collector_health

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/3").mock(
            return_value=httpx.Response(
                200,
                json={"id": 3, "hostname": "col-03", "status": 1, "isDown": False},
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        alerts = respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=httpx.Response(500, json={"errorMessage": "portal unavailable"})
        )

        _mock_evidence()
        result = await get_collector_health(client, collector_id=3, include_history=True)

        collector = json.loads(result[0].text)["collectors"][0]
        assert collector["collector_down_history"] is None
        assert collector["history_warning"].startswith("Alert history read failed:")
        assert "alertType" not in alerts.calls.last.request.url.params["filter"]


_BASE = "https://test.logicmonitor.com/santaba/rest"

# Answers of a sandbox portal at X-Version 3 on 2026-11-11, as read but for two cuts.
# events_26 keeps the first 5 of the 50 rows its page held, under the total the portal
# sent (-51). logs_82 lists the one file uploaded from collector 82 with the !uploadlog
# debug command; logs_41 is a collector with none. log_file_82 is that file read without
# format=zip, which answers its metadata. log_file_missing_zip is the 404 a missing file
# answers with format=zip; its path names the company UUID, zeroed here. postcheck_member
# holds the first 6 lines of the file's one zip member, postcheck.log (26,553 bytes): the
# rest names the portal and that UUID, so the tests zip the lines under the member's name.
LIVE = json.loads((Path(__file__).parent.parent / "fixtures" / "collector_reads.json").read_text())

# Answers of the same portal on 2026-11-11 to the status check and the down acknowledgement.
# status_check_82_finished is collector 82's check before a trigger and
# status_check_82_finished_new a later finished one, each cut to its first 6 of 68
# checkpoints; status_check_82_running was read 5 s after the trigger. Collector 26 is
# down: its trigger answers 400 and its check reads the ERROR and WARN it keeps.
# collectors_page holds rows 26 and 82 of the collector list.
OPS = json.loads((Path(__file__).parent.parent / "fixtures" / "collector_ops.json").read_text())


def _mock_evidence(
    collector_id: str = r"\d+", status_check: dict | None = None, events: dict | None = None
) -> tuple[respx.Route, respx.Route]:
    """Route a collector's evidence reads, its latest status check and its events, for
    get_collector_health; by default any collector answers a finished check and no events."""
    collectors = re.escape(f"{_BASE}/setting/collector/collectors/")
    status = respx.get(url__regex=rf"^{collectors}{collector_id}/services/getStatusCheck$").mock(
        return_value=httpx.Response(200, json=status_check or OPS["status_check_82_finished_new"])
    )
    events_route = respx.get(url__regex=rf"^{collectors}{collector_id}/events(\?.*)?$").mock(
        return_value=httpx.Response(200, json=events or {"total": 0, "items": []})
    )
    return status, events_route


def _zip(members: dict[str, bytes]) -> bytes:
    """Zip the members into one archive, as the portal sends a log file with format=zip."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


_POSTCHECK_LINES = [line.encode() for line in LIVE["postcheck_member"]["lines"]]
_POSTCHECK = b"".join(_POSTCHECK_LINES)


class TestGetCollectorEvents:
    """R3.4: a collector's events page through its events path, each row projected."""

    @respx.mock
    async def test_projects_each_event_and_reads_the_negative_total_as_more(self, client):
        from lm_mcp.tools.collectors import get_collector_events

        route = respx.get(f"{_BASE}/setting/collector/collectors/26/events").mock(
            return_value=httpx.Response(200, json=LIVE["events_26"])
        )

        body = json.loads((await get_collector_events(client, collector_id=26, limit=5))[0].text)

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("5", "0")
        assert "total" not in body
        assert body["has_more"] is True
        assert len(body["events"]) == 5
        assert body["events"][0] == {
            "id": "qzGSS6euRTWf6BWUjh04QA",
            "reported_on": 1793727768,
            "event_code": 8,
            "message": "The collector is down or unreachable",
            "collector_build": "39200",
            "collector_platform": "linux",
        }
        assert [e["message"] for e in body["events"][1:3]] == [
            "Agent successfully restarted.",
            "Sbproxy successfully started.",
        ]

    @respx.mock
    async def test_an_unknown_collector_is_not_found(self, client):
        from lm_mcp.tools.collectors import get_collector_events

        respx.get(f"{_BASE}/setting/collector/collectors/999999/events").mock(
            return_value=httpx.Response(404, json=LIVE["events_unknown_collector"])
        )

        error = envelope(await get_collector_events(client, collector_id=999999))
        assert error["code"] == "NOT_FOUND"


class TestGetCollectorLogFiles:
    """R3.4: the log files a collector has uploaded, one page, each row projected."""

    @respx.mock
    async def test_projects_each_uploaded_file(self, client):
        from lm_mcp.tools.collectors import get_collector_log_files

        route = respx.get(f"{_BASE}/setting/collector/collectors/82/logs").mock(
            return_value=httpx.Response(200, json=LIVE["logs_82"])
        )

        body = json.loads((await get_collector_log_files(client, collector_id=82))[0].text)

        assert route.calls.last.request.url.params["size"] == "50"
        assert "format" not in route.calls.last.request.url.params
        assert body["total"] == 1
        assert body["has_more"] is False
        assert body["log_files"] == [
            {
                "file_name": "82.postcheck.log.zip",
                "size": 3759,
                "last_modified": 1764040316,
                "uploaded": 1794445292,
            }
        ]

    @respx.mock
    async def test_a_collector_with_no_uploaded_file_is_an_empty_page(self, client):
        from lm_mcp.tools.collectors import get_collector_log_files

        respx.get(f"{_BASE}/setting/collector/collectors/41/logs").mock(
            return_value=httpx.Response(200, json=LIVE["logs_41"])
        )

        body = json.loads((await get_collector_log_files(client, collector_id=41))[0].text)

        assert (body["total"], body["log_files"]) == (0, [])


class TestGetCollectorLogFile:
    """R3.4: one uploaded log file read as its zip, the member's text capped from the end."""

    @respx.mock
    async def test_reads_the_zip_form_and_returns_the_member_text_whole(self, client):
        from lm_mcp.tools.collectors import get_collector_log_file

        route = respx.get(
            f"{_BASE}/setting/collector/collectors/82/logs/82.postcheck.log.zip"
        ).mock(
            return_value=httpx.Response(
                200,
                content=_zip({"postcheck.log": _POSTCHECK}),
                headers={"content-type": "application/octet-stream"},
            )
        )

        body = json.loads(
            (await get_collector_log_file(client, 82, "82.postcheck.log.zip"))[0].text
        )

        assert dict(route.calls.last.request.url.params) == {"format": "zip"}
        assert body == {
            "collector_id": 82,
            "file_name": "82.postcheck.log.zip",
            "member": "postcheck.log",
            "size": len(_POSTCHECK),
            "truncated": False,
            "text": _POSTCHECK.decode(),
            "other_members": [],
        }

    @pytest.mark.parametrize("spare", [40, 0], ids=["mid-line", "on-a-line-boundary"])
    @respx.mock
    async def test_a_longer_member_keeps_its_last_whole_lines_within_max_bytes(self, client, spare):
        from lm_mcp.tools.collectors import get_collector_log_file

        respx.get(f"{_BASE}/setting/collector/collectors/82/logs/82.postcheck.log.zip").mock(
            return_value=httpx.Response(200, content=_zip({"postcheck.log": _POSTCHECK}))
        )
        cap = len(b"".join(_POSTCHECK_LINES[-2:])) + spare

        body = json.loads(
            (await get_collector_log_file(client, 82, "82.postcheck.log.zip", max_bytes=cap))[
                0
            ].text
        )

        assert body["truncated"] is True
        assert body["size"] == len(_POSTCHECK)
        assert body["text"] == b"".join(_POSTCHECK_LINES[-2:]).decode()

    @respx.mock
    async def test_a_last_line_longer_than_max_bytes_keeps_its_end(self, client):
        from lm_mcp.tools.collectors import get_collector_log_file

        respx.get(f"{_BASE}/setting/collector/collectors/82/logs/82.postcheck.log.zip").mock(
            return_value=httpx.Response(200, content=_zip({"postcheck.log": _POSTCHECK}))
        )

        body = json.loads(
            (await get_collector_log_file(client, 82, "82.postcheck.log.zip", max_bytes=30))[0].text
        )

        assert (body["truncated"], body["text"]) == (True, _POSTCHECK[-30:].decode())

    @respx.mock
    async def test_an_archive_with_more_files_names_the_others(self, client):
        from lm_mcp.tools.collectors import get_collector_log_file

        respx.get(f"{_BASE}/setting/collector/collectors/82/logs/two.zip").mock(
            return_value=httpx.Response(
                200, content=_zip({"postcheck.log": _POSTCHECK, "setup.log": b"x\r\n"})
            )
        )

        body = json.loads((await get_collector_log_file(client, 82, "two.zip"))[0].text)

        assert (body["member"], body["other_members"]) == ("postcheck.log", ["setup.log"])

    @respx.mock
    async def test_a_missing_file_is_not_found(self, client):
        from lm_mcp.tools.collectors import get_collector_log_file

        respx.get(f"{_BASE}/setting/collector/collectors/82/logs/no-such-file.log").mock(
            return_value=httpx.Response(404, json=LIVE["log_file_missing_zip"])
        )

        error = envelope(await get_collector_log_file(client, 82, "no-such-file.log"))
        assert error["code"] == "NOT_FOUND"
        assert error["message"].startswith("The file is not found or restrict read-access")

    @respx.mock
    async def test_an_answer_that_is_not_a_zip_is_an_upstream_error(self, client):
        from lm_mcp.tools.collectors import get_collector_log_file

        respx.get(f"{_BASE}/setting/collector/collectors/82/logs/82.postcheck.log.zip").mock(
            return_value=httpx.Response(200, json=LIVE["log_file_82"])
        )

        error = envelope(await get_collector_log_file(client, 82, "82.postcheck.log.zip"))
        assert (error["code"], error["details"]) == (
            "UPSTREAM_ERROR",
            {"exception": "BadZipFile"},
        )


class TestGetCollectorUpgradeHistory:
    """R3.4: the portal's collector upgrade history, one page, rows as the API returns them."""

    @respx.mock
    async def test_pages_the_upgrade_history_path(self, client):
        from lm_mcp.tools.collectors import get_collector_upgrade_history

        route = respx.get(f"{_BASE}/setting/collector/collectors/upgradeHistory").mock(
            return_value=httpx.Response(200, json=LIVE["upgrade_history"])
        )

        body = json.loads((await get_collector_upgrade_history(client, offset=5))[0].text)

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("50", "5")
        assert body == {"total": 0, "count": 0, "offset": 5, "has_more": False, "upgrades": []}


def _writes(monkeypatch, enabled: bool = True) -> None:
    """Set the portal and the write flag a write-gated collector tool reads."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true" if enabled else "false")


_SERVICES_82 = f"{_BASE}/setting/collector/collectors/82/services"


class TestGetCollectorsIsDown:
    """A row's status reads 1 up or down, so it carries isDown as is_down."""

    @respx.mock
    async def test_rows_carry_is_down_from_the_record(self, client):
        from lm_mcp.tools.collectors import get_collectors

        respx.get(f"{_BASE}/setting/collector/collectors").mock(
            return_value=httpx.Response(200, json=OPS["collectors_page"])
        )

        rows = json.loads((await get_collectors(client))[0].text)["collectors"]

        assert [(r["id"], r["status"], r["is_down"]) for r in rows] == [
            (26, 1, True),
            (82, 1, False),
        ]


class TestRunCollectorStatusCheck:
    """R3.4: trigger a status check, then read until a check newer than the last finishes."""

    @pytest.fixture(autouse=True)
    def _no_wait(self, monkeypatch):
        from lm_mcp.tools import collectors

        monkeypatch.setattr(collectors, "STATUS_CHECK_POLL_SECONDS", 0)

    @respx.mock
    async def test_reads_until_a_check_newer_than_the_last_finishes(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.collectors import run_collector_status_check

        order: list[str] = []
        reads = iter(
            [
                OPS["status_check_82_finished"],
                OPS["status_check_82_finished"],
                OPS["status_check_82_running"],
                OPS["status_check_82_finished_new"],
            ]
        )

        def read(request: httpx.Request) -> httpx.Response:
            order.append("read")
            return httpx.Response(200, json=next(reads))

        def trigger(request: httpx.Request) -> httpx.Response:
            order.append("trigger")
            return httpx.Response(200, json=OPS["trigger_82"])

        respx.get(f"{_SERVICES_82}/getStatusCheck").mock(side_effect=read)
        respx.post(f"{_SERVICES_82}/triggerStatusCheck").mock(side_effect=trigger)

        body = json.loads((await run_collector_status_check(client, collector_id=82))[0].text)

        assert order == ["read", "trigger", "read", "read", "read"]
        assert body == {
            "collector_id": 82,
            "triggered": "Collector 82 status check triggered",
            "finished": True,
            "aborted": False,
            "last_triggered": 1794446525370,
            "last_updated": 1794446528850,
            "scripts_total": 44,
            "scripts_finished": 37,
            "scripts_skipped": 7,
            "checks_ok": 6,
            "problems": [],
        }

    @respx.mock
    async def test_a_check_still_running_at_the_budget_is_returned_unfinished(
        self, client, monkeypatch
    ):
        _writes(monkeypatch)
        from lm_mcp.tools import collectors

        monkeypatch.setattr(collectors, "STATUS_CHECK_BUDGET_SECONDS", 0)
        reads = respx.get(f"{_SERVICES_82}/getStatusCheck").mock(
            side_effect=[
                httpx.Response(200, json=OPS["status_check_82_finished"]),
                httpx.Response(200, json=OPS["status_check_82_running"]),
            ]
        )
        respx.post(f"{_SERVICES_82}/triggerStatusCheck").mock(
            return_value=httpx.Response(200, json=OPS["trigger_82"])
        )

        body = json.loads(
            (await collectors.run_collector_status_check(client, collector_id=82))[0].text
        )

        assert reads.call_count == 2
        assert (body["finished"], body["scripts_finished"], body["last_triggered"]) == (
            False,
            0,
            1794446198549,
        )
        assert "get_collector_health" in body["note"]

    @respx.mock
    async def test_a_new_check_that_aborts_returns_with_no_running_note(self, client, monkeypatch):
        """No live check aborted; the running read is marked aborted to stand for one."""
        _writes(monkeypatch)
        from lm_mcp.tools.collectors import run_collector_status_check

        aborted = {**OPS["status_check_82_running"], "aborted": True}
        respx.get(f"{_SERVICES_82}/getStatusCheck").mock(
            side_effect=[
                httpx.Response(200, json=OPS["status_check_82_finished"]),
                httpx.Response(200, json=aborted),
            ]
        )
        respx.post(f"{_SERVICES_82}/triggerStatusCheck").mock(
            return_value=httpx.Response(200, json=OPS["trigger_82"])
        )

        body = json.loads((await run_collector_status_check(client, collector_id=82))[0].text)

        assert (body["aborted"], body["finished"]) == (True, False)
        assert "note" not in body

    @respx.mock
    async def test_no_newer_check_by_the_budget_reads_unfinished_and_says_so(
        self, client, monkeypatch
    ):
        _writes(monkeypatch)
        from lm_mcp.tools import collectors

        monkeypatch.setattr(collectors, "STATUS_CHECK_BUDGET_SECONDS", 0)
        respx.get(f"{_SERVICES_82}/getStatusCheck").mock(
            return_value=httpx.Response(200, json=OPS["status_check_82_finished"])
        )
        respx.post(f"{_SERVICES_82}/triggerStatusCheck").mock(
            return_value=httpx.Response(200, json=OPS["trigger_82"])
        )

        body = json.loads(
            (await collectors.run_collector_status_check(client, collector_id=82))[0].text
        )

        assert body["finished"] is False
        assert body["note"] == collectors.STATUS_CHECK_NOT_STARTED_NOTE

    @respx.mock
    async def test_a_down_collector_refuses_the_trigger(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.collectors import run_collector_status_check

        services = f"{_BASE}/setting/collector/collectors/26/services"
        respx.get(f"{services}/getStatusCheck").mock(
            return_value=httpx.Response(200, json=OPS["status_check_26_down"])
        )
        respx.post(f"{services}/triggerStatusCheck").mock(
            return_value=httpx.Response(400, json=OPS["trigger_26_down"])
        )

        error = envelope(await run_collector_status_check(client, collector_id=26))

        assert error["code"] == "INVALID_REQUEST"
        assert "Collector is down or unreachable" in error["message"]

    @respx.mock
    async def test_refused_with_writes_off(self, client, monkeypatch):
        _writes(monkeypatch, enabled=False)
        from lm_mcp.tools.collectors import run_collector_status_check

        trigger = respx.post(f"{_SERVICES_82}/triggerStatusCheck")

        error = envelope(await run_collector_status_check(client, collector_id=82))

        assert error["code"] == "WRITE_DISABLED"
        assert not trigger.called


# Collector 41's record as the restart reads it. The keys and the size are the live
# record's; the five config files are placeholders, since the live ones carry the
# collector's credentials. A restart sent with {} answered job 760 and reset 41's size
# from Large to Custom (4G); one sent with these fields back changed nothing (probe
# 2026-11-11).
_COLLECTOR_41 = {
    "id": 41,
    "hostname": "lm-container-argus-0",
    "isDown": False,
    "collectorSize": "large",
    "collectorConf": "agent.conf text",
    "sbproxyConf": "sbproxy.conf text",
    "wrapperConf": "wrapper.conf text",
    "watchdogConf": "watchdog.conf text",
    "websiteConf": "website.conf text",
}


class TestRestartCollector:
    """R3.4: restart a collector through services/restart, sending its own size and config
    files back so the restart changes neither."""

    @respx.mock
    async def test_sends_the_collectors_own_size_and_config_back_and_returns_the_job(
        self, client, monkeypatch
    ):
        _writes(monkeypatch)
        from lm_mcp.tools.collectors import restart_collector

        respx.get(f"{_BASE}/setting/collector/collectors/41").mock(
            return_value=httpx.Response(200, json=_COLLECTOR_41)
        )
        route = respx.post(f"{_BASE}/setting/collector/collectors/41/services/restart").mock(
            return_value=httpx.Response(200, json=760)
        )

        body = json.loads((await restart_collector(client, collector_id=41))[0].text)

        assert json.loads(route.calls.last.request.content) == {
            key: _COLLECTOR_41[key]
            for key in (
                "collectorSize",
                "collectorConf",
                "sbproxyConf",
                "wrapperConf",
                "watchdogConf",
                "websiteConf",
            )
        }
        assert body == {"collector_id": 41, "restart_job_id": 760, "collector_size": "large"}

    @respx.mock
    async def test_a_record_without_a_size_is_refused_before_the_restart(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.collectors import restart_collector

        record = {key: value for key, value in _COLLECTOR_41.items() if key != "collectorSize"}
        respx.get(f"{_BASE}/setting/collector/collectors/41").mock(
            return_value=httpx.Response(200, json=record)
        )
        route = respx.post(f"{_BASE}/setting/collector/collectors/41/services/restart")

        error = envelope(await restart_collector(client, collector_id=41))

        assert error["code"] == "REJECTED_BY_TOOL"
        assert "size" in error["message"]
        assert not route.called

    @respx.mock
    async def test_refused_with_writes_off(self, client, monkeypatch):
        _writes(monkeypatch, enabled=False)
        from lm_mcp.tools.collectors import restart_collector

        route = respx.post(f"{_SERVICES_82}/restart")

        error = envelope(await restart_collector(client, collector_id=82))

        assert error["code"] == "WRITE_DISABLED"
        assert not route.called


class TestAcknowledgeCollectorDown:
    """R3.4: acknowledge a down collector's alert with a comment through ackdown."""

    @respx.mock
    async def test_posts_the_comment_and_reports_the_acknowledgement(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.collectors import acknowledge_collector_down

        route = respx.post(f"{_BASE}/setting/collector/collectors/26/ackdown").mock(
            return_value=httpx.Response(200, json=OPS["ackdown_26"])
        )

        body = json.loads(
            (await acknowledge_collector_down(client, 26, comment="lm-mcp Step 65 probe"))[0].text
        )

        assert json.loads(route.calls.last.request.content) == {"comment": "lm-mcp Step 65 probe"}
        assert body == {"collector_id": 26, "acknowledged": True, "comment": "lm-mcp Step 65 probe"}

    @respx.mock
    async def test_an_up_collector_refuses_the_acknowledgement(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.collectors import acknowledge_collector_down

        respx.post(f"{_BASE}/setting/collector/collectors/82/ackdown").mock(
            return_value=httpx.Response(400, json=OPS["ackdown_82_up"])
        )

        error = envelope(await acknowledge_collector_down(client, 82, comment="x"))

        assert error["code"] == "INVALID_REQUEST"
        assert "The agent is alive" in error["message"]

    @respx.mock
    async def test_refused_with_writes_off(self, client, monkeypatch):
        _writes(monkeypatch, enabled=False)
        from lm_mcp.tools.collectors import acknowledge_collector_down

        route = respx.post(f"{_BASE}/setting/collector/collectors/26/ackdown")

        error = envelope(await acknowledge_collector_down(client, 26, comment="x"))

        assert error["code"] == "WRITE_DISABLED"
        assert not route.called


_DOWN_26_EVIDENCE = {
    "status_check": {
        "finished": True,
        "aborted": False,
        "last_triggered": 1794446328793,
        "last_updated": 1794446328793,
        "scripts_total": 44,
        "scripts_finished": 36,
        "scripts_skipped": 8,
        "checks_ok": 0,
        "problems": [
            {
                "name": "module.Collector",
                "status": "ERROR",
                "detail": OPS["status_check_26_down"]["checkPoints"][0]["detail"],
            },
            {
                "name": "module.Watchdog",
                "status": "WARN",
                "detail": OPS["status_check_26_down"]["checkPoints"][1]["detail"],
            },
        ],
    },
    "recent_events": [
        {
            "id": "qzGSS6euRTWf6BWUjh04QA",
            "reported_on": 1793727768,
            "event_code": 8,
            "message": "The collector is down or unreachable",
            "collector_build": "39200",
            "collector_platform": "linux",
        },
        {
            "id": "kPCwInVFSiaWQbAo58B4Jw",
            "reported_on": 1793678241,
            "event_code": 4,
            "message": "Agent successfully restarted.",
            "collector_build": "39200",
            "collector_platform": "linux",
        },
    ],
}


class TestCollectorHealthEvidence:
    """R3.4: get_collector_health cites each collector's latest status check and recent
    events as evidence, read once each: for one collector asked by id, and in a list for
    the collectors not known to be up."""

    @respx.mock
    async def test_a_down_collector_carries_its_status_check_and_recent_events(self, client):
        from lm_mcp.tools.collectors import get_collector_health

        respx.get(f"{_BASE}/setting/collector/collectors/26").mock(
            return_value=httpx.Response(200, json=OPS["collector_26"])
        )
        respx.get(f"{_BASE}/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 3})
        )
        events_page = {"total": -6, "items": LIVE["events_26"]["items"][:2]}
        status, events = _mock_evidence("26", OPS["status_check_26_down"], events_page)

        body = json.loads((await get_collector_health(client, collector_id=26))[0].text)

        assert (status.call_count, events.call_count) == (1, 1)
        assert events.calls.last.request.url.params["size"] == "5"
        record = body["collectors"][0]
        assert record["is_down"] is True
        assert record["evidence"] == _DOWN_26_EVIDENCE
        assert "evidence_warning" not in record

    @respx.mock
    async def test_one_up_collector_asked_by_id_carries_evidence_too(self, client):
        from lm_mcp.tools.collectors import get_collector_health

        respx.get(f"{_BASE}/setting/collector/collectors/82").mock(
            return_value=httpx.Response(200, json=OPS["collectors_page"]["items"][1])
        )
        respx.get(f"{_BASE}/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        _mock_evidence("82")

        record = json.loads((await get_collector_health(client, collector_id=82))[0].text)[
            "collectors"
        ][0]

        assert record["evidence"]["status_check"]["checks_ok"] == 6
        assert record["evidence"]["status_check"]["problems"] == []
        assert record["evidence"]["recent_events"] == []

    @respx.mock
    async def test_a_list_reads_evidence_only_for_collectors_not_known_up(self, client):
        from lm_mcp.tools.collectors import get_collector_health

        respx.get(f"{_BASE}/setting/collector/collectors").mock(
            return_value=httpx.Response(200, json=OPS["collectors_page"])
        )
        respx.get(f"{_BASE}/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        down = _mock_evidence("26", OPS["status_check_26_down"])
        up = _mock_evidence("82")

        records = json.loads((await get_collector_health(client))[0].text)["collectors"]

        assert [r["id"] for r in records] == [26, 82]
        assert records[0]["evidence"]["status_check"]["checks_ok"] == 0
        assert "evidence" not in records[1]
        assert [route.call_count for route in (*down, *up)] == [1, 1, 0, 0]

    @respx.mock
    async def test_a_failed_read_leaves_its_part_null_with_a_warning(self, client, caplog):
        from lm_mcp.tools.collectors import get_collector_health

        respx.get(f"{_BASE}/setting/collector/collectors/26").mock(
            return_value=httpx.Response(200, json=OPS["collector_26"])
        )
        respx.get(f"{_BASE}/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 3})
        )
        status, events = _mock_evidence("26")
        status.mock(return_value=httpx.Response(403, json={"errorMessage": "Permission denied"}))

        record = json.loads((await get_collector_health(client, collector_id=26))[0].text)[
            "collectors"
        ][0]

        assert record["evidence"] == {"status_check": None, "recent_events": []}
        assert record["evidence_warning"].startswith("Status check read failed:")
        assert events.call_count == 1
        (logged,) = [r for r in caplog.records if r.name == "lm_mcp.tools.collectors"]
        assert (logged.levelname, logged.getMessage(), logged.exc_info is not None) == (
            "WARNING",
            "collector 26: status check read failed",
            True,
        )


# (handler name, endpoint path, extra required arguments)
_COLLECTORS_LISTS = [
    ("get_collectors", "/setting/collector/collectors", {}),
    ("get_collector_groups", "/setting/collector/groups", {}),
    ("get_collector_events", "/setting/collector/collectors/26/events", {"collector_id": 26}),
    ("get_collector_log_files", "/setting/collector/collectors/82/logs", {"collector_id": 82}),
    ("get_collector_upgrade_history", "/setting/collector/collectors/upgradeHistory", {}),
]


class TestCollectorListPaging:
    """R2.5: the collector list tools declare offset, send it, and read a negative total as more."""

    @pytest.mark.parametrize(("name", "path", "kwargs"), _COLLECTORS_LISTS)
    @respx.mock
    async def test_offset_is_declared_and_sent(self, client, name, path, kwargs):
        from lm_mcp.tools import collectors

        await assert_offset_declared_and_sent(client, getattr(collectors, name), path, kwargs)

    @pytest.mark.parametrize(("name", "path", "kwargs"), _COLLECTORS_LISTS)
    @respx.mock
    async def test_negative_total_reads_as_more(self, client, name, path, kwargs):
        from lm_mcp.tools import collectors

        await assert_negative_total_reads_as_more(client, getattr(collectors, name), path, kwargs)
