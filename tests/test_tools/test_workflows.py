# Description: Tests for composite workflow tools.
# Description: Validates triage, health_check, capacity_plan, portal_overview, diagnose.

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import anyio
import httpx
import jsonschema
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import call_sub_tool, validation_error
from lm_mcp.tools.alerts import ALERT_WINDOW_TRUNCATED_WARNING
from lm_mcp.tools.workflows import (
    CAPACITY_PLAN_OUTPUT_SCHEMA,
    DETECT_SITE_OUTAGE_OUTPUT_SCHEMA,
    DIAGNOSE_OUTPUT_SCHEMA,
    HEALTH_CHECK_OUTPUT_SCHEMA,
    PORTAL_OVERVIEW_OUTPUT_SCHEMA,
    TRIAGE_OUTPUT_SCHEMA,
    _resolve_device,
    _trim_detail,
    capacity_plan,
    check_required_tools,
    detect_site_outage,
    diagnose,
    health_check,
    portal_overview,
    search_tools,
    triage,
)
from tests.alert_pages import alert_lists
from tests.sdk_call import replay_through_sdk, structured
from tests.test_tools.test_diagnostic_remediation import _assigned_source, _execution


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


# ---------------------------------------------------------------------------
# Helpers for building mock sub-tool responses
# ---------------------------------------------------------------------------


def _mock_text(data: dict) -> list:
    """Build a list matching the TextContent return format of tool handlers."""
    from mcp.types import TextContent

    return [TextContent(type="text", text=json.dumps(data))]


def _patch_sub(module_path: str, data: dict) -> patch:
    """Return an AsyncMock patch that returns TextContent wrapping *data*."""
    return patch(module_path, new_callable=AsyncMock, return_value=_mock_text(data))


def _patch_no_diagnostics() -> ExitStack:
    """Patch diagnose's two ADR reads to answer that nothing is assigned or has run."""
    stack = ExitStack()
    for name, data in (
        ("assignments", {"total": 0, "count": 0, "assigned_sources": []}),
        ("results", {"total": 0, "count": 0, "executions": []}),
    ):
        path = f"lm_mcp.tools.diagnostic_remediation.get_diagnostic_remediation_{name}"
        stack.enter_context(_patch_sub(path, data))
    return stack


def _patch_window(**sections: dict) -> patch:
    """Patch analyze_alerts to return a complete window holding the given sections."""
    return _patch_sub(
        "lm_mcp.tools.analyze_alerts.analyze_alerts",
        {"total_alerts": 0, "truncated": False, "api_total": 0, **sections},
    )


# ---------------------------------------------------------------------------
# Helpers for driving detect_site_outage through respx
# ---------------------------------------------------------------------------


async def _progress_of(client, name: str, arguments: dict, *, ask: bool) -> tuple:
    """Call a composite from an in-memory SDK client with ``client`` as the startup client.

    With ``ask`` the request carries a progressToken and the progress callback records each
    notification; without it the request still carries a _meta, with no token in it. The
    message handler records every progress notification either way. Returns the result,
    the callback's (progress, total, message) rows and the handler's.
    """
    from mcp.shared.memory import create_connected_server_and_client_session
    from mcp.types import ProgressNotification, ServerNotification

    from lm_mcp.server import server

    called: list = []
    received: list = []

    async def on_progress(progress, total, message):
        called.append((progress, total, message))

    async def on_message(message):
        if isinstance(message, ServerNotification) and isinstance(
            message.root, ProgressNotification
        ):
            params = message.root.params
            received.append((params.progress, params.total, params.message))

    with patch("lm_mcp.server._client", client):
        async with create_connected_server_and_client_session(
            server, message_handler=on_message
        ) as session:
            if ask:
                result = await session.call_tool(name, arguments, progress_callback=on_progress)
            else:
                result = await session.call_tool(name, arguments, meta={"origin": "test"})
    assert result.isError is False, result.content[0].text
    return result, called, received


_BASE = "https://test.logicmonitor.com/santaba/rest"
_ALERTS_URL = f"{_BASE}/alert/alerts"
_AUDIT_URL = f"{_BASE}/setting/accesslogs"


def _window_reads(route) -> list[list[str]]:
    """The filter clauses of each alert-window read a route served."""
    return [
        c.request.url.params["filter"].split(",")
        for c in route.calls
        if "startEpoch>:" in c.request.url.params.get("filter", "")
    ]


def _one_alert_per_device(n: int) -> list[dict]:
    now = int(time.time())
    return [
        {
            "id": f"LMA{i}",
            "severity": 4,
            "monitorObjectName": f"dev-{i % 2}",
            "resourceTemplateName": "Ping",
            "dataPointName": "PingLossPercent",
            "startEpoch": now - 600 - i,
            "endEpoch": 0,
            "cleared": False,
        }
        for i in range(n)
    ]


def _device_alert(alert_id: int, device: str, object_id: int, object_type: str = "device") -> dict:
    """An open window alert with the monitorObjectId and monitorObjectType every live row
    carries (probe of lmryanmatuszewski, 2026-11-09)."""
    return {
        "id": f"LMA{alert_id}",
        "severity": 4,
        "monitorObjectName": device,
        "monitorObjectId": object_id,
        "monitorObjectType": object_type,
        "resourceTemplateName": "Ping",
        "dataPointName": "PingLossPercent",
        "startEpoch": int(time.time()) - 600 - alert_id,
        "endEpoch": 0,
        "cleared": False,
    }


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


# One device's alert list, which analyze_blast_radius reads for each device it reaches.
_DEVICE_ALERTS = rf"{re.escape(_BASE)}/device/devices/\d+/alerts"


def _device_alerts(rows_by_device: dict[int, list[dict]]):
    """Serve analyze_blast_radius' open-alert check of one device from rows_by_device."""

    def respond(request: httpx.Request) -> httpx.Response:
        rows = rows_by_device.get(int(request.url.path.split("/")[-2]), [])
        return _ok({"items": rows, "total": len(rows)})

    return respond


_NEIGHBORS = re.compile(rf"{re.escape(_BASE)}/(topology|device)/devices/\d+/neighbors")


def _topology(graph: dict[int, list[dict]], unreadable: set[int]):
    """Serve both neighbor paths from graph; a device in unreadable answers 404 on each."""

    def respond(request: httpx.Request) -> httpx.Response:
        device_id = int(request.url.path.split("/")[-2])
        if device_id in unreadable:
            return httpx.Response(404, json={"errorMessage": "not found", "errorCode": 1400})
        rows = graph.get(device_id, [])
        return _ok({"items": rows, "total": len(rows)})

    return respond


def _portal_error() -> httpx.Response:
    return httpx.Response(500, json={"errorMessage": "portal unavailable"})


def _alert_window(*alerts: dict) -> httpx.Response:
    return _ok({"items": list(alerts), "total": len(alerts)})


def _power_alert() -> dict:
    return {
        "id": 7,
        "dataSourceName": "APC_UPS_Battery",
        "alertName": "OnBattery",
        "monitorObjectName": "ups-1",
        "startEpoch": int(time.time()) - 60,
        "severity": 4,
    }


# Collector answers of a sandbox portal on 2026-11-11 (tests/test_tools/test_collectors.py).
_COLLECTOR_OPS = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "collector_ops.json").read_text()
)


