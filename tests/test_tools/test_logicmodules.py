# Description: Tests for the LogicModule table and the eight tool modules that delegate to it.
# Description: Routing for all eight types, overwrite without delete-first, and per-module cases.

import dataclasses
import importlib
import json
from pathlib import Path

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result
from tests.envelope import envelope

BASE = "https://test.logicmonitor.com/santaba/rest"

# The DiagnosticSource cases name the REST base BASE_URL.
BASE_URL = BASE

# GET /setting/topologysources/1 on a live portal, 2026-11-07 (the update_logicmodule
# fixture).
_TOPOLOGYSOURCE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "topologysource_1.json").read_text()
)

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


# Module type -> (list response key, the named filter clauses the list tool sends).
_LISTS = {
    "datasource": ("datasources", {"name_filter": "name~", "applies_to_filter": "appliesTo~"}),
    "configsource": ("configsources", {"name_filter": "name~", "applies_to_filter": "appliesTo~"}),
    "eventsource": ("eventsources", {"name_filter": "name~", "applies_to_filter": "appliesTo~"}),
    "propertysource": (
        "propertysources",
        {"name_filter": "name~", "applies_to_filter": "appliesTo~"},
    ),
    "logsource": ("logsources", {"name_filter": "name~", "applies_to_filter": "appliesTo~"}),
    "topologysource": (
        "topologysources",
        {"name_filter": "name~", "applies_to_filter": "appliesTo~"},
    ),
    "diagnosticsource": ("diagnosticsources", {"name_filter": "name~", "group_filter": "group~"}),
    "remediationsource": ("remediationsources", {"name_filter": "name~", "group_filter": "group~"}),
}


@pytest.mark.parametrize("module_type", sorted(_TYPES))
class TestUpdateAndListThroughTheTable:
    """R2.4: update_<module> (the internal PUT) and get_<modules> read the table."""

    async def test_update_without_confirm_writes_nothing(self, client, writes_on, module_type):
        _, path, _, delete_id = _TYPES[module_type]
        with respx.mock(assert_all_called=False) as mock:
            put = mock.put(f"{BASE}/setting/{path}/5").mock(
                return_value=httpx.Response(200, json={})
            )
            result = await _handler(module_type, "update")(
                client, **{delete_id: 5}, definition={"name": "M"}
            )

        assert envelope(result)["code"] == "INVALID_REQUEST"
        assert f"update_{module_type} is full-replace" in envelope(result)["message"]
        assert put.call_count == 0

    @respx.mock
    async def test_update_puts_the_definition_without_its_id(
        self, client, writes_on, monkeypatch, module_type
    ):
        _, path, _, delete_id = _TYPES[module_type]
        put = respx.put(f"{BASE}/setting/{path}/5").mock(
            return_value=httpx.Response(200, json={"id": 5, "name": "M"})
        )
        _swap(monkeypatch, module_type, label="TableLabel")

        result = await _handler(module_type, "update")(
            client, **{delete_id: 5}, definition={"id": 5, "name": "M"}, confirm=True
        )

        data = json.loads(result[0].text)
        assert json.loads(put.calls.last.request.content) == {"name": "M"}
        assert data["message"] == "TableLabel 'M' updated successfully"
        assert data[module_type]["id"] == 5

    @respx.mock
    async def test_list_pages_through_list_tool_with_the_table_row(
        self, client, monkeypatch, module_type
    ):
        _, path, _, _ = _TYPES[module_type]
        key, named = _LISTS[module_type]
        route = respx.get(f"{BASE}/setting/{path}").mock(
            return_value=httpx.Response(200, json={"items": [{"id": 1, "name": "A"}], "total": 9})
        )
        _swap(monkeypatch, module_type, list_row=lambda r: {"via_table": r["name"]})
        args = dict.fromkeys(named, "x*")

        result = await getattr(
            importlib.import_module(f"lm_mcp.tools.{_TYPES[module_type][0]}"), f"get_{key}"
        )(client, **args, limit=1, offset=3)

        data = json.loads(result[0].text)
        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("1", "3")
        assert params["filter"] == ",".join(f'{clause}"x"' for clause in named.values())
        assert data[key] == [{"via_table": "A"}]
        assert (data["total"], data["has_more"]) == (9, True)

    @respx.mock
    async def test_list_sends_a_raw_filter_as_written(self, client, module_type):
        _, path, _, _ = _TYPES[module_type]
        key, _ = _LISTS[module_type]
        route = respx.get(f"{BASE}/setting/{path}").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await getattr(
            importlib.import_module(f"lm_mcp.tools.{_TYPES[module_type][0]}"), f"get_{key}"
        )(client, name_filter="ignored", filter='group:"Core"')

        assert route.calls.last.request.url.params["filter"] == 'group:"Core"'

    @respx.mock
    async def test_update_logicmodule_applies_through_the_table(
        self, client, writes_on, monkeypatch, module_type
    ):
        """Every type, topologysource included, reads and PUTs the table's path."""
        from lm_mcp.tools.workflows import update_logicmodule

        for name in ("LM_ENABLED_TOOLS", "LM_DISABLED_TOOLS", "LM_MCP_CATEGORIES"):
            monkeypatch.delenv(name, raising=False)
        _, path, _, _ = _TYPES[module_type]
        body = {"id": 1, "name": "M", "displayName": "M", "description": "before"}
        respx.get(f"{BASE}/setting/{path}/1").mock(return_value=httpx.Response(200, json=body))
        put = respx.put(f"{BASE}/setting/{path}/1").mock(
            return_value=httpx.Response(200, json={**body, "description": "after"})
        )
        _swap(monkeypatch, module_type, label="TableLabel")

        result = await update_logicmodule(
            client, type=module_type, id=1, changes={"description": "after"}, mode="apply"
        )

        payload = json.loads(result[0].text)
        assert payload["applied"] is True
        assert json.loads(put.calls.last.request.content)["description"] == "after"
        assert payload["result"]["message"] == "TableLabel 'M' updated successfully"


