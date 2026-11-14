# Description: Tests for resource/property management MCP tools.
# Description: Validates the device and device group property reads, writes and deletes.

import json
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


# Rows of GET /device/devices/{id}/properties as a live portal returned them on 2026-11-13,
# one of each kind seen: an automatic property that lists a property rule, a custom one, an
# inherited one, a system one that lists four groups, and a system one with no
# source. A row has no "inherit" key; "type" says custom, inherit, auto or system.
DEVICE_PROPERTY_ROWS = [
    {
        "type": "auto",
        "name": "auto.lm.age",
        "value": "0.0004976852",
        "inheritList": [
            {"fullpath": "Device_BasicInfo", "id": 60, "value": "", "type": "propertyRule"}
        ],
    },
    {
        "type": "custom",
        "name": "system.categories",
        "value": "",
        "inheritList": [{"fullpath": "", "id": 1, "value": "", "type": "group"}],
    },
    {
        "type": "inherit",
        "name": "netapp.ssl",
        "value": "true",
        "inheritList": [{"fullpath": "", "id": 1, "value": "true", "type": "group"}],
    },
    {
        "type": "system",
        "name": "system.deviceGroupId",
        "value": "16,120",
        "inheritList": [
            {
                "fullpath": "Devices by Type/Minimal Monitoring",
                "id": 16,
                "value": "16",
                "type": "group",
            },
            {"fullpath": "Devices by Type", "id": 2, "value": "2", "type": "group"},
            {"fullpath": "All Devices", "id": 120, "value": "120", "type": "group"},
            {"fullpath": "", "id": 1, "value": "1", "type": "group"},
        ],
    },
    {"type": "system", "name": "system.enablenetflow", "value": "false", "inheritList": []},
]


class TestGetDeviceProperties:
    """Tests for get_device_properties tool."""

    @respx.mock
    async def test_get_device_properties_returns_list(self, client):
        """get_device_properties returns properly formatted property list."""
        from lm_mcp.tools.resources import get_device_properties

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/100/properties").mock(
            return_value=httpx.Response(
                200,
                json={"items": DEVICE_PROPERTY_ROWS, "total": 5, "searchId": None, "isMin": False},
            )
        )

        result = await get_device_properties(client, device_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 100
        assert data["total"] == 5
        assert data["properties"] == [
            {
                "name": "auto.lm.age",
                "value": "0.0004976852",
                "type": "auto",
                "sources": [
                    {"type": "propertyRule", "id": 60, "path": "Device_BasicInfo", "value": ""}
                ],
            },
            {
                "name": "system.categories",
                "value": "",
                "type": "custom",
                "sources": [{"type": "group", "id": 1, "path": "", "value": ""}],
            },
            {
                "name": "netapp.ssl",
                "value": "true",
                "type": "inherit",
                "sources": [{"type": "group", "id": 1, "path": "", "value": "true"}],
            },
            {
                "name": "system.deviceGroupId",
                "value": "16,120",
                "type": "system",
                "sources": [
                    {
                        "type": "group",
                        "id": 16,
                        "path": "Devices by Type/Minimal Monitoring",
                        "value": "16",
                    },
                    {"type": "group", "id": 2, "path": "Devices by Type", "value": "2"},
                    {"type": "group", "id": 120, "path": "All Devices", "value": "120"},
                    {"type": "group", "id": 1, "path": "", "value": "1"},
                ],
            },
            {"name": "system.enablenetflow", "value": "false", "type": "system", "sources": []},
        ]

    @respx.mock
    async def test_get_device_properties_with_name_filter(self, client):
        """get_device_properties passes name filter to API."""
        from lm_mcp.tools.resources import get_device_properties

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_device_properties(client, device_id=100, name_filter="system.*")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_device_properties_handles_error(self, client):
        """get_device_properties handles 404 error gracefully."""
        from lm_mcp.tools.resources import get_device_properties

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/999/properties").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Device not found"})
        )

        result = await get_device_properties(client, device_id=999)

        assert is_error_result(result)


class TestGetDeviceProperty:
    """Tests for get_device_property tool."""

    @respx.mock
    async def test_get_device_property_returns_details(self, client):
        """get_device_property returns property details."""
        from lm_mcp.tools.resources import get_device_property

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties/netapp.ssl"
        ).mock(
            return_value=httpx.Response(
                200,
                json=DEVICE_PROPERTY_ROWS[2],
            )
        )

        result = await get_device_property(client, device_id=100, property_name="netapp.ssl")

        assert len(result) == 1
        assert json.loads(result[0].text) == {
            "device_id": 100,
            "name": "netapp.ssl",
            "value": "true",
            "type": "inherit",
            "sources": [{"type": "group", "id": 1, "path": "", "value": "true"}],
        }

    @respx.mock
    async def test_get_device_property_not_found(self, client):
        """get_device_property returns error for missing property."""
        from lm_mcp.tools.resources import get_device_property

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties/nonexistent"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Property not found"}))

        result = await get_device_property(client, device_id=100, property_name="nonexistent")

        assert is_error_result(result)


