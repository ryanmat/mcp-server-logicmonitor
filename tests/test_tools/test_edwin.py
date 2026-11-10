# Description: Tests for the Edwin AI query tools and the filterCondition builder.
# Description: Rows are trimmed from the 2026-11-10 probe of lmryanmatuszewski.dexda.ai.

import json

import httpx
import pytest
import respx

from lm_mcp.client.edwin import build_edwin_client
from lm_mcp.tools.edwin import (
    equals,
    filter_condition,
    get_edwin_insight,
    get_edwin_insights,
    in_,
    list_contains,
    within,
)

HOST = "https://lmryanmatuszewski.dexda.ai"
RECORDS = f"{HOST}/ui/query/records"

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