class TestDatasourceCases:
    """R2.4: DataSource cases the parametrized table tests do not cover."""

    @respx.mock
    async def test_get_datasources_returns_list(self, client):
        """get_datasources returns properly formatted datasource list."""
        from lm_mcp.tools.datasources import get_datasources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "CPU",
                            "displayName": "CPU Usage",
                            "description": "Monitors CPU usage",
                            "appliesTo": "isWindows()",
                            "group": "Core",
                            "collectMethod": "wmi",
                            "hasMultiInstances": False,
                        },
                        {
                            "id": 2,
                            "name": "Memory",
                            "displayName": "Memory Usage",
                            "description": "Monitors memory usage",
                            "appliesTo": "isWindows()",
                            "group": "Core",
                            "collectMethod": "wmi",
                            "hasMultiInstances": False,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_datasources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["datasources"]) == 2
        assert data["datasources"][0]["name"] == "CPU"
        assert data["datasources"][1]["name"] == "Memory"

    @respx.mock
    async def test_get_datasources_handles_error(self, client):
        """get_datasources handles errors gracefully."""
        from lm_mcp.tools.datasources import get_datasources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(403, json={"errorMessage": "Permission denied"})
        )

        result = await get_datasources(client)

        assert is_error_result(result)

    @respx.mock
    async def test_get_datasource_returns_details(self, client):
        """get_datasource returns detailed datasource info."""
        from lm_mcp.tools.datasources import get_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "CPU",
                    "displayName": "CPU Usage",
                    "description": "Monitors CPU usage metrics",
                    "appliesTo": "isWindows()",
                    "group": "Core",
                    "collectMethod": "wmi",
                    "collectInterval": 60,
                    "hasMultiInstances": True,
                    "dataPoints": [
                        {
                            "id": 1,
                            "name": "CPUBusyPercent",
                            "description": "CPU busy percentage",
                            "type": 0,
                            "alertExpr": "> 90",
                        },
                        {
                            "id": 2,
                            "name": "CPUIdlePercent",
                            "description": "CPU idle percentage",
                            "type": 0,
                            "alertExpr": "",
                        },
                        {
                            "id": 3,
                            "name": "CPUUsagePercent",
                            "description": "Computed CPU usage",
                            "type": 0,
                            "alertExpr": "> 95",
                            "postProcessorMethod": "expression",
                            "postProcessorParam": "(cpuUsageNanoCores*100)/cpuNanoCoreCapacity",
                        },
                    ],
                    "graphs": [
                        {
                            "id": 10,
                            "name": "CPUGraph",
                            "title": "CPU Usage Over Time",
                        }
                    ],
                },
            )
        )

        result = await get_datasource(client, datasource_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 100
        assert data["name"] == "CPU"
        assert len(data["datapoints"]) == 3
        assert data["datapoints"][0]["name"] == "CPUBusyPercent"
        assert data["datapoints"][0]["post_processor_method"] == ""
        assert data["datapoints"][0]["post_processor_param"] == ""
        assert data["datapoints"][2]["name"] == "CPUUsagePercent"
        assert data["datapoints"][2]["post_processor_method"] == "expression"
        assert data["datapoints"][2]["post_processor_param"] == (
            "(cpuUsageNanoCores*100)/cpuNanoCoreCapacity"
        )
        assert len(data["graphs"]) == 1
        assert data["graphs"][0]["title"] == "CPU Usage Over Time"

    @respx.mock
    async def test_get_datasource_not_found(self, client):
        """get_datasource returns error for missing datasource."""
        from lm_mcp.tools.datasources import get_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "DataSource not found"})
        )

        result = await get_datasource(client, datasource_id=999)

        assert is_error_result(result)

    @respx.mock
    async def test_get_datasource_empty_datapoints(self, client):
        """get_datasource handles datasource with no datapoints."""
        from lm_mcp.tools.datasources import get_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 101,
                    "name": "SimpleDS",
                    "displayName": "Simple DataSource",
                    "description": "A simple datasource",
                    "appliesTo": "true()",
                    "group": "Test",
                    "collectMethod": "script",
                    "collectInterval": 300,
                    "hasMultiInstances": False,
                    "dataPoints": [],
                    "graphs": [],
                },
            )
        )

        result = await get_datasource(client, datasource_id=101)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 101
        assert len(data["datapoints"]) == 0
        assert len(data["graphs"]) == 0

    @respx.mock
    async def test_get_datasources_pagination_info(self, client):
        """get_datasources returns pagination info."""
        from lm_mcp.tools.datasources import get_datasources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": 1, "name": "CPU"}],
                    "total": 500,
                },
            )
        )

        result = await get_datasources(client, limit=50, offset=0)

        data = json.loads(result[0].text)
        assert data["total"] == 500
        assert data["has_more"] is True
        assert data["offset"] == 0

    async def test_create_datasource_requires_write_permission(self, client, monkeypatch):
        """create_datasource requires write permission."""
        from lm_mcp.tools.datasources import create_datasource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_datasource(client, definition={"name": "TestDS"})

        assert len(result) == 1
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_datasource_posts_definition(self, client, writes_on):
        """create_datasource posts definition to /setting/datasources."""
        from lm_mcp.tools.datasources import create_datasource

        definition = {
            "name": "CustomDS",
            "displayName": "Custom DataSource",
            "appliesTo": "isLinux()",
            "collectMethod": "script",
            "dataPoints": [{"name": "dp1", "type": 0}],
        }

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5001,
                    "name": "CustomDS",
                    "displayName": "Custom DataSource",
                },
            )
        )

        await create_datasource(client, definition=definition)

        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "CustomDS"
        assert request_body["appliesTo"] == "isLinux()"

    @respx.mock
    async def test_create_datasource_returns_created_fields(self, client, writes_on):
        """create_datasource returns id, name, displayName from response."""
        from lm_mcp.tools.datasources import create_datasource

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5002,
                    "name": "NewDS",
                    "displayName": "New DataSource",
                },
            )
        )

        result = await create_datasource(
            client,
            definition={"name": "NewDS", "displayName": "New DataSource"},
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["datasource"]["id"] == 5002
        assert data["datasource"]["name"] == "NewDS"
        assert data["datasource"]["display_name"] == "New DataSource"

    @respx.mock
    async def test_create_datasource_strips_id_from_definition(self, client, writes_on):
        """create_datasource strips id from definition before POST."""
        from lm_mcp.tools.datasources import create_datasource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 5003, "name": "ClonedDS", "displayName": "Cloned DS"},
            )
        )

        definition = {"id": 999, "name": "ClonedDS", "displayName": "Cloned DS"}
        await create_datasource(client, definition=definition)

        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    @respx.mock
    async def test_create_datasource_handles_api_error(self, client, writes_on):
        """create_datasource handles API errors gracefully."""
        from lm_mcp.tools.datasources import create_datasource

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(400, json={"errorMessage": "Invalid DataSource definition"})
        )

        result = await create_datasource(client, definition={"name": "Bad"})

        assert is_error_result(result)

    @respx.mock
    async def test_create_normalizes_snake_case_fields(self, client, writes_on):
        """create_datasource normalizes snake_case to camelCase before POST."""
        from lm_mcp.tools.datasources import create_datasource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200, json={"id": 1, "name": "TestDS", "displayName": "Test"}
            )
        )

        await create_datasource(
            client,
            definition={
                "name": "TestDS",
                "display_name": "Test",
                "collect_method": "script",
                "applies_to": "isLinux()",
            },
        )

        import json as json_mod

        body = json_mod.loads(route.calls[0].request.content)
        assert body["displayName"] == "Test"
        assert body["collectMethod"] == "script"
        assert body["appliesTo"] == "isLinux()"
        assert "display_name" not in body

    @respx.mock
    async def test_create_datasource_overwrite_no_existing(self, client, writes_on):
        """create_datasource with overwrite=True works when no existing DS found."""
        from lm_mcp.tools.datasources import create_datasource

        # GET returns no existing DS
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={"items": [], "total": 0},
            )
        )

        # POST new DS (no DELETE needed)
        respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 502, "name": "NewDS", "displayName": "New DS"},
            )
        )

        result = await create_datasource(
            client,
            definition={"name": "NewDS", "displayName": "New DS"},
            overwrite=True,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["datasource"]["id"] == 502

    @respx.mock
    async def test_create_datasource_without_overwrite_unchanged(self, client, writes_on):
        """create_datasource without overwrite flag does not look up existing."""
        from lm_mcp.tools.datasources import create_datasource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 503, "name": "PlainDS", "displayName": "Plain DS"},
            )
        )

        result = await create_datasource(client, definition={"name": "PlainDS"}, overwrite=False)

        data = json.loads(result[0].text)
        assert data["success"] is True
        # Should only have the POST call, no GET for lookup
        assert route.called

    async def test_update_datasource_requires_write_permission(self, client, monkeypatch):
        """update_datasource requires write permission."""
        from lm_mcp.tools.datasources import update_datasource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_datasource(client, datasource_id=100, definition={"name": "Updated"})

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_datasource_puts_definition(self, client, writes_on):
        """update_datasource PUTs definition to /setting/datasources/{id}."""
        from lm_mcp.tools.datasources import update_datasource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "UpdatedDS",
                    "displayName": "Updated DataSource",
                },
            )
        )

        result = await update_datasource(
            client,
            datasource_id=100,
            definition={"name": "UpdatedDS", "displayName": "Updated DataSource"},
            confirm=True,
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["datasource"]["id"] == 100
        assert data["datasource"]["name"] == "UpdatedDS"

    async def test_update_datasource_without_confirm_errors_with_pointer(self, client, writes_on):
        """update_datasource without confirm=True returns INVALID_REQUEST."""
        from lm_mcp.tools.datasources import update_datasource

        result = await update_datasource(client, datasource_id=100, definition={"name": "X"})

        text = result[0].text
        assert "confirm=true" in text.lower() or "confirm" in text.lower()
        assert "update_logicmodule" in text

    @respx.mock
    async def test_update_datasource_handles_error(self, client, writes_on):
        """update_datasource handles API errors."""
        from lm_mcp.tools.datasources import update_datasource

        respx.put("https://test.logicmonitor.com/santaba/rest/setting/datasources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "DataSource not found"})
        )

        result = await update_datasource(
            client, datasource_id=999, definition={"name": "Missing"}, confirm=True
        )

        assert is_error_result(result)

    async def test_delete_datasource_requires_write_permission(self, client, monkeypatch):
        """delete_datasource requires write permission."""
        from lm_mcp.tools.datasources import delete_datasource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_datasource(client, datasource_id=100)

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_datasource_not_found(self, client, writes_on):
        """delete_datasource handles 404 errors."""
        from lm_mcp.tools.datasources import delete_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "DataSource not found"})
        )

        result = await delete_datasource(client, datasource_id=999)

        assert is_error_result(result)

    @respx.mock
    async def test_raw_returns_the_rest_object_and_default_projects(self, client):
        from lm_mcp.tools.datasources import get_datasource

        body = {
            "id": 100,
            "name": "CPU",
            "displayName": "CPU Usage",
            "appliesTo": "isWindows()",
            "collectMethod": "wmi",
            "collectInterval": 60,
            "collectorAttribute": {"name": "wmi"},
            "dataPoints": [{"id": 1, "name": "CPUBusyPercent", "type": 0, "alertExpr": "> 90"}],
            "graphs": [],
        }
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/100").mock(
            return_value=httpx.Response(200, json=body)
        )

        raw = json.loads((await get_datasource(client, datasource_id=100, raw=True))[0].text)
        projected = json.loads((await get_datasource(client, datasource_id=100))[0].text)

        assert raw == body
        assert "displayName" not in projected
        assert projected["display_name"] == body["displayName"]