def _mock_site_portal(
    devices: list[dict],
    collector: httpx.Response,
    burst: httpx.Response,
    power: httpx.Response,
) -> None:
    """Route one detect_site_outage run on group 42, served by collector 1.

    Collector 1's evidence reads answer a down collector's status check and no events.
    The burst read is analyze_alerts on interface datasources: its active read gets
    burst and its cleared read an empty page. The power read carries no datasource
    clause and gets power.
    """

    def device_route(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("filter", "").startswith("currentCollectorId"):
            return _ok({"items": [], "total": len(devices)})
        return _ok({"items": devices, "total": len(devices)})

    respx.get(f"{_BASE}/device/devices").mock(side_effect=device_route)
    respx.get(f"{_BASE}/setting/collector/collectors/1").mock(return_value=collector)
    respx.get(f"{_BASE}/setting/collector/collectors/1/services/getStatusCheck").mock(
        return_value=_ok(_COLLECTOR_OPS["status_check_26_down"])
    )
    respx.get(f"{_BASE}/setting/collector/collectors/1/events").mock(
        return_value=_ok({"total": 0, "items": []})
    )
    respx.get(f"{_BASE}/device/groups/42").mock(
        return_value=_ok({"id": 42, "fullPath": "Sites/HQ"})
    )

    def alert_route(request: httpx.Request) -> httpx.Response:
        clauses = request.url.params.get("filter", "").split(",")
        if 'resourceTemplateName~"interface"' not in clauses:
            return power
        return _alert_window() if "cleared:true" in clauses else burst

    respx.get(f"{_BASE}/alert/alerts").mock(side_effect=alert_route)


def _collector_record(is_down: bool) -> httpx.Response:
    """Collector 1 as a live portal returns it: status is 1 whether it is up or down."""
    return _ok({"id": 1, "hostname": "col-01", "status": 1, "isDown": is_down, "numberOfHosts": 5})


def _site_devices(count: int, status: str) -> list[dict]:
    return [
        {"id": i, "displayName": f"sw-{i}", "hostStatus": status, "currentCollectorId": 1}
        for i in range(1, count + 1)
    ]


@pytest.fixture
def lm_env(monkeypatch):
    """LM credentials and no tool filters, so composite tools pass check_required_tools."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
    monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
    monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
    monkeypatch.delenv("LM_MCP_CATEGORIES", raising=False)


_DS_URL = f"{_BASE}/device/devices/1/devicedatasources"


def _mock_capacity_portal(
    instance_data: dict[int, httpx.Response | list[httpx.Response]],
) -> None:
    """Route capacity_plan for device 1, datasource CPU (10).

    An instance given one response serves it to every data read; one given a list
    serves its pages in order.
    """
    respx.get(f"{_BASE}/device/devices/1").mock(
        return_value=_ok({"id": 1, "displayName": "server-01"})
    )
    respx.get(_DS_URL).mock(
        return_value=_ok({"items": [{"id": 10, "dataSourceName": "CPU"}], "total": 1})
    )
    respx.get(f"{_DS_URL}/10/instances").mock(
        return_value=_ok(
            {
                "items": [{"id": iid, "displayName": f"cpu{iid}"} for iid in instance_data],
                "total": len(instance_data),
            }
        )
    )
    for iid, response in instance_data.items():
        route = respx.get(f"{_DS_URL}/10/instances/{iid}/data")
        if isinstance(response, list):
            route.mock(side_effect=response)
        else:
            route.mock(return_value=response)


def _rising_cpu_and_sparse_mem() -> httpx.Response:
    """cpu climbs 10 per 5 minutes toward the 90 threshold; mem has one sample."""
    rows = [
        [10.0, "No Data"],
        [20.0, "No Data"],
        [30.0, 55.0],
        [40.0, "No Data"],
        [50.0, "No Data"],
    ]
    start = int(time.time()) - 3600
    return _ok(
        {
            "dataPoints": ["cpu", "mem"],
            "values": rows,
            "time": [(start + i * 300) * 1000 for i in range(len(rows))],
        }
    )


def _steady_cpu_and_mem() -> httpx.Response:
    """cpu and mem hold nearly level on one final page, newest first, in the live shape."""
    newest = int(time.time()) - 60
    return _ok(
        {
            "dataSourceName": "CPU",
            "dataPoints": ["cpu", "mem"],
            "values": [[51.0, 61.0], [50.5, 60.5], [50.0, 60.0]],
            "time": [(newest - i * 300) * 1000 for i in range(3)],
            "nextPageParams": "",
        }
    )


def _capped_read() -> list[httpx.Response]:
    """One read's pages, newest first, the last still naming a next page: the cap binds."""
    from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES

    now = int(time.time())
    pages = []
    for page in range(MAX_SERIES_PAGES):
        newest = now - page * 600
        pages.append(
            _ok(
                {
                    "dataSourceName": "CPU",
                    "dataPoints": ["cpu", "mem"],
                    "values": [[50.0, 60.0], [50.5, 60.5]],
                    "time": [newest * 1000, (newest - 300) * 1000],
                    "nextPageParams": f"start={now - 86400}&end={newest - 301}",
                }
            )
        )
    return pages


def _swinging_cpu() -> httpx.Response:
    """cpu swings between 5 and 95 every 5 minutes, which the trend section labels volatile."""
    rows = [[5.0], [95.0], [5.0], [95.0], [5.0], [95.0]]
    start = int(time.time()) - 3600
    return _ok(
        {
            "dataPoints": ["cpu"],
            "values": rows,
            "time": [(start + i * 300) * 1000 for i in range(len(rows))],
        }
    )


# ---------------------------------------------------------------------------
# TestCheckRequiredTools
# ---------------------------------------------------------------------------


class TestCheckRequiredTools:
    """Tests for check_required_tools utility."""

    def test_every_composite_requires_only_registered_tools(self):
        """Every composite's required list names only tools the registry holds."""
        from lm_mcp.registry import TOOLS
        from lm_mcp.tools import workflows

        registered = {tool.name for tool in TOOLS}
        lists = {
            name: value
            for name, value in vars(workflows).items()
            if name.startswith("_") and name.endswith("_REQUIRED")
        }
        assert len(lists) == 8
        for name, required in lists.items():
            assert set(required) <= registered, f"{name}: {sorted(set(required) - registered)}"

    def test_all_tools_pass_returns_none(self, monkeypatch):
        """When no filtering is configured, all tools pass."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = check_required_tools(["get_alerts", "analyze_alerts"])
        assert result is None
        reset_config()

    def test_blocked_with_enabled_tools(self, monkeypatch):
        """Tools not matching LM_ENABLED_TOOLS are blocked."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_alerts,get_devices")
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = check_required_tools(["get_alerts", "analyze_alerts"])
        assert result is not None
        text = result[0].text
        assert "analyze_alerts" in text
        reset_config()

    def test_blocked_with_disabled_tools(self, monkeypatch):
        """Tools matching LM_DISABLED_TOOLS are blocked."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "analyze_*")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = check_required_tools(["get_alerts", "analyze_alerts"])
        assert result is not None
        text = result[0].text
        assert "analyze_alerts" in text
        reset_config()


# ---------------------------------------------------------------------------
# TestResolveDevice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema",
    [
        HEALTH_CHECK_OUTPUT_SCHEMA,
        CAPACITY_PLAN_OUTPUT_SCHEMA,
        DIAGNOSE_OUTPUT_SCHEMA,
        DETECT_SITE_OUTAGE_OUTPUT_SCHEMA,
    ],
    ids=["health_check", "capacity_plan", "diagnose", "detect_site_outage"],
)
def test_the_part_two_output_schemas_refuse_an_undocumented_key(schema):
    """Each of these four composite report schemas is a valid JSON Schema and closed to keys
    it does not document, a health_score among them."""
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    with pytest.raises(jsonschema.ValidationError, match="health_score"):
        jsonschema.validate({"health_score": 80}, {**schema, "required": []})


class TestResolveDevice:
    """Tests for _resolve_device utility."""

    async def test_resolve_by_id(self, client):
        """Resolving by device_id calls get_device."""
        mock_device = {"id": 42, "displayName": "server-01"}
        with _patch_sub("lm_mcp.tools.devices.get_device", mock_device):
            dev_id, dev_data = await _resolve_device(client, device_id=42)
        assert dev_id == 42
        assert dev_data["displayName"] == "server-01"

    async def test_resolve_by_name(self, client):
        """Resolving by device_name calls get_devices and returns first match."""
        mock_result = {"devices": [{"id": 99, "displayName": "web-01"}]}
        with _patch_sub("lm_mcp.tools.devices.get_devices", mock_result):
            dev_id, _dev_data = await _resolve_device(client, device_name="web-01")
        assert dev_id == 99

    async def test_not_found_raises(self, client):
        """Raises ValueError when no device matches the name."""
        mock_result = {"devices": []}
        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", mock_result),
            pytest.raises(ValueError, match="No device found"),
        ):
            await _resolve_device(client, device_name="ghost")

    async def test_missing_params_raises(self, client):
        """Raises ValueError when neither device_id nor device_name given."""
        with pytest.raises(ValueError, match="Either device_id or device_name"):
            await _resolve_device(client)


# ---------------------------------------------------------------------------
# TestTrimDetail
# ---------------------------------------------------------------------------


class TestTrimDetail:
    """Tests for _trim_detail utility."""

    def test_summary_strips_keys(self):
        report = {"a": 1, "b": 2, "c": 3}
        trimmed = _trim_detail(report, "summary", {"b", "c"})
        assert trimmed == {"a": 1}

    def test_full_keeps_all(self):
        report = {"a": 1, "b": 2, "c": 3}
        trimmed = _trim_detail(report, "full", {"b", "c"})
        assert trimmed == report

    def test_summary_lifts_the_warnings_of_trimmed_keys(self):
        """A trimmed key's nested warnings, list or string, reach the top-level warnings,
        named by the datasource and instance around them, or by the key."""
        report = {
            "a": 1,
            "metrics": [
                {"datasource": "CPU", "instance": "cpu0", "analysis": {"warnings": ["w1"]}},
                {"datasource": "Disk", "instances": [{"instance": "vol0", "warnings": ["w2"]}]},
            ],
            "blast_radius": {"warning": "w3", "counts": {"n": 1}},
            "warnings": ["w0"],
        }
        trimmed = _trim_detail(report, "summary", {"metrics", "blast_radius"})
        assert trimmed == {
            "a": 1,
            "warnings": ["w0", "CPU/cpu0: w1", "Disk/vol0: w2", "blast_radius: w3"],
        }

    def test_summary_adds_no_warnings_key_when_none_are_nested(self):
        trimmed = _trim_detail({"a": 1, "b": {"c": [{"d": 2}]}}, "summary", {"b"})
        assert trimmed == {"a": 1}


# blast-radius rows _mock_blast_portal yields for core-sw and edge-fw
_CORE_SW_COUNTS = {
    "device": "core-sw",
    "device_id": 100,
    "total_affected_devices": 1,
    "neighbor_count": 1,
    "dependent_count": 0,
    "critical_alert_count": 1,
    "unreadable_count": 0,
}
_EDGE_FW_COUNTS = {
    "device": "edge-fw",
    "device_id": 101,
    "total_affected_devices": 0,
    "neighbor_count": 0,
    "dependent_count": 0,
    "critical_alert_count": 0,
    "unreadable_count": 1,
    "warning": (
        "Neighbors of 1 device(s) could not be read on either topology path; the counts "
        "cover only the devices read."
    ),
}


# ---------------------------------------------------------------------------
# TestTriage
# ---------------------------------------------------------------------------


class TestTriage:
    """Tests for the triage composite tool."""

    async def test_happy_path_summary(self, client, monkeypatch):
        """Triage returns a report with expected keys in summary mode."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        stats_data = {"active": 5, "cleared": 0, "hourly": []}
        clusters_data = {"clusters": [], "cluster_count": 0}
        noise_data = {"noise_score": 10, "total_alerts": 5}
        changes_data = {"correlated_events": [], "total_changes": 0}

        with _patch_window(
            statistics=stats_data, clusters=clusters_data, noise=noise_data, changes=changes_data
        ):
            result = await triage(client, detail_level="summary")

        data = json.loads(result[0].text)
        assert data["statistics"] == stats_data
        assert data["noise"] == noise_data
        # blast-radius counts stay in summary mode; no device cluster, no rows
        assert data["blast_radius"] == []
        reset_config()

    async def test_happy_path_full(self, client, monkeypatch):
        """Triage full mode includes blast_radius."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        stats_data = {"active": 0, "cleared": 0, "hourly": []}
        clusters_data = {"clusters": [], "cluster_count": 0}
        noise_data = {"noise_score": 0, "total_alerts": 0}
        changes_data = {"correlated_events": [], "total_changes": 0}

        with _patch_window(
            statistics=stats_data, clusters=clusters_data, noise=noise_data, changes=changes_data
        ):
            result = await triage(client, detail_level="full")

        data = json.loads(result[0].text)
        assert "blast_radius" in data
        reset_config()

    async def test_required_tool_blocked(self, client, monkeypatch):
        """Triage returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "analyze_alerts")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = await triage(client)
        text = result[0].text
        assert "requires disabled tools" in text
        assert "analyze_alerts" in text
        reset_config()

    async def test_sub_tool_failure_partial_results(self, client, monkeypatch):
        """Triage returns partial results with warnings when the window read fails."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        with patch(
            "lm_mcp.tools.analyze_alerts.analyze_alerts",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API timeout"),
        ):
            result = await triage(client, detail_level="full")

        data = json.loads(result[0].text)
        for key in ("statistics", "clusters", "noise", "changes"):
            assert data[key] is None
        assert data["blast_radius"] == []
        assert data["warnings"] == ["analyze_alerts failed: API timeout"]
        jsonschema.validate(data, TRIAGE_OUTPUT_SCHEMA)
        structured(await replay_through_sdk(monkeypatch, "triage", {"detail_level": "full"}, data))
        reset_config()

    @respx.mock
    async def test_reads_the_alert_window_once(self, auth, lm_env):
        """R2.2: one active read and one cleared read feed statistics, clusters, noise and
        changes, and the audit log is read once."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        alerts = respx.get(_ALERTS_URL).mock(side_effect=alert_lists(_one_alert_per_device(3)))
        audit = respx.get(_AUDIT_URL).mock(return_value=_ok({"items": []}))

        result = await triage(client, severity="critical", hours_back=2, detail_level="full")

        data = json.loads(result[0].text)
        reads = _window_reads(alerts)
        assert len(reads) == 2
        assert alerts.call_count == 2
        assert all("severity:4" in clauses for clauses in reads)
        assert audit.call_count == 1
        assert data["statistics"]["active"] == 3
        assert data["clusters"]["clusters"][0]["key"] == "dev-0"
        assert data["noise"]["total_alerts"] == 3
        assert data["changes"]["total_changes"] == 0
        assert "warnings" not in data

    @respx.mock
    async def test_a_capped_window_is_a_warning(self, auth, lm_env):
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        respx.get(_ALERTS_URL).mock(
            side_effect=alert_lists(_one_alert_per_device(6000), lower_bound=True)
        )
        respx.get(_AUDIT_URL).mock(return_value=_ok({"items": []}))

        result = await triage(client, detail_level="full")

        data = json.loads(result[0].text)
        assert data["warnings"] == [ALERT_WINDOW_TRUNCATED_WARNING]

    @staticmethod
    def _mock_blast_portal() -> tuple[respx.Route, respx.Route, respx.Route]:
        """Two device clusters and a website cluster: core-sw (100) reaches access-1 (200),
        which has a critical alert open; edge-fw's (101) neighbors answer 404 on both paths."""
        active = [
            _device_alert(1, "core-sw", 100),
            _device_alert(2, "core-sw", 100),
            _device_alert(3, "edge-fw", 101),
            _device_alert(4, "edge-fw", 101),
            _device_alert(5, "shop", 7, "website"),
            _device_alert(6, "shop", 7, "website"),
        ]
        alerts = respx.get(_ALERTS_URL).mock(side_effect=alert_lists(active))
        device_alerts = respx.get(url__regex=_DEVICE_ALERTS).mock(
            side_effect=_device_alerts({200: [{"severity": 4}]})
        )
        respx.get(_AUDIT_URL).mock(return_value=_ok({"items": []}))
        respx.get(url__regex=_NEIGHBORS).mock(
            side_effect=_topology({100: [{"id": 200, "displayName": "access-1"}]}, {101})
        )
        devices = respx.get(f"{_BASE}/device/devices").mock(
            return_value=_ok({"items": [], "total": 0})
        )
        return alerts, devices, device_alerts

    @respx.mock
    async def test_summary_reports_blast_radius_counts_by_cluster_device_id(self, auth, lm_env):
        """R2.3: the window is read once, each device cluster's id goes to analyze_blast_radius
        with no device search, the website cluster gets none, and an unreadable neighbor
        read is counted rather than reported as zero reach."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        alerts, devices, device_alerts = self._mock_blast_portal()

        data = json.loads((await triage(client))[0].text)

        assert len(_window_reads(alerts)) == 2
        assert alerts.call_count == 2  # the two window reads
        # access-1's open-alert check reads its own alert list
        assert [c.request.url.params["filter"] for c in device_alerts.calls] == ["cleared:false"]
        assert devices.call_count == 0
        assert data["blast_radius"] == [_CORE_SW_COUNTS, _EDGE_FW_COUNTS]
        device_keys = {c["key"] for c in data["clusters"]["clusters"] if c["type"] == "device"}
        assert device_keys == {"core-sw", "edge-fw", "shop"}
        assert data["noise"]["total_alerts"] == 6
        assert "warnings" not in data
        jsonschema.validate(data, TRIAGE_OUTPUT_SCHEMA)

    @respx.mock
    async def test_full_adds_the_devices_reached(self, auth, lm_env):
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        self._mock_blast_portal()

        data = json.loads((await triage(client, detail_level="full"))[0].text)

        core, edge = data["blast_radius"]
        assert core == {
            **_CORE_SW_COUNTS,
            "affected_devices": [
                {
                    "device_id": 200,
                    "device_name": "access-1",
                    "depth": 1,
                    "active_alert_count": 1,
                    "has_critical": True,
                }
            ],
            "critical_path_devices": [],
        }
        assert edge == {**_EDGE_FW_COUNTS, "affected_devices": [], "critical_path_devices": []}
        assert set(data) == set(TRIAGE_OUTPUT_SCHEMA["properties"]) - {"warnings"}
        jsonschema.validate(data, TRIAGE_OUTPUT_SCHEMA)

    @respx.mock
    async def test_counts_at_most_three_device_clusters_past_a_website(self, auth, lm_env):
        """The busiest cluster is a website, which takes no slot; of four device clusters the
        three largest are read and the fourth is not."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        active = [_device_alert(i, "shop", 7, "website") for i in range(1, 6)]
        # 4, 3, 2 and 2 alerts: clusters sort largest first, ties in the order they appear
        for device_id, size in ((100, 4), (101, 3), (102, 2), (103, 2)):
            active += [
                _device_alert(10 * device_id + k, f"dev-{device_id}", device_id)
                for k in range(size)
            ]
        respx.get(_ALERTS_URL).mock(side_effect=alert_lists(active))
        respx.get(url__regex=_DEVICE_ALERTS).mock(side_effect=_device_alerts({}))
        respx.get(_AUDIT_URL).mock(return_value=_ok({"items": []}))
        topology = respx.get(url__regex=_NEIGHBORS).mock(side_effect=_topology({}, set()))

        data = json.loads((await triage(client))[0].text)

        assert [row["device_id"] for row in data["blast_radius"]] == [100, 101, 102]
        assert sorted(int(c.request.url.path.split("/")[-2]) for c in topology.calls) == [
            100,
            101,
            102,
        ]

    def test_the_output_schema_refuses_an_undocumented_key(self):
        report = {
            "hours_back": 4,
            "detail_level": "summary",
            "statistics": None,
            "clusters": None,
            "noise": None,
            "changes": None,
            "blast_radius": [],
        }
        jsonschema.validate(report, TRIAGE_OUTPUT_SCHEMA)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**report, "health_score": 80}, TRIAGE_OUTPUT_SCHEMA)
        with pytest.raises(jsonschema.ValidationError):
            row = {**_CORE_SW_COUNTS, "score": 40}
            jsonschema.validate({**report, "blast_radius": [row]}, TRIAGE_OUTPUT_SCHEMA)

    # ---------------------------------------------------------------------------
    # TestHealthCheck
    # ---------------------------------------------------------------------------

    @pytest.mark.parametrize("ask", [True, False], ids=["token", "no_token"])
    async def test_progress_per_phase_only_when_asked(self, client, lm_env, ask, caplog):
        """R4.3: one notification per phase when the request carries a progressToken, and
        no attempt to send one when it does not."""
        with (
            patch(
                "lm_mcp.tools.analyze_alerts.analyze_alerts",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API timeout"),
            ),
            caplog.at_level(logging.WARNING, logger="lm_mcp.tools"),
        ):
            _, called, received = await _progress_of(client, "triage", {}, ask=ask)

        expected = [(1, 2, "alert window read"), (2, 2, "blast radius read")]
        assert called == (expected if ask else [])
        assert received == (expected if ask else [])
        assert [r for r in caplog.records if "progress" in r.getMessage()] == []

    async def test_a_progress_send_failure_is_logged_and_the_call_goes_on(
        self, client, lm_env, caplog
    ):
        from mcp.server.session import ServerSession

        with (
            patch(
                "lm_mcp.tools.analyze_alerts.analyze_alerts",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API timeout"),
            ),
            patch.object(
                ServerSession,
                "send_progress_notification",
                new_callable=AsyncMock,
                side_effect=anyio.ClosedResourceError(),
            ),
            caplog.at_level(logging.WARNING, logger="lm_mcp.tools"),
        ):
            result, called, _ = await _progress_of(client, "triage", {}, ask=True)

        assert json.loads(result.content[0].text)["blast_radius"] == []
        assert called == []
        assert [r.getMessage() for r in caplog.records if r.name == "lm_mcp.tools"] == [
            "progress notification 1/2 not sent",
            "progress notification 2/2 not sent",
        ]


