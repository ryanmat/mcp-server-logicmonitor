# Description: Tests for the Edwin AI query tools and the filterCondition builder.
# Description: Rows are trimmed from the 2026-11-10 probe of lmryanmatuszewski.dexda.ai.

import json
import logging
from pathlib import Path

import httpx
import pytest
import respx

from lm_mcp.client.edwin import build_edwin_client
from lm_mcp.config import reset_config
from lm_mcp.logging import log_write_operation
from lm_mcp.tools.edwin import (
    edwin_run_tool,
    equals,
    filter_condition,
    get_edwin_alert_volume,
    get_edwin_insight,
    get_edwin_insights,
    get_edwin_metadata,
    get_edwin_records,
    get_edwin_tools,
    in_,
    list_contains,
    within,
)

HOST = "https://lmryanmatuszewski.dexda.ai"
RECORDS = f"{HOST}/ui/query/records"
METRICS = f"{HOST}/ui/query/metrics"

# Insight rows from POST /ui/query/records on lmryanmatuszewski.dexda.ai, 2026-11-10
# (docs/validation/probes-2026-11.md, Step 54): 26 of the 52 live fields of ANALYZED and
# 16 of the 30 of PLAIN. Each keeps the fields get_edwin_insights projects plus some it
# drops (genAi.logs_summary, meta.alertCurrentSeverities, ml.uiResult), so the tests see
# them removed. Every string value over 90 characters is cut to its first 90 except
# meta.link, kept whole. ANALYZED carries Edwin's genAi analysis; PLAIN is the newest
# insight in the window and has none yet.
ANALYZED = {
    "_id": "correlation_36fa3f53-e608-4192-aeca-e0097d2a1e94_1794020047392",
    "genAi.contributing_factors": '["Successful scheduling and container starts for two pods '
    "occurred near the alert sequence",
    "genAi.evidence": '["Host Status alerts reported 308 seconds without data for '
    "`retina-agent-rwpch-pod-kube-sy",
    "genAi.impact": "- **Issue Summary:** Monitoring visibility was lost for three Retina agent "
    "pods.\n- **Impac",
    "genAi.logs_summary": '{"ci_summaries":[{"event_ci":"retina-agent-j4sjn-pod-kube-system-'
    'rm-aks-cluster","referenc',
    "genAi.remediation": "**Immediate Fix**\n- Verify current pod status and whether each "
    "monitored hostname resolves",
    "genAi.rootCause": "## Root Cause Analysis\n\nThe most likely immediate cause was loss of "
    "collector-to-pod monit",
    "genAi.similar_incidents": "[]",
    "genAi.summary": "Monitoring lost data or ping results for three Retina agent pods. Logs "
    "show successful sch",
    "genAi.timeline": "- 2026-11-07 02:50:02 UTC — `rwpch` Host Status alert triggered "
    "for missing data.\n- 2026-1",
    "genAi.title": "Retina Agent Pods Lost Monitoring Reachability",
    "insightDetails.workflowState": "incident-resolved",
    "meta.alertCurrentSeverities": '{"retina-agent-rwpch-pod-kube-system-rm-aks-cluster_event_'
    "LogicMonitor_Ping_average.Ping.d",
    "meta.alertKeyList": "retina-agent-rwpch-pod-kube-system-rm-aks-cluster_event_LogicMonitor_"
    "HostStatus_idleInterv",
    "meta.createdTimestamp": 1794020047392,
    "meta.displayId": "EDN000029424",
    "meta.firstEventTimestamp": 1794019782000,
    "meta.lastEventTimestamp": 1794021876000,
    "meta.link": "https://lmryanmatuszewski.dexda.ai/link/insight/correlation_36fa3f53-e608-"
    "4192-aeca-e0097d2a1e94_1794020047392",
    "meta.state": "cleared",
    "meta.totalAlerts": 11,
    "meta.updatedTimestamp": 1794022352546,
    "ml.causalCI": "retina-agent-rwpch-pod-kube-system-rm-aks-cluster",
    "ml.impactedCIList": "retina-agent-tv7sz-pod-kube-system-rm-aks-cluster retina-agent-rwpch-"
    "pod-kube-system-rm-ak",
    "ml.insightSeverity": 0,
    "ml.uiResult": '{"modelResults":[{"modelId":"86f99e3e-4bd6-4640-b910-4665cdf10978",'
    '"modelType":"correlatio',
}
PLAIN = {
    "_id": "correlation_6eefa6d5-e9f8-4579-a226-fee870081f5c_1794311918529",
    "insightDetails.workflowState": "closed",
    "meta.alertCurrentSeverities": '{"email-deploy-otel-demo-rm-aro-cluster_event_LogicMonitor_'
    "Kubernetes_Deployment_Config_Di",
    "meta.alertKeyList": "email-deploy-otel-demo-rm-aro-cluster_event_LogicMonitor_Kubernetes_"
    "Deployment_Config_Diff",
    "meta.createdTimestamp": 1794311918529,
    "meta.displayId": "EDN000029227",
    "meta.firstEventTimestamp": 1794311325000,
    "meta.lastEventTimestamp": 1794312495000,
    "meta.link": "https://lmryanmatuszewski.dexda.ai/link/insight/correlation_6eefa6d5-e9f8-"
    "4579-a226-fee870081f5c_1794311918529",
    "meta.state": "cleared",
    "meta.totalAlerts": 2,
    "meta.updatedTimestamp": 1794315518529,
    "ml.causalCI": "email-deploy-otel-demo-rm-aro-cluster",
    "ml.impactedCIList": "email-deploy-otel-demo-rm-aro-cluster flagd-deploy-otel-demo-rm-aro-"
    "cluster",
    "ml.insightSeverity": 0,
    "ml.uiResult": '{"modelResults":[{"modelId":"92564c7d-309f-4614-bf90-bfbe050cd6e3",'
    '"modelType":"correlatio',
}

