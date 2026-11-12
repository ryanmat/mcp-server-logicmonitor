# Description: Tests for the Step 68 reads: datasource devices, unmonitored devices,
# Description: the website checkpoint locations and the device delta.

import json
from pathlib import Path

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from tests.envelope import envelope
from tests.list_paging import assert_negative_total_reads_as_more, assert_offset_declared_and_sent

# Answers of a sandbox portal at X-Version 3 on 2026-11-12 (Step 68 probe), each with its
# request, parameters, status and body. Cuts: datasource_devices_1613 keeps the first 2 of its
# 10 rows under the total sent; each delta row keeps the first 2 entries of each of its four
# property lists, a cut that also leaves out the collector's internal hostname and an inherited
# property naming a private host. Replaced values: a private address (192.0.2.10) and the portal
# name (sandbox). The sandbox lists no unmonitored device, so
# unmonitored_swagger_item is the swagger UnmonitoredDevices definition's properties with
# placeholder values of the declared types, not a live row.
LIVE = json.loads((Path(__file__).parent.parent / "fixtures" / "inventory_reads.json").read_text())
_BASE = "https://test.logicmonitor.com/santaba/rest"


def _answer(name: str) -> httpx.Response:
    """The fixture entry's status and body as an httpx response."""
    return httpx.Response(LIVE[name]["status"], json=LIVE[name]["body"])


@pytest.fixture
def client():
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(base_url=_BASE, auth=BearerAuth("test-token"), timeout=30)


class TestGetDatasourceDevices:
    """R3.6: the devices a datasource applies to, each with up to 10 of its instances."""

    @respx.mock
    async def test_projects_each_device_with_its_instances(self, client):
        from lm_mcp.tools.datasources import get_datasource_devices

        route = respx.get(f"{_BASE}/setting/datasources/1679/devices").mock(
            return_value=_answer("datasource_devices_1679")
        )

        body = json.loads(
            (await get_datasource_devices(client, datasource_id=1679, limit=3))[0].text
        )

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("3", "0")
        assert (body["datasource_id"], body["total"], body["count"]) == (1679, 875, 3)
        assert body["devices"][0] == {
            "device_id": 1786,
            "name": "rm-aws-ubuntu",
            "host": "127.0.0.1",
            "instances": [{"id": 370242186, "name": "Ping", "alias": ""}],
            "more_instances": False,
            "has_active_instance": True,
        }

    @respx.mock
    async def test_more_instances_reads_the_portals_has_more(self, client):
        from lm_mcp.tools.datasources import get_datasource_devices

        respx.get(f"{_BASE}/setting/datasources/1613/devices").mock(
            return_value=_answer("datasource_devices_1613")
        )

        body = json.loads(
            (await get_datasource_devices(client, datasource_id=1613, limit=10))[0].text
        )

        first = body["devices"][0]
        assert (first["device_id"], len(first["instances"]), first["more_instances"]) == (
            89818,
            10,
            True,
        )

    @respx.mock
    async def test_name_filter_matches_the_display_name(self, client):
        from lm_mcp.tools.datasources import get_datasource_devices

        route = respx.get(f"{_BASE}/setting/datasources/1679/devices").mock(
            return_value=_answer("datasource_devices_1679_filter")
        )

        body = json.loads(
            (
                await get_datasource_devices(
                    client, datasource_id=1679, name_filter="ubuntu", limit=3
                )
            )[0].text
        )

        assert route.calls.last.request.url.params["filter"] == 'displayName~"ubuntu"'
        assert [d["device_id"] for d in body["devices"]] == [1786]

    @respx.mock
    async def test_an_unknown_datasource_is_not_found(self, client):
        from lm_mcp.tools.datasources import get_datasource_devices

        respx.get(f"{_BASE}/setting/datasources/99999999/devices").mock(
            return_value=_answer("datasource_missing")
        )

        error = envelope(await get_datasource_devices(client, datasource_id=99999999))

        assert error["code"] == "NOT_FOUND"


class TestGetUnmonitoredDevices:
    """R3.6: the unmonitored device list pages through as the API returns its rows."""

    @respx.mock
    async def test_an_empty_list_is_an_empty_page(self, client):
        from lm_mcp.tools.devices import get_unmonitored_devices

        route = respx.get(f"{_BASE}/device/unmonitoreddevices").mock(
            return_value=_answer("unmonitored_empty")
        )

        body = json.loads((await get_unmonitored_devices(client, limit=3))[0].text)

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("3", "0")
        assert (body["total"], body["has_more"], body["devices"]) == (0, False, [])

    @respx.mock
    async def test_rows_are_returned_as_the_api_sends_them(self, client):
        from lm_mcp.tools.devices import get_unmonitored_devices

        item = LIVE["unmonitored_swagger_item"]["item"]
        respx.get(f"{_BASE}/device/unmonitoreddevices").mock(
            return_value=httpx.Response(200, json={"total": 1, "items": [item]})
        )

        body = json.loads((await get_unmonitored_devices(client))[0].text)

        assert body["devices"] == [item]