class TestHealthCheck:
    """Tests for the health_check composite tool."""

    @staticmethod
    def _subs(*datasources: dict) -> ExitStack:
        """Patch every sub-tool but analyze_metric, which reads the series through respx.

        Each datasource's one instance is cpu100 (id 100).
        """
        stack = ExitStack()
        for path, data in (
            ("lm_mcp.tools.devices.get_device", {"id": 1, "displayName": "server-01"}),
            ("lm_mcp.tools.metrics.get_device_datasources", {"datasources": list(datasources)}),
            (
                "lm_mcp.tools.metrics.get_device_instances",
                {"instances": [{"id": 100, "name": "cpu100"}]},
            ),
            ("lm_mcp.tools.alerts.get_alerts", {"total": 0, "alerts": []}),
            ("lm_mcp.tools.scoring.calculate_availability", {"availability_percent": 99.99}),
        ):
            stack.enter_context(_patch_sub(path, data))
        return stack

    @respx.mock
    async def test_summary_trims_the_metrics_block(self, auth, lm_env):
        """The summary level keeps the device id and datasource count and trims metrics."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        respx.get(f"{_DS_URL}/10/instances/100/data").mock(return_value=_steady_cpu_and_mem())

        with self._subs({"id": 10, "name": "CPU"}):
            result = await health_check(client, device_id=1, detail_level="summary")

        data = json.loads(result[0].text)
        assert data["device_id"] == 1
        assert data["datasource_count"] == 1
        assert "metrics" not in data

    @respx.mock
    async def test_full_reads_each_datasource_once_for_summary_and_anomalies(self, auth, lm_env):
        """R2.1: one analyze_metric read per datasource, summary and anomalies over 24 hours."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        cpu_read = respx.get(f"{_DS_URL}/10/instances/100/data").mock(
            return_value=_steady_cpu_and_mem()
        )
        mem_read = respx.get(f"{_DS_URL}/11/instances/100/data").mock(
            return_value=_steady_cpu_and_mem()
        )

        with self._subs({"id": 10, "name": "CPU"}, {"id": 11, "name": "Memory"}):
            result = await health_check(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert cpu_read.call_count == 1
        assert mem_read.call_count == 1
        assert [(row["datasource"], row["instance"]) for row in data["metrics"]] == [
            ("CPU", "cpu100"),
            ("Memory", "cpu100"),
        ]
        analysis = data["metrics"][0]["analysis"]
        assert analysis["hours"] == 24
        assert analysis["analyses"] == ["summary", "anomalies"]
        cpu = analysis["datapoints"]["cpu"]
        assert cpu["summary"]["latest"] == 51.0
        assert set(cpu["anomalies"]) == {"zscore", "iqr", "mad"}
        assert "health_scores" not in data
        assert "anomalies" not in data

    @respx.mock
    async def test_a_failed_read_is_a_warning(self, auth, lm_env):
        """A datasource whose read fails is absent from metrics and named in warnings."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        respx.get(f"{_DS_URL}/10/instances/100/data").mock(return_value=_portal_error())

        with self._subs({"id": 10, "name": "CPU"}):
            result = await health_check(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert data["metrics"] == []
        (warning,) = data["warnings"]
        assert warning.startswith("analyze_metric for CPU failed:")
        assert "portal unavailable" in warning

    @respx.mock
    async def test_an_instance_fetch_failure_is_a_warning(self, auth, lm_env):
        """A datasource whose instance list fails is skipped with a warning naming the fetch."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        with (
            _patch_sub("lm_mcp.tools.devices.get_device", {"id": 1, "displayName": "server-01"}),
            _patch_sub(
                "lm_mcp.tools.metrics.get_device_datasources",
                {"datasources": [{"id": 10, "name": "CPU"}]},
            ),
            patch(
                "lm_mcp.tools.metrics.get_device_instances",
                new_callable=AsyncMock,
                side_effect=RuntimeError("instances down"),
            ),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", {"total": 0, "alerts": []}),
            _patch_sub(
                "lm_mcp.tools.scoring.calculate_availability", {"availability_percent": 99.99}
            ),
        ):
            result = await health_check(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert data["metrics"] == []
        assert data["warnings"] == ["instance fetch for CPU failed: instances down"]

    @staticmethod
    def _subs_but_datasources() -> ExitStack:
        """Patch the sub-tools around the datasource list, which a test serves through respx."""
        stack = ExitStack()
        for path, data in (
            ("lm_mcp.tools.devices.get_device", {"id": 1, "displayName": "server-01"}),
            (
                "lm_mcp.tools.metrics.get_device_instances",
                {"instances": [{"id": 100, "name": "inst100"}]},
            ),
            ("lm_mcp.tools.alerts.get_alerts", {"total": 0, "alerts": []}),
            ("lm_mcp.tools.scoring.calculate_availability", {"availability_percent": 99.99}),
        ):
            stack.enter_context(_patch_sub(path, data))
        return stack

    @respx.mock
    async def test_picks_datasources_by_name_not_position(self, auth, lm_env):
        """R2.3: CPU, memory and disk datasources by name, one of each in turn and
        alphabetical within each; the API's order and a datasource with no instances count
        for nothing, and every datasource is listed in one read.

        Names from a read-only probe of a Windows host on lmryanmatuszewski (2026-11-09),
        where Microsoft_Windows_CPU sat 16th of 102 datasources by position.
        """
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        rows = [
            ("Ping", 1),
            ("HTTP-", 1),
            ("dns", 1),
            ("Port-", 1),
            ("HostStatus", 1),
            ("WinVolumeUsage-", 2),
            ("Win2k12_HyperV_HypervisorMemory", 0),
            ("WinMemory64", 1),
            ("Win_HyperV_CPU", 1),
            ("Microsoft_Windows_CPU", 1),
        ]
        listing = respx.get(_DS_URL).mock(
            return_value=_ok(
                {
                    "items": [
                        {"id": i, "dataSourceName": name, "instanceNumber": count}
                        for i, (name, count) in enumerate(rows, start=1)
                    ],
                    "total": len(rows),
                }
            )
        )
        reads = {
            ds_id: respx.get(f"{_DS_URL}/{ds_id}/instances/100/data").mock(
                return_value=_steady_cpu_and_mem()
            )
            for ds_id in (6, 8, 9, 10)
        }

        with self._subs_but_datasources():
            result = await health_check(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert listing.calls.last.request.url.params["size"] == "1000"
        assert data["datasource_count"] == 10
        assert [row["datasource"] for row in data["metrics"]] == [
            "Microsoft_Windows_CPU",
            "WinMemory64",
            "WinVolumeUsage-",
            "Win_HyperV_CPU",
        ]
        assert all(read.call_count == 1 for read in reads.values())
        jsonschema.validate(data, HEALTH_CHECK_OUTPUT_SCHEMA)

    @respx.mock
    async def test_a_device_without_cpu_memory_or_disk_datasources_is_a_warning(
        self, auth, lm_env, monkeypatch
    ):
        """No positional stand-in: the device's other datasources are not analyzed."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        respx.get(_DS_URL).mock(
            return_value=_ok(
                {
                    "items": [
                        {"id": 1, "dataSourceName": "Ping", "instanceNumber": 1},
                        {"id": 2, "dataSourceName": "HostStatus", "instanceNumber": 1},
                    ],
                    "total": 2,
                }
            )
        )

        with self._subs_but_datasources():
            result = await health_check(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert data["metrics"] == []
        assert data["warnings"] == [
            "None of the device's 2 datasources names CPU, memory or disk with an "
            "instance; metrics is empty."
        ]
        jsonschema.validate(data, HEALTH_CHECK_OUTPUT_SCHEMA)
        structured(
            await replay_through_sdk(
                monkeypatch, "health_check", {"device_id": 1, "detail_level": "full"}, data
            )
        )

    @respx.mock
    async def test_summary_lifts_the_metric_warnings(self, auth, lm_env):
        """A capped read's warnings reach the summary, which trims metrics, one per datapoint."""
        from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        respx.get(f"{_DS_URL}/10/instances/100/data").mock(side_effect=_capped_read())

        with self._subs({"id": 10, "name": "CPU"}):
            result = await health_check(client, device_id=1, detail_level="summary")

        data = json.loads(result[0].text)
        assert "metrics" not in data
        cpu, mem = data["warnings"]
        assert cpu.startswith("CPU/cpu100: cpu: ")
        assert mem.startswith("CPU/cpu100: mem: ")
        assert f"{MAX_SERIES_PAGES}-page cap" in cpu
        jsonschema.validate(data, HEALTH_CHECK_OUTPUT_SCHEMA)

    @respx.mock
    @pytest.mark.parametrize("disabled", ["get_device_datasources", "analyze_metric"])
    async def test_required_tool_blocked(self, client, monkeypatch, disabled):
        """Health check returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", disabled)
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = await health_check(client, device_id=1)
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or disabled in text
        reset_config()

    async def test_sub_tool_failure(self, client, monkeypatch):
        """Health check returns partial results with warnings on sub-tool failure."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        alert_data = {"total": 0, "alerts": []}
        avail_data = {"availability_percent": 99.99}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            patch(
                "lm_mcp.tools.metrics.get_device_datasources",
                new_callable=AsyncMock,
                side_effect=RuntimeError("timeout"),
            ),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alert_data),
            _patch_sub("lm_mcp.tools.scoring.calculate_availability", avail_data),
        ):
            result = await health_check(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert data["datasource_count"] == 0
        assert "warnings" in data
        reset_config()


# ---------------------------------------------------------------------------
# TestCapacityPlan
# ---------------------------------------------------------------------------


class TestCapacityPlan:
    """Tests for the capacity_plan composite tool."""

    @respx.mock
    async def test_summary_trims_the_datasources_block(self, auth, lm_env):
        """The summary level keeps the device and the forecast headlines and trims datasources."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _steady_cpu_and_mem()})

        result = await capacity_plan(client, device_id=1, detail_level="summary")

        data = json.loads(result[0].text)
        assert data["device_id"] == 1
        assert data["forecast_summary"]
        assert "datasources" not in data

    @respx.mock
    async def test_full_reads_each_instance_once_for_every_section(self, auth, lm_env):
        """R2.1: one analyze_metric read per instance carries trend, seasonality, change
        points and the forecast against 90 over hours_back."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _steady_cpu_and_mem(), 101: _steady_cpu_and_mem()})

        result = await capacity_plan(client, device_id=1, hours_back=72, detail_level="full")

        data = json.loads(result[0].text)
        reads = [
            call.request.url.path for call in respx.calls if call.request.url.path.endswith("/data")
        ]
        assert sorted(reads) == [
            "/santaba/rest/device/devices/1/devicedatasources/10/instances/100/data",
            "/santaba/rest/device/devices/1/devicedatasources/10/instances/101/data",
        ]
        (ds,) = data["datasources"]
        assert ds["datasource"] == "CPU"
        analysis = ds["instances"][0]["analysis"]
        assert analysis["hours"] == 72
        assert analysis["analyses"] == ["trend", "seasonality", "change_points", "forecast"]
        cpu = analysis["datapoints"]["cpu"]
        assert set(cpu) >= {"trend", "seasonality", "change_points", "forecast"}
        assert cpu["forecast"]["threshold"] == 90.0

    @respx.mock
    async def test_a_volatile_instance_is_read_once(self, auth, lm_env):
        """Change points come from the read the other sections use: one read per instance."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({102: _swinging_cpu()})

        result = await capacity_plan(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        (read,) = [call for call in respx.calls if call.request.url.path.endswith("/data")]
        cpu = data["datasources"][0]["instances"][0]["analysis"]["datapoints"]["cpu"]
        assert cpu["trend"]["label"] == "volatile"
        assert "change_points" in cpu
        assert read.request.url.path.endswith("/instances/102/data")

    @respx.mock
    async def test_summary_carries_forecast_headlines_and_instance_errors(self, auth, lm_env):
        """R4.4: the summary keeps each forecast's headline and every per-instance error.

        cpu100 climbs 120 an hour to 50, a third of an hour short of the 90 threshold, and
        varies by more than half its mean, so the trend section labels it volatile;
        cpu101's data read fails. The raw datasources block is still trimmed.
        """
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _rising_cpu_and_sparse_mem(), 101: _portal_error()})

        result = await capacity_plan(client, device_id=1)

        data = json.loads(result[0].text)
        assert "datasources" not in data
        cpu, mem = data["forecast_summary"]
        assert cpu["datasource"] == "CPU"
        assert cpu["instance"] == "cpu100"
        assert cpu["datapoint"] == "cpu"
        assert cpu["trend"] == "volatile"
        assert cpu["hours_until_breach"]["linear"] == pytest.approx(1 / 3, abs=1e-3)
        assert cpu["hours_until_breach"]["holt_winters"] is None
        assert mem == {
            "datasource": "CPU",
            "instance": "cpu100",
            "datapoint": "mem",
            "status": "insufficient_data",
        }
        (failed,) = data["warnings"]
        assert failed.startswith("analyze_metric for CPU/cpu101 failed:")
        assert "portal unavailable" in failed

    @respx.mock
    async def test_threshold_sets_each_instance_breach_eta(self, auth, lm_env, monkeypatch):
        """R2.3: threshold reaches analyze_metric's forecast, and each summary row carries
        the breach ETA in epoch seconds beside the hours.

        cpu100 climbs 120 an hour to 50 at its last sample, 40 minutes ago, so 60 is five
        minutes past that sample; mem has one sample and no forecast.
        """
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _rising_cpu_and_sparse_mem()})

        before = int(time.time())
        summary = json.loads((await capacity_plan(client, device_id=1, threshold=60))[0].text)
        full = json.loads(
            (await capacity_plan(client, device_id=1, threshold=60, detail_level="full"))[0].text
        )

        assert summary["threshold"] == 60
        cpu, mem = summary["forecast_summary"]
        assert cpu["hours_until_breach"]["linear"] == pytest.approx(1 / 12, abs=1e-3)
        assert abs(cpu["breach_eta"]["linear"] - (before - 2400 + 300)) <= 2
        assert cpu["breach_eta"]["holt_winters"] is None
        assert "breach_eta" not in mem
        forecast = full["datasources"][0]["instances"][0]["analysis"]["datapoints"]["cpu"]
        assert forecast["forecast"]["threshold"] == 60
        jsonschema.validate(summary, CAPACITY_PLAN_OUTPUT_SCHEMA)
        jsonschema.validate(full, CAPACITY_PLAN_OUTPUT_SCHEMA)
        structured(
            await replay_through_sdk(
                monkeypatch, "capacity_plan", {"device_id": 1, "threshold": 60}, summary
            )
        )
        structured(
            await replay_through_sdk(
                monkeypatch,
                "capacity_plan",
                {"device_id": 1, "threshold": 60, "detail_level": "full"},
                full,
            )
        )

    @respx.mock
    async def test_summary_carries_truncation_warnings_once_per_datapoint(self, auth, lm_env):
        """R5: a capped series reaches the summary, one line per datapoint."""
        from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _capped_read(), 101: _steady_cpu_and_mem()})

        result = await capacity_plan(client, device_id=1)

        data = json.loads(result[0].text)
        assert "datasources" not in data
        cpu, mem = data["warnings"]
        assert cpu.startswith("CPU/cpu100: cpu: ")
        assert mem.startswith("CPU/cpu100: mem: ")
        assert f"{MAX_SERIES_PAGES}-page cap" in cpu

    @respx.mock
    async def test_summary_of_complete_reads_has_no_warnings(self, auth, lm_env):
        """R5: a complete read adds nothing to the summary."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _steady_cpu_and_mem()})

        result = await capacity_plan(client, device_id=1)

        data = json.loads(result[0].text)
        assert data["forecast_summary"]
        assert "warnings" not in data

    @respx.mock
    async def test_full_detail_keeps_truncation_warnings_on_the_instance(self, auth, lm_env):
        """R5: detail_level=full leaves the warning under datasources and copies nothing up."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _capped_read()})

        result = await capacity_plan(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert "warnings" not in data
        instance = data["datasources"][0]["instances"][0]
        assert len(instance["analysis"]["warnings"]) == 2

    @respx.mock
    async def test_full_detail_adds_no_summary_or_copied_errors(self, auth, lm_env):
        """R4.4: detail_level=full keeps the raw block and adds no summary or copied errors."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _rising_cpu_and_sparse_mem(), 101: _portal_error()})

        result = await capacity_plan(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        assert "forecast_summary" not in data
        assert "warnings" not in data
        failed = data["datasources"][0]["instances"][1]
        assert failed["instance"] == "cpu101"
        assert failed["analysis"] is None
        assert "portal unavailable" in failed["analysis_error"]

    @respx.mock
    async def test_surfaces_an_analysis_failure(self, client, monkeypatch):
        """A failing analyze_metric is surfaced as analysis_error, not a silent None."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        ds_data = {"datasources": [{"id": 10, "name": "CPU"}]}
        inst_data = {"instances": [{"id": 100, "name": "main"}]}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_datasources", ds_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_instances", inst_data),
            patch(
                "lm_mcp.tools.analyze_metric.analyze_metric",
                new_callable=AsyncMock,
                side_effect=RuntimeError("analysis down"),
            ),
        ):
            result = await capacity_plan(client, device_id=1, detail_level="full")

        data = json.loads(result[0].text)
        inst0 = data["datasources"][0]["instances"][0]
        assert inst0["analysis"] is None
        assert "analysis down" in inst0["analysis_error"]
        reset_config()

    @respx.mock
    async def test_required_tool_blocked(self, client, monkeypatch):
        """Capacity plan returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "analyze_metric")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = await capacity_plan(client, device_id=1)
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or "analyze_metric" in text
        reset_config()

    async def test_empty_datasources(self, client, monkeypatch):
        """Capacity plan handles a device with no datasources gracefully."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        device_data = {"id": 1, "displayName": "server-01"}
        ds_data = {"datasources": []}

        with (
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.metrics.get_device_datasources", ds_data),
        ):
            result = await capacity_plan(
                client,
                device_id=1,
                detail_level="full",
            )

        data = json.loads(result[0].text)
        assert data["datasources"] == []
        reset_config()

    # ---------------------------------------------------------------------------
    # TestPortalOverview
    # ---------------------------------------------------------------------------

    @pytest.mark.parametrize("ask", [True, False], ids=["token", "no_token"])
    @respx.mock
    async def test_progress_per_phase_only_when_asked(self, auth, lm_env, ask):
        """R4.3: one notification per phase when the request carries a progressToken."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_capacity_portal({100: _rising_cpu_and_sparse_mem()})

        _, called, received = await _progress_of(client, "capacity_plan", {"device_id": 1}, ask=ask)

        expected = [
            (1, 3, "device resolved"),
            (2, 3, "datasources read"),
            (3, 3, "instances analyzed"),
        ]
        assert called == (expected if ask else [])
        assert received == (expected if ask else [])


class TestPortalOverview:
    """Tests for the portal_overview composite tool."""

    async def test_happy_path_summary(self, client, monkeypatch):
        """Portal overview returns expected keys in summary mode."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        stats_data = {"active": 10, "cleared": 0}
        alert_data = {"total": 2, "alerts": []}
        coll_data = {"total": 3, "collectors": []}
        sdt_data = {"active_sdts": []}
        cluster_data = {"clusters": [], "cluster_count": 0}
        noise_data = {"noise_score": 5}
        dead_data = {"devices": [], "total": 0}

        with (
            _patch_window(statistics=stats_data, clusters=cluster_data, noise=noise_data),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alert_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", coll_data),
            _patch_sub("lm_mcp.tools.sdts.get_active_sdts", sdt_data),
            _patch_sub("lm_mcp.tools.devices.get_devices", dead_data),
        ):
            result = await portal_overview(client, detail_level="summary")

        data = json.loads(result[0].text)
        assert data["alert_statistics"] == stats_data
        assert data["alert_clusters"] == cluster_data
        assert data["noise"] == noise_data
        # summary strips detail lists
        assert "critical_alerts" not in data
        assert "dead_devices" not in data
        reset_config()

    async def test_happy_path_full(self, client, monkeypatch):
        """Portal overview full mode includes all keys."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        stats_data = {"active": 10, "cleared": 0}
        alert_data = {"total": 2, "alerts": []}
        coll_data = {"total": 3, "collectors": []}
        sdt_data = {"active_sdts": []}
        cluster_data = {"clusters": [], "cluster_count": 0}
        noise_data = {"noise_score": 5}
        dead_data = {"devices": [], "total": 0}

        with (
            _patch_window(statistics=stats_data, clusters=cluster_data, noise=noise_data),
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alert_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", coll_data),
            _patch_sub("lm_mcp.tools.sdts.get_active_sdts", sdt_data),
            _patch_sub("lm_mcp.tools.devices.get_devices", dead_data),
        ):
            result = await portal_overview(client, detail_level="full")

        data = json.loads(result[0].text)
        assert "critical_alerts" in data
        assert "dead_devices" in data
        reset_config()

    async def test_required_tool_blocked(self, client, monkeypatch):
        """Portal overview returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "get_collectors")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = await portal_overview(client)
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or "get_collectors" in text
        reset_config()

    @staticmethod
    def _mock_portal() -> dict[str, respx.Route]:
        return {
            "alerts": respx.get(_ALERTS_URL).mock(
                side_effect=alert_lists(_one_alert_per_device(2))
            ),
            "audit": respx.get(_AUDIT_URL).mock(return_value=_ok({"items": []})),
            "collectors": respx.get(f"{_BASE}/setting/collector/collectors").mock(
                return_value=_ok({"items": [{"id": 1, "hostname": "coll-1"}], "total": 1})
            ),
            "sdts": respx.get(f"{_BASE}/sdt/sdts").mock(
                return_value=_ok({"items": [], "total": 0})
            ),
            "devices": respx.get(f"{_BASE}/device/devices").mock(
                return_value=_ok({"items": [{"id": 5, "displayName": "dead-1"}], "total": 1})
            ),
        }

    @respx.mock
    async def test_summary_reads_alerts_collectors_and_sdts_once(self, auth, lm_env, monkeypatch):
        """R2.3: summary reads the alert window once (one active and one
        cleared request), collectors once and SDTs once, and skips the open-alert and
        dead-device reads whose lists it does not report."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        routes = self._mock_portal()

        data = json.loads((await portal_overview(client, hours_back=8))[0].text)

        assert len(_window_reads(routes["alerts"])) == 2
        assert routes["alerts"].call_count == 2
        assert routes["collectors"].call_count == 1
        assert routes["sdts"].call_count == 1
        assert routes["devices"].call_count == 0
        assert routes["audit"].call_count == 0
        assert data["alert_statistics"]["active"] == 2
        assert data["alert_clusters"]["cluster_count"] == 2
        assert data["noise"]["total_alerts"] == 2
        assert set(data) == {
            "hours_back",
            "detail_level",
            "alert_statistics",
            "alert_clusters",
            "noise",
            "collectors",
            "active_sdts",
        }
        jsonschema.validate(data, PORTAL_OVERVIEW_OUTPUT_SCHEMA)
        structured(
            await replay_through_sdk(monkeypatch, "portal_overview", {"hours_back": 8}, data)
        )

    @respx.mock
    async def test_full_adds_the_open_alert_and_dead_device_reads(self, auth, lm_env):
        """Full keeps the portal-wide open critical and error lists, read once each."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        routes = self._mock_portal()

        data = json.loads((await portal_overview(client, detail_level="full"))[0].text)

        open_reads = [
            c.request.url.params["filter"].split(",")
            for c in routes["alerts"].calls
            if "startEpoch>:" not in c.request.url.params.get("filter", "")
        ]
        assert len(_window_reads(routes["alerts"])) == 2
        assert sorted(next(x for x in r if x.startswith("severity:")) for r in open_reads) == [
            "severity:3",
            "severity:4",
        ]
        assert all("cleared:false" in r for r in open_reads)
        assert routes["collectors"].call_count == 1
        assert routes["sdts"].call_count == 1
        assert routes["devices"].call_count == 1
        assert set(data) == set(PORTAL_OVERVIEW_OUTPUT_SCHEMA["properties"]) - {"warnings"}
        jsonschema.validate(data, PORTAL_OVERVIEW_OUTPUT_SCHEMA)

    @respx.mock
    async def test_only_full_mode_needs_get_alerts_and_get_devices(self, auth, lm_env, monkeypatch):
        """Summary never calls get_alerts or get_devices, so disabling them refuses only full."""
        from lm_mcp.config import reset_config

        monkeypatch.setenv("LM_DISABLED_TOOLS", "get_alerts,get_devices")
        reset_config()
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        self._mock_portal()

        summary = json.loads((await portal_overview(client))[0].text)
        full = (await portal_overview(client, detail_level="full"))[0].text
        reset_config()

        assert summary["alert_statistics"]["active"] == 2
        jsonschema.validate(summary, PORTAL_OVERVIEW_OUTPUT_SCHEMA)
        assert "requires disabled tools: get_alerts, get_devices" in full

    async def test_a_report_of_failed_reads_validates_against_the_schema(self, client, lm_env):
        """Every read failing leaves each key null with one warning per tool, in full mode."""
        failing = {
            name: patch(name, new_callable=AsyncMock, side_effect=RuntimeError("API timeout"))
            for name in (
                "lm_mcp.tools.analyze_alerts.analyze_alerts",
                "lm_mcp.tools.collectors.get_collectors",
                "lm_mcp.tools.sdts.get_active_sdts",
                "lm_mcp.tools.alerts.get_alerts",
                "lm_mcp.tools.devices.get_devices",
            )
        }
        with ExitStack() as stack:
            for patcher in failing.values():
                stack.enter_context(patcher)
            data = json.loads((await portal_overview(client, detail_level="full"))[0].text)

        null_keys = set(PORTAL_OVERVIEW_OUTPUT_SCHEMA["properties"]) - {
            "hours_back",
            "detail_level",
            "warnings",
        }
        assert {key: data[key] for key in null_keys} == dict.fromkeys(null_keys)
        assert len(data["warnings"]) == 5
        jsonschema.validate(data, PORTAL_OVERVIEW_OUTPUT_SCHEMA)

    def test_the_output_schema_refuses_an_undocumented_key(self):
        report = {
            "hours_back": 4,
            "detail_level": "summary",
            "alert_statistics": None,
            "alert_clusters": None,
            "noise": None,
            "collectors": None,
            "active_sdts": None,
        }
        jsonschema.validate(report, PORTAL_OVERVIEW_OUTPUT_SCHEMA)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**report, "top_talkers": []}, PORTAL_OVERVIEW_OUTPUT_SCHEMA)

    # ---------------------------------------------------------------------------
    # TestDiagnose
    # ---------------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("detail_level", "ask", "expected"),
        [
            (
                "summary",
                True,
                [
                    (1, 3, "alert window read"),
                    (2, 3, "collectors read"),
                    (3, 3, "active SDTs read"),
                ],
            ),
            (
                "full",
                True,
                [
                    (1, 5, "alert window read"),
                    (2, 5, "collectors read"),
                    (3, 5, "active SDTs read"),
                    (4, 5, "open alerts read"),
                    (5, 5, "dead devices read"),
                ],
            ),
            ("full", False, []),
        ],
        ids=["summary", "full", "no_token"],
    )
    @respx.mock
    async def test_progress_per_phase_only_when_asked(
        self, auth, lm_env, detail_level, ask, expected
    ):
        """R4.3: one notification per phase when the request carries a progressToken."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        self._mock_portal()

        _, called, received = await _progress_of(
            client, "portal_overview", {"detail_level": detail_level}, ask=ask
        )

        assert called == expected
        assert received == expected


class TestDiagnose:
    """Tests for the diagnose composite tool."""

    async def test_happy_path_with_alert_id(self, client, monkeypatch):
        """Diagnose by alert_id returns expected keys."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        alert_detail = {
            "id": "LMA123",
            "severity": 4,
            "monitorObjectId": 42,
            "monitorObjectName": "server-01",
        }
        device_data = {"id": 42, "displayName": "server-01"}
        props_data = {"properties": [{"name": "os", "value": "linux"}]}
        corr_data = {"clusters": [], "cluster_count": 0}
        changes_data = {"correlated_events": []}
        blast_data = {"neighbor_count": 1, "dependent_count": 0, "unreadable": []}

        with (
            _patch_sub("lm_mcp.tools.alerts.get_alert_details", alert_detail),
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.resources.get_device_properties", props_data),
            _patch_window(clusters=corr_data, changes=changes_data),
            _patch_sub("lm_mcp.tools.topology_analysis.analyze_blast_radius", blast_data),
            _patch_no_diagnostics(),
        ):
            result = await diagnose(client, alert_id="LMA123", detail_level="full")

        data = json.loads(result[0].text)
        assert data.get("alert", {}).get("id") == "LMA123"
        assert "device" in data
        assert "blast_radius" in data
        assert data["correlated_alerts"] == corr_data
        assert data["changes"] == changes_data
        reset_config()

    async def test_happy_path_with_device_name(self, client, monkeypatch):
        """Diagnose by device_name resolves most recent critical alert."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        alerts_list = {"total": 1, "alerts": [{"id": "LMA456", "severity": 4}]}
        alert_detail = {
            "id": "LMA456",
            "severity": 4,
            "monitorObjectId": 55,
        }
        device_data = {"id": 55, "displayName": "db-01"}
        props_data = {"properties": []}
        corr_data = {"clusters": [], "cluster_count": 0}
        changes_data = {"correlated_events": []}
        blast_data = {"neighbor_count": 0, "dependent_count": 0, "unreadable": []}

        with (
            _patch_sub("lm_mcp.tools.alerts.get_alerts", alerts_list),
            _patch_sub("lm_mcp.tools.alerts.get_alert_details", alert_detail),
            _patch_sub("lm_mcp.tools.devices.get_device", device_data),
            _patch_sub("lm_mcp.tools.resources.get_device_properties", props_data),
            _patch_window(clusters=corr_data, changes=changes_data),
            _patch_sub("lm_mcp.tools.topology_analysis.analyze_blast_radius", blast_data),
            _patch_no_diagnostics(),
        ):
            result = await diagnose(client, device_name="db-01", detail_level="full")

        data = json.loads(result[0].text)
        assert data.get("alert", {}).get("id") == "LMA456"
        reset_config()

    async def test_missing_params(self, client, monkeypatch):
        """Diagnose returns error when neither alert_id nor device_name given."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = await diagnose(client)
        text = result[0].text
        assert "MISSING_PARAMS" in text or "alert_id or device_name" in text
        reset_config()

    async def test_required_tool_blocked(self, client, monkeypatch):
        """Diagnose returns error when a required tool is disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "analyze_blast_radius")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        from lm_mcp.config import reset_config

        reset_config()

        result = await diagnose(client, alert_id="LMA123")
        text = result[0].text
        assert "REQUIRED_TOOLS_DISABLED" in text or "analyze_blast_radius" in text
        reset_config()

    @staticmethod
    def _context_subs(blast: dict) -> ExitStack:
        """Patch the alert, device, window and blast-radius reads for alert DS362333940 on
        host 1786, the ids of the ADR fixtures; the ADR reads go through respx."""
        stack = ExitStack()
        for path, data in (
            (
                "lm_mcp.tools.alerts.get_alert_details",
                {"id": "DS362333940", "severity": 4, "monitorObjectId": 1786},
            ),
            ("lm_mcp.tools.devices.get_device", {"id": 1786, "displayName": "web-01"}),
            ("lm_mcp.tools.resources.get_device_properties", {"properties": []}),
            ("lm_mcp.tools.topology_analysis.analyze_blast_radius", blast),
        ):
            stack.enter_context(_patch_sub(path, data))
        stack.enter_context(
            _patch_window(clusters={"clusters": [], "cluster_count": 0}, changes={})
        )
        return stack

    @respx.mock
    async def test_reads_the_assigned_diagnostics_and_their_latest_results(
        self, auth, lm_env, monkeypatch
    ):
        """rul-43402c07ec: the device's assigned DiagnosticSources and the latest results of
        the alert's diagnostic runs, read and never run; the summary lifts the trimmed blast
        radius' warning."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        assigned = respx.get(f"{_BASE}/setting/diagnosticRemediation/list").mock(
            return_value=_ok({"items": [_assigned_source()], "total": 1})
        )
        results = respx.get(f"{_BASE}/setting/diagnosticRemediation/executionResults").mock(
            return_value=_ok({"items": [_execution()], "total": 1})
        )
        blast = {"neighbor_count": 0, "dependent_count": 0, "unreadable": [9], "warning": "w"}

        with self._context_subs(blast):
            result = await diagnose(client, alert_id="DS362333940")

        data = json.loads(result[0].text)
        assert dict(assigned.calls.last.request.url.params) == {
            "resourceId": "1786",
            "moduleType": "diagnosticsource",
        }
        results_params = results.calls.last.request.url.params
        assert results_params["alertId"] == "DS362333940"
        assert results_params["moduleType"] == "diagnostic"
        assert "hostId" not in results_params
        assert {call.request.method for call in respx.calls} == {"GET"}
        diagnostics = data["diagnostics"]
        assert [s["name"] for s in diagnostics["assigned"]] == ["Top CPU Processes"]
        (run,) = diagnostics["latest_results"]
        assert (run["status"], run["output"]) == ("COMPLETED", "PID 4242 java 93%")
        assert "blast_radius" not in data
        assert data["warnings"] == ["blast_radius: w"]
        jsonschema.validate(data, DIAGNOSE_OUTPUT_SCHEMA)
        structured(
            await replay_through_sdk(monkeypatch, "diagnose", {"alert_id": "DS362333940"}, data)
        )

    @respx.mock
    async def test_a_failed_diagnostics_read_is_a_warning(self, auth, lm_env, caplog):
        """A portal without ADR, or a failed read, leaves that list null and names it, and
        the failure is logged with its traceback."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        respx.get(f"{_BASE}/setting/diagnosticRemediation/list").mock(return_value=_portal_error())
        respx.get(f"{_BASE}/setting/diagnosticRemediation/executionResults").mock(
            return_value=_portal_error()
        )

        with self._context_subs({"neighbor_count": 0, "dependent_count": 0, "unreadable": []}):
            result = await diagnose(client, alert_id="DS362333940", detail_level="full")

        data = json.loads(result[0].text)
        assert data["diagnostics"] == {"assigned": None, "latest_results": None}
        assigned_warning, results_warning = data["warnings"]
        assert assigned_warning.startswith("get_diagnostic_remediation_assignments failed:")
        assert results_warning.startswith("get_diagnostic_remediation_results failed:")
        jsonschema.validate(data, DIAGNOSE_OUTPUT_SCHEMA)
        logged = [r for r in caplog.records if r.name == "lm_mcp.audit" and r.exc_info]
        assert [r.getMessage().split(" failed")[0] for r in logged] == [
            "diagnose: get_diagnostic_remediation_assignments",
            "diagnose: get_diagnostic_remediation_results",
        ]

    def test_the_description_says_no_health_score_is_computed(self):
        """R2.3: diagnose stops promising a health score and says it computes none."""
        from lm_mcp.registry import TOOLS

        (tool,) = [t for t in TOOLS if t.name == "diagnose"]
        assert "computes no health score" in tool.description
        assert "health_score" not in DIAGNOSE_OUTPUT_SCHEMA["properties"]

    def test_nothing_offers_the_removed_health_score(self):
        """Step 33 removed score_device_health: a tool description or best practice names
        the health score only as absent or removed."""
        from lm_mcp.registry import TOOLS
        from lm_mcp.resources.best_practices import BEST_PRACTICES

        for text in [t.description for t in TOOLS] + [json.dumps(BEST_PRACTICES)]:
            for match in re.finditer(r"health scores?", text):
                assert text[: match.start()].endswith(("no ", "removed 0 to 100 ")), text

    @respx.mock
    async def test_reads_the_alert_window_once(self, auth, lm_env):
        """R2.2: the last four hours are read once for clusters and changes."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        alerts = respx.get(_ALERTS_URL).mock(side_effect=alert_lists(_one_alert_per_device(2)))
        audit = respx.get(_AUDIT_URL).mock(return_value=_ok({"items": []}))

        before = int(time.time())
        with _patch_sub("lm_mcp.tools.alerts.get_alert_details", {"id": "LMA1"}):
            result = await diagnose(client, alert_id="LMA1", detail_level="full")

        data = json.loads(result[0].text)
        reads = _window_reads(alerts)
        assert len(reads) == 2
        assert alerts.call_count == 2
        start = int(next(c for c in reads[0] if c.startswith("startEpoch>:")).split(":")[1])
        assert before - 4 * 3600 <= start <= int(time.time()) - 4 * 3600
        assert audit.call_count == 1
        assert data["correlated_alerts"]["cluster_count"] == 2
        assert data["changes"]["total_changes"] == 0


# ---------------------------------------------------------------------------
# TestSearchTools
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("lm_env")
class TestSearchTools:
    """Tests for the search_tools discovery tool."""

    async def test_keyword_name_match(self, client):
        """Searching for a tool name returns it with high score."""
        result = await search_tools(client, query="get_alerts")
        data = json.loads(result[0].text)
        matches = data["matches"]
        assert len(matches) > 0
        # The exact name match should be first
        assert matches[0]["name"] == "get_alerts"

    async def test_description_match(self, client):
        """Searching for a word in descriptions returns relevant tools."""
        result = await search_tools(client, query="forecast")
        data = json.loads(result[0].text)
        assert data["total"] > 0
        tool_names = [m["name"] for m in data["matches"]]
        assert "analyze_metric" in tool_names

    async def test_category_filter(self, client):
        """Category filter restricts results to that category's tools."""
        result = await search_tools(client, query="alert", category="alerts")
        data = json.loads(result[0].text)
        # All results should be from the alerts category
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        alert_tools = set(TOOL_CATEGORIES["categories"]["alerts"]["tools"])
        for match in data["matches"]:
            assert match["name"] in alert_tools

    async def test_limit(self, client):
        """Limit parameter caps the number of results."""
        result = await search_tools(client, query="get", limit=3)
        data = json.loads(result[0].text)
        assert len(data["matches"]) <= 3

    async def test_composite_suggestion(self, client):
        """Workflow-related queries suggest composite tools."""
        result = await search_tools(client, query="incident triage")
        data = json.loads(result[0].text)
        suggestions = data.get("suggestions") or []
        assert "triage" in suggestions or "diagnose" in suggestions

    async def test_no_matches(self, client):
        """Non-matching query returns empty results."""
        result = await search_tools(client, query="xyznonexistent123")
        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["matches"] == []