# The fields an insight list row carries (spec R3.1), each timestamp with its ISO twin.
PROJECTED = {
    "_id",
    "meta.displayId",
    "meta.state",
    "insightDetails.workflowState",
    "ml.insightSeverity",
    "ml.causalCI",
    "ml.impactedCIList",
    "meta.totalAlerts",
    "meta.alertKeyList",
    "meta.link",
    "meta.createdTimestamp",
    "meta.createdTimestamp_iso",
    "meta.updatedTimestamp",
    "meta.updatedTimestamp_iso",
    "meta.firstEventTimestamp",
    "meta.firstEventTimestamp_iso",
    "meta.lastEventTimestamp",
    "meta.lastEventTimestamp_iso",
}
GENAI = {
    "genAi.title",
    "genAi.summary",
    "genAi.rootCause",
    "genAi.impact",
    "genAi.timeline",
    "genAi.remediation",
    "genAi.evidence",
    "genAi.contributing_factors",
    "genAi.similar_incidents",
}

# Error bodies from the 2026-11-10 probe.
BODY_403 = {
    "code": 403,
    "message": "User not authorized.",
    "id": "40d471e067f52571fc3b6968845efc09-27875ebf58a0f013",
}
BODY_404 = {
    "code": 404,
    "message": "Record not found",
    "id": "ea0ec09740098361e17d76db82e1b5d5-918b90c8c4cc5e34",
}


def records_response(*rows: dict, count: int) -> httpx.Response:
    return httpx.Response(
        200, json={"meta": {"count": count, "recordType": "insights"}, "results": list(rows)}
    )


def payload(result: list) -> dict:
    return json.loads(result[0].text)


@pytest.fixture
def client(monkeypatch):
    """The Edwin client as the server builds it, with the token exchange answered."""
    monkeypatch.setenv("LM_PORTAL", "lmryanmatuszewski.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "lm-bearer-token-fixture")
    monkeypatch.setenv("EDWIN_CLIENT_ID", "edwin-client-id-fixture")
    monkeypatch.setenv("EDWIN_CLIENT_TOKEN", "edwin-secret-fix")
    monkeypatch.delenv("EDWIN_HOST", raising=False)
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{HOST}/auth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "eyJhbGciOiJSUzI1NiJ9.fixture.sig",
                    "token_type": "Bearer",
                    "expires_in": 1799,
                },
            )
        )
        edwin = build_edwin_client("lmryanmatuszewski.logicmonitor.com")
        assert edwin is not None
        yield edwin, router


class TestFilterBuilder:
    def test_no_condition_is_an_empty_and_never_null(self):
        assert filter_condition() == {
            "schemaName": "filterCondition",
            "schemaVersion": "4",
            "expression": {"AND": []},
        }

    def test_within_matches_the_captured_request(self):
        # edwin-fullscope-records-insights-within.json, request.filter (2026-11-07).
        captured = {
            "schemaName": "filterCondition",
            "schemaVersion": "4",
            "expression": {
                "AND": [
                    {
                        "WITHIN": [
                            {"type": "long", "field": "meta.createdTimestamp"},
                            {"duration": 7, "unit": "day"},
                        ]
                    }
                ]
            },
        }
        assert filter_condition(within("meta.createdTimestamp", 7, "day")) == captured

    def test_equals_matches_the_captured_request(self):
        # edwin-fullscope-records-insights-and-equals.json, request.filter.expression.AND[0].
        assert equals("meta.state", "OPEN") == {
            "EQUALS": [{"type": "string", "field": "meta.state"}, "OPEN"]
        }

    def test_in_carries_the_type_and_the_value_list(self):
        assert in_("ml.insightSeverity", [4, 5], "long") == {
            "IN": [{"type": "long", "field": "ml.insightSeverity"}, [4, 5]]
        }

    def test_list_contains(self):
        assert list_contains("ml.impactedCIList", "flagd-deploy-otel-demo-rm-aro-cluster") == {
            "LIST_CONTAINS": [
                {"type": "string", "field": "ml.impactedCIList"},
                "flagd-deploy-otel-demo-rm-aro-cluster",
            ]
        }


