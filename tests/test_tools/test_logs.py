# Description: Tests for the LM Logs read tools: pipelines, tracked queries, query groups,
# Description: partitions and usage, against live reads of a portal kept in a fixture.

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from tests.envelope import envelope

BASE = "https://test.logicmonitor.com/santaba/rest"

# Answers of a sandbox portal at X-Version 3 on 2026-11-11, every key as read. The
# *_size1_offset1 entries answered size=1&offset=1: /logpipelines returned all four rows
# (it applied neither), /log/logquerygroups an empty page under total 1.
LIVE = json.loads((Path(__file__).parent.parent / "fixtures" / "log_reads.json").read_text())


@pytest.fixture
def client():
    return LogicMonitorClient(base_url=BASE, auth=BearerAuth("test-token"), timeout=30)


def _body(result: list) -> dict:
    return json.loads(result[0].text)


class TestGetLogPipelines:
    @respx.mock
    async def test_reads_every_pipeline_in_one_call_with_no_paging(self, client):
        from lm_mcp.tools.logs import get_log_pipelines

        route = respx.get(f"{BASE}/logpipelines").mock(
            return_value=httpx.Response(200, json=LIVE["logpipelines"])
        )

        body = _body(await get_log_pipelines(client))

        assert route.call_count == 1
        assert dict(route.calls.last.request.url.params) == {}
        assert body["total"] == 4
        assert [p["name"] for p in body["pipelines"]] == [
            "demo pipeline",
            "OpenShift AlertManager - All",
            "OpenShift AlertManager - Critical",
            "OpenShift AlertManager - Platform",
        ]
        assert body["pipelines"][1] == {
            "id": "3",
            "name": "OpenShift AlertManager - All",
            "description": "All alerts from OpenShift Prometheus AlertManager",
            "query": 'source_type="prometheus_alertmanager"',
            "partitions": ["default"],
        }
        assert body["pipelines"][0]["description"] is None
        assert body["pipelines"][0]["partitions"] == []

    @respx.mock
    async def test_a_refused_read_is_the_error_envelope(self, client):
        from lm_mcp.tools.logs import get_log_pipelines

        respx.get(f"{BASE}/logpipelines").mock(
            return_value=httpx.Response(403, json={"errorMessage": "Permission denied"})
        )

        assert envelope(await get_log_pipelines(client))["code"] == "AUTH_FAILED"


class TestGetTrackedLogQueries:
    @respx.mock
    async def test_pages_tracked_log_and_passes_rows_through(self, client):
        from lm_mcp.tools.logs import get_tracked_log_queries

        route = respx.get(f"{BASE}/tracked/log").mock(
            return_value=httpx.Response(200, json=LIVE["tracked_log"])
        )

        body = _body(await get_tracked_log_queries(client, limit=25, offset=5))

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("25", "5")
        assert body == {
            "total": 0,
            "count": 0,
            "offset": 5,
            "has_more": False,
            "tracked_queries": [],
        }


class TestGetLogQueryGroups:
    @respx.mock
    async def test_projects_each_group(self, client):
        from lm_mcp.tools.logs import get_log_query_groups

        route = respx.get(f"{BASE}/log/logquerygroups").mock(
            return_value=httpx.Response(200, json=LIVE["logquerygroups"])
        )

        body = _body(await get_log_query_groups(client))

        assert route.calls.last.request.url.params["size"] == "50"
        assert body["total"] == 1
        assert body["has_more"] is False
        assert body["query_groups"] == [
            {
                "id": 1,
                "name": "Ungrouped",
                "description": "Ungrouped folder",
                "parent_id": 0,
                "owner_id": 0,
                "group_type": "PRIVATE",
                "user_permission": "WRITE",
                "log_queries": [],
            }
        ]

    @respx.mock
    async def test_a_group_s_saved_queries_pass_through_as_read(self, client):
        from lm_mcp.tools.logs import get_log_query_groups

        # The live group holds no query; this entry takes the swagger Log Query model's
        # required id and version plus its label and query.
        live = json.loads(json.dumps(LIVE["logquerygroups"]))
        saved = {"id": 7, "version": "2", "label": "oom kills", "query": '"OOMKilled"'}
        live["items"][0]["logQuery"] = [saved]
        respx.get(f"{BASE}/log/logquerygroups").mock(return_value=httpx.Response(200, json=live))

        body = _body(await get_log_query_groups(client))

        assert body["query_groups"][0]["log_queries"] == [saved]

    @respx.mock
    async def test_an_offset_past_the_end_is_an_empty_page(self, client):
        from lm_mcp.tools.logs import get_log_query_groups

        respx.get(f"{BASE}/log/logquerygroups").mock(
            return_value=httpx.Response(200, json=LIVE["logquerygroups_size1_offset1"])
        )

        body = _body(await get_log_query_groups(client, limit=1, offset=1))

        assert (body["total"], body["count"], body["has_more"]) == (1, 0, False)
        assert body["query_groups"] == []


class TestGetLogPartitions:
    @respx.mock
    async def test_projects_each_partition_with_its_active_contract(self, client):
        from lm_mcp.tools.logs import get_log_partitions

        route = respx.get(f"{BASE}/log/partitions").mock(
            return_value=httpx.Response(200, json=LIVE["partitions"])
        )

        body = _body(await get_log_partitions(client, limit=1))

        assert route.calls.last.request.url.params["size"] == "1"
        paused, default = body["partitions"]
        assert paused == {
            "id": "3",
            "name": "k8JobLogs",
            "description": "",
            "tenant": "argus",
            "active": False,
            "paused_at": 1777060505648,
            "priority": 0,
            "criteria": None,
            "active_contract": {
                "id": 31,
                "state": "active",
                "sku": "LG3",
                "retention": 35,
                "usage_limit": "0B",
                "stop_ingestion_on_limit": False,
                "limit_reached_at": None,
                "from_epoch": 1793491200,
                "to_epoch": 1796083200,
            },
        }
        assert (default["name"], default["active"], default["paused_at"]) == (
            "default",
            True,
            None,
        )

    @respx.mock
    async def test_a_partition_without_an_active_contract_reads_none(self, client):
        from lm_mcp.tools.logs import get_log_partitions

        live = json.loads(json.dumps(LIVE["partitions"]))
        live["items"][0]["activeContract"] = None
        respx.get(f"{BASE}/log/partitions").mock(return_value=httpx.Response(200, json=live))

        body = _body(await get_log_partitions(client))

        assert body["partitions"][0]["active_contract"] is None


class TestGetLogUsage:
    @respx.mock
    async def test_reports_the_usage_figure_as_read(self, client):
        from lm_mcp.tools.logs import get_log_usage

        route = respx.get(f"{BASE}/log/usage").mock(
            return_value=httpx.Response(200, json=LIVE["usage"])
        )

        body = _body(await get_log_usage(client))

        assert route.call_count == 1
        assert body == {"usage": 503681379607}


class TestDispatch:
    @respx.mock
    async def test_execute_tool_serves_get_log_partitions_through_the_bound_client(
        self, client, monkeypatch
    ):
        from lm_mcp.server import execute_tool

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        respx.get(f"{BASE}/log/partitions").mock(
            return_value=httpx.Response(200, json=LIVE["partitions"])
        )

        with patch("lm_mcp.server._client", client):
            result = await execute_tool("get_log_partitions", {"limit": 10})

        assert [p["name"] for p in _body(result)["partitions"]] == ["k8JobLogs", "default"]