class TestUpdateDeviceProperty:
    """Tests for update_device_property tool."""

    @respx.mock
    async def test_update_device_property_blocked_by_default(self, client, monkeypatch):
        """update_device_property blocked when writes disabled."""
        from lm_mcp.tools.resources import update_device_property

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_device_property(
            client, device_id=100, property_name="location", property_value="US-West"
        )

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_update_device_property_succeeds_when_enabled(self, client, monkeypatch):
        """update_device_property works when writes enabled."""
        from lm_mcp.tools.resources import update_device_property

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.put(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties/location"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "location",
                    "value": "US-West",
                    "type": "custom",
                },
            )
        )

        result = await update_device_property(
            client, device_id=100, property_name="location", property_value="US-West"
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["device_id"] == 100
        assert data["property"]["name"] == "location"
        assert data["property"]["value"] == "US-West"

    @respx.mock
    async def test_update_device_property_creates_on_404(self, client, monkeypatch):
        """update_device_property falls back to POST when PUT returns 404."""
        from lm_mcp.tools.resources import update_device_property

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        # PUT returns 404 (property doesn't exist yet)
        respx.put(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties/new.prop"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "No such property"}))

        # POST creates it
        respx.post("https://test.logicmonitor.com/santaba/rest/device/devices/100/properties").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "new.prop",
                    "value": "hello",
                    "type": "custom",
                },
            )
        )

        result = await update_device_property(
            client, device_id=100, property_name="new.prop", property_value="hello"
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["property"]["name"] == "new.prop"
        assert data["property"]["value"] == "hello"


# Answers of a sandbox portal at X-Version 3 on 2026-11-12. Group 3339 is a
# throwaway group under the root, 3340 its child and 3341 the child's child; 3343 is a child of
# another throwaway group, 3342, whose lmmcp.order it inherits. Its property page
# held six rows; one, an inherited endpoint URL naming a private host, is cut, under the total
# the portal sent. Each entry keeps the request, the status and the body as read.
LIVE = json.loads((Path(__file__).parent.parent / "fixtures" / "property_ops.json").read_text())
_BASE = "https://test.logicmonitor.com/santaba/rest"
_GROUP_3339 = f"{_BASE}/device/groups/3339/properties"


def _answer(name: str) -> httpx.Response:
    """The fixture entry's status and body as an httpx response."""
    return httpx.Response(LIVE[name]["status"], json=LIVE[name]["body"])


def _writes(monkeypatch, enabled: bool = True) -> None:
    """Set the portal and the write flag a write-gated property tool reads."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true" if enabled else "false")


class TestGetDeviceGroupProperties:
    """R3.6: a group's properties page through its properties path; one name reads alone."""

    @respx.mock
    async def test_projects_each_row_with_the_ancestors_holding_its_name(self, client):
        from lm_mcp.tools.resources import get_device_group_properties

        route = respx.get(_GROUP_3339).mock(return_value=_answer("group_properties_3339"))

        body = json.loads((await get_device_group_properties(client, group_id=3339))[0].text)

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("100", "0")
        assert "filter" not in params
        assert (body["group_id"], body["total"], body["count"]) == (3339, 6, 5)
        assert body["properties"][:3] == [
            {
                "name": "netapp.ssl",
                "value": "true",
                "type": "inherit",
                "ancestors": [{"group_id": 1, "path": "", "value": "true"}],
            },
            {"name": "lmmcp.seed", "value": "seed", "type": "custom", "ancestors": []},
            {
                "name": "system.deviceGroupId",
                "value": "3339",
                "type": "system",
                "ancestors": [{"group_id": 1, "path": "", "value": "1"}],
            },
        ]

    @respx.mock
    async def test_ancestors_come_nearest_first_and_the_value_is_the_nearest(self, client):
        from lm_mcp.tools.resources import get_device_group_properties

        respx.get(f"{_BASE}/device/groups/3341/properties").mock(
            return_value=_answer("grandchild_properties_3341")
        )

        body = json.loads((await get_device_group_properties(client, group_id=3341))[0].text)

        order = next(row for row in body["properties"] if row["name"] == "lmmcp.order")
        assert order == {
            "name": "lmmcp.order",
            "value": "child",
            "type": "inherit",
            "ancestors": [
                {
                    "group_id": 3340,
                    "path": "lm-mcp-step67-probe/lm-mcp-step67-child",
                    "value": "child",
                },
                {"group_id": 3339, "path": "lm-mcp-step67-probe", "value": "parent"},
            ],
        }

    @respx.mock
    async def test_pages_and_filters_by_name(self, client):
        from lm_mcp.tools.resources import get_device_group_properties

        route = respx.get(_GROUP_3339).mock(
            return_value=_answer("group_properties_3339_size2_offset1")
        )

        body = json.loads(
            (
                await get_device_group_properties(
                    client, group_id=3339, name_filter="lmmcp", limit=2, offset=1
                )
            )[0].text
        )

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"], params["filter"]) == ("2", "1", 'name~"lmmcp"')
        assert (body["count"], body["offset"], body["has_more"]) == (2, 1, True)

    @respx.mock
    async def test_property_name_reads_that_one_property(self, client):
        from lm_mcp.tools.resources import get_device_group_properties

        one = respx.get(f"{_BASE}/device/groups/3341/properties/lmmcp.order").mock(
            return_value=_answer("grandchild_property_order")
        )
        page = respx.get(f"{_BASE}/device/groups/3341/properties")

        body = json.loads(
            (await get_device_group_properties(client, group_id=3341, property_name="lmmcp.order"))[
                0
            ].text
        )

        assert one.called and not page.called
        assert body == {
            "group_id": 3341,
            "name": "lmmcp.order",
            "value": "child",
            "type": "inherit",
            "ancestors": [
                {
                    "group_id": 3340,
                    "path": "lm-mcp-step67-probe/lm-mcp-step67-child",
                    "value": "child",
                },
                {"group_id": 3339, "path": "lm-mcp-step67-probe", "value": "parent"},
            ],
        }

    @respx.mock
    async def test_a_missing_name_and_a_missing_group_are_not_found(self, client):
        from lm_mcp.tools.resources import get_device_group_properties

        respx.get(f"{_GROUP_3339}/lmmcp.nothere").mock(
            return_value=_answer("group_property_missing")
        )
        respx.get(f"{_BASE}/device/groups/99999999/properties").mock(
            return_value=_answer("group_missing")
        )

        name = envelope(
            await get_device_group_properties(client, group_id=3339, property_name="lmmcp.nothere")
        )
        group = envelope(await get_device_group_properties(client, group_id=99999999))

        assert name["code"] == group["code"] == "NOT_FOUND"
        assert "lmmcp.nothere" in name["message"]

    @respx.mock
    async def test_offset_is_declared_and_sent(self, client):
        from lm_mcp.tools.resources import get_device_group_properties

        await assert_offset_declared_and_sent(
            client,
            get_device_group_properties,
            "/device/groups/3339/properties",
            {"group_id": 3339},
        )

    @respx.mock
    async def test_negative_total_reads_as_more(self, client):
        from lm_mcp.tools.resources import get_device_group_properties

        await assert_negative_total_reads_as_more(
            client,
            get_device_group_properties,
            "/device/groups/3339/properties",
            {"group_id": 3339},
        )


class TestUpdateDeviceGroupProperty:
    """R3.6: a group property is set by PUT, and created by POST when the group holds no
    value of its own under that name."""

    @respx.mock
    async def test_sets_the_groups_own_value(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.resources import update_device_group_property

        put = respx.put(f"{_GROUP_3339}/lmmcp.probe").mock(
            return_value=_answer("group_property_put")
        )
        post = respx.post(_GROUP_3339)

        body = json.loads(
            (
                await update_device_group_property(
                    client, group_id=3339, property_name="lmmcp.probe", property_value="b"
                )
            )[0].text
        )

        assert json.loads(put.calls.last.request.content) == {"value": "b"}
        assert not post.called
        assert body == {
            "success": True,
            "group_id": 3339,
            "property": {"name": "lmmcp.probe", "value": "b", "type": "custom"},
        }

    @respx.mock
    async def test_an_inherited_name_gets_its_own_value_by_post(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.resources import update_device_group_property

        put = respx.put(f"{_BASE}/device/groups/3343/properties/lmmcp.order").mock(
            return_value=_answer("child_put_inherited")
        )
        post = respx.post(f"{_BASE}/device/groups/3343/properties").mock(
            return_value=_answer("child_post_inherited")
        )

        body = json.loads(
            (
                await update_device_group_property(
                    client, group_id=3343, property_name="lmmcp.order", property_value="x"
                )
            )[0].text
        )

        assert put.called
        assert json.loads(post.calls.last.request.content) == {"name": "lmmcp.order", "value": "x"}
        assert body["property"] == {"name": "lmmcp.order", "value": "x", "type": "custom"}

    @respx.mock
    async def test_a_system_property_is_refused(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.resources import update_device_group_property

        respx.put(f"{_GROUP_3339}/system.groupType").mock(
            return_value=_answer("group_property_put_system")
        )
        post = respx.post(_GROUP_3339)

        error = envelope(
            await update_device_group_property(
                client, group_id=3339, property_name="system.groupType", property_value="x"
            )
        )

        assert error["code"] == "INVALID_REQUEST"
        assert not post.called

    @respx.mock
    async def test_refused_with_writes_off(self, client, monkeypatch):
        _writes(monkeypatch, enabled=False)
        from lm_mcp.tools.resources import update_device_group_property

        put = respx.put(f"{_GROUP_3339}/lmmcp.probe")

        error = envelope(
            await update_device_group_property(
                client, group_id=3339, property_name="lmmcp.probe", property_value="b"
            )
        )

        assert error["code"] == "WRITE_DISABLED"
        assert not put.called


class TestDeleteDeviceGroupProperty:
    """R3.6: a group's own property is deleted; an inherited or system one is not."""

    @respx.mock
    async def test_deletes_the_groups_own_property(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.resources import delete_device_group_property

        route = respx.delete(f"{_GROUP_3339}/lmmcp.probe").mock(
            return_value=_answer("group_property_delete")
        )

        body = json.loads(
            (
                await delete_device_group_property(
                    client, group_id=3339, property_name="lmmcp.probe"
                )
            )[0].text
        )

        assert route.called
        assert body == {"success": True, "group_id": 3339, "deleted": "lmmcp.probe"}

    @respx.mock
    async def test_an_inherited_name_is_not_found_and_a_system_one_refused(
        self, client, monkeypatch
    ):
        _writes(monkeypatch)
        from lm_mcp.tools.resources import delete_device_group_property

        respx.delete(f"{_BASE}/device/groups/3341/properties/lmmcp.order").mock(
            return_value=_answer("grandchild_delete_inherited")
        )
        respx.delete(f"{_GROUP_3339}/system.groupType").mock(
            return_value=_answer("group_property_delete_system")
        )

        inherited = envelope(
            await delete_device_group_property(client, group_id=3341, property_name="lmmcp.order")
        )
        system = envelope(
            await delete_device_group_property(
                client, group_id=3339, property_name="system.groupType"
            )
        )

        assert inherited["code"] == "NOT_FOUND"
        assert "own property" in inherited["message"]
        assert system["code"] == "INVALID_REQUEST"
        assert "not allowed to delete" in system["message"]

    @respx.mock
    async def test_refused_with_writes_off(self, client, monkeypatch):
        _writes(monkeypatch, enabled=False)
        from lm_mcp.tools.resources import delete_device_group_property

        route = respx.delete(f"{_GROUP_3339}/lmmcp.probe")

        error = envelope(
            await delete_device_group_property(client, group_id=3339, property_name="lmmcp.probe")
        )

        assert error["code"] == "WRITE_DISABLED"
        assert not route.called


class TestDeleteDeviceProperty:
    """R3.6: a device's own property is deleted; an inherited or system one is not."""

    @respx.mock
    async def test_deletes_the_devices_own_property(self, client, monkeypatch):
        _writes(monkeypatch)
        from lm_mcp.tools.resources import delete_device_property

        route = respx.delete(f"{_BASE}/device/devices/1786/properties/lmmcp.probe").mock(
            return_value=_answer("device_property_delete")
        )

        body = json.loads(
            (await delete_device_property(client, device_id=1786, property_name="lmmcp.probe"))[
                0
            ].text
        )

        assert route.called
        assert body == {"success": True, "device_id": 1786, "deleted": "lmmcp.probe"}

    @pytest.mark.parametrize(
        ("name", "fixture", "code", "words"),
        [
            ("snmp.version", "device_property_delete_inherited", "NOT_FOUND", "own property"),
            ("system.hostname", "device_property_delete_system", "INVALID_REQUEST", "not allowed"),
        ],
    )
    @respx.mock
    async def test_an_inherited_name_is_not_found_and_a_system_one_refused(
        self, client, monkeypatch, name, fixture, code, words
    ):
        _writes(monkeypatch)
        from lm_mcp.tools.resources import delete_device_property

        respx.delete(f"{_BASE}/device/devices/1786/properties/{name}").mock(
            return_value=_answer(fixture)
        )

        error = envelope(await delete_device_property(client, device_id=1786, property_name=name))

        assert error["code"] == code
        assert words in error["message"]

    @respx.mock
    async def test_refused_with_writes_off(self, client, monkeypatch):
        _writes(monkeypatch, enabled=False)
        from lm_mcp.tools.resources import delete_device_property

        route = respx.delete(f"{_BASE}/device/devices/1786/properties/lmmcp.probe")

        error = envelope(
            await delete_device_property(client, device_id=1786, property_name="lmmcp.probe")
        )

        assert error["code"] == "WRITE_DISABLED"
        assert not route.called
