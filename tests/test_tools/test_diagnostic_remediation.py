# Description: Tests for Automated Diagnostics & Remediation (ADR) tools.
# Description: Covers assigned-source listing and structured execution results.

import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result

BASE = "https://test.logicmonitor.com/santaba/rest"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def auth():
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
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


def assignments_route(request: httpx.Request) -> httpx.Response:
    """The list route as the sandbox answered on 2026-11-13: moduleType is diagnostic or
    remediation, and any other value is a 400 with this body."""
    if request.url.params.get("moduleType") not in (None, "diagnostic", "remediation"):
        body = {
            "errorMessage": "Invalid moduleType: use diagnostic or remediation",
            "errorCode": 1400,
            "errorDetail": None,
        }
        return httpx.Response(400, json=body)
    body = {"total": 1, "items": [_assigned_source()], "searchId": None, "isMin": False}
    return httpx.Response(200, json=body)


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
            return_value=httpx.Response(200, json={"items": [_assigned_source()], "total": 1})
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
            client, alert_id="DS123", module_type="remediation"
        )

        params = route.calls[0].request.url.params
        assert params["alertId"] == "DS123"
        assert params["moduleType"] == "remediation"
        assert "resourceId" not in params

    @respx.mock
    async def test_every_module_type_the_schema_offers_is_one_the_api_accepts(self, client):
        """The schema's enum is the caller's only guide to module_type, and the route
        answers 400 to any value but diagnostic and remediation."""
        from lm_mcp.registry import TOOLS
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_assignments,
        )

        respx.get(f"{BASE}/setting/diagnosticRemediation/list").mock(side_effect=assignments_route)
        (tool,) = [t for t in TOOLS if t.name == "get_diagnostic_remediation_assignments"]
        offered = tool.inputSchema["properties"]["module_type"]["enum"]

        assert offered == ["diagnostic", "remediation"]
        for module_type in offered:
            result = await get_diagnostic_remediation_assignments(
                client, resource_id=42, module_type=module_type
            )
            assert not is_error_result(result), module_type
            assert json.loads(result[0].text)["count"] == 1

    @pytest.mark.parametrize(
        "path", [".claude/skills/lm-remediate/SKILL.md", "src/lm_mcp/prompts/templates.py"]
    )
    def test_the_remediation_runbooks_name_module_types_the_tools_take(self, path):
        """The skill and the prompt tell the model which module_type to pass to the
        assignments and results tools; each value they name is one the API accepts."""
        named = set(re.findall(r'module_type`? "(\w+)"', (ROOT / path).read_text()))

        assert named
        assert named <= {"diagnostic", "remediation", "both"}

    async def test_assignments_requires_target(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_assignments,
        )

        result = await get_diagnostic_remediation_assignments(client)

        assert is_error_result(result)
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

        result = await get_diagnostic_remediation_assignments(client, resource_id=1, limit=2)

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
        both = await get_diagnostic_remediation_results(client, alert_id="DS1", host_id=1)

        for result in (neither, both):
            assert is_error_result(result)
            assert "exactly one of alert_id or host_id" in result[0].text

    async def test_results_rejects_cursor_with_module_type_both(self, client):
        from lm_mcp.tools.diagnostic_remediation import (
            get_diagnostic_remediation_results,
        )

        result = await get_diagnostic_remediation_results(client, host_id=1, cursor="abc")

        assert is_error_result(result)
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
            return_value=httpx.Response(400, json={"errorMessage": "alertId and device mismatch"})
        )

        result = await get_diagnostic_remediation_results(client, host_id=99999)

        assert "error" in result[0].text.lower()