# ---------------------------------------------------------------------------
# TestCallSubTool (robustness against non-JSON / error-formatted responses)
# ---------------------------------------------------------------------------


class TestCallSubTool:
    """Direct tests for `call_sub_tool` parse and error-handling behavior."""

    async def test_happy_path_returns_parsed_json(self, client):
        from mcp.types import TextContent

        async def handler(_client):
            return [TextContent(type="text", text=json.dumps({"ok": True, "n": 42}))]

        data = await call_sub_tool(handler, client)
        assert data == {"ok": True, "n": 42}

    async def test_error_formatted_text_raises_runtime_error(self, client):
        """A sub-tool's error envelope raises a clean RuntimeError with its message.

        `call_sub_tool` must not hand the composite the envelope as data.
        """

        async def handler(_client):
            return validation_error("NOT_FOUND", "collector 999 not found", "Verify the ID.")

        with pytest.raises(RuntimeError, match=r"^collector 999 not found\. Verify the ID\.$"):
            await call_sub_tool(handler, client)

    async def test_non_json_non_error_text_raises_with_snippet(self, client):
        """Text that is not JSON surfaces a snippet."""
        from mcp.types import TextContent

        async def handler(_client):
            return [TextContent(type="text", text="<html>gateway timeout</html>")]

        with pytest.raises(RuntimeError, match="non-JSON response"):
            await call_sub_tool(handler, client)

    async def test_dict_with_error_field_raises(self, client):
        """A parsed error envelope triggers RuntimeError with its message."""
        from mcp.types import TextContent

        async def handler(_client):
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": {"code": "NOT_FOUND", "message": "nope"}}),
                )
            ]

        with pytest.raises(RuntimeError, match="nope"):
            await call_sub_tool(handler, client)