class TestGetWebsiteCheckpoints:
    """R3.6: the portal's website checkpoint locations; each id is the smg_id a website's
    checkpoints carry."""

    @respx.mock
    async def test_projects_each_location(self, client):
        from lm_mcp.tools.websites import get_website_checkpoints

        respx.get(f"{_BASE}/website/smcheckpoints").mock(return_value=_answer("checkpoints"))

        body = json.loads((await get_website_checkpoints(client))[0].text)

        assert (body["total"], body["count"]) == (5, 5)
        assert body["checkpoints"][0] == {
            "id": 2,
            "name": "US - Washington DC",
            "geo_info": "US - Washington DC",
            "description": "This is DC7 group",
            "display_priority": 60,
            "enabled_in_root": True,
        }

    @respx.mock
    async def test_pages(self, client):
        from lm_mcp.tools.websites import get_website_checkpoints

        route = respx.get(f"{_BASE}/website/smcheckpoints").mock(
            return_value=_answer("checkpoints_size2_offset1")
        )

        body = json.loads((await get_website_checkpoints(client, limit=2, offset=1))[0].text)

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("2", "1")
        assert [c["id"] for c in body["checkpoints"]] == [4, 3]
        assert body["has_more"] is True


class TestGetDeviceDelta:
    """R3.6: a read without delta_id lists the matching devices and starts a delta; a read
    with it lists the devices changed since that delta started."""

    @respx.mock
    async def test_a_read_without_an_id_starts_a_delta_and_returns_its_id(self, client):
        from lm_mcp.tools.devices import get_device_delta

        route = respx.get(f"{_BASE}/device/devices/delta").mock(
            return_value=_answer("delta_first_page")
        )

        body = json.loads((await get_device_delta(client, limit=3))[0].text)

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("3", "0")
        assert body["delta_id"] == "a11654364568495ba22ffa4c4c61a259"
        assert (body["total"], body["count"], body["has_more"]) == (5847, 3, True)
        assert body["devices"][0] == {
            "id": 1786,
            "name": "rm-aws-ubuntu",
            "status": "dead-collector",
            "collector_id": 26,
            "change": "",
        }

    @respx.mock
    async def test_a_read_with_an_id_lists_the_changed_devices(self, client):
        from lm_mcp.tools.devices import get_device_delta

        by_id = respx.get(f"{_BASE}/device/devices/delta/a11654364568495ba22ffa4c4c61a259").mock(
            return_value=_answer("delta_by_id_after_change")
        )
        start = respx.get(f"{_BASE}/device/devices/delta")

        body = json.loads(
            (await get_device_delta(client, delta_id="a11654364568495ba22ffa4c4c61a259"))[0].text
        )

        assert by_id.called and not start.called
        assert body["delta_id"] == "a11654364568495ba22ffa4c4c61a259"
        assert [(d["id"], d["change"]) for d in body["devices"]] == [
            (1786, "updated"),
            (451886, "updated"),
        ]

    @respx.mock
    async def test_a_read_with_an_id_pages(self, client):
        from lm_mcp.tools.devices import get_device_delta

        route = respx.get(f"{_BASE}/device/devices/delta/a11654364568495ba22ffa4c4c61a259").mock(
            return_value=_answer("delta_by_id_size1_offset1")
        )

        body = json.loads(
            (
                await get_device_delta(
                    client, delta_id="a11654364568495ba22ffa4c4c61a259", limit=1, offset=1
                )
            )[0].text
        )

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("1", "1")
        assert (body["total"], body["has_more"]) == (6, True)
        assert [d["id"] for d in body["devices"]] == [451843]

    @respx.mock
    async def test_name_filter_goes_on_a_read_without_an_id(self, client):
        from lm_mcp.tools.devices import get_device_delta

        route = respx.get(f"{_BASE}/device/devices/delta").mock(
            return_value=_answer("delta_first_page")
        )

        await get_device_delta(client, name_filter="rm-aws-ubuntu", limit=3)

        assert route.calls.last.request.url.params["filter"] == 'displayName~"rm-aws-ubuntu"'

    @respx.mock
    async def test_name_filter_with_an_id_is_refused_before_any_call(self, client):
        from lm_mcp.tools.devices import get_device_delta

        route = respx.get(url__regex=rf"^{_BASE}/device/devices/delta.*")

        error = envelope(await get_device_delta(client, delta_id="a1b2", name_filter="web"))

        assert error["code"] == "INVALID_REQUEST"
        assert not route.called

    @respx.mock
    async def test_an_unknown_id_is_not_found(self, client):
        from lm_mcp.tools.devices import get_device_delta

        respx.get(f"{_BASE}/device/devices/delta/notadelta").mock(
            return_value=_answer("delta_unknown_id")
        )

        error = envelope(await get_device_delta(client, delta_id="notadelta"))

        assert error["code"] == "NOT_FOUND"


# (handler module, handler name, endpoint path, required arguments)
_STEP_68_LISTS = [
    (
        "datasources",
        "get_datasource_devices",
        "/setting/datasources/7/devices",
        {"datasource_id": 7},
    ),
    ("devices", "get_unmonitored_devices", "/device/unmonitoreddevices", {}),
    ("websites", "get_website_checkpoints", "/website/smcheckpoints", {}),
    ("devices", "get_device_delta", "/device/devices/delta", {}),
]


class TestStep68Paging:
    """R2.5: each declares offset, sends it, and reads a negative total as more."""

    @pytest.mark.parametrize(("module", "name", "path", "kwargs"), _STEP_68_LISTS)
    @respx.mock
    async def test_offset_is_declared_and_sent(self, client, module, name, path, kwargs):
        import importlib

        handler = getattr(importlib.import_module(f"lm_mcp.tools.{module}"), name)
        await assert_offset_declared_and_sent(client, handler, path, kwargs)

    @pytest.mark.parametrize(("module", "name", "path", "kwargs"), _STEP_68_LISTS)
    @respx.mock
    async def test_negative_total_reads_as_more(self, client, module, name, path, kwargs):
        import importlib

        handler = getattr(importlib.import_module(f"lm_mcp.tools.{module}"), name)
        await assert_negative_total_reads_as_more(client, handler, path, kwargs)