class TestGetEdwinInsights:
    async def test_default_request_is_the_last_24_hours_newest_first(self, client):
        edwin, router = client
        route = router.post(RECORDS).mock(return_value=records_response(PLAIN, count=4))

        result = await get_edwin_insights(edwin)

        assert json.loads(route.calls.last.request.content) == {
            "source": "insights",
            "env": {"timezone": "UTC"},
            "filter": {
                "schemaName": "filterCondition",
                "schemaVersion": "4",
                "expression": {
                    "AND": [
                        {
                            "WITHIN": [
                                {"type": "long", "field": "meta.createdTimestamp"},
                                {"duration": 24, "unit": "hour"},
                            ]
                        }
                    ]
                },
            },
            "columns": None,
            "groups": None,
            "order": [{"field": "meta.createdTimestamp", "type": "desc", "size": None}],
            "size": 10,
        }
        body = payload(result)
        assert body["count"] == 1
        assert body["total"] == 4
        assert body["has_more"] is True

    async def test_each_filter_lands_in_the_expression(self, client):
        edwin, router = client
        route = router.post(RECORDS).mock(return_value=records_response(count=0))

        result = await get_edwin_insights(
            edwin,
            hours=6,
            state="active",
            severity=[4, 5],
            causal_ci="email-deploy-otel-demo-rm-aro-cluster",
            impacted_ci="flagd-deploy-otel-demo-rm-aro-cluster",
            limit=3,
        )

        sent = json.loads(route.calls.last.request.content)
        assert sent["filter"]["expression"]["AND"] == [
            {
                "WITHIN": [
                    {"type": "long", "field": "meta.createdTimestamp"},
                    {"duration": 6, "unit": "hour"},
                ]
            },
            {"EQUALS": [{"type": "string", "field": "meta.state"}, "active"]},
            {"IN": [{"type": "long", "field": "ml.insightSeverity"}, [4, 5]]},
            {
                "EQUALS": [
                    {"type": "string", "field": "ml.causalCI"},
                    "email-deploy-otel-demo-rm-aro-cluster",
                ]
            },
            {
                "LIST_CONTAINS": [
                    {"type": "string", "field": "ml.impactedCIList"},
                    "flagd-deploy-otel-demo-rm-aro-cluster",
                ]
            },
        ]
        assert sent["size"] == 3
        body = payload(result)
        assert body == {"insights": [], "count": 0, "total": 0, "has_more": False}

    async def test_rows_carry_the_spec_fields_verbatim_with_iso_twins(self, client):
        edwin, router = client
        router.post(RECORDS).mock(return_value=records_response(ANALYZED, PLAIN, count=2))

        body = payload(await get_edwin_insights(edwin, hours=168))

        analyzed, plain = body["insights"]
        assert set(analyzed) == PROJECTED | GENAI
        assert set(plain) == PROJECTED
        for key in PROJECTED | GENAI:
            if not key.endswith("_iso"):
                assert analyzed[key] == ANALYZED[key]
        assert analyzed["meta.createdTimestamp_iso"] == "2026-11-07T02:54:07.392+00:00"
        assert analyzed["meta.firstEventTimestamp_iso"] == "2026-11-07T02:49:42.000+00:00"
        assert plain["meta.updatedTimestamp_iso"] == "2026-11-10T12:58:38.529+00:00"
        assert body["has_more"] is False

    @pytest.mark.parametrize(
        ("kwargs", "word"),
        [({"hours": 0}, "hours"), ({"limit": 0}, "limit"), ({"limit": 51}, "limit")],
    )
    async def test_out_of_range_arguments_are_refused_before_any_request(
        self, client, kwargs, word
    ):
        edwin, router = client
        route = router.post(RECORDS).mock(return_value=records_response(count=0))

        body = payload(await get_edwin_insights(edwin, **kwargs))

        assert route.call_count == 0
        assert body["error"]["code"] == "INVALID_REQUEST"
        assert word in body["error"]["message"]

    async def test_a_403_is_scope_missing_naming_query_records(self, client):
        edwin, router = client
        router.post(RECORDS).mock(return_value=httpx.Response(403, json=BODY_403))

        body = payload(await get_edwin_insights(edwin))

        assert body["error"]["code"] == "SCOPE_MISSING"
        assert "query_records" in body["error"]["message"]


