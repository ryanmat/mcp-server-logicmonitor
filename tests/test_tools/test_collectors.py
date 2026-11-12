# Description: Tests for collector MCP tools.
# Description: Validates collector read, update, and delete functions.

import io
import json
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
