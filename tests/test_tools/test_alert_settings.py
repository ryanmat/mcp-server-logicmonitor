# Description: Tests for get_alert_settings and update_alert_settings over the /alertsettings
# Description: paths at instance, device and group level, against live reads kept in a fixture.

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from tests.envelope import envelope

BASE = "https://test.logicmonitor.com/santaba/rest"

# Answers of a sandbox portal at X-Version 3 on 2026-11-11 for device 1786 (Ping, instance
# 370242186, device datasource 13522, datasource 1679) and its group 16. device_1786 keeps
# 3 of its 16 rows under the total read. average_inherited is the datapoint "average" with
# no threshold of its own; average_own after the instance PATCH; average_under_group while
# group 16 held "> 100000"; group_16_ping before and group_16_ping_set after that group
# PATCH. alert_expr_corpus is every distinct alertExpr in the portal's datasource definitions.
LIVE = json.loads((Path(__file__).parent.parent / "fixtures" / "alert_settings.json").read_text())

_DEVICE = f"{BASE}/device/devices/1786"
_INSTANCE = f"{_DEVICE}/devicedatasources/13522/instances/370242186/alertsettings"
_GROUP = f"{BASE}/device/groups/16/datasources/1679/alertsettings"
_INSTANCE_ARGS = {"device_id": 1786, "device_datasource_id": 13522, "instance_id": 370242186}


@pytest.fixture
def client():
    return LogicMonitorClient(base_url=BASE, auth=BearerAuth("test-token"), timeout=30)


