# Description: Tests for get_terraform_imports: one Terraform import block per portal object for the
# Description: 16 provider resource types that import by ID, refusals, names and the registry entry.

from __future__ import annotations

import json
import re

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.registry import TOOLS, get_tool_handler
from lm_mcp.tools.terraform_imports import _safe_name, get_terraform_imports
from tests.envelope import envelope

BASE = "https://test.logicmonitor.com/santaba/rest"

# The 16 resources of logicmonitor/logicmonitor v2.1.7 whose docs carry an Import section by ID,
# with the path that lists them and one synthetic row in the keys the 2026-11-13 probe read
# (the sdt and cluster alert conf rows follow the swagger: the sandbox held none).
TYPES = {
    "alert_rule": ("/setting/alert/rules", {"id": 11, "name": "Critical to NOC"}),
    "collector": ("/setting/collector/collectors", {"id": 12, "description": "dc1 collector"}),
    "collector_group": ("/setting/collector/groups", {"id": 13, "name": "Data Center"}),
    "dashboard": ("/dashboard/dashboards", {"id": 14, "name": "Kubernetes Overview"}),
    "dashboard_group": ("/dashboard/groups", {"id": 15, "name": "Platform"}),
    "datasource": ("/setting/datasources", {"id": 16, "name": "HostStatus"}),
    "device": ("/device/devices", {"id": 17, "displayName": "web-01", "name": "10.0.0.17"}),
    "device_group": ("/device/groups", {"id": 18, "name": "Linux Servers"}),
    "device_group_cluster_alert_conf": (
        "/device/groups/42/clusterAlertConf",
        {"id": 19, "dataSourceDisplayName": "Ping", "dataPointName": "PingLossPercent"},
    ),
    "escalation_chain": ("/setting/alert/chains", {"id": 20, "name": "NOC Team"}),
    "report_group": ("/report/groups", {"id": 21, "name": "Firewall Reports"}),
    "role": ("/setting/roles", {"id": 22, "name": "readonly"}),
    "sdt": ("/sdt/sdts", {"id": "R_23", "type": "ResourceSDT"}),
    "website": ("/website/websites", {"id": 24, "name": "Status Page"}),
    "website_group": ("/website/groups", {"id": 25, "name": "Public Sites"}),
    "widget": ("/dashboard/widgets", {"id": 26, "name": "CPU by Host"}),
}

# One HCL import block as the tool writes it.
BLOCK = re.compile(
    r'\Aimport \{\n  to = (logicmonitor_[a-z_]+)\.([a-z_][a-z0-9_]*)\n  id = "([^"]+)"\n\}\Z'
)


@pytest.fixture
def client():
    return LogicMonitorClient(base_url=BASE, auth=BearerAuth("test-token"), timeout=30)


def _kwargs(resource_type: str) -> dict:
    extra = {"device_group_id": 42} if resource_type == "device_group_cluster_alert_conf" else {}
    return {"resource_type": resource_type, **extra}


async def _imports(client, resource_type: str, rows: list[dict], **kwargs) -> tuple[dict, object]:
    path = TYPES[resource_type][0]
    route = respx.get(f"{BASE}{path}").mock(
        return_value=httpx.Response(200, json={"total": len(rows), "items": rows})
    )
    result = await get_terraform_imports(client, **{**_kwargs(resource_type), **kwargs})
    return json.loads(result[0].text), route