# ---------------------------------------------------------------------------
# TestSiteOutageHelpers (shape compatibility with get_devices formatted output)
# ---------------------------------------------------------------------------


class TestSiteOutageHelpers:
    """Direct tests for _collector_ids_from_devices and _count_dead_devices.

    These helpers receive output from the formatted `get_devices` sub-tool
    (which renames `currentCollectorId` -> `collector_id` and `hostStatus`
    -> `status`). The helpers must handle both shapes.
    """

    def test_collector_ids_from_formatted_shape(self):
        """Formatted get_devices output uses `collector_id`."""
        from lm_mcp.tools.workflows import _collector_ids_from_devices

        devices = [
            {"id": 1, "collector_id": 10},
            {"id": 2, "collector_id": 10},  # duplicate
            {"id": 3, "collector_id": 20},
            {"id": 4, "collector_id": None},  # unassigned
        ]
        assert _collector_ids_from_devices(devices) == [10, 20]

    def test_collector_ids_from_raw_shape(self):
        """Raw LM API items use `currentCollectorId`."""
        from lm_mcp.tools.workflows import _collector_ids_from_devices

        devices = [
            {"id": 1, "currentCollectorId": 11},
            {"id": 2, "preferredCollectorId": 22},
        ]
        assert _collector_ids_from_devices(devices) == [11, 22]

    def test_collector_ids_empty(self):
        """No collector fields present returns empty list."""
        from lm_mcp.tools.workflows import _collector_ids_from_devices

        assert _collector_ids_from_devices([{"id": 1}]) == []

    def test_dead_devices_counts_dead_and_dead_collector(self):
        """R6.1: both hostStatus "dead" and "dead-collector" count."""
        from lm_mcp.tools.workflows import _count_dead_devices

        devices = [
            {"id": 1, "status": "normal"},
            {"id": 2, "status": "dead"},
            {"id": 3, "status": "dead-collector"},
            {"id": 4, "status": "unmonitored"},  # not counted
        ]
        assert _count_dead_devices(devices) == 2

    def test_dead_devices_accepts_raw_host_status_field(self):
        """R6.1: raw LM API shape uses `hostStatus` not `status`."""
        from lm_mcp.tools.workflows import _count_dead_devices

        devices = [
            {"id": 1, "hostStatus": "dead"},
            {"id": 2, "hostStatus": "dead-collector"},
            {"id": 3, "hostStatus": "normal"},
        ]
        assert _count_dead_devices(devices) == 2

    def test_dead_devices_ignores_numeric_host_status(self):
        """R6.1: the v3 API reports hostStatus as a word, so a number is not a dead device."""
        from lm_mcp.tools.workflows import _count_dead_devices

        devices = [
            {"id": 1, "hostStatus": 1},
            {"id": 2, "hostStatus": 2},
            {"id": 3, "status": "1"},
            {"id": 4, "status": "2"},
        ]
        assert _count_dead_devices(devices) == 0

    def test_dead_devices_falls_back_to_alert_status(self):
        """When hostStatus absent, alertStatus strings still flag dead devices."""
        from lm_mcp.tools.workflows import _count_dead_devices

        devices = [
            {"id": 1, "alertStatus": "dead"},
            {"id": 2, "alertStatus": "dead-collector"},
            {"id": 3, "alertStatus": "normal"},
        ]
        assert _count_dead_devices(devices) == 2