class TestConfigsourceCases:
    """R2.4: ConfigSource cases the parametrized table tests do not cover."""

    async def test_create_configsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.configsources import create_configsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_configsource(client, definition={"name": "TestCS"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_configsource_posts_definition(self, client, writes_on):
        from lm_mcp.tools.configsources import create_configsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/configsources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 6001, "name": "CustomCS", "displayName": "Custom ConfigSource"},
            )
        )

        result = await create_configsource(
            client,
            definition={"name": "CustomCS", "displayName": "Custom ConfigSource"},
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["configsource"]["id"] == 6001

    @respx.mock
    async def test_create_configsource_strips_id(self, client, writes_on):
        from lm_mcp.tools.configsources import create_configsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/configsources").mock(
            return_value=httpx.Response(200, json={"id": 6002, "name": "CS"}),
        )

        await create_configsource(client, definition={"id": 999, "name": "CS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    async def test_update_configsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.configsources import update_configsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_configsource(
            client, configsource_id=100, definition={"name": "Updated"}
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_configsource_puts_definition(self, client, writes_on):
        from lm_mcp.tools.configsources import update_configsource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/configsources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "UpdatedCS", "displayName": "Updated ConfigSource"},
            )
        )

        result = await update_configsource(
            client,
            configsource_id=100,
            definition={"name": "UpdatedCS", "displayName": "Updated ConfigSource"},
            confirm=True,
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["configsource"]["id"] == 100

    async def test_update_configsource_without_confirm_errors_with_pointer(self, client, writes_on):
        from lm_mcp.tools.configsources import update_configsource

        result = await update_configsource(client, configsource_id=100, definition={"name": "X"})
        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text

    async def test_delete_configsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.configsources import delete_configsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_configsource(client, configsource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_configsource_not_found(self, client, writes_on):
        from lm_mcp.tools.configsources import delete_configsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/configsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_configsource(client, configsource_id=999)
        assert is_error_result(result)

    @respx.mock
    async def test_raw_returns_the_rest_object_and_default_projects(self, client):
        from lm_mcp.tools.configsources import get_configsource

        body = {
            "id": 7,
            "name": "Cisco_IOS",
            "displayName": "Cisco IOS",
            "appliesTo": "isCisco()",
            "collectMethod": "script",
            "collectInterval": 3600,
            "configChecks": [{"id": 1, "name": "Config change", "type": "any"}],
        }
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/configsources/7").mock(
            return_value=httpx.Response(200, json=body)
        )

        raw = json.loads((await get_configsource(client, configsource_id=7, raw=True))[0].text)
        projected = json.loads((await get_configsource(client, configsource_id=7))[0].text)

        assert raw == body
        assert "displayName" not in projected
        assert projected["display_name"] == body["displayName"]


class TestEventsourceCases:
    """R2.4: EventSource cases the parametrized table tests do not cover."""

    @respx.mock
    async def test_get_eventsources_returns_list(self, client):
        """get_eventsources returns properly formatted list."""
        from lm_mcp.tools.eventsources import get_eventsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "WindowsEventLog",
                            "displayName": "Windows Event Log",
                            "description": "Collects Windows events",
                            "appliesTo": "isWindows()",
                            "technology": "Windows",
                            "group": "Events",
                            "version": 1,
                        },
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_eventsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert len(data["eventsources"]) == 1
        assert data["eventsources"][0]["name"] == "WindowsEventLog"

    @respx.mock
    async def test_get_eventsource_returns_detail(self, client):
        """get_eventsource returns detailed EventSource info."""
        from lm_mcp.tools.eventsources import get_eventsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "WindowsEventLog",
                    "displayName": "Windows Event Log",
                    "description": "Collects Windows events",
                    "appliesTo": "isWindows()",
                    "technology": "Windows",
                    "group": "Events",
                    "version": 1,
                    "tags": "windows,events",
                    "auditVersion": 123,
                    "installDate": "2024-01-15",
                    "filters": [],
                },
            )
        )

        result = await get_eventsource(client, eventsource_id=1)

        data = json.loads(result[0].text)
        assert data["id"] == 1
        assert data["name"] == "WindowsEventLog"
        assert data["display_name"] == "Windows Event Log"

    async def test_create_eventsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.eventsources import create_eventsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_eventsource(client, definition={"name": "TestES"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_eventsource_posts_definition(self, client, writes_on):
        from lm_mcp.tools.eventsources import create_eventsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/eventsources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 9001, "name": "CustomES", "displayName": "Custom EventSource"},
            )
        )

        result = await create_eventsource(
            client,
            definition={
                "name": "CustomES",
                "alertEffectiveIval": 60,
            },
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["eventsource"]["id"] == 9001

    @respx.mock
    async def test_create_eventsource_strips_id(self, client, writes_on):
        from lm_mcp.tools.eventsources import create_eventsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/eventsources").mock(
            return_value=httpx.Response(200, json={"id": 9002, "name": "ES"}),
        )

        await create_eventsource(client, definition={"id": 999, "name": "ES"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    async def test_update_eventsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.eventsources import update_eventsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_eventsource(
            client, eventsource_id=100, definition={"name": "Updated"}
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_eventsource_puts_definition(self, client, writes_on):
        from lm_mcp.tools.eventsources import update_eventsource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/eventsources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "UpdatedES", "displayName": "Updated EventSource"},
            )
        )

        result = await update_eventsource(
            client,
            eventsource_id=100,
            definition={"name": "UpdatedES", "displayName": "Updated EventSource"},
            confirm=True,
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["eventsource"]["id"] == 100

    async def test_update_eventsource_without_confirm_errors_with_pointer(self, client, writes_on):
        from lm_mcp.tools.eventsources import update_eventsource

        result = await update_eventsource(client, eventsource_id=100, definition={"name": "X"})
        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text

    async def test_delete_eventsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.eventsources import delete_eventsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_eventsource(client, eventsource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_eventsource_not_found(self, client, writes_on):
        from lm_mcp.tools.eventsources import delete_eventsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_eventsource(client, eventsource_id=999)
        assert is_error_result(result)

    @respx.mock
    async def test_raw_returns_the_rest_object_and_default_projects(self, client):
        from lm_mcp.tools.eventsources import get_eventsource

        body = {
            "id": 1,
            "name": "WindowsEventLog",
            "displayName": "Windows Event Log",
            "appliesTo": "isWindows()",
            "technology": "Windows",
            "group": "Events",
            "filters": [],
        }
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources/1").mock(
            return_value=httpx.Response(200, json=body)
        )

        raw = json.loads((await get_eventsource(client, eventsource_id=1, raw=True))[0].text)
        projected = json.loads((await get_eventsource(client, eventsource_id=1))[0].text)

        assert raw == body
        assert "displayName" not in projected
        assert projected["display_name"] == body["displayName"]


class TestPropertysourceCases:
    """R2.4: PropertySource cases the parametrized table tests do not cover."""

    async def test_create_propertysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.propertysources import create_propertysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_propertysource(client, definition={"name": "TestPS"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_propertysource_posts_definition(self, client, writes_on):
        from lm_mcp.tools.propertysources import create_propertysource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/propertyrules").mock(
            return_value=httpx.Response(200, json={"id": 7001, "name": "CustomPS"})
        )

        result = await create_propertysource(
            client, definition={"name": "CustomPS", "technology": "script"}
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["propertysource"]["id"] == 7001

    @respx.mock
    async def test_create_propertysource_strips_id(self, client, writes_on):
        from lm_mcp.tools.propertysources import create_propertysource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/propertyrules").mock(
            return_value=httpx.Response(200, json={"id": 7002, "name": "PS"}),
        )

        await create_propertysource(client, definition={"id": 999, "name": "PS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    async def test_update_propertysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.propertysources import update_propertysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_propertysource(
            client, propertysource_id=100, definition={"name": "Updated"}
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_propertysource_puts_definition(self, client, writes_on):
        from lm_mcp.tools.propertysources import update_propertysource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/propertyrules/100"
        ).mock(return_value=httpx.Response(200, json={"id": 100, "name": "UpdatedPS"}))

        result = await update_propertysource(
            client, propertysource_id=100, definition={"name": "UpdatedPS"}, confirm=True
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["propertysource"]["id"] == 100

    async def test_update_propertysource_without_confirm_errors_with_pointer(
        self, client, writes_on
    ):
        from lm_mcp.tools.propertysources import update_propertysource

        result = await update_propertysource(
            client, propertysource_id=100, definition={"name": "X"}
        )
        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text

    async def test_delete_propertysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.propertysources import delete_propertysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_propertysource(client, propertysource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_propertysource_not_found(self, client, writes_on):
        from lm_mcp.tools.propertysources import delete_propertysource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/propertyrules/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_propertysource(client, propertysource_id=999)
        assert is_error_result(result)

    @respx.mock
    async def test_raw_returns_the_rest_object_and_default_projects(self, client):
        from lm_mcp.tools.propertysources import get_propertysource

        body = {
            "id": 5,
            "name": "addCategory_Linux",
            "appliesTo": "isLinux()",
            "groovyScript": "println 'system.categories=Linux'",
            "version": 1,
        }
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/propertyrules/5").mock(
            return_value=httpx.Response(200, json=body)
        )

        raw = json.loads((await get_propertysource(client, propertysource_id=5, raw=True))[0].text)
        projected = json.loads((await get_propertysource(client, propertysource_id=5))[0].text)

        assert raw == body
        assert "appliesTo" not in projected
        assert projected["applies_to"] == body["appliesTo"]


class TestLogsourceCases:
    """R2.4: LogSource cases the parametrized table tests do not cover."""

    @respx.mock
    async def test_get_logsources_returns_list(self, client):
        """get_logsources returns properly formatted list."""
        from lm_mcp.tools.logsources import get_logsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "LinuxSyslog",
                            "description": "Linux syslog collection",
                            "appliesTo": "isLinux()",
                            "group": "Linux",
                            "logType": "syslog",
                            "collectMethod": "file",
                            "version": 1,
                        },
                        {
                            "id": 2,
                            "name": "WindowsEventLog",
                            "description": "Windows event log collection",
                            "appliesTo": "isWindows()",
                            "group": "Windows",
                            "logType": "eventlog",
                            "collectMethod": "wmi",
                            "version": 2,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_logsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["logsources"]) == 2
        assert data["logsources"][0]["name"] == "LinuxSyslog"
        assert data["logsources"][1]["name"] == "WindowsEventLog"

    @respx.mock
    async def test_get_logsources_handles_error(self, client):
        """get_logsources returns error response on API failure."""
        from lm_mcp.tools.logsources import get_logsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(401, json={"errorMessage": "Unauthorized"})
        )

        result = await get_logsources(client)

        assert len(result) == 1
        assert is_error_result(result)

    @respx.mock
    async def test_get_logsource_returns_details(self, client):
        """get_logsource returns single logsource details."""
        from lm_mcp.tools.logsources import get_logsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "LinuxSyslog",
                    "description": "Linux syslog collection",
                    "appliesTo": "isLinux()",
                    "group": "Linux",
                    "logType": "syslog",
                    "collectMethod": "file",
                    "version": 1,
                    "logFilePath": "/var/log/syslog",
                    "logFileFormat": "auto",
                    "filters": [],
                },
            )
        )

        result = await get_logsource(client, logsource_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 123
        assert data["name"] == "LinuxSyslog"
        assert data["log_file_path"] == "/var/log/syslog"

    @respx.mock
    async def test_get_logsource_not_found(self, client):
        """get_logsource returns error for missing logsource."""
        from lm_mcp.tools.logsources import get_logsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "LogSource not found"})
        )

        result = await get_logsource(client, logsource_id=999)

        assert is_error_result(result)

    async def test_create_logsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.logsources import create_logsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_logsource(client, definition={"name": "TestLS"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_logsource_posts_definition(self, client, writes_on):
        from lm_mcp.tools.logsources import create_logsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(200, json={"id": 10001, "name": "CustomLS"})
        )

        result = await create_logsource(
            client, definition={"name": "CustomLS", "collectionMethod": "script"}
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["logsource"]["id"] == 10001

    @respx.mock
    async def test_create_logsource_strips_id(self, client, writes_on):
        from lm_mcp.tools.logsources import create_logsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(200, json={"id": 10002, "name": "LS"}),
        )

        await create_logsource(client, definition={"id": 999, "name": "LS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    @respx.mock
    async def test_create_logsource_keeps_collection_method(self, client, writes_on):
        """The LogSource REST model names the field collectionMethod; the POST keeps it."""
        from lm_mcp.tools.logsources import create_logsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(200, json={"id": 10003, "name": "LS"}),
        )

        await create_logsource(
            client, definition={"name": "LS", "collectionMethod": "KUBERNETES_EVENT"}
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["collectionMethod"] == "KUBERNETES_EVENT"
        assert "collectMethod" not in request_body

    async def test_update_logsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.logsources import update_logsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_logsource(client, logsource_id=100, definition={"name": "Updated"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_logsource_puts_definition(self, client, writes_on):
        from lm_mcp.tools.logsources import update_logsource

        route = respx.put("https://test.logicmonitor.com/santaba/rest/setting/logsources/100").mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "UpdatedLS"})
        )

        result = await update_logsource(
            client, logsource_id=100, definition={"name": "UpdatedLS"}, confirm=True
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["logsource"]["id"] == 100

    async def test_update_logsource_without_confirm_errors_with_pointer(self, client, writes_on):
        from lm_mcp.tools.logsources import update_logsource

        result = await update_logsource(client, logsource_id=100, definition={"name": "X"})
        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text

    @respx.mock
    async def test_update_logsource_keeps_collection_method(self, client, writes_on):
        """The LogSource REST model names the field collectionMethod; the PUT keeps it."""
        from lm_mcp.tools.logsources import update_logsource

        route = respx.put("https://test.logicmonitor.com/santaba/rest/setting/logsources/100").mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "LS"}),
        )

        await update_logsource(
            client,
            logsource_id=100,
            definition={"name": "LS", "collectionMethod": "KUBERNETES_EVENT"},
            confirm=True,
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["collectionMethod"] == "KUBERNETES_EVENT"
        assert "collectMethod" not in request_body

    async def test_delete_logsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.logsources import delete_logsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_logsource(client, logsource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_logsource_not_found(self, client, writes_on):
        from lm_mcp.tools.logsources import delete_logsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_logsource(client, logsource_id=999)
        assert is_error_result(result)

    @respx.mock
    async def test_raw_returns_the_rest_object_and_default_projects(self, client):
        from lm_mcp.tools.logsources import get_logsource

        body = {
            "id": 123,
            "name": "Syslog",
            "appliesTo": "isLinux()",
            "logType": "syslog",
            "collectMethod": "syslog",
            "resourceMapping": [{"index": 0, "key": "system.hostname"}],
        }
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources/123").mock(
            return_value=httpx.Response(200, json=body)
        )

        raw = json.loads((await get_logsource(client, logsource_id=123, raw=True))[0].text)
        projected = json.loads((await get_logsource(client, logsource_id=123))[0].text)

        assert raw == body
        assert "logType" not in projected
        assert projected["log_type"] == body["logType"]


class TestTopologysourceCases:
    """R2.4: TopologySource cases the parametrized table tests do not cover."""

    async def test_create_topologysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.topologysources import create_topologysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_topologysource(client, definition={"name": "TestTS"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_topologysource_posts_definition(self, client, writes_on):
        from lm_mcp.tools.topologysources import create_topologysource

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 8001, "name": "CustomTS", "displayName": "Custom TopologySource"},
            )
        )

        result = await create_topologysource(
            client,
            definition={
                "name": "CustomTS",
                "collectionMethod": "script",
                "collectorAttribute": {},
            },
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["topologysource"]["id"] == 8001

    @respx.mock
    async def test_create_topologysource_strips_id(self, client, writes_on):
        from lm_mcp.tools.topologysources import create_topologysource

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources"
        ).mock(
            return_value=httpx.Response(200, json={"id": 8002, "name": "TS"}),
        )

        await create_topologysource(client, definition={"id": 999, "name": "TS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    @respx.mock
    async def test_create_topologysource_keeps_collection_method(self, client, writes_on):
        """The TopologySource REST model names the field collectionMethod; the POST keeps it."""
        from lm_mcp.tools.topologysources import create_topologysource

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources"
        ).mock(
            return_value=httpx.Response(200, json={"id": 10003, "name": "TS"}),
        )

        await create_topologysource(client, definition={"name": "TS", "collectionMethod": "script"})

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["collectionMethod"] == "script"
        assert "collectMethod" not in request_body

    async def test_update_topologysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.topologysources import update_topologysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_topologysource(
            client, topologysource_id=100, definition={"name": "Updated"}
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_topologysource_puts_definition(self, client, writes_on):
        from lm_mcp.tools.topologysources import update_topologysource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "UpdatedTS", "displayName": "Updated TopologySource"},
            )
        )

        result = await update_topologysource(
            client,
            topologysource_id=100,
            definition={"name": "UpdatedTS", "displayName": "Updated TopologySource"},
            confirm=True,
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["topologysource"]["id"] == 100

    async def test_update_topologysource_without_confirm_errors_with_pointer(
        self, client, writes_on
    ):
        from lm_mcp.tools.topologysources import update_topologysource

        result = await update_topologysource(
            client, topologysource_id=100, definition={"name": "X"}
        )
        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text

    @respx.mock
    async def test_update_topologysource_keeps_collection_method(self, client, writes_on):
        """The TopologySource REST model names the field collectionMethod; the PUT keeps it."""
        from lm_mcp.tools.topologysources import update_topologysource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/topologysources/100"
        ).mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "TS"}),
        )

        await update_topologysource(
            client,
            topologysource_id=100,
            definition={"name": "TS", "collectionMethod": "script"},
            confirm=True,
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["collectionMethod"] == "script"
        assert "collectMethod" not in request_body

    async def test_delete_topologysource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.topologysources import delete_topologysource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_topologysource(client, topologysource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_topologysource_not_found(self, client, writes_on):
        from lm_mcp.tools.topologysources import delete_topologysource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/topologysources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_topologysource(client, topologysource_id=999)
        assert is_error_result(result)

    @respx.mock
    async def test_raw_returns_the_rest_object_and_default_projects(self, client):
        from lm_mcp.tools.topologysources import get_topologysource

        body = _TOPOLOGYSOURCE
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/topologysources/1").mock(
            return_value=httpx.Response(200, json=body)
        )

        raw = json.loads((await get_topologysource(client, topologysource_id=1, raw=True))[0].text)
        projected = json.loads((await get_topologysource(client, topologysource_id=1))[0].text)

        assert raw == body
        assert "appliesTo" not in projected
        assert projected["applies_to"] == body["appliesTo"]


class TestDiagnosticsourceCases:
    """R2.4: DiagnosticSource cases the parametrized table tests do not cover."""

    @respx.mock
    async def test_get_diagnosticsources_returns_list(self, client):
        """get_diagnosticsources reads /setting/diagnosticsources and projects items."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 2,
                    "items": [
                        {
                            "id": 1,
                            "name": "Disk_Check",
                            "displayName": "Disk Check",
                            "description": "Check disk utilization",
                            "appliesTo": "isLinux()",
                            "group": "Storage",
                            "collectMethod": "script",
                            "tags": ["disk", "storage"],
                            "technicalNotes": "Uses df command",
                        },
                        {
                            "id": 2,
                            "name": "CPU_Check",
                            "displayName": "CPU Check",
                            "description": "Check CPU usage",
                            "group": "Compute",
                            "collectMethod": "script",
                            "tags": ["cpu"],
                        },
                    ],
                },
            )
        )

        result = await get_diagnosticsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert data["count"] == 2
        assert data["offset"] == 0
        assert data["has_more"] is False
        assert len(data["diagnosticsources"]) == 2
        names = {s["name"] for s in data["diagnosticsources"]}
        assert names == {"Disk_Check", "CPU_Check"}

    @respx.mock
    async def test_get_diagnosticsources_with_name_filter(self, client):
        """name_filter builds a server-side filter clause."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [
                        {
                            "id": 1,
                            "name": "Disk_Check",
                            "displayName": "Disk Check",
                            "group": "Storage",
                        }
                    ],
                },
            )
        )

        result = await get_diagnosticsources(client, name_filter="Disk")

        assert route.called
        filter_param = route.calls.last.request.url.params.get("filter", "")
        assert "name~" in filter_param
        assert "Disk" in filter_param

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["diagnosticsources"][0]["name"] == "Disk_Check"

    @respx.mock
    async def test_get_diagnosticsources_with_group_filter(self, client):
        """group_filter builds a server-side filter clause."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [
                        {
                            "id": 2,
                            "name": "CPU_Check",
                            "group": "Compute",
                        }
                    ],
                },
            )
        )

        result = await get_diagnosticsources(client, group_filter="Compute")

        assert route.called
        filter_param = route.calls.last.request.url.params.get("filter", "")
        assert "group~" in filter_param

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["diagnosticsources"][0]["group"] == "Compute"

    @respx.mock
    async def test_get_diagnosticsources_pagination_passed_to_api(self, client):
        """limit/offset map to size/offset query params."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources"
        ).mock(return_value=httpx.Response(200, json={"total": 200, "items": []}))

        result = await get_diagnosticsources(client, limit=25, offset=50)

        params = route.calls.last.request.url.params
        assert params.get("size") == "25"
        assert params.get("offset") == "50"

        data = json.loads(result[0].text)
        assert data["offset"] == 50
        assert data["has_more"] is True

    @respx.mock
    async def test_get_diagnosticsources_empty_response(self, client):
        """get_diagnosticsources handles an empty items list."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )

        result = await get_diagnosticsources(client)

        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["count"] == 0
        assert data["diagnosticsources"] == []

    @respx.mock
    async def test_get_diagnosticsources_handles_error(self, client):
        """get_diagnosticsources returns a structured error on API failure."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_diagnosticsources(client)

        assert is_error_result(result)

    @respx.mock
    async def test_get_diagnosticsource_returns_details(self, client):
        """get_diagnosticsource returns detailed source info."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources/10").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 10,
                    "name": "Disk_Check",
                    "displayName": "Disk Check",
                    "description": "Check disk utilization",
                    "appliesTo": "isLinux()",
                    "group": "Storage",
                    "collectMethod": "script",
                    "collectInterval": 300,
                    "tags": ["disk"],
                    "technicalNotes": "Uses df",
                    "dataPoints": [{"id": 1, "name": "usage", "type": 1, "description": "% used"}],
                },
            )
        )

        result = await get_diagnosticsource(client, source_id=10)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Disk_Check"
        assert data["display_name"] == "Disk Check"
        assert data["group"] == "Storage"
        assert data["collect_interval"] == 300
        assert len(data["datapoints"]) == 1
        assert data["datapoints"][0]["name"] == "usage"

    @respx.mock
    async def test_get_diagnosticsource_not_found(self, client):
        """get_diagnosticsource returns error for missing source."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await get_diagnosticsource(client, source_id=999)

        assert is_error_result(result)

    async def test_create_requires_write_permission(self, client, monkeypatch):
        """create_diagnosticsource is blocked when writes are disabled."""
        from lm_mcp.tools.diagnosticsources import create_diagnosticsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_diagnosticsource(client, definition={"name": "X"})

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_posts_definition(self, client, writes_on):
        """create_diagnosticsource posts the normalized definition."""
        from lm_mcp.tools.diagnosticsources import create_diagnosticsource

        route = respx.post(f"{BASE_URL}/setting/diagnosticsources").mock(
            return_value=httpx.Response(
                200, json={"id": 77, "name": "DiskDiag", "displayName": "Disk Diagnostics"}
            )
        )

        definition = {
            "name": "DiskDiag",
            "displayName": "Disk Diagnostics",
            "appliesTo": "isLinux()",
            "groovyScript": "println 'df -h'",
        }
        result = await create_diagnosticsource(client, definition=definition)

        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "DiskDiag"
        assert body["groovyScript"] == "println 'df -h'"
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["diagnosticsource"]["id"] == 77

    @respx.mock
    async def test_create_strips_id(self, client, writes_on):
        """create_diagnosticsource drops any id field from the definition."""
        from lm_mcp.tools.diagnosticsources import create_diagnosticsource

        route = respx.post(f"{BASE_URL}/setting/diagnosticsources").mock(
            return_value=httpx.Response(200, json={"id": 78, "name": "X"})
        )

        await create_diagnosticsource(client, definition={"id": 12, "name": "X"})

        body = json.loads(route.calls[0].request.content)
        assert "id" not in body

    @respx.mock
    async def test_create_handles_api_error(self, client, writes_on):
        """create_diagnosticsource surfaces 400 errors."""
        from lm_mcp.tools.diagnosticsources import create_diagnosticsource

        respx.post(f"{BASE_URL}/setting/diagnosticsources").mock(
            return_value=httpx.Response(400, json={"errorMessage": "name required"})
        )

        result = await create_diagnosticsource(client, definition={"displayName": "X"})

        assert "error" in result[0].text.lower()

    async def test_update_without_confirm_is_guarded(self, client, writes_on):
        """update_diagnosticsource without confirm=True returns INVALID_REQUEST."""
        from lm_mcp.tools.diagnosticsources import update_diagnosticsource

        result = await update_diagnosticsource(
            client, diagnosticsource_id=12, definition={"name": "X"}
        )

        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text

    @respx.mock
    async def test_update_with_confirm_puts_definition(self, client, writes_on):
        """update_diagnosticsource with confirm=True PUTs the full definition."""
        from lm_mcp.tools.diagnosticsources import update_diagnosticsource

        route = respx.put(f"{BASE_URL}/setting/diagnosticsources/12").mock(
            return_value=httpx.Response(200, json={"id": 12, "name": "Top CPU"})
        )

        definition = {"name": "Top CPU", "displayName": "Top CPU", "groovyScript": "x"}
        result = await update_diagnosticsource(
            client, diagnosticsource_id=12, definition=definition, confirm=True
        )

        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "Top CPU"
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_update_requires_write_permission(self, client, monkeypatch):
        """update_diagnosticsource is blocked when writes are disabled."""
        from lm_mcp.tools.diagnosticsources import update_diagnosticsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_diagnosticsource(
            client, diagnosticsource_id=12, definition={"name": "X"}, confirm=True
        )

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_not_found(self, client, writes_on):
        """delete_diagnosticsource surfaces 404."""
        from lm_mcp.tools.diagnosticsources import delete_diagnosticsource

        respx.get(f"{BASE_URL}/setting/diagnosticsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_diagnosticsource(client, diagnosticsource_id=999)

        assert "error" in result[0].text.lower()

    @respx.mock
    async def test_raw_returns_the_rest_object_and_default_projects(self, client):
        from lm_mcp.tools.diagnosticsources import get_diagnosticsource

        body = {
            "id": 10,
            "name": "Top CPU",
            "displayName": "Top CPU",
            "appliesTo": "isLinux()",
            "groovyScript": "println 'top'",
            "scriptType": "groovy",
        }
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources/10").mock(
            return_value=httpx.Response(200, json=body)
        )

        raw = json.loads((await get_diagnosticsource(client, source_id=10, raw=True))[0].text)
        projected = json.loads((await get_diagnosticsource(client, source_id=10))[0].text)

        assert raw == body
        assert "displayName" not in projected
        assert projected["display_name"] == body["displayName"]


