# Description: Tests for Automated Diagnostics & Remediation (ADR) tools.
# Description: Covers assigned-source listing and structured execution results.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient

BASE = "https://test.logicmonitor.com/santaba/rest"


@pytest.fixture
def auth():
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
        api_version=3,
    )


def _assigned_source(**overrides) -> dict:
    item = {
        "id": 12,
        "name": "Top CPU Processes",
        "description": "Collects top CPU consumers",
        "appliesTo": 'system.hostname == "web-01"',
        "type": "diagnosticsource",
        "group": "Diagnostics",
    }
    item.update(overrides)
    return item


def _execution(**overrides) -> dict:
    item = {
        "executionId": 9001,
        "sourceType": "diagnosticSource",
        "diagnosticSourceId": 12,
        "remediationSourceId": 0,
        "moduleName": "Top CPU Processes",
        "hostId": 1786,
        "alertId": "DS362333940",
        "executionStatus": "COMPLETED",
        "triggeredType": "manual",
        "executedBy": "rmatuszewski",
        "output": "PID 4242 java 93%",
        "startTime": 1781200000,
        "endTime": 1781200042,
    }
    item.update(overrides)
    return item


class TestGetDiagnosticRemediationAssignments:
    @respx.mock
    async def test_assignments_by_resource(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_assignments,
        )

        route = respx.get(f"{BASE}/setting/diagnosticRemediation/list").mock(
            return_value=httpx.Response(
                200, json={"items": [_assigned_source()], "total": 1}
            )
        )

        result = await get_diagnostic_remediation_assignments(client, resource_id=1786)

        data = json.loads(result[0].text)
        assert data["total"] == 1
        src = data["assigned_sources"][0]
        assert src["name"] == "Top CPU Processes"
        assert src["type"] == "diagnosticsource"
        assert src["applies_to"] == 'system.hostname == "web-01"'
        assert route.calls[0].request.url.params["resourceId"] == "1786"

    @respx.mock
    async def test_assignments_by_alert_with_module_type(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_assignments,
        )

        route = respx.get(f"{BASE}/setting/diagnosticRemediation/list").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_diagnostic_remediation_assignments(
            client, alert_id="DS123", module_type="remediationsource"
        )

        params = route.calls[0].request.url.params
        assert params["alertId"] == "DS123"
        assert params["moduleType"] == "remediationsource"
        assert "resourceId" not in params

    async def test_assignments_requires_target(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_assignments,
        )

        result = await get_diagnostic_remediation_assignments(client)

        assert "Error" in result[0].text
        assert "resource_id or alert_id" in result[0].text

    @respx.mock
    async def test_assignments_limit_applied_client_side(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_assignments,
        )

        items = [_assigned_source(id=i, name=f"src-{i}") for i in range(5)]
        respx.get(f"{BASE}/setting/diagnosticRemediation/list").mock(
            return_value=httpx.Response(200, json={"items": items, "total": 5})
        )

        result = await get_diagnostic_remediation_assignments(
            client, resource_id=1, limit=2
        )

        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert data["total"] == 5


class TestGetDiagnosticRemediationResults:
    @respx.mock
    async def test_results_by_host(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_results,
        )

        route = respx.get(f"{BASE}/setting/diagnosticRemediation/executionResults").mock(
            return_value=httpx.Response(
                200,
                json={"items": [_execution()], "total": 1, "sort": "-startTime"},
            )
        )

        result = await get_diagnostic_remediation_results(client, host_id=1786)

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["sort"] == "-startTime"
        ex = data["executions"][0]
        assert ex["execution_id"] == 9001
        assert ex["status"] == "COMPLETED"
        assert ex["triggered_type"] == "manual"
        assert ex["output"] == "PID 4242 java 93%"
        assert ex["start_time_epoch"] == 1781200000

        params = route.calls[0].request.url.params
        assert params["hostId"] == "1786"
        assert params["moduleType"] == "both"
        assert params["perPageCount"] == "50"
        assert params["pageOffsetCount"] == "0"

    @respx.mock
    async def test_results_param_mapping(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_results,
        )

        route = respx.get(f"{BASE}/setting/diagnosticRemediation/executionResults").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_diagnostic_remediation_results(
            client,
            alert_id="DS123",
            module_type="diagnostic",
            diagnostic_source_id=12,
            start_time_ms=1781200000000,
            end_time_ms=1781203600000,
            limit=10,
            offset=20,
            cursor="abc",
        )

        params = route.calls[0].request.url.params
        assert params["alertId"] == "DS123"
        assert params["moduleType"] == "diagnostic"
        assert params["diagnosticSourceId"] == "12"
        assert params["startTimeMs"] == "1781200000000"
        assert params["endTimeMs"] == "1781203600000"
        assert params["perPageCount"] == "10"
        assert params["pageOffsetCount"] == "20"
        assert params["cursor"] == "abc"

    async def test_results_requires_exactly_one_target(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_results,
        )

        neither = await get_diagnostic_remediation_results(client)
        both = await get_diagnostic_remediation_results(
            client, alert_id="DS1", host_id=1
        )

        for result in (neither, both):
            assert "Error" in result[0].text
            assert "exactly one of alert_id or host_id" in result[0].text

    async def test_results_rejects_cursor_with_module_type_both(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_results,
        )

        result = await get_diagnostic_remediation_results(
            client, host_id=1, cursor="abc"
        )

        assert "Error" in result[0].text
        assert "Cursors are not supported" in result[0].text

    @respx.mock
    async def test_results_truncates_long_output(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            _OUTPUT_CHAR_LIMIT,
            get_diagnostic_remediation_results,
        )

        long_output = "x" * (_OUTPUT_CHAR_LIMIT + 500)
        respx.get(f"{BASE}/setting/diagnosticRemediation/executionResults").mock(
            return_value=httpx.Response(
                200,
                json={"items": [_execution(output=long_output)], "total": 1},
            )
        )

        result = await get_diagnostic_remediation_results(client, host_id=1786)

        data = json.loads(result[0].text)
        ex = data["executions"][0]
        assert len(ex["output"]) == _OUTPUT_CHAR_LIMIT
        assert ex["output_truncated"] is True

    @respx.mock
    async def test_results_surfaces_cursors(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_results,
        )

        respx.get(f"{BASE}/setting/diagnosticRemediation/executionResults").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [_execution()],
                    "total": 10,
                    "cursor": "next-diag",
                    "remediationCursor": "next-rem",
                },
            )
        )

        result = await get_diagnostic_remediation_results(
            client, host_id=1786, module_type="diagnostic"
        )

        data = json.loads(result[0].text)
        assert data["cursor"] == "next-diag"
        assert data["remediation_cursor"] == "next-rem"

    @respx.mock
    async def test_results_api_error_handled(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_results,
        )

        respx.get(f"{BASE}/setting/diagnosticRemediation/executionResults").mock(
            return_value=httpx.Response(
                400, json={"errorMessage": "alertId and device mismatch"}
            )
        )

        result = await get_diagnostic_remediation_results(client, host_id=99999)

        assert "error" in result[0].text.lower()
