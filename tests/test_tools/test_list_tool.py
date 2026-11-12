# Description: Tests for list_tool, the shared helper that builds a list tool's query and response.
# Description: Covers the query it builds, the projection callback, totals and errors.

import json
import logging

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import WILDCARD_STRIP_NOTE, ErrorContent, list_tool

BASE_URL = "https://test.logicmonitor.com/santaba/rest"


@pytest.fixture
def client():
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url=BASE_URL,
        auth=BearerAuth("test-token"),
        timeout=30,
    )


def _project(item: dict) -> dict:
    """Project one API row onto the tool's own field names."""
    return {"id": item.get("id"), "name": item.get("displayName")}


def _rows(n: int) -> list[dict]:
    """Build n API rows."""
    return [{"id": i, "displayName": f"row{i}"} for i in range(n)]


class TestListToolQuery:
    """R2.5: list_tool builds the query from limit, offset, a raw filter and named filters."""

    @respx.mock
    async def test_named_filters_are_sanitized_quoted_and_joined(self, client):
        route = respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": 1, "items": _rows(1)})
        )

        await list_tool(
            client,
            "/device/devices",
            key="devices",
            project=_project,
            limit=25,
            offset=50,
            named={"displayName~": "web*", "name~": 'a"b', "description~": None},
            clauses=["hostGroupIds:6"],
        )

        assert route.call_count == 1
        params = dict(route.calls[0].request.url.params)
        assert params["size"] == "25"
        assert params["offset"] == "50"
        assert params["filter"] == 'hostGroupIds:6,displayName~"web",name~"a\\"b"'

    @respx.mock
    async def test_raw_filter_replaces_named_filters_and_clauses(self, client):
        route = respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )

        await list_tool(
            client,
            "/device/devices",
            key="devices",
            project=_project,
            limit=50,
            filter="systemProperties.name:system.hostname",
            named={"displayName~": "web"},
            clauses=["hostGroupIds:6"],
        )

        params = dict(route.calls[0].request.url.params)
        assert params["filter"] == "systemProperties.name:system.hostname"

    @respx.mock
    async def test_no_filter_parameter_when_nothing_filters(self, client):
        route = respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )

        await list_tool(
            client, "/device/devices", key="devices", project=_project, limit=50, named={}
        )

        params = dict(route.calls[0].request.url.params)
        assert "filter" not in params
        assert params["offset"] == "0"

    @respx.mock
    async def test_extra_params_reach_the_query(self, client):
        route = respx.get(f"{BASE_URL}/report/reports").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )

        await list_tool(
            client,
            "/report/reports",
            key="reports",
            project=_project,
            limit=10,
            params={"showNextGenReports": "true"},
        )

        params = dict(route.calls[0].request.url.params)
        assert params["showNextGenReports"] == "true"
        assert params["size"] == "10"


class TestListToolResponse:
    """R2.5: list_tool projects each row and returns paginated_response under the tool's key."""

    @respx.mock
    async def test_projection_and_key_and_extra(self, client):
        respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": 10, "items": _rows(3)})
        )

        result = await list_tool(
            client,
            "/device/devices",
            key="devices",
            project=_project,
            limit=3,
            extra={"device_id": 7},
        )

        data = json.loads(result[0].text)
        assert data["devices"] == [
            {"id": 0, "name": "row0"},
            {"id": 1, "name": "row1"},
            {"id": 2, "name": "row2"},
        ]
        assert data["device_id"] == 7
        assert data["total"] == 10
        assert data["count"] == 3
        assert data["offset"] == 0
        assert data["has_more"] is True
        assert "note" not in data

    @respx.mock
    async def test_async_projection_is_awaited_per_row(self, client):
        respx.get(f"{BASE_URL}/setting/recipientgroups").mock(
            return_value=httpx.Response(200, json={"total": 2, "items": _rows(2)})
        )
        seen: list[int] = []

        async def project(item: dict) -> dict:
            seen.append(item["id"])
            return _project(item)

        result = await list_tool(
            client, "/setting/recipientgroups", key="groups", project=project, limit=2
        )

        data = json.loads(result[0].text)
        assert data["groups"] == [{"id": 0, "name": "row0"}, {"id": 1, "name": "row1"}]
        assert seen == [0, 1]

    @respx.mock
    async def test_wildcard_strip_adds_the_note(self, client):
        respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )

        result = await list_tool(
            client,
            "/device/devices",
            key="devices",
            project=_project,
            limit=50,
            named={"displayName~": "*web?"},
        )

        assert json.loads(result[0].text)["note"] == WILDCARD_STRIP_NOTE

    @respx.mock
    async def test_negative_total_reads_as_more_without_a_total(self, client):
        # The portal's form, -(offset + size + 1), while rows exist past the page.
        respx.get(f"{BASE_URL}/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"total": -16, "items": _rows(5)})
        )

        result = await list_tool(
            client, "/setting/accesslogs", key="logs", project=_project, limit=5, offset=10
        )

        data = json.loads(result[0].text)
        assert "total" not in data
        assert data["count"] == 5
        assert data["offset"] == 10
        assert data["has_more"] is True
        assert "exact count" in data["total_note"]

    @respx.mock
    async def test_offset_past_the_end_is_an_empty_last_page(self, client):
        respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": 10, "items": []})
        )

        result = await list_tool(
            client, "/device/devices", key="devices", project=_project, limit=5, offset=50
        )

        data = json.loads(result[0].text)
        assert data["devices"] == []
        assert data["count"] == 0
        assert data["has_more"] is False

    @respx.mock
    async def test_projection_that_raises_is_logged_and_handled(self, client, caplog):
        respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": 1, "items": _rows(1)})
        )

        def broken(item: dict) -> dict:
            raise KeyError("displayName")

        with caplog.at_level(logging.ERROR, logger="lm_mcp.tools"):
            result = await list_tool(
                client, "/device/devices", key="devices", project=broken, limit=5
            )

        assert isinstance(result[0], ErrorContent)
        assert "displayName" in result[0].text
        logged = [r for r in caplog.records if r.exc_info]
        assert logged
        assert logged[0].exc_info[0] is KeyError

    @respx.mock
    async def test_api_error_surfaces_through_handle_error(self, client):
        respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(404, json={"errorMessage": "no such path"})
        )

        result = await list_tool(
            client, "/device/devices", key="devices", project=_project, limit=5
        )

        assert isinstance(result[0], ErrorContent)