class TestImportBlocks:
    @pytest.mark.parametrize("resource_type", list(TYPES))
    @respx.mock
    async def test_one_block_per_object_for_each_importable_type(self, client, resource_type):
        row = TYPES[resource_type][1]
        body, route = await _imports(client, resource_type, [row])

        assert route.call_count == 1
        assert body["resource_type"] == resource_type
        assert body["count"] == 1
        [entry] = body["imports"]
        match = BLOCK.match(entry["import"])
        assert match, entry["import"]
        assert match.group(1) == f"logicmonitor_{resource_type}"
        assert match.group(3) == str(row["id"])
        assert entry["to"] == f"{match.group(1)}.{match.group(2)}"
        assert entry["id"] == row["id"]
        # Each row lists the field that names the object first, after its id.
        name = next(value for key, value in row.items() if key != "id")
        assert entry["name"] == name
        assert match.group(2) == _safe_name(f"{name} {row['id']}")

    @respx.mock
    async def test_the_name_field_and_id_make_the_address(self, client):
        rows = [
            {"id": 17, "displayName": "web-01.prod (eu)", "name": "10.0.0.17"},
            {"id": 9, "name": "10.0.0.9"},
            {"id": 5},
        ]
        body, _ = await _imports(client, "device", rows)

        assert [(e["name"], e["to"]) for e in body["imports"]] == [
            ("web-01.prod (eu)", "logicmonitor_device.web_01_prod_eu_17"),
            ("10.0.0.9", "logicmonitor_device.r_10_0_0_9_9"),
            (None, "logicmonitor_device.device_5"),
        ]

    @respx.mock
    async def test_objects_sharing_a_name_get_distinct_addresses(self, client):
        rows = [{"id": 3, "name": "Linux"}, {"id": 4, "name": "Linux"}]
        body, _ = await _imports(client, "device_group", rows)

        addresses = [e["to"] for e in body["imports"]]
        assert addresses == [
            "logicmonitor_device_group.linux_3",
            "logicmonitor_device_group.linux_4",
        ]

    @respx.mock
    async def test_a_string_id_is_kept_whole(self, client):
        body, _ = await _imports(client, "sdt", [{"id": "R_23", "type": "ResourceSDT"}])

        [entry] = body["imports"]
        assert entry["to"] == "logicmonitor_sdt.resourcesdt_r_23"
        assert entry["import"].endswith('  id = "R_23"\n}')

    @respx.mock
    async def test_the_page_and_filter_reach_the_api(self, client):
        _, route = await _imports(
            client, "dashboard", [], filter='name~"Kube"', limit=25, offset=50
        )

        assert dict(route.calls.last.request.url.params) == {
            "size": "25",
            "offset": "50",
            "filter": 'name~"Kube"',
        }

    @respx.mock
    async def test_the_answer_names_the_next_step_and_the_provider_auth(self, client):
        body, _ = await _imports(client, "role", [TYPES["role"][1]])

        assert "terraform plan -generate-config-out=generated.tf" in body["next_step"]
        assert "LM_API_ID" in body["next_step"] and "LM_API_KEY" in body["next_step"]


class TestRefusals:
    @pytest.mark.parametrize("resource_type", ["service_insights", "devices", ""])
    @respx.mock
    async def test_a_type_without_an_import_is_refused_before_any_call(self, client, resource_type):
        route = respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json={}))

        error = envelope(await get_terraform_imports(client, resource_type=resource_type))

        assert error["code"] == "INVALID_REQUEST"
        assert "alert_rule" in error["message"] and "widget" in error["message"]
        assert route.call_count == 0

    @respx.mock
    async def test_the_cluster_alert_conf_type_needs_a_device_group(self, client):
        route = respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json={}))

        error = envelope(
            await get_terraform_imports(client, resource_type="device_group_cluster_alert_conf")
        )

        assert error["code"] == "INVALID_REQUEST"
        assert "device_group_id" in error["message"]
        assert route.call_count == 0

    @respx.mock
    async def test_any_other_type_refuses_a_device_group(self, client):
        route = respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json={}))

        error = envelope(
            await get_terraform_imports(client, resource_type="device", device_group_id=42)
        )

        assert error["code"] == "INVALID_REQUEST"
        assert "device_group_id" in error["message"]
        assert route.call_count == 0

    @respx.mock
    async def test_an_api_error_is_the_envelope(self, client):
        respx.get(f"{BASE}/setting/roles").mock(
            return_value=httpx.Response(403, json={"errorMessage": "Permission denied"})
        )

        error = envelope(await get_terraform_imports(client, resource_type="role"))

        assert error["code"] == "AUTH_FAILED"


class TestSafeName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Linux Servers", "linux_servers"),
            ("web-01.prod (eu)", "web_01_prod_eu"),
            ("10.0.0.9", "r_10_0_0_9"),
            ("__x__", "x"),
            ("!!!", "resource"),
        ],
    )
    def test_names_become_hcl_identifiers(self, raw, expected):
        assert _safe_name(raw) == expected


class TestRegistry:
    def test_get_terraform_imports_replaces_terraform_generate(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        tools = {tool.name: tool for tool in TOOLS}

        assert "terraform_generate" not in tools
        assert tools["get_terraform_imports"].annotations.readOnlyHint is True
        assert get_tool_handler("get_terraform_imports") is get_terraform_imports
        assert TOOL_CATEGORIES["categories"]["terraform"]["tools"] == ["get_terraform_imports"]

    def test_the_schema_lists_the_16_types(self):
        schema = {tool.name: tool.inputSchema for tool in TOOLS}["get_terraform_imports"]

        assert schema["required"] == ["resource_type"]
        assert schema["properties"]["resource_type"]["enum"] == list(TYPES)
        assert set(schema["properties"]) == {
            "resource_type",
            "filter",
            "limit",
            "offset",
            "device_group_id",
        }