# ---------------------------------------------------------------------------
# TestDetectSiteOutage
# ---------------------------------------------------------------------------


class TestDetectSiteOutage:
    """Tests for the detect_site_outage composite."""

    @pytest.fixture(autouse=True)
    def _reset_config(self, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_MCP_CATEGORIES", raising=False)
        from lm_mcp.config import reset_config

        reset_config()
        yield
        reset_config()

    async def test_the_collector_down_signal_cites_each_down_collectors_evidence(
        self, client, monkeypatch
    ):
        """R3.4: the evidence get_collector_health read for each down collector, once per
        collector, rides on the collector_down signal; an up collector adds none."""
        from lm_mcp.tools.workflows import detect_site_outage

        evidence = {
            "status_check": {"finished": True, "checks_ok": 0, "problems": [{"name": "x"}]},
            "recent_events": [{"message": "The collector is down or unreachable"}],
        }
        records = {
            1: {"id": 1, "hostname": "col-01", "is_down": True, "evidence": evidence},
            2: {"id": 2, "hostname": "col-02", "is_down": False, "evidence": {}},
        }
        health = AsyncMock(
            side_effect=lambda client, collector_id, include_history: _mock_text(
                {"collectors": [records[collector_id]]}
            )
        )
        devices_data = {
            "devices": [
                {"id": 1, "status": "dead-collector", "collector_id": 1},
                {"id": 2, "status": "normal", "collector_id": 2},
            ]
        }

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            patch("lm_mcp.tools.collectors.get_collector_health", health),
            _patch_window(bursts={"bursts_detected": 0, "bursts": []}),
            _patch_sub(
                "lm_mcp.tools.networking.get_power_events",
                {"total_power_events": 0, "events": []},
            ),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        jsonschema.validate(data, DETECT_SITE_OUTAGE_OUTPUT_SCHEMA)
        structured(
            await replay_through_sdk(monkeypatch, "detect_site_outage", {"group_id": 42}, data)
        )
        assert sorted(call.kwargs["collector_id"] for call in health.await_args_list) == [1, 2]
        assert data["signals"]["collector_down"] == {
            "triggered": True,
            "count": 1,
            "weight": 40,
            "evidence": [{"collector_id": 1, "hostname": "col-01", "evidence": evidence}],
        }

    async def test_all_signals_trigger_site_outage_detected(self, client):
        """CollectorDown + burst + power + silence → verdict = site_outage_detected.

        Uses the formatted `get_devices` shape (`status`, `collector_id`) that
        the composite actually receives from the sub-tool dispatch.
        """
        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {
            "devices": [{"id": i, "status": "dead", "collector_id": 1} for i in range(10)]
        }
        collector_data = {
            "total_collectors": 1,
            "collectors_down": 1,
            "collectors": [{"id": 1, "hostname": "col-01", "is_down": True}],
        }
        burst_data = {
            "bursts_detected": 1,
            "bursts": [{"datasource": "SNMP_Network_Interfaces", "alert_count": 20}],
        }
        power_data = {
            "total_power_events": 3,
            "events": [
                {"id": 1, "datasource": "APC_UPS_Battery"},
                {"id": 2, "datasource": "APC_UPS_Battery"},
                {"id": 3, "datasource": "Liebert_UPS"},
            ],
        }

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collector_health", collector_data),
            _patch_window(bursts=burst_data),
            _patch_sub("lm_mcp.tools.networking.get_power_events", power_data),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["verdict"] == "site_outage_detected"
        assert data["confidence"] == 100
        assert data["signals"]["collector_down"]["triggered"] is True
        assert data["signals"]["interface_burst"]["triggered"] is True
        assert data["signals"]["power_events"]["triggered"] is True

    async def test_no_signals_returns_no_outage(self, client):
        """Clean state → verdict = no_outage_signature."""
        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {"devices": [{"id": 1, "status": "normal", "collector_id": 1}]}
        collector_data = {
            "total_collectors": 1,
            "collectors_down": 0,
            "collectors": [{"id": 1, "hostname": "col-01", "is_down": False}],
        }
        burst_data = {"bursts_detected": 0, "bursts": []}
        power_data = {"total_power_events": 0, "events": []}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collector_health", collector_data),
            _patch_window(bursts=burst_data),
            _patch_sub("lm_mcp.tools.networking.get_power_events", power_data),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["verdict"] == "no_outage_signature"
        assert data["confidence"] == 0

    async def test_possible_outage_at_boundary(self, client):
        """Burst + power (no collector down) → 50 confidence → possible_site_outage."""
        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {"devices": [{"id": 1, "status": "normal", "collector_id": 1}]}
        collector_data = {
            "total_collectors": 1,
            "collectors_down": 0,
            "collectors": [{"id": 1, "hostname": "col-01", "is_down": False}],
        }
        burst_data = {"bursts_detected": 1, "bursts": []}
        power_data = {"total_power_events": 2, "events": []}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collector_health", collector_data),
            _patch_window(bursts=burst_data),
            _patch_sub("lm_mcp.tools.networking.get_power_events", power_data),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["verdict"] == "possible_site_outage"
        assert data["confidence"] == 50

    async def test_sub_tool_failure_appends_warning(self, client):
        """Failure in one sub-tool is captured as warning, composite continues."""
        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {"devices": [{"id": 1, "status": "dead", "collector_id": 1}]}

        async def failing_mock(*args, **kwargs):
            raise RuntimeError("sub-tool exploded")

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            patch(
                "lm_mcp.tools.collectors.get_collector_health",
                new_callable=AsyncMock,
                side_effect=failing_mock,
            ),
            _patch_window(bursts={"bursts_detected": 0, "bursts": []}),
            _patch_sub(
                "lm_mcp.tools.networking.get_power_events",
                {"total_power_events": 0, "events": []},
            ),
        ):
            result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert len(data["warnings"]) >= 1
        assert any("collector health probes failed" in w for w in data["warnings"])
        assert any("collector_id=1" in w for w in data["warnings"])
        # A failed probe leaves the CollectorDown signal unknown, not untriggered.
        assert data["signals"]["collector_down"]["triggered"] is None
        assert data["signals"]["collector_down"]["status"] == "unavailable"
        assert data["unavailable_signals"] == ["collector_down"]

    async def test_partial_collector_failures_do_not_abort_loop(self, client):
        """One bad collector probe no longer aborts the rest (v3.8.2 fix).

        Composite must continue probing remaining collector IDs and
        surface a single aggregate warning summarizing the failures.
        """
        from mcp.types import TextContent

        from lm_mcp.tools.workflows import detect_site_outage

        devices_data = {
            "devices": [
                {"id": 1, "status": "dead", "collector_id": 10},
                {"id": 2, "status": "dead", "collector_id": 20},
                {"id": 3, "status": "dead", "collector_id": 30},
            ]
        }

        async def selective_health(_client, collector_id, **_kwargs):
            # Collector 20 fails; 10 and 30 succeed.
            if collector_id == 20:
                return validation_error("NOT_FOUND", "collector 20 not found", "Verify ID.")
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "total_collectors": 1,
                            "collectors_down": 0,
                            "collectors": [
                                {
                                    "id": collector_id,
                                    "hostname": f"col-{collector_id}",
                                    "is_down": False,
                                }
                            ],
                        }
                    ),
                )
            ]

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            patch(
                "lm_mcp.tools.collectors.get_collector_health",
                new_callable=AsyncMock,
                side_effect=selective_health,
            ),
            _patch_window(bursts={"bursts_detected": 0, "bursts": []}),
            _patch_sub(
                "lm_mcp.tools.networking.get_power_events",
                {"total_power_events": 0, "events": []},
            ),
        ):
            result = await detect_site_outage(client, group_id=42, detail_level="full")

        data = json.loads(result[0].text)
        # Composite kept going past collector 20 and probed 30.
        inspected_ids = [c.get("id") for c in data["collectors_inspected"]]
        assert 10 in inspected_ids
        assert 30 in inspected_ids
        assert 20 not in inspected_ids
        # Warning mentions the failed collector specifically.
        assert any("collector_id=20" in w for w in data["warnings"])
        assert any("1/3" in w for w in data["warnings"])

    @respx.mock
    async def test_failed_burst_read_is_unavailable_not_negative(self, auth):
        """R4.4: a failed burst read is unknown; power alone cannot settle the verdict.

        Power (25) is the only known trigger. Read as untriggered, the lost burst
        signal would have scored 25 and said no_outage_signature; known, it could
        have reached 50, so the verdict cannot be named.
        """
        from lm_mcp.tools.workflows import detect_site_outage

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(1, "normal"),
            collector=_collector_record(False),
            burst=_portal_error(),
            power=_alert_window(_power_alert()),
        )

        result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        burst = data["signals"]["interface_burst"]
        assert burst["triggered"] is None
        assert burst["status"] == "unavailable"
        assert "portal unavailable" in burst["error"]
        assert data["signals"]["power_events"] == {"triggered": True, "count": 1, "weight": 25}
        assert data["confidence"] == 25
        assert data["confidence_level"] == "reduced"
        assert data["unavailable_signals"] == ["interface_burst"]
        assert data["verdict"] == "indeterminate"
        assert any("Burst detection failed" in w for w in data["warnings"])

    @respx.mock
    async def test_down_collector_trips_the_collector_signal(self, auth):
        """R5: a collector whose record says isDown trips the signal from a real sub-tool read."""
        from lm_mcp.tools.workflows import detect_site_outage

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(1, "normal"),
            collector=_collector_record(True),
            burst=_alert_window(),
            power=_alert_window(),
        )

        result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["signals"]["collector_down"]["triggered"] is True
        assert data["confidence"] == 40
        assert "unavailable_signals" not in data
        assert "confidence_level" not in data

    @respx.mock
    async def test_record_without_is_down_leaves_the_signal_unknown(self, auth):
        """R4.4: a collector record with no isDown is unknown, not a healthy collector."""
        from lm_mcp.tools.workflows import detect_site_outage

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(1, "normal"),
            collector=_ok({"id": 1, "hostname": "col-01", "status": 1, "numberOfHosts": 5}),
            burst=_alert_window(),
            power=_alert_window(),
        )

        result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["signals"]["collector_down"]["triggered"] is None
        assert data["signals"]["collector_down"]["status"] == "unavailable"
        assert data["unavailable_signals"] == ["collector_down"]
        assert data["confidence_level"] == "reduced"
        assert not any("collector health probes failed" in w for w in data["warnings"])

    @respx.mock
    async def test_up_collector_leaves_the_signal_untriggered(self, auth):
        """R5: isDown false is a known negative, so the signal stays in the score untriggered."""
        from lm_mcp.tools.workflows import detect_site_outage

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(1, "normal"),
            collector=_collector_record(False),
            burst=_alert_window(),
            power=_alert_window(),
        )

        result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["signals"]["collector_down"]["triggered"] is False
        assert data["verdict"] == "no_outage_signature"
        assert "unavailable_signals" not in data

    @respx.mock
    async def test_device_scope_reads_the_group_by_exact_membership(self, auth):
        """R5: the site's device read sends hostGroupIds:42, so groups 142 or 420 stay out."""
        from lm_mcp.tools.workflows import detect_site_outage

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(1, "normal"),
            collector=_collector_record(False),
            burst=_alert_window(),
            power=_alert_window(),
        )

        await detect_site_outage(client, group_id=42)

        device_filters = [
            call.request.url.params.get("filter", "")
            for call in respx.calls
            if call.request.url.path.endswith("/device/devices")
        ]
        assert "hostGroupIds:42" in device_filters

    @respx.mock
    async def test_unavailable_signal_that_cannot_change_the_verdict_keeps_it(self, auth):
        """R4.4: the verdict comes from the signals that read when the lost one cannot move it.

        CollectorDown (40), power (25) and silence (10) score 75; the lost burst
        signal could only raise that, and site_outage_detected starts at 70.
        """
        from lm_mcp.tools.workflows import detect_site_outage

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(5, "dead"),
            collector=_collector_record(True),
            burst=_portal_error(),
            power=_alert_window(_power_alert()),
        )

        result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["verdict"] == "site_outage_detected"
        assert data["confidence"] == 75
        assert data["confidence_level"] == "reduced"
        assert data["unavailable_signals"] == ["interface_burst"]
        assert data["signals"]["collector_down"]["triggered"] is True

    @respx.mock
    async def test_every_signal_read_failing_is_indeterminate(self, auth):
        """R4.4: with the collector, burst and power reads all failing, no verdict is named.

        Throttling during an outage fails exactly these reads; before R4.4 the run
        said no_outage_signature.
        """
        from lm_mcp.tools.workflows import detect_site_outage

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(1, "normal"),
            collector=_portal_error(),
            burst=_portal_error(),
            power=_portal_error(),
        )

        result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["verdict"] == "indeterminate"
        assert data["confidence"] == 0
        assert data["confidence_level"] == "reduced"
        assert data["unavailable_signals"] == [
            "collector_down",
            "interface_burst",
            "power_events",
        ]
        for name in ("collector_down", "interface_burst", "power_events"):
            assert data["signals"][name]["triggered"] is None
            assert data["signals"][name]["status"] == "unavailable"
        assert data["signals"]["device_silence"]["triggered"] is False
        assert not any("No outage signature" in r for r in data["recommendations"])

    @respx.mock
    async def test_all_signals_healthy_output_is_unchanged(self, auth):
        """R4.4: with every read answering, the report carries no unavailable-signal fields."""
        from lm_mcp.tools.workflows import detect_site_outage

        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(1, "normal"),
            collector=_collector_record(False),
            burst=_alert_window(),
            power=_alert_window(),
        )

        result = await detect_site_outage(client, group_id=42)

        assert json.loads(result[0].text) == {
            "verdict": "no_outage_signature",
            "confidence": 0,
            "group_id": 42,
            "window_seconds": 300,
            "hours_back": 1,
            "scope": {"devices_in_group": 1, "dead_devices": 0, "collectors_serving_group": 1},
            "signals": {
                "collector_down": {"triggered": False, "count": 0},
                "interface_burst": {"triggered": False, "burst_count": 0},
                "power_events": {"triggered": False, "count": 0},
                "device_silence": {"triggered": False, "dead_devices": 0, "threshold": 3},
            },
            "recommendations": [
                "No outage signature detected. If symptoms persist, widen the group scope "
                "or lengthen the hours_back window."
            ],
            "warnings": [],
        }

    @respx.mock
    async def test_interface_burst_in_the_live_alert_shape_trips_the_signal(self, auth):
        """Five interface alerts on three switches inside the window, keyed on
        resourceTemplateName as live rows carry it, trip the burst signal."""
        from lm_mcp.tools.workflows import detect_site_outage

        now = int(time.time())
        burst_alerts = [
            {
                "id": f"LMA{i}",
                "severity": 4,
                "monitorObjectName": f"sw-{i % 3}",
                "resourceTemplateName": "SNMP_Network_Interfaces",
                "dataPointName": "OperStatus",
                "startEpoch": now - 600 + i * 30,
                "endEpoch": 0,
                "cleared": False,
            }
            for i in range(5)
        ]
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(1, "normal"),
            collector=_collector_record(False),
            burst=_alert_window(*burst_alerts),
            power=_alert_window(),
        )

        result = await detect_site_outage(client, group_id=42)

        data = json.loads(result[0].text)
        assert data["signals"]["interface_burst"] == {
            "triggered": True,
            "burst_count": 1,
            "weight": 25,
        }

    @respx.mock
    @pytest.mark.parametrize("detail_level", ["summary", "full"])
    async def test_reports_validate_against_the_output_schema(self, auth, detail_level):
        """R2.3: the documented keys cover a reduced-confidence report, and full mode
        carries every one of them."""
        client = LogicMonitorClient(base_url=_BASE, auth=auth, max_retries=0)
        _mock_site_portal(
            devices=_site_devices(5, "dead"),
            collector=_collector_record(True),
            burst=_portal_error(),
            power=_alert_window(_power_alert()),
        )

        result = await detect_site_outage(client, group_id=42, detail_level=detail_level)

        data = json.loads(result[0].text)
        assert data["confidence_level"] == "reduced"
        jsonschema.validate(data, DETECT_SITE_OUTAGE_OUTPUT_SCHEMA)
        if detail_level == "full":
            assert set(data) == set(DETECT_SITE_OUTAGE_OUTPUT_SCHEMA["properties"])

    def test_the_output_schema_refuses_an_unknown_signal_state(self):
        """A signal entry takes only the documented fields, and the verdict its four values."""
        report = {
            "verdict": "no_outage_signature",
            "confidence": 0,
            "group_id": 42,
            "window_seconds": 300,
            "hours_back": 1,
            "scope": {"devices_in_group": 1, "dead_devices": 0, "collectors_serving_group": 1},
            "signals": {
                "collector_down": {"triggered": False, "count": 0},
                "interface_burst": {"triggered": False, "burst_count": 0},
                "power_events": {"triggered": False, "count": 0},
                "device_silence": {"triggered": False, "dead_devices": 0, "threshold": 3},
            },
            "recommendations": [],
            "warnings": [],
        }
        jsonschema.validate(report, DETECT_SITE_OUTAGE_OUTPUT_SCHEMA)
        signals = report["signals"]
        for bad in (
            {**report, "verdict": "outage"},
            {**report, "signals": {**signals, "power_events": {"triggered": "maybe"}}},
            {**report, "signals": {**signals, "device_silence": {"triggered": False, "x": 1}}},
        ):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(bad, DETECT_SITE_OUTAGE_OUTPUT_SCHEMA)

    async def test_required_tools_disabled_blocks_composite(self, client, monkeypatch):
        """LM_DISABLED_TOOLS matching a required sub-tool blocks execution."""
        from lm_mcp.config import reset_config
        from lm_mcp.tools.workflows import detect_site_outage

        monkeypatch.setenv("LM_DISABLED_TOOLS", "analyze_alerts")
        reset_config()

        result = await detect_site_outage(client, group_id=42)
        assert "requires disabled tools" in result[0].text
        assert "analyze_alerts" in result[0].text
        reset_config()

    # ---------------------------------------------------------------------------
    # TestAuditNetworkMonitoringCoverage
    # ---------------------------------------------------------------------------

    @pytest.mark.parametrize("ask", [True, False], ids=["token", "no_token"])
    async def test_progress_per_phase_only_when_asked(self, client, lm_env, ask):
        """R4.3: one notification per phase when the request carries a progressToken."""
        health = AsyncMock(
            return_value=_mock_text({"collectors": [{"id": 1, "is_down": False, "evidence": {}}]})
        )
        devices_data = {"devices": [{"id": 1, "status": "normal", "collector_id": 1}]}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            patch("lm_mcp.tools.collectors.get_collector_health", health),
            _patch_window(bursts={"bursts_detected": 0, "bursts": []}),
            _patch_sub(
                "lm_mcp.tools.networking.get_power_events",
                {"total_power_events": 0, "events": []},
            ),
        ):
            _, called, received = await _progress_of(
                client, "detect_site_outage", {"group_id": 42}, ask=ask
            )

        expected = [
            (1, 4, "devices read"),
            (2, 4, "collectors checked"),
            (3, 4, "alert window read"),
            (4, 4, "power events read"),
        ]
        assert called == (expected if ask else [])
        assert received == (expected if ask else [])


