# Description: Tests for the LogicModule module table and its generic get, delete and create.
# Description: Covers routing for all eight module types and overwrite without delete-first.

import dataclasses
import importlib
import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from tests.envelope import envelope

BASE = "https://test.logicmonitor.com/santaba/rest"

# Module type -> (tool module, settings path, get id argument, delete id argument).
_TYPES = {
    "datasource": ("datasources", "datasources", "datasource_id", "datasource_id"),
    "configsource": ("configsources", "configsources", "configsource_id", "configsource_id"),
    "eventsource": ("eventsources", "eventsources", "eventsource_id", "eventsource_id"),
    "propertysource": (
        "propertysources",
        "propertyrules",
        "propertysource_id",
        "propertysource_id",
    ),
    "logsource": ("logsources", "logsources", "logsource_id", "logsource_id"),
    "topologysource": (
        "topologysources",
        "topologysources",
        "topologysource_id",
        "topologysource_id",
    ),
    "diagnosticsource": (
        "diagnosticsources",
        "diagnosticsources",
        "source_id",
        "diagnosticsource_id",
    ),
    "remediationsource": (
        "remediationsources",
        "remediationsources",
        "source_id",
        "remediationsource_id",
    ),
}


@pytest.fixture
def auth():
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    # The overwrite tests stub HTTP 500 replies; a zero-retry client sends once, no backoff.
    return LogicMonitorClient(base_url=BASE, auth=auth, timeout=30, max_retries=0)