class TestListToolKeep:
    """list_tool's keep predicate drops rows after the fetch; paging follows the fetched page."""

    @pytest.mark.parametrize(("total", "has_more"), [(3, False), (10, True), (-4, True)])
    @respx.mock
    async def test_dropped_rows_leave_the_page_but_not_the_paging(self, client, total, has_more):
        respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": total, "items": _rows(3)})
        )

        result = await list_tool(
            client,
            "/device/devices",
            key="devices",
            project=_project,
            limit=3,
            offset=0,
            keep=lambda item: item["id"] != 1,
        )

        data = json.loads(result[0].text)
        assert [row["id"] for row in data["devices"]] == [0, 2]
        assert data["count"] == 2
        assert data["dropped"] == 1
        assert data["next_offset"] == 3
        assert data["has_more"] is has_more

    @respx.mock
    async def test_a_page_whose_rows_are_all_dropped_still_reads_more(self, client):
        respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": -7, "items": _rows(3)})
        )

        result = await list_tool(
            client,
            "/device/devices",
            key="devices",
            project=_project,
            limit=3,
            keep=lambda _: False,
        )

        data = json.loads(result[0].text)
        assert data["devices"] == []
        assert data["count"] == 0
        assert data["dropped"] == 3
        assert data["has_more"] is True

    @respx.mock
    async def test_without_keep_the_response_carries_no_drop_fields(self, client):
        respx.get(f"{BASE_URL}/device/devices").mock(
            return_value=httpx.Response(200, json={"total": 3, "items": _rows(3)})
        )

        result = await list_tool(
            client, "/device/devices", key="devices", project=_project, limit=3
        )

        data = json.loads(result[0].text)
        assert "dropped" not in data
        assert "next_offset" not in data


class TestListToolCarry:
    """R3.6: carry copies named keys of the API answer into the response beside the page."""

    @respx.mock
    async def test_carried_keys_are_renamed_and_a_missing_one_is_none(self, client):
        respx.get(f"{BASE_URL}/device/devices/delta").mock(
            return_value=httpx.Response(
                200, json={"total": 1, "items": _rows(1), "deltaId": "a1b2"}
            )
        )

        result = await list_tool(
            client,
            "/device/devices/delta",
            key="devices",
            project=_project,
            limit=1,
            carry={"deltaId": "delta_id", "searchId": "search_id"},
        )

        body = json.loads(result[0].text)
        assert (body["delta_id"], body["search_id"]) == ("a1b2", None)
        assert body["devices"] == [{"id": 0, "name": "row0"}]

    @respx.mock
    async def test_without_carry_no_answer_key_is_copied(self, client):
        respx.get(f"{BASE_URL}/device/devices/delta").mock(
            return_value=httpx.Response(
                200, json={"total": 1, "items": _rows(1), "deltaId": "a1b2"}
            )
        )

        result = await list_tool(
            client, "/device/devices/delta", key="devices", project=_project, limit=1
        )

        assert "deltaId" not in result[0].text