class TestGetEdwinInsight:
    async def test_reads_one_insight_by_id_with_iso_twins(self, client):
        edwin, router = client
        route = router.get(f"{HOST}/ui/query/record/insights/{ANALYZED['_id']}").mock(
            return_value=records_response(ANALYZED, count=1)
        )

        body = payload(await get_edwin_insight(edwin, insight_id=ANALYZED["_id"]))

        assert route.call_count == 1
        for key, value in ANALYZED.items():
            assert body[key] == value
        assert body["meta.createdTimestamp_iso"] == "2026-11-07T02:54:07.392+00:00"
        assert body["meta.lastEventTimestamp_iso"] == "2026-11-07T03:24:36.000+00:00"

    async def test_a_404_is_not_found(self, client):
        edwin, router = client
        router.get(f"{HOST}/ui/query/record/insights/does-not-exist").mock(
            return_value=httpx.Response(404, json=BODY_404)
        )

        body = payload(await get_edwin_insight(edwin, insight_id="does-not-exist"))

        assert body["error"]["code"] == "NOT_FOUND"
        assert "Record not found" in body["error"]["message"]

    async def test_an_id_with_a_slash_is_refused_before_any_request(self, client):
        edwin, router = client
        route = router.get(url__startswith=f"{HOST}/ui/query/record/").mock(
            return_value=records_response(ANALYZED, count=1)
        )

        body = payload(await get_edwin_insight(edwin, insight_id="insight/1"))

        assert route.call_count == 0
        assert body["error"]["code"] == "INVALID_REQUEST"


# An alert and an event row from POST /ui/query/records on lmryanmatuszewski.dexda.ai,
# 2026-11-10 (docs/validation/probes-2026-11.md, Step 55): kept fields only, strings
# over 90 characters cut to their first 90. Live rows carry 107 to 125 fields.
ALERT = {
    "_id": "observability-observatorium-api-7974845f49-rs-open-cluster-management-"
    "observability-rm-aro",
    "alertDetails.alertState": "cleared",
    "alertDetails.currentSeverity": 0,
    "alertDetails.workflowState": "new",
    "cf.eventCI": "observability-observatorium-api-7974845f49-rs-open-cluster-management-"
    "observability-rm-aro",
    "cf.eventName": "DifferenceCheck.Kubernetes ReplicaSet Config.dataSourceAlert",
    "cf.eventSeverity": 2,
    "cf.eventTime": "2026-11-10T19:04:43.00000Z",
    "meta.createdTimestamp": 1794337502820,
    "meta.link": "https://lmryanmatuszewski.dexda.ai/link/alert/observability-observatorium-"
    "api-7974845f49-r",
    "extra.lm_system_deviceid": "532100",
    "extra.lm_display_name": "observability-observatorium-api-7974845f49-rs-open-cluster-"
    "management-observability-rm-aro",
    "raw.sourceRecord": '{"sdtIds":"","resourceId":4361829,"threshold":"= 1",'
    '"type":"dataSourceAlert","startEpoch":',
}
EVENT = {
    "_id": "argocd-notifications-controller-5754577c7b-nf2kk-pod-argocd-rm-aro-cluster_event_"
    "LogicMoni",
    "cf.eventCI": "argocd-notifications-controller-5754577c7b-nf2kk-pod-argocd-rm-aro-cluster",
    "cf.eventName": "idleInterval.Host Status.dataSourceAlert",
    "cf.eventSeverity": 5,
    "cf.eventTime": "2026-11-10T19:20:22.00000Z",
    "meta.eventTimestamp": 1794338422000,
    "extra.lm_kubernetes_spec_nodeselector_appliesto": "kubernetes.label.kubernetes.io/os "
    '== "linux"',
}

# POST /ui/query/metrics answers from the same probe: alerts in the last 24 hours, COUNT
# of meta.rowKey grouped by hour (first 3 of 25 buckets) and by alertDetails.alertState.
VOLUME_BY_HOUR = {
    "meta": {"recordType": "alerts", "count": 141},
    "results": [[1794250800000, [10]], [1794254400000, [2]], [1794258000000, [3]]],
}
VOLUME_BY_STATE = {
    "meta": {"recordType": "alerts", "count": 141},
    "results": [["cleared", [73]], ["active", [6]]],
}

# GET /metadata from the 2026-11-07 capture (edwin-samples/edwin-metadata.json), all 29
# record types with at most three fields and two extra.* fields each.
METADATA = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "edwin_metadata.json").read_text()
)