class TestAuditNetworkMonitoringCoverage:
    """Tests for the audit_network_monitoring_coverage composite."""

    @pytest.fixture(autouse=True)
    def _reset_config(self, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
        monkeypatch.delenv("LM_MCP_CATEGORIES", raising=False)
        from lm_mcp.config import reset_config

        reset_config()
        yield
        reset_config()

    async def test_reports_power_gap_when_no_ups_devices(self, client):
        """No UPS/PDU → high-severity power gap."""
        from lm_mcp.tools.workflows import audit_network_monitoring_coverage

        devices_data = {
            "devices": [
                {
                    "id": 1,
                    "displayName": "core-switch-01",
                    "systemCategories": "switch,network",
                    "customProperties": [{"name": "snmp.version", "value": "v2c"}],
                },
                {
                    "id": 2,
                    "displayName": "core-switch-02",
                    "systemCategories": "switch,network",
                    "customProperties": [{"name": "snmp.version", "value": "v2c"}],
                },
            ]
        }
        collectors_data = {"collectors": [{"id": 1, "hostname": "col-01", "status": "normal"}]}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", collectors_data),
        ):
            result = await audit_network_monitoring_coverage(client, group_id=1)

        data = json.loads(result[0].text)
        power_gaps = [g for g in data["gaps"] if g["category"] == "power"]
        assert len(power_gaps) == 1
        assert power_gaps[0]["severity"] == "high"
        assert data["inventory"]["total_devices"] == 2
        assert data["coverage_counts"]["snmp_credentialed"] == 2

    async def test_flags_missing_netflow_exporters(self, client):
        """No NetFlow exporters on network gear → medium netflow gap."""
        from lm_mcp.tools.workflows import audit_network_monitoring_coverage

        devices_data = {
            "devices": [
                {
                    "id": 1,
                    "displayName": "router-01",
                    "systemCategories": "router",
                    "customProperties": [{"name": "snmp.version", "value": "v2c"}],
                }
            ]
        }
        collectors_data = {"collectors": [{"id": 1, "status": "normal"}]}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", collectors_data),
        ):
            result = await audit_network_monitoring_coverage(client)

        data = json.loads(result[0].text)
        netflow_gaps = [g for g in data["gaps"] if g["category"] == "netflow"]
        assert len(netflow_gaps) == 1

    async def test_power_coverage_healthy_when_ups_present(self, client):
        """UPS device present → no power gap."""
        from lm_mcp.tools.workflows import audit_network_monitoring_coverage

        devices_data = {
            "devices": [
                {
                    "id": 1,
                    "displayName": "ups-01",
                    "systemCategories": "ups",
                    "customProperties": [],
                }
            ]
        }
        collectors_data = {"collectors": [{"id": 1, "status": "normal"}]}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", collectors_data),
        ):
            result = await audit_network_monitoring_coverage(client)

        data = json.loads(result[0].text)
        assert data["coverage_counts"]["power_monitored_devices"] == 1
        power_gaps = [g for g in data["gaps"] if g["category"] == "power"]
        assert power_gaps == []

    async def test_critical_when_no_collectors(self, client):
        """Zero collectors → critical gap."""
        from lm_mcp.tools.workflows import audit_network_monitoring_coverage

        devices_data = {"devices": []}
        collectors_data = {"collectors": []}

        with (
            _patch_sub("lm_mcp.tools.devices.get_devices", devices_data),
            _patch_sub("lm_mcp.tools.collectors.get_collectors", collectors_data),
        ):
            result = await audit_network_monitoring_coverage(client)

        data = json.loads(result[0].text)
        critical = [g for g in data["gaps"] if g["severity"] == "critical"]
        assert len(critical) == 1
        assert critical[0]["category"] == "collectors"