@pytest.fixture
def writes(monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")


def _body(result: list) -> dict:
    return json.loads(result[0].text)


class TestThresholdGrammar:
    """R3.5: a threshold parses as LogicMonitor writes one, or is refused before any call."""

    def test_every_threshold_the_portals_datasources_hold_parses_but_one(self):
        from lm_mcp.tools.alert_settings import threshold_parses

        refused = [expr for expr in LIVE["alert_expr_corpus"] if not threshold_parses(expr)]

        # The API answered 500 to "!=0" written to an instance: it needs a space after
        # the operator.
        assert refused == ["!=0"]

    @pytest.mark.parametrize(
        "expr",
        [
            "",
            "> 100000 200000 300000",
            ">= .5",
            "delta> 100000",
            "delta|> 100000",
            "|>= 1000",
            "= 2 -1 1",
            "( 00:00 12:00 ) > 100000 , > 200000",
            "( 23:00 24:00 ) < 200 , ( 00:00 23:00 ) < 200 ,> 299",
        ],
    )
    def test_the_forms_the_api_accepted_parse(self, expr):
        from lm_mcp.tools.alert_settings import threshold_parses

        assert threshold_parses(expr)

    @pytest.mark.parametrize(
        "expr", ["> abc", "> 1 2 3 4", "100000", "=> 5", "!=0", ">", "> 1,", ", > 1"]
    )
    def test_the_forms_the_api_refused_or_mishandled_do_not(self, expr):
        from lm_mcp.tools.alert_settings import threshold_parses

        assert not threshold_parses(expr)


class TestGetAlertSettings:
    """R3.5: each level reads its /alertsettings path and projects datapoint, thresholds and
    the level the threshold in force comes from."""

    @respx.mock
    async def test_device_level_pages_the_devices_settings(self, client):
        from lm_mcp.tools.alert_settings import get_alert_settings

        route = respx.get(f"{_DEVICE}/alertsettings").mock(
            return_value=httpx.Response(200, json=LIVE["device_1786"])
        )

        body = _body(await get_alert_settings(client, "device", device_id=1786, limit=3))

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("3", "0")
        assert (body["total"], body["has_more"]) == (16, True)
        assert body["settings"][0] == {
            "setting_id": 10957,
            "datapoint": "ResponseTime",
            "datapoint_id": 10957,
            "instance": "22",
            "instance_id": 370242244,
            "threshold": ">= 500",
            "source": "global",
            "source_group": None,
            "instance_threshold": "",
            "global_threshold": ">= 500",
            "alerting_disabled": False,
        }

    @respx.mock
    async def test_instance_level_lists_the_instances_datapoints(self, client):
        from lm_mcp.tools.alert_settings import get_alert_settings

        respx.get(_INSTANCE).mock(return_value=httpx.Response(200, json=LIVE["instance_list_ping"]))

        body = _body(await get_alert_settings(client, "instance", **_INSTANCE_ARGS))

        assert [(s["datapoint"], s["threshold"], s["source"]) for s in body["settings"]] == [
            ("average", "> 200", "global"),
            ("maxrtt", None, None),
            ("minrtt", None, None),
            ("PingLossPercent", "> 20 70 90", "global"),
            ("recvdpkts", None, None),
            ("sentpkts", None, None),
        ]

    @pytest.mark.parametrize(
        ("key", "threshold", "source", "source_group"),
        [
            ("average_inherited", "> 200", "global", None),
            ("average_own", "> 100000 200000 300000", "instance", None),
            (
                "average_under_group",
                "> 100000",
                "device_group",
                "Devices by Type/Minimal Monitoring",
            ),
        ],
    )
    @respx.mock
    async def test_one_datapoint_names_the_level_its_threshold_comes_from(
        self, client, key, threshold, source, source_group
    ):
        from lm_mcp.tools.alert_settings import get_alert_settings

        route = respx.get(f"{_INSTANCE}/17144").mock(
            return_value=httpx.Response(200, json=LIVE[key])
        )

        body = _body(
            await get_alert_settings(client, "instance", datapoint_id=17144, **_INSTANCE_ARGS)
        )

        assert route.call_count == 1
        setting = body["setting"]
        assert (setting["threshold"], setting["source"], setting["source_group"]) == (
            threshold,
            source,
            source_group,
        )

    @pytest.mark.parametrize(
        ("parent", "source"),
        [
            ("parentInstanceGroupAlertExpr", "instance_group"),
            ("parentResourceDataSourceAlertExpr", "device_datasource"),
        ],
    )
    def test_an_instance_group_or_device_datasource_threshold_outranks_a_groups(
        self, parent, source
    ):
        """The precedence LogicMonitor documents: instance, instance group, resource
        datasource, resource groups, global. The sandbox holds neither parent, so the two
        are set on the live record in the swagger's shape."""
        from lm_mcp.tools.alert_settings import setting_row

        record = {**LIVE["average_under_group"], parent: {"alertExpr": "> 7"}}

        row = setting_row(record)

        assert (row["threshold"], row["source"], row["source_group"]) == ("> 7", source, None)

    @respx.mock
    async def test_group_level_reads_the_groups_datasource_config(self, client):
        from lm_mcp.tools.alert_settings import get_alert_settings

        respx.get(_GROUP).mock(return_value=httpx.Response(200, json=LIVE["group_16_ping_set"]))

        body = _body(await get_alert_settings(client, "group", group_id=16, datasource_id=1679))

        assert body["datasource_type"] == "DS"
        average = next(s for s in body["settings"] if s["datapoint"] == "average")
        assert average == {
            "datapoint": "average",
            "datapoint_id": 17144,
            "threshold": "> 100000",
            "source": "group",
            "source_group": None,
            "group_threshold": "> 100000",
            "global_threshold": "> 200",
            "alerting_disabled": False,
        }
        loss = next(s for s in body["settings"] if s["datapoint"] == "PingLossPercent")
        assert (loss["threshold"], loss["source"]) == ("> 20 70 90", "global")

    @pytest.mark.parametrize(
        ("level", "kwargs", "missing"),
        [
            ("device", {}, "device_id"),
            ("instance", {"device_id": 1786}, "device_datasource_id, instance_id"),
            ("group", {"group_id": 16}, "datasource_id"),
        ],
    )
    @respx.mock
    async def test_a_level_without_its_ids_is_refused_before_any_call(
        self, client, level, kwargs, missing
    ):
        from lm_mcp.tools.alert_settings import get_alert_settings

        error = envelope(await get_alert_settings(client, level, **kwargs))

        assert error["code"] == "INVALID_REQUEST"
        assert missing in error["message"]
        assert not respx.calls


class TestUpdateAlertSettings:
    """R3.5: a write PATCHes the instance or group path with the intervals in force, is
    write-gated, and refuses a threshold that does not parse."""

    @respx.mock
    async def test_instance_write_sends_the_threshold_with_the_intervals_in_force(
        self, client, writes
    ):
        from lm_mcp.tools.alert_settings import update_alert_settings

        respx.get(f"{_INSTANCE}/17144").mock(
            return_value=httpx.Response(200, json=LIVE["average_inherited"])
        )
        patch = respx.patch(f"{_INSTANCE}/17144").mock(
            return_value=httpx.Response(200, json=LIVE["average_patch_answer"])
        )

        body = _body(
            await update_alert_settings(
                client,
                "instance",
                "> 100000 200000 300000",
                datapoint_id=17144,
                note="lm-mcp Step 66 probe",
                **_INSTANCE_ARGS,
            )
        )

        assert json.loads(patch.calls.last.request.content) == {
            "alertExpr": "> 100000 200000 300000",
            "alertExprNote": "lm-mcp Step 66 probe",
            "alertTransitionInterval": 3,
            "alertClearInterval": 0,
            "alertForNoData": 2,
        }
        assert (body["setting"]["threshold"], body["setting"]["source"]) == (
            "> 100000 200000 300000",
            "instance",
        )

    @respx.mock
    async def test_instance_intervals_come_from_the_group_whose_threshold_is_in_force(
        self, client, writes
    ):
        from lm_mcp.tools.alert_settings import update_alert_settings

        under_group = LIVE["average_under_group"]
        parent = {**under_group["parentDeviceGroupAlertExprList"][0], "alertTransitionInterval": 7}
        record = {**under_group, "parentDeviceGroupAlertExprList": [parent]}
        respx.get(f"{_INSTANCE}/17144").mock(return_value=httpx.Response(200, json=record))
        patch = respx.patch(f"{_INSTANCE}/17144").mock(
            return_value=httpx.Response(200, json=LIVE["average_patch_answer"])
        )

        await update_alert_settings(client, "instance", "> 5", datapoint_id=17144, **_INSTANCE_ARGS)

        sent = json.loads(patch.calls.last.request.content)
        assert (
            sent["alertTransitionInterval"],
            sent["alertClearInterval"],
            sent["alertForNoData"],
        ) == (
            7,
            0,
            2,
        )

    @respx.mock
    async def test_an_empty_threshold_clears_the_instances_own_settings(self, client, writes):
        from lm_mcp.tools.alert_settings import update_alert_settings

        read = respx.get(f"{_INSTANCE}/17144")
        patch = respx.patch(f"{_INSTANCE}/17144").mock(
            return_value=httpx.Response(200, json=LIVE["average_inherited"])
        )

        body = _body(
            await update_alert_settings(
                client, "instance", "", datapoint_id=17144, **_INSTANCE_ARGS
            )
        )

        assert not read.called
        assert json.loads(patch.calls.last.request.content) == {"alertExpr": ""}
        assert body["setting"]["source"] == "global"

    @respx.mock
    async def test_group_write_patches_only_its_datapoint(self, client, writes):
        from lm_mcp.tools.alert_settings import update_alert_settings

        respx.get(_GROUP).mock(return_value=httpx.Response(200, json=LIVE["group_16_ping"]))
        patch = respx.patch(_GROUP).mock(
            return_value=httpx.Response(200, json=LIVE["group_16_ping_set"])
        )

        body = _body(
            await update_alert_settings(
                client, "group", "> 100000", datapoint_id=17144, group_id=16, datasource_id=1679
            )
        )

        assert json.loads(patch.calls.last.request.content) == {
            "dpConfig": [
                {
                    "dataPointId": 17144,
                    "dataPointName": "average",
                    "alertExpr": "> 100000",
                    "alertTransitionInterval": 3,
                    "alertClearTransitionInterval": 0,
                    "alertForNoData": 2,
                }
            ]
        }
        assert (body["setting"]["threshold"], body["setting"]["source"]) == ("> 100000", "group")

    @respx.mock
    async def test_a_group_clear_resets_the_datapoints_intervals_to_inherit(self, client, writes):
        from lm_mcp.tools.alert_settings import update_alert_settings

        respx.get(_GROUP).mock(return_value=httpx.Response(200, json=LIVE["group_16_ping_set"]))
        patch = respx.patch(_GROUP).mock(
            return_value=httpx.Response(200, json=LIVE["group_16_ping"])
        )

        await update_alert_settings(
            client, "group", "", datapoint_id=17144, group_id=16, datasource_id=1679
        )

        (entry,) = json.loads(patch.calls.last.request.content)["dpConfig"]
        assert entry == {
            "dataPointId": 17144,
            "dataPointName": "average",
            "alertExpr": "",
            "alertTransitionInterval": -1,
            "alertClearTransitionInterval": -1,
            "alertForNoData": -1,
        }

    @respx.mock
    async def test_a_datapoint_the_group_does_not_hold_is_not_found(self, client, writes):
        from lm_mcp.tools.alert_settings import update_alert_settings

        respx.get(_GROUP).mock(return_value=httpx.Response(200, json=LIVE["group_16_ping"]))
        patch = respx.patch(_GROUP)

        error = envelope(
            await update_alert_settings(
                client, "group", "> 1", datapoint_id=99, group_id=16, datasource_id=1679
            )
        )

        assert error["code"] == "NOT_FOUND"
        assert not patch.called

    @pytest.mark.parametrize("expr", ["> abc", "> 1 2 3 4", "!=0"])
    @respx.mock
    async def test_a_threshold_that_does_not_parse_is_refused_before_any_call(
        self, client, writes, expr
    ):
        from lm_mcp.tools.alert_settings import update_alert_settings

        error = envelope(
            await update_alert_settings(
                client, "instance", expr, datapoint_id=17144, **_INSTANCE_ARGS
            )
        )

        assert error["code"] == "INVALID_REQUEST"
        assert repr(expr) in error["message"]
        assert not respx.calls

    @respx.mock
    async def test_the_device_level_has_no_write(self, client, writes):
        from lm_mcp.tools.alert_settings import update_alert_settings

        error = envelope(await update_alert_settings(client, "device", "> 1", device_id=1786))

        assert error["code"] == "INVALID_REQUEST"
        assert "instance or group" in error["message"]
        assert not respx.calls

    @respx.mock
    async def test_refused_with_writes_off(self, client, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp.tools.alert_settings import update_alert_settings

        error = envelope(
            await update_alert_settings(
                client, "instance", "> 1", datapoint_id=17144, **_INSTANCE_ARGS
            )
        )

        assert error["code"] == "WRITE_DISABLED"
        assert not respx.calls