class TestGetEdwinRecords:
    @pytest.mark.parametrize(
        ("source", "time_field", "row"),
        [("alerts", "meta.createdTimestamp", ALERT), ("events", "meta.eventTimestamp", EVENT)],
    )
    async def test_request_windows_and_orders_on_the_source_time_field(
        self, client, source, time_field, row
    ):
        edwin, router = client
        route = router.post(RECORDS).mock(
            return_value=httpx.Response(
                200, json={"meta": {"count": 141, "recordType": source}, "results": [row]}
            )
        )

        body = payload(await get_edwin_records(edwin, source=source))

        assert json.loads(route.calls.last.request.content) == {
            "source": source,
            "env": {"timezone": "UTC"},
            "filter": {
                "schemaName": "filterCondition",
                "schemaVersion": "4",
                "expression": {
                    "AND": [
                        {
                            "WITHIN": [
                                {"type": "long", "field": time_field},
                                {"duration": 24, "unit": "hour"},
                            ]
                        }
                    ]
                },
            },
            "columns": None,
            "groups": None,
            "order": [{"field": time_field, "type": "desc", "size": None}],
            "size": 10,
        }
        assert body["source"] == source
        assert (body["count"], body["total"], body["has_more"]) == (1, 141, True)

    async def test_filter_order_and_limit_pass_through(self, client):
        edwin, router = client
        route = router.post(RECORDS).mock(
            return_value=httpx.Response(200, json={"meta": {"count": 0}, "results": []})
        )
        condition = equals("alertDetails.alertState", "active")
        order = [{"field": "cf.eventSeverity", "type": "desc", "size": None}]

        await get_edwin_records(
            edwin, source="alerts", hours=6, filter=condition, order=order, limit=25
        )

        sent = json.loads(route.calls.last.request.content)
        assert sent["filter"]["expression"]["AND"] == [
            within("meta.createdTimestamp", 6, "hour"),
            condition,
        ]
        assert sent["order"] == order
        assert sent["size"] == 25

    async def test_without_columns_extra_and_raw_fields_are_left_out(self, client):
        edwin, router = client
        router.post(RECORDS).mock(
            return_value=httpx.Response(200, json={"meta": {"count": 1}, "results": [ALERT]})
        )

        body = payload(await get_edwin_records(edwin, source="alerts"))

        (record,) = body["records"]
        assert record == {
            key: value for key, value in ALERT.items() if not key.startswith(("extra.", "raw."))
        }
        assert "extra." in body["note"]
        assert "get_edwin_metadata" in body["note"]

    async def test_columns_keep_the_id_and_the_named_fields(self, client):
        edwin, router = client
        router.post(RECORDS).mock(
            return_value=httpx.Response(200, json={"meta": {"count": 1}, "results": [ALERT]})
        )

        body = payload(
            await get_edwin_records(
                edwin, source="alerts", columns=["cf.eventCI", "extra.lm_system_deviceid"]
            )
        )

        assert body["records"] == [
            {
                "_id": ALERT["_id"],
                "cf.eventCI": ALERT["cf.eventCI"],
                "extra.lm_system_deviceid": "532100",
            }
        ]
        assert "note" not in body

    @pytest.mark.parametrize(
        ("kwargs", "words"),
        [
            ({"source": "insights"}, "get_edwin_insights"),
            ({"source": "incidents"}, "alerts"),
            ({"source": "alerts", "hours": 0}, "hours"),
            ({"source": "alerts", "limit": 0}, "limit"),
            ({"source": "alerts", "limit": 51}, "limit"),
        ],
    )
    async def test_refusals_send_nothing(self, client, kwargs, words):
        edwin, router = client
        route = router.post(RECORDS).mock(
            return_value=httpx.Response(200, json={"meta": {"count": 0}, "results": []})
        )

        body = payload(await get_edwin_records(edwin, **kwargs))

        assert route.call_count == 0
        assert body["error"]["code"] == "INVALID_REQUEST"
        assert words in body["error"]["message"]


class TestGetEdwinAlertVolume:
    async def test_hourly_counts_as_epoch_count_pairs(self, client):
        edwin, router = client
        route = router.post(METRICS).mock(return_value=httpx.Response(200, json=VOLUME_BY_HOUR))

        body = payload(await get_edwin_alert_volume(edwin))

        assert json.loads(route.calls.last.request.content) == {
            "source": "alerts",
            "env": {"timezone": "UTC"},
            "filter": filter_condition(within("meta.createdTimestamp", 24, "hour")),
            "columns": [{"field": "meta.rowKey", "type": "COUNT"}],
            "groups": [{"field": "meta.createdTimestamp", "type": "HOUR"}],
            "order": None,
        }
        assert body == {
            "group_by": "hour",
            "hours": 24,
            "total": 141,
            "bucketed": 15,
            "buckets": [[1794250800000, 10], [1794254400000, 2], [1794258000000, 3]],
        }

    async def test_state_counts_report_the_alerts_no_bucket_holds(self, client):
        edwin, router = client
        route = router.post(METRICS).mock(return_value=httpx.Response(200, json=VOLUME_BY_STATE))

        body = payload(await get_edwin_alert_volume(edwin, hours=12, group_by="state"))

        sent = json.loads(route.calls.last.request.content)
        assert sent["groups"] == [{"field": "alertDetails.alertState", "type": "COLUMN"}]
        assert sent["filter"] == filter_condition(within("meta.createdTimestamp", 12, "hour"))
        assert body["buckets"] == [["cleared", 73], ["active", 6]]
        assert (body["total"], body["bucketed"]) == (141, 79)

    async def test_an_unreadable_bucket_is_reported_and_logged(self, client, caplog):
        edwin, router = client
        broken = {"meta": {"count": 12}, "results": [[1794250800000, [10]], [1794254400000]]}
        router.post(METRICS).mock(return_value=httpx.Response(200, json=broken))

        with caplog.at_level(logging.WARNING, logger="lm_mcp.tools.edwin"):
            body = payload(await get_edwin_alert_volume(edwin))

        assert body["buckets"] == [[1794250800000, 10]]
        assert body["unreadable"] == [[1794254400000]]
        assert body["bucketed"] == 10
        assert "unreadable" in caplog.text
        assert caplog.records[0].exc_info is not None

    async def test_a_403_is_scope_missing_naming_query_aggregate(self, client):
        # The scope gate: the read-scope credential (query_records query_record) got
        # this 403 from /ui/query/metrics in the 2026-11-10 probe.
        edwin, router = client
        router.post(METRICS).mock(return_value=httpx.Response(403, json=BODY_403))

        body = payload(await get_edwin_alert_volume(edwin))

        assert body["error"]["code"] == "SCOPE_MISSING"
        assert body["error"]["errorCategory"] == "permission"
        assert "query_aggregate" in body["error"]["message"]

    @pytest.mark.parametrize(
        ("kwargs", "word"), [({"group_by": "severity"}, "group_by"), ({"hours": 0}, "hours")]
    )
    async def test_refusals_send_nothing(self, client, kwargs, word):
        edwin, router = client
        route = router.post(METRICS).mock(return_value=httpx.Response(200, json=VOLUME_BY_HOUR))

        body = payload(await get_edwin_alert_volume(edwin, **kwargs))

        assert route.call_count == 0
        assert body["error"]["code"] == "INVALID_REQUEST"
        assert word in body["error"]["message"]