class TestRemediationsourceCases:
    """R2.4: RemediationSource cases the parametrized table tests do not cover."""

    @respx.mock
    async def test_get_remediationsources_returns_list(self, client):
        """get_remediationsources reads /setting/remediationsources and projects items."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 2,
                    "items": [
                        {
                            "id": 1,
                            "name": "Restart_Service",
                            "displayName": "Restart Service",
                            "description": "Restart a failed service",
                            "appliesTo": "isLinux()",
                            "group": "Services",
                            "collectMethod": "script",
                            "tags": ["restart", "service"],
                            "technicalNotes": "Uses systemctl",
                        },
                        {
                            "id": 2,
                            "name": "Clear_Disk",
                            "displayName": "Clear Disk",
                            "description": "Clear temp files",
                            "group": "Storage",
                            "collectMethod": "script",
                            "tags": ["disk", "cleanup"],
                        },
                    ],
                },
            )
        )

        result = await get_remediationsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert data["count"] == 2
        assert data["offset"] == 0
        assert data["has_more"] is False
        names = {s["name"] for s in data["remediationsources"]}
        assert names == {"Restart_Service", "Clear_Disk"}

    @respx.mock
    async def test_get_remediationsources_with_name_filter(self, client):
        """name_filter builds a server-side filter clause."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/remediationsources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [{"id": 1, "name": "Restart_Service", "group": "Services"}],
                },
            )
        )

        result = await get_remediationsources(client, name_filter="Restart")

        assert route.called
        filter_param = route.calls.last.request.url.params.get("filter", "")
        assert "name~" in filter_param
        assert "Restart" in filter_param

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["remediationsources"][0]["name"] == "Restart_Service"

    @respx.mock
    async def test_get_remediationsources_with_group_filter(self, client):
        """group_filter builds a server-side filter clause."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/remediationsources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [{"id": 2, "name": "Clear_Disk", "group": "Storage"}],
                },
            )
        )

        result = await get_remediationsources(client, group_filter="Storage")

        assert route.called
        filter_param = route.calls.last.request.url.params.get("filter", "")
        assert "group~" in filter_param

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["remediationsources"][0]["group"] == "Storage"

    @respx.mock
    async def test_get_remediationsources_pagination_passed_to_api(self, client):
        """limit/offset map to size/offset query params."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/remediationsources"
        ).mock(return_value=httpx.Response(200, json={"total": 200, "items": []}))

        result = await get_remediationsources(client, limit=25, offset=50)

        params = route.calls.last.request.url.params
        assert params.get("size") == "25"
        assert params.get("offset") == "50"

        data = json.loads(result[0].text)
        assert data["offset"] == 50
        assert data["has_more"] is True

    @respx.mock
    async def test_get_remediationsources_empty_response(self, client):
        """get_remediationsources handles an empty items list."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )

        result = await get_remediationsources(client)

        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["count"] == 0
        assert data["remediationsources"] == []

    @respx.mock
    async def test_get_remediationsources_handles_error(self, client):
        """get_remediationsources returns a structured error on API failure."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_remediationsources(client)

        assert is_error_result(result)

    @respx.mock
    async def test_get_remediationsource_returns_details(self, client):
        """get_remediationsource returns detailed source info."""
        from lm_mcp.tools.remediationsources import get_remediationsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources/10").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 10,
                    "name": "Restart_Service",
                    "displayName": "Restart Service",
                    "description": "Restart a systemd service",
                    "appliesTo": "isLinux()",
                    "group": "Services",
                    "collectMethod": "script",
                    "collectInterval": 300,
                    "tags": ["restart"],
                    "technicalNotes": "Uses systemctl restart",
                    "groovyScript": "println 'restart'",
                },
            )
        )

        result = await get_remediationsource(client, source_id=10)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Restart_Service"
        assert data["display_name"] == "Restart Service"
        assert data["group"] == "Services"
        assert data["collect_interval"] == 300
        assert data["groovy_script"] == "println 'restart'"

    @respx.mock
    async def test_get_remediationsource_not_found(self, client):
        """get_remediationsource returns error for missing source."""
        from lm_mcp.tools.remediationsources import get_remediationsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await get_remediationsource(client, source_id=999)

        assert is_error_result(result)

    async def test_create_requires_write_permission(self, client, monkeypatch):
        """create_remediationsource is blocked when writes are disabled."""
        from lm_mcp.tools.remediationsources import create_remediationsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_remediationsource(client, definition={"name": "X"})

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_posts_definition(self, client, writes_on):
        """create_remediationsource posts the normalized definition."""
        from lm_mcp.tools.remediationsources import create_remediationsource

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/remediationsources"
        ).mock(
            return_value=httpx.Response(
                200, json={"id": 88, "name": "RestartSvc", "displayName": "Restart Service"}
            )
        )

        definition = {
            "name": "RestartSvc",
            "displayName": "Restart Service",
            "appliesTo": "false()",
            "groovyScript": "println 'restart'",
        }
        result = await create_remediationsource(client, definition=definition)

        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "RestartSvc"
        assert "id" not in body
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["remediationsource"]["id"] == 88

    @respx.mock
    async def test_create_handles_api_error(self, client, writes_on):
        """create_remediationsource surfaces 400 errors."""
        from lm_mcp.tools.remediationsources import create_remediationsource

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/remediationsources").mock(
            return_value=httpx.Response(400, json={"errorMessage": "name required"})
        )

        result = await create_remediationsource(client, definition={"displayName": "X"})

        assert "error" in result[0].text.lower()

    async def test_update_without_confirm_is_guarded(self, client, writes_on):
        """update_remediationsource without confirm=True returns INVALID_REQUEST."""
        from lm_mcp.tools.remediationsources import update_remediationsource

        result = await update_remediationsource(
            client, remediationsource_id=3, definition={"name": "X"}
        )

        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text

    @respx.mock
    async def test_update_with_confirm_puts_definition(self, client, writes_on):
        """update_remediationsource with confirm=True PUTs the full definition."""
        from lm_mcp.tools.remediationsources import update_remediationsource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/remediationsources/3"
        ).mock(return_value=httpx.Response(200, json={"id": 3, "name": "RestartSvc"}))

        definition = {"name": "RestartSvc", "displayName": "Restart", "groovyScript": "x"}
        result = await update_remediationsource(
            client, remediationsource_id=3, definition=definition, confirm=True
        )

        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "RestartSvc"
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_update_requires_write_permission(self, client, monkeypatch):
        """update_remediationsource is blocked when writes are disabled."""
        from lm_mcp.tools.remediationsources import update_remediationsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_remediationsource(
            client, remediationsource_id=3, definition={"name": "X"}, confirm=True
        )

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_not_found(self, client, writes_on):
        """delete_remediationsource surfaces 404."""
        from lm_mcp.tools.remediationsources import delete_remediationsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_remediationsource(client, remediationsource_id=999)

        assert "error" in result[0].text.lower()

    @respx.mock
    async def test_raw_returns_the_rest_object_and_default_projects(self, client):
        from lm_mcp.tools.remediationsources import get_remediationsource

        body = {
            "id": 10,
            "name": "RestartSvc",
            "displayName": "Restart service",
            "appliesTo": "false()",
            "groovyScript": "println 'restart'",
            "accessGroupIds": [1],
        }
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources/10").mock(
            return_value=httpx.Response(200, json=body)
        )

        raw = json.loads((await get_remediationsource(client, source_id=10, raw=True))[0].text)
        projected = json.loads((await get_remediationsource(client, source_id=10))[0].text)

        assert raw == body
        assert "displayName" not in projected
        assert projected["display_name"] == body["displayName"]