@pytest.fixture
def writes_on(monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    import lm_mcp.config

    importlib.reload(lm_mcp.config)


def _handler(module_type, verb):
    module = importlib.import_module(f"lm_mcp.tools.{_TYPES[module_type][0]}")
    return getattr(module, f"{verb}_{module_type}")


def _swap(monkeypatch, module_type, **fields):
    """Replace one table row's fields, so a handler's output shows it read the table."""
    from lm_mcp.tools import logicmodules

    row = dataclasses.replace(logicmodules.MODULES[module_type], **fields)
    monkeypatch.setitem(logicmodules.MODULES, module_type, row)


class TestModuleTable:
    """R2.4: one table of endpoint, id field and projection for the eight module types."""

    def test_the_table_holds_the_eight_types(self):
        from lm_mcp.tools.logicmodules import MODULES

        assert set(MODULES) == set(_TYPES)
        for module_type, (_, path, _, delete_id) in _TYPES.items():
            row = MODULES[module_type]
            assert row.path == path
            assert row.id_field == delete_id
            assert callable(row.project)


@pytest.mark.parametrize("module_type", sorted(_TYPES))
class TestRoutedThroughTheTable:
    """R2.4: get_<module> and delete_<module> for every type read the table."""

    @respx.mock
    async def test_get_projects_through_the_table(self, client, monkeypatch, module_type):
        _, path, get_id, _ = _TYPES[module_type]
        respx.get(f"{BASE}/setting/{path}/5").mock(
            return_value=httpx.Response(200, json={"id": 5, "name": "M"})
        )
        _swap(monkeypatch, module_type, project=lambda r: {"via_table": r["name"]})

        result = await _handler(module_type, "get")(client, **{get_id: 5})

        assert json.loads(result[0].text) == {"via_table": "M"}

    @respx.mock
    async def test_get_raw_skips_the_projection(self, client, module_type):
        _, path, get_id, _ = _TYPES[module_type]
        body = {"id": 5, "name": "M", "appliesTo": "false()"}
        respx.get(f"{BASE}/setting/{path}/5").mock(return_value=httpx.Response(200, json=body))

        result = await _handler(module_type, "get")(client, **{get_id: 5}, raw=True)

        assert json.loads(result[0].text) == body

    @respx.mock
    async def test_delete_reads_the_name_then_deletes(
        self, client, writes_on, monkeypatch, module_type
    ):
        _, path, _, delete_id = _TYPES[module_type]
        respx.get(f"{BASE}/setting/{path}/5").mock(
            return_value=httpx.Response(200, json={"id": 5, "name": "M"})
        )
        deleted = respx.delete(f"{BASE}/setting/{path}/5").mock(
            return_value=httpx.Response(200, json={})
        )
        _swap(monkeypatch, module_type, label="TableLabel")

        result = await _handler(module_type, "delete")(client, **{delete_id: 5})

        data = json.loads(result[0].text)
        assert deleted.call_count == 1
        assert data == {"success": True, "message": "TableLabel 'M' deleted", delete_id: 5}

    @respx.mock
    async def test_overwrite_on_an_existing_name_puts_the_existing_id(
        self, client, writes_on, module_type
    ):
        _, path, _, _ = _TYPES[module_type]
        lookup = respx.get(f"{BASE}/setting/{path}").mock(
            return_value=httpx.Response(200, json={"items": [{"id": 500, "name": "M"}], "total": 1})
        )
        put = respx.put(f"{BASE}/setting/{path}/500").mock(
            return_value=httpx.Response(200, json={"id": 500, "name": "M"})
        )
        posted = respx.post(f"{BASE}/setting/{path}").mock(
            return_value=httpx.Response(200, json={"id": 501, "name": "M"})
        )
        deleted = respx.delete(url__startswith=f"{BASE}/setting/{path}/").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await _handler(module_type, "create")(
            client, definition={"id": 9, "name": "M", "appliesTo": "false()"}, overwrite=True
        )

        data = json.loads(result[0].text)
        assert lookup.calls.last.request.url.params["filter"] == 'name:"M"'
        assert json.loads(put.calls.last.request.content) == {"name": "M", "appliesTo": "false()"}
        assert (put.call_count, posted.call_count, deleted.call_count) == (1, 0, 0)
        assert data["success"] is True
        assert data[module_type]["id"] == 500
        assert "replaced" in data["message"]

    @respx.mock
    async def test_overwrite_on_a_new_name_posts(self, client, writes_on, module_type):
        _, path, _, _ = _TYPES[module_type]
        respx.get(f"{BASE}/setting/{path}").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        posted = respx.post(f"{BASE}/setting/{path}").mock(
            return_value=httpx.Response(200, json={"id": 501, "name": "M"})
        )

        result = await _handler(module_type, "create")(
            client, definition={"name": "M"}, overwrite=True
        )

        data = json.loads(result[0].text)
        assert posted.call_count == 1
        assert data[module_type]["id"] == 501
        assert "created" in data["message"]


class TestOverwriteNeverDeletes:
    """R2.4 acceptance: a failed write under overwrite=true leaves the original in place."""

    @respx.mock
    async def test_a_failed_post_sends_no_delete(self, client, writes_on):
        from lm_mcp.tools.datasources import create_datasource

        respx.get(f"{BASE}/setting/datasources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        respx.post(f"{BASE}/setting/datasources").mock(
            return_value=httpx.Response(500, json={"errorMessage": "boom", "errorCode": 1500})
        )
        deleted = respx.delete(url__startswith=f"{BASE}/setting/datasources/").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await create_datasource(
            client, definition={"name": "MyDS", "displayName": "My DS"}, overwrite=True
        )

        assert envelope(result)["code"]
        assert deleted.call_count == 0

    @respx.mock
    async def test_a_failed_put_on_the_existing_module_sends_no_delete(self, client, writes_on):
        from lm_mcp.tools.datasources import create_datasource

        respx.get(f"{BASE}/setting/datasources").mock(
            return_value=httpx.Response(
                200, json={"items": [{"id": 500, "name": "MyDS"}], "total": 1}
            )
        )
        respx.put(f"{BASE}/setting/datasources/500").mock(
            return_value=httpx.Response(500, json={"errorMessage": "boom", "errorCode": 1500})
        )
        posted = respx.post(f"{BASE}/setting/datasources").mock(
            return_value=httpx.Response(200, json={"id": 501, "name": "MyDS"})
        )
        deleted = respx.delete(url__startswith=f"{BASE}/setting/datasources/").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await create_datasource(
            client, definition={"name": "MyDS", "displayName": "My DS"}, overwrite=True
        )

        assert envelope(result)["code"]
        assert (posted.call_count, deleted.call_count) == (0, 0)

    @respx.mock
    async def test_without_overwrite_there_is_no_lookup(self, client, writes_on):
        from lm_mcp.tools.datasources import create_datasource

        lookup = respx.get(f"{BASE}/setting/datasources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )
        posted = respx.post(f"{BASE}/setting/datasources").mock(
            return_value=httpx.Response(200, json={"id": 503, "name": "Plain", "displayName": "P"})
        )

        result = await create_datasource(client, definition={"name": "Plain"})

        data = json.loads(result[0].text)
        assert (lookup.call_count, posted.call_count) == (0, 1)
        assert data["datasource"] == {"id": 503, "name": "Plain", "display_name": "P"}