class TestGetEdwinMetadata:
    async def test_without_a_type_lists_the_29_record_types(self, client):
        edwin, router = client
        router.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json=METADATA))

        body = payload(await get_edwin_metadata(edwin))

        assert body["count"] == 29
        assert {"recordType": "alerts", "queryable": True, "fields": 5} in body["record_types"]
        assert {"recordType": "ml", "queryable": False, "fields": 3} in body["record_types"]

    async def test_a_type_lists_its_fields_without_the_extra_ones(self, client):
        edwin, router = client
        router.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json=METADATA))
        alerts = next(r for r in METADATA["records"] if r["recordType"] == "alerts")

        body = payload(await get_edwin_metadata(edwin, record_type="alerts"))

        assert body["recordType"] == "alerts"
        assert body["attributes"] == alerts["attributes"]
        assert body["fields"] == alerts["fields"][:3]
        assert body["extra_fields"] == 2
        assert "prefix" in body["note"]

    @pytest.mark.parametrize(
        ("prefix", "names"),
        [
            ("extra.", ["extra.lm__lm_resourceid", "extra.lm_a_genurl"]),
            ("alertDetails.", ["alertDetails.actionedBy", "alertDetails.alertState"]),
        ],
    )
    async def test_a_prefix_narrows_the_fields(self, client, prefix, names):
        edwin, router = client
        router.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json=METADATA))

        body = payload(await get_edwin_metadata(edwin, record_type="alerts", prefix=prefix))

        assert [field["name"] for field in body["fields"]] == names
        assert "extra_fields" not in body

    async def test_an_unknown_type_is_refused(self, client):
        edwin, router = client
        router.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json=METADATA))

        body = payload(await get_edwin_metadata(edwin, record_type="incidents"))

        assert body["error"]["code"] == "INVALID_REQUEST"
        assert "incidents" in body["error"]["message"]


# Edwin's agent and tool catalog, from the 2026-11-10 probe of lmryanmatuszewski.dexda.ai
# (docs/validation/probes-2026-11.md, Step 56): three of the seven agents, the
# LMDiagnosticsAgent MCP list verbatim, the query-mcp tool list verbatim, and two of the
# 68 mcp-server-logicmonitor tools (edwin-fullscope-mcp-mcp-server-logicmonitor-tools.json).
AGENTS = {
    "agents": [
        {
            "name": "ChitChatAgent",
            "display_name": "General Chat Agent",
            "customer_facing_description": "Handles simple greetings and conversational "
            "interactions. Does not perform technical analysis or actions.",
            "agent_route": "ws/chitchat",
            "is_active": True,
            "created_at": "2026-04-09T01:30:19.323948Z",
            "updated_at": "2026-04-09T01:30:19.323948Z",
        },
        {
            "name": "DynatraceDiagnosticsAgent",
            "display_name": "Dynatrace Diagnostics",
            "customer_facing_description": "Diagnose Dynatrace-backed alerts and problems by "
            "inspecting problems, entities, topology, Kubernetes events, metrics, anomalies, "
            "synthetic monitors, and vulnerability context.",
            "agent_route": "ws/dynatrace",
            "is_active": False,
            "created_at": "2026-05-18T17:43:33.231286Z",
            "updated_at": "2026-05-18T17:43:33.231286Z",
        },
        {
            "name": "LMDiagnosticsAgent",
            "display_name": "LogicMonitor Diagnostics",
            "customer_facing_description": "Diagnose LogicMonitor-monitored systems by "
            "inspecting alerts, collectors, services, devices, datasource coverage, and "
            "configuration to surface actionable insights.",
            "agent_route": "ws/lm",
            "is_active": True,
            "created_at": "2026-04-24T16:11:49.961621Z",
            "updated_at": "2026-04-24T16:11:49.961621Z",
        },
    ],
    "total": 7,
}
AGENT_MCPS = {
    "org_id": "lmryanmatuszewski",
    "agent_name": "LMDiagnosticsAgent",
    "mcps": [
        {
            "mcp_name": "mcp-server-logicmonitor",
            "display_name": "LogicMonitor",
            "is_enabled": True,
            "is_required": False,
            "endpoint": "http://mcp-server-logicmonitor:8080/mcp",
        },
        {
            "mcp_name": "query-mcp",
            "display_name": "Query Generator",
            "is_enabled": True,
            "is_required": False,
            "endpoint": "http://query-mcp:9020/mcp",
        },
    ],
    "total": 2,
}


def _tool(mcp: str, name: str, display: str, short: str | None, created: str) -> dict:
    return {
        "id": f"{mcp}:{name}",
        "mcp_name": mcp,
        "name": name,
        "display_name": display,
        "short_description": short,
        "is_active": True,
        "created_at": created,
    }


_QUERY_CREATED = "2026-04-09T01:30:19.393329Z"
QUERY_MCP_TOOLS = {
    "mcp_name": "query-mcp",
    "tools": [
        _tool(
            "query-mcp",
            "fetch_alert_by_id",
            "Fetch Alert By Id",
            "Fetch a single alert record by ID.",
            _QUERY_CREATED,
        ),
        _tool(
            "query-mcp",
            "fetch_event_by_id",
            "Fetch Event By Id",
            "Fetch a single event record by ID.",
            _QUERY_CREATED,
        ),
        _tool(
            "query-mcp",
            "fetch_insight_by_id",
            "Fetch Insight By Id",
            "Fetch a single insight record (with its alerts) by ID.",
            _QUERY_CREATED,
        ),
        _tool(
            "query-mcp",
            "get_alert_context",
            "Get Alert Context",
            "Build a structured context summary for a single alert.",
            _QUERY_CREATED,
        ),
        _tool(
            "query-mcp",
            "get_insight_context",
            "Get Insight Context",
            "Build a structured context summary for an insight and its alerts.",
            _QUERY_CREATED,
        ),
        _tool(
            "query-mcp",
            "search",
            "Search",
            "Search alerts, events, or insights using a natural-language question.",
            _QUERY_CREATED,
        ),
    ],
    "total": 6,
}
LM_MCP_TOOLS = {
    "mcp_name": "mcp-server-logicmonitor",
    "tools": [
        _tool(
            "mcp-server-logicmonitor",
            "get_alert_details",
            "Get Alert Details",
            "Fetch a specific LogicMonitor alert by ID.",
            "2026-04-24T16:11:49.961621Z",
        ),
        _tool(
            "mcp-server-logicmonitor",
            "get_alert_rule",
            "Get Alert Rule",
            None,
            "2026-06-12T00:44:48.143780Z",
        ),
    ],
    "total": 68,
}

# POST /api/run-tool answers from the same probe: a read tool that succeeded (content
# cut to its first 120 characters of 86 KB) and one Edwin could not reach.
RUN_OK = {
    "success": True,
    "content": '{"insight": {"genAi": {"summary": "Monitoring lost data or ping results for '
    "three Retina agent pods. Logs show successfu",
    "error": None,
}
RUN_FAILED = {
    "success": False,
    "content": "",
    "error": "MCP server 'no-such-mcp' not found or not enabled for this organization",
}
RUN_TOOL = f"{HOST}/api/run-tool"


@pytest.fixture
def writable(monkeypatch):
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    reset_config()


class TestGetEdwinTools:
    async def test_without_an_agent_lists_every_agent(self, client):
        edwin, router = client
        route = router.get(f"{HOST}/api/agents").mock(return_value=httpx.Response(200, json=AGENTS))

        body = payload(await get_edwin_tools(edwin))

        assert dict(route.calls.last.request.url.params) == {"active_only": "false"}
        assert body["count"] == 3
        assert body["agents"][1] == {
            "name": "DynatraceDiagnosticsAgent",
            "display_name": "Dynatrace Diagnostics",
            "customer_facing_description": AGENTS["agents"][1]["customer_facing_description"],
            "is_active": False,
        }

    async def test_an_agent_lists_its_mcps_and_their_active_tools(self, client):
        edwin, router = client
        mcps = router.get(f"{HOST}/api/org/agents/LMDiagnosticsAgent/mcps").mock(
            return_value=httpx.Response(200, json=AGENT_MCPS)
        )
        lm_tools = router.get(f"{HOST}/api/mcp-servers/mcp-server-logicmonitor/tools").mock(
            return_value=httpx.Response(200, json=LM_MCP_TOOLS)
        )
        query_tools = router.get(f"{HOST}/api/mcp-servers/query-mcp/tools").mock(
            return_value=httpx.Response(200, json=QUERY_MCP_TOOLS)
        )

        body = payload(await get_edwin_tools(edwin, agent="LMDiagnosticsAgent"))

        assert mcps.call_count == 1
        for route in (lm_tools, query_tools):
            assert dict(route.calls.last.request.url.params) == {
                "active_only": "true",
                "agent_name": "LMDiagnosticsAgent",
            }
        assert body["agent"] == "LMDiagnosticsAgent"
        assert body["tool_count"] == 8
        lm, query = body["mcps"]
        assert {k: lm[k] for k in ("mcp_name", "display_name", "is_enabled")} == {
            "mcp_name": "mcp-server-logicmonitor",
            "display_name": "LogicMonitor",
            "is_enabled": True,
        }
        assert "endpoint" not in lm
        assert lm["tools"][1] == {
            "name": "get_alert_rule",
            "display_name": "Get Alert Rule",
            "short_description": None,
        }
        assert [tool["name"] for tool in query["tools"]] == [
            tool["name"] for tool in QUERY_MCP_TOOLS["tools"]
        ]

    async def test_an_unknown_agent_is_not_found_in_edwin_words(self, client):
        edwin, router = client
        router.get(f"{HOST}/api/org/agents/NoSuchAgent/mcps").mock(
            return_value=httpx.Response(404, json={"detail": "Agent 'NoSuchAgent' not found"})
        )

        body = payload(await get_edwin_tools(edwin, agent="NoSuchAgent"))

        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"].startswith(
            "Edwin AI found nothing at GET /api/org/agents/NoSuchAgent/mcps: "
            "Agent 'NoSuchAgent' not found"
        )

    async def test_an_agent_name_with_a_slash_is_refused_before_any_request(self, client):
        edwin, router = client
        route = router.get(url__startswith=f"{HOST}/api/").mock(
            return_value=httpx.Response(200, json=AGENT_MCPS)
        )

        body = payload(await get_edwin_tools(edwin, agent="LMDiagnosticsAgent/x"))

        assert route.call_count == 0
        assert body["error"]["code"] == "INVALID_REQUEST"


class TestEdwinRunTool:
    async def test_refused_while_writes_are_off(self, client):
        edwin, router = client
        route = router.post(RUN_TOOL).mock(return_value=httpx.Response(200, json=RUN_OK))

        body = payload(
            await edwin_run_tool(
                edwin, mcp_name="query-mcp", tool_name="fetch_insight_by_id", parameters={}
            )
        )

        assert route.call_count == 0
        assert body["error"]["code"] == "WRITE_DISABLED"

    async def test_parameters_reach_edwin_unchanged_and_content_comes_back(self, client, writable):
        edwin, router = client
        route = router.post(RUN_TOOL).mock(return_value=httpx.Response(200, json=RUN_OK))
        parameters = {"insight_id": ANALYZED["_id"], "password": "pw-value-fixture"}

        body = payload(
            await edwin_run_tool(
                edwin,
                mcp_name="query-mcp",
                tool_name="fetch_insight_by_id",
                parameters=parameters,
            )
        )

        assert json.loads(route.calls.last.request.content) == {
            "mcp_name": "query-mcp",
            "tool_name": "fetch_insight_by_id",
            "parameters": parameters,
        }
        assert body == {
            "mcp_name": "query-mcp",
            "tool_name": "fetch_insight_by_id",
            "content": RUN_OK["content"],
        }

    async def test_a_tool_edwin_reports_failed_is_rejected_by_tool(self, client, writable):
        edwin, router = client
        router.post(RUN_TOOL).mock(return_value=httpx.Response(200, json=RUN_FAILED))

        body = payload(
            await edwin_run_tool(edwin, mcp_name="no-such-mcp", tool_name="x", parameters={})
        )

        assert body["error"]["code"] == "REJECTED_BY_TOOL"
        assert body["error"]["isRetryable"] is False
        assert "no-such-mcp/x" in body["error"]["message"]
        assert body["error"]["details"]["edwin_error"] == RUN_FAILED["error"]

    def test_the_audit_line_masks_credential_named_parameter_keys(self, caplog):
        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            log_write_operation(
                "edwin_run_tool",
                {
                    "mcp_name": "query-mcp",
                    "tool_name": "fetch_insight_by_id",
                    "parameters": {"api_key": "key-value-fixture", "host": "web01"},
                },
                success=True,
            )

        assert "key-value-fixture" not in caplog.text
        assert "web01" in caplog.text
        assert "edwin_run_tool" in caplog.text
