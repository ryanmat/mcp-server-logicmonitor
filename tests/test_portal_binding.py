# Description: Tests for the per-call portal binding (spec R2.12, R4.2): execute_tool binds the
# Description: client, write flag and portal name per call, from the default or a portal argument.

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from unittest.mock import patch

import anyio
import httpx
import pytest
import respx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent

from lm_mcp import portals
from lm_mcp.tools import ErrorContent, format_response, require_write_permission
from tests.portal_env import two_portal_vault

ACME = "https://acme.example.com/santaba/rest"
GLOBEX = "https://globex.example.com/santaba/rest"
REPO = Path(__file__).resolve().parents[1]

# The tools whose schemas never carry the portal argument: the session tools, the four
# portal tools, the two discovery tools that read no client, and the Edwin tools.
SESSION_TOOLS = {
    "get_session_context",
    "set_session_variable",
    "get_session_variable",
    "delete_session_variable",
    "clear_session_context",
    "get_session_history",
}
PORTAL_TOOLS = {"get_portals", "use_portal", "get_current_portal", "run_portal_reload"}
DISCOVERY_TOOLS = {"search_tools", "get_reference"}


@pytest.fixture
def two_portals(tmp_path, monkeypatch, reset_portals):
    """Multi-portal mode over a vault with a writable acme and a read-only globex."""
    two_portal_vault(tmp_path, monkeypatch)


def _device(device_id: int, name: str) -> httpx.Response:
    return httpx.Response(200, json={"id": device_id, "name": name, "displayName": name})


class TestBinding:
    """execute_tool binds the call's client, write flag and portal for the call's duration."""

    @pytest.mark.asyncio
    async def test_handler_sees_the_binding_of_its_call(self, two_portals):
        from lm_mcp.context import current_binding, current_client
        from lm_mcp.server import execute_tool

        portals.activate("acme")
        seen = {}

        async def handler(client, **kwargs):
            binding = current_binding()
            seen.update(
                client=client,
                current=current_client(),
                writable=binding.writable,
                portal=binding.portal,
            )
            return format_response({"ok": True})

        with patch("lm_mcp.server.get_tool_handler", return_value=handler):
            await execute_tool("get_device", {"device_id": 1})

        acme_client = portals._state["clients"]["acme"]
        assert seen == {
            "client": acme_client,
            "current": acme_client,
            "writable": True,
            "portal": "acme",
        }
        with pytest.raises(RuntimeError, match="binding"):
            current_binding()

    @pytest.mark.asyncio
    async def test_read_only_portal_binds_writable_false(self, two_portals):
        from lm_mcp.context import current_binding
        from lm_mcp.server import execute_tool

        portals.activate("globex")
        seen = {}

        async def handler(client, **kwargs):
            seen["writable"] = current_binding().writable
            return format_response({"ok": True})

        with patch("lm_mcp.server.get_tool_handler", return_value=handler):
            await execute_tool("get_device", {"device_id": 1})

        assert seen == {"writable": False}

    @pytest.mark.asyncio
    async def test_single_portal_binds_the_startup_client_and_no_portal_name(self, monkeypatch):
        from lm_mcp.context import current_binding
        from lm_mcp.server import execute_tool

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)
        monkeypatch.delenv("LM_ENABLE_WRITE_OPERATIONS", raising=False)
        startup_client = object()
        seen = {}

        async def handler(client, **kwargs):
            binding = current_binding()
            seen.update(client=client, writable=binding.writable, portal=binding.portal)
            return format_response({"ok": True})

        with (
            patch("lm_mcp.server._client", startup_client),
            patch("lm_mcp.server.get_tool_handler", return_value=handler),
        ):
            result = await execute_tool("get_device", {"device_id": 1})

        assert seen == {"client": startup_client, "writable": False, "portal": None}
        assert "portal" not in json.loads(result[0].text)


class TestConcurrentCalls:
    """Two calls in flight under different portals each keep their own client and portal."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_switch_mid_call_leaves_the_running_call_on_its_portal(self, two_portals):
        from lm_mcp.server import execute_tool

        acme_reached = asyncio.Event()
        release_acme = asyncio.Event()

        async def slow_acme(request):
            acme_reached.set()
            await release_acme.wait()
            return _device(1, "acme-web")

        acme_route = respx.get(f"{ACME}/device/devices/1").mock(side_effect=slow_acme)
        globex_route = respx.get(f"{GLOBEX}/device/devices/1").mock(
            return_value=_device(1, "globex-web")
        )

        portals.activate("acme")
        first = asyncio.create_task(execute_tool("get_device", {"device_id": 1}))
        await asyncio.wait_for(acme_reached.wait(), timeout=5)

        await execute_tool("use_portal", {"customer": "globex"})
        second = asyncio.create_task(execute_tool("get_device", {"device_id": 1}))
        release_acme.set()
        first_result, second_result = await asyncio.gather(first, second)

        first_data = json.loads(first_result[0].text)
        second_data = json.loads(second_result[0].text)
        assert (first_data["name"], first_data["portal"]) == ("acme-web", "acme")
        assert (second_data["name"], second_data["portal"]) == ("globex-web", "globex")
        assert first_data["portal_url"].startswith("https://acme.example.com/")
        assert second_data["portal_url"].startswith("https://globex.example.com/")
        assert acme_route.call_count == 1
        assert globex_route.call_count == 1


class TestNoBinding:
    """In multi-portal mode a helper reached outside a call raises, never reading the default."""

    def test_current_client_raises_outside_a_call(self, two_portals):
        from lm_mcp.context import current_client

        portals.activate("acme")
        with pytest.raises(RuntimeError, match="binding"):
            current_client()

    @pytest.mark.asyncio
    async def test_write_gate_raises_outside_a_call(self, two_portals):
        portals.activate("acme")

        @require_write_permission
        async def _do_write():
            return format_response({"ok": True})

        with pytest.raises(RuntimeError, match="binding"):
            await _do_write()

    def test_portal_url_raises_outside_a_call(self, two_portals):
        from lm_mcp.tools import portal_url

        portals.activate("acme")
        with pytest.raises(RuntimeError, match="binding"):
            portal_url("device", 5)

    @pytest.mark.asyncio
    @respx.mock
    async def test_unbound_handler_call_raises(self, two_portals):
        """A write handler called straight, not through execute_tool, raises."""
        from lm_mcp.tools.devices import delete_device

        portals.activate("acme")
        with pytest.raises(RuntimeError, match="binding"):
            await delete_device(portals._state["clients"]["acme"], device_id=7)

    def test_audit_line_outside_a_call_carries_no_portal(self, two_portals, caplog):
        """The audit logger never fails its caller: outside a call the line has no portal."""
        from lm_mcp.logging import log_write_operation

        portals.activate("acme")
        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            log_write_operation("delete_device", {"device_id": 7}, success=True)

        assert [r.getMessage() for r in caplog.records if r.name == "lm_mcp.audit"] == [
            "Write operation: delete_device args={'device_id': 7}"
        ]


class TestPortalStamp:
    """Every result dict in multi-portal mode carries the portal its call was bound to."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_success_result_carries_portal(self, two_portals):
        from lm_mcp.server import execute_tool

        respx.get(f"{ACME}/device/devices/1").mock(return_value=_device(1, "acme-web"))
        portals.activate("acme")

        result = await execute_tool("get_device", {"device_id": 1})

        assert type(result[0]) is TextContent
        assert json.loads(result[0].text)["portal"] == "acme"

    @pytest.mark.asyncio
    @respx.mock
    async def test_error_result_carries_portal_in_details(self, two_portals):
        from lm_mcp.server import execute_tool
        from tests.envelope import envelope

        respx.get(f"{ACME}/device/devices/9").mock(
            return_value=httpx.Response(404, json={"errorMessage": "not found"})
        )
        portals.activate("acme")

        result = await execute_tool("get_device", {"device_id": 9})

        assert isinstance(result[0], ErrorContent)
        error = envelope(result)
        assert error["code"] == "NOT_FOUND"
        assert error["details"]["portal"] == "acme"

    @pytest.mark.asyncio
    async def test_no_portal_selected_error_carries_null_portal(self, two_portals):
        from lm_mcp.server import execute_tool
        from tests.envelope import envelope

        error = envelope(await execute_tool("get_device", {"device_id": 1}))

        assert (error["code"], error["isRetryable"]) == ("INVALID_REQUEST", False)
        assert "No portal selected" in error["message"]
        assert error["details"]["portal"] is None

    @pytest.mark.asyncio
    async def test_write_before_use_portal_is_refused_and_audited(self, two_portals, caplog):
        from lm_mcp.server import execute_tool
        from tests.envelope import envelope

        with caplog.at_level(logging.INFO):
            error = envelope(await execute_tool("delete_device", {"device_id": 7}))

        assert (error["code"], error["isRetryable"]) == ("INVALID_REQUEST", False)
        assert "use_portal" in error["message"]
        assert [r.getMessage() for r in caplog.records if r.name == "lm_mcp.audit"] == [
            "Write operation failed: delete_device args={'device_id': 7}"
        ]
        assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []

    @pytest.mark.asyncio
    async def test_session_result_carries_portal(self, two_portals):
        from lm_mcp.server import execute_tool

        portals.activate("globex")

        result = await execute_tool("get_session_context", {})

        assert json.loads(result[0].text)["portal"] == "globex"

    @pytest.mark.asyncio
    async def test_portal_tool_results_keep_their_own_portal_field(self, two_portals):
        """use_portal's `portal` is the host it switched to, not the name it was bound to."""
        from lm_mcp.server import execute_tool

        portals.activate("acme")

        result = await execute_tool("use_portal", {"customer": "globex"})

        assert json.loads(result[0].text) == {
            "active": "globex",
            "portal": "globex.example.com",
            "writable": False,
        }

    @pytest.mark.asyncio
    async def test_single_portal_error_has_no_portal(self, monkeypatch):
        from lm_mcp.server import execute_tool
        from tests.envelope import envelope

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

        with patch("lm_mcp.server._client", None):
            error = envelope(await execute_tool("get_device", {"device_id": 1}))

        assert error["message"] == "Client not initialized"
        assert error["details"] is None or "portal" not in error["details"]


class TestAuditMarker:
    """The audit line names the portal the call was bound to, read before the handler returns."""

    @pytest.mark.asyncio
    async def test_switch_inside_the_handler_does_not_move_the_marker(self, two_portals, caplog):
        from lm_mcp.server import execute_tool

        portals.activate("acme")

        async def switching_write(client, **kwargs):
            portals.activate("globex")
            return format_response({"success": True})

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=switching_write),
            caplog.at_level(logging.INFO, logger="lm_mcp.audit"),
        ):
            await execute_tool("delete_device", {"device_id": 7})

        audit = [r.getMessage() for r in caplog.records if r.name == "lm_mcp.audit"]
        assert audit == ["Write operation: delete_device args={'device_id': 7} portal=acme"]
        assert portals.active()["active"] == "globex"


def _properties(tool) -> dict:
    return tool.inputSchema.get("properties") or {}


@pytest.fixture
def unfiltered(monkeypatch):
    """No operator name or category filter, so the listing is every tool the mode serves."""
    for name in ("LM_ENABLED_TOOLS", "LM_DISABLED_TOOLS", "LM_MCP_CATEGORIES"):
        monkeypatch.delenv(name, raising=False)


class TestPortalArgumentSchema:
    """With LM_MULTI_PORTAL on, every LM tool lists an optional portal string (spec R4.2)."""

    @pytest.mark.asyncio
    async def test_lm_tool_schemas_carry_an_optional_portal_string(self, two_portals, unfiltered):
        from lm_mcp.registry import TOOLS
        from lm_mcp.server import list_tools

        with patch("lm_mcp.server._edwin_client", object()):
            listed = await list_tools()

        names = {tool.name for tool in listed}
        edwin = {name for name in names if "edwin" in name}
        without = {tool.name for tool in listed if "portal" not in _properties(tool)}
        assert edwin and names >= SESSION_TOOLS | PORTAL_TOOLS
        assert without == SESSION_TOOLS | PORTAL_TOOLS | DISCOVERY_TOOLS | edwin
        carrying = [tool for tool in listed if tool.name not in without]
        assert len(carrying) > 240
        for tool in carrying:
            assert _properties(tool)["portal"]["type"] == "string", tool.name
            assert "portal" not in tool.inputSchema.get("required", []), tool.name
        assert [t.name for t in TOOLS if "portal" in _properties(t)] == []

    @pytest.mark.asyncio
    async def test_single_portal_schemas_carry_no_portal(self, monkeypatch, unfiltered):
        from lm_mcp.server import list_tools

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

        listed = await list_tools()

        assert len(listed) > 240
        assert [tool.name for tool in listed if "portal" in _properties(tool)] == []


class TestPortalArgumentCall:
    """A call's portal argument binds that portal for the call and leaves the default alone."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_call_with_portal_binds_it_and_keeps_the_default(self, two_portals):
        from lm_mcp.server import execute_tool

        acme_route = respx.get(f"{ACME}/device/devices/1").mock(return_value=_device(1, "acme-web"))
        globex_route = respx.get(f"{GLOBEX}/device/devices/1").mock(
            return_value=_device(1, "globex-web")
        )
        portals.activate("acme")

        named = json.loads(
            (await execute_tool("get_device", {"device_id": 1, "portal": "globex"}))[0].text
        )
        default = json.loads((await execute_tool("get_device", {"device_id": 1}))[0].text)

        assert (named["name"], named["portal"]) == ("globex-web", "globex")
        assert named["portal_url"].startswith("https://globex.example.com/")
        assert (default["name"], default["portal"]) == ("acme-web", "acme")
        assert (globex_route.call_count, acme_route.call_count) == (1, 1)
        assert portals.active()["active"] == "acme"

    @pytest.mark.asyncio
    @respx.mock
    async def test_portal_argument_needs_no_use_portal(self, two_portals):
        from lm_mcp.server import execute_tool

        respx.get(f"{GLOBEX}/device/devices/1").mock(return_value=_device(1, "globex-web"))

        result = await execute_tool("get_device", {"device_id": 1, "portal": "globex"})

        assert json.loads(result[0].text)["portal"] == "globex"
        assert portals.active()["active"] is None

    @pytest.mark.asyncio
    async def test_handler_gets_the_named_portal_and_not_the_argument(self, two_portals):
        from lm_mcp.context import current_binding
        from lm_mcp.server import execute_tool

        portals.activate("acme")
        seen = {}

        async def handler(client, **kwargs):
            seen.update(client=client, kwargs=kwargs, portal=current_binding().portal)
            return format_response({"ok": True})

        with patch("lm_mcp.server.get_tool_handler", return_value=handler):
            await execute_tool("get_device", {"device_id": 1, "portal": "globex"})

        assert seen == {
            "client": portals._state["clients"]["globex"],
            "kwargs": {"device_id": 1},
            "portal": "globex",
        }

    @pytest.mark.asyncio
    @respx.mock
    async def test_named_read_only_portal_refuses_a_write_while_the_default_is_writable(
        self, two_portals, caplog
    ):
        from lm_mcp.server import execute_tool
        from tests.envelope import envelope

        portals.activate("acme")
        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            error = envelope(
                await execute_tool("delete_device", {"device_id": 7, "portal": "globex"})
            )

        assert (error["code"], error["message"]) == (
            "WRITE_DISABLED",
            "Portal 'globex' is read-only. Set \"writable\": true on this portal's vault record "
            "to allow writes",
        )
        assert error["details"]["portal"] == "globex"
        assert [r.getMessage() for r in caplog.records if r.name == "lm_mcp.audit"] == [
            "Write operation failed: delete_device args={'device_id': 7} portal=globex"
        ]

    @pytest.mark.asyncio
    @respx.mock
    async def test_named_writable_portal_writes_while_the_default_is_read_only(
        self, two_portals, caplog
    ):
        from lm_mcp.server import execute_tool

        respx.get(f"{ACME}/device/devices/7").mock(return_value=_device(7, "acme-db"))
        route = respx.delete(f"{ACME}/device/devices/7").mock(
            return_value=httpx.Response(200, json={})
        )
        portals.activate("globex")
        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await execute_tool("delete_device", {"device_id": 7, "portal": "acme"})

        assert not isinstance(result[0], ErrorContent)
        assert json.loads(result[0].text)["portal"] == "acme"
        assert route.call_count == 1
        assert [r.getMessage() for r in caplog.records if r.name == "lm_mcp.audit"] == [
            "Write operation: delete_device args={'device_id': 7} portal=acme"
        ]
        assert portals.active()["active"] == "globex"

    @pytest.mark.asyncio
    @respx.mock
    async def test_unknown_portal_is_invalid_request(self, two_portals):
        from lm_mcp.server import execute_tool
        from tests.envelope import envelope

        portals.activate("acme")

        error = envelope(await execute_tool("get_device", {"device_id": 1, "portal": "initech"}))

        assert (error["code"], error["isRetryable"]) == ("INVALID_REQUEST", False)
        assert error["message"] == "portal 'initech' not found. Available: acme, globex"
        assert error["details"]["portal"] is None
        assert portals.active()["active"] == "acme"
        assert "initech" not in portals._state["clients"]

    @pytest.mark.asyncio
    async def test_write_to_an_unknown_portal_is_refused_and_audited(self, two_portals, caplog):
        from lm_mcp.server import execute_tool
        from tests.envelope import envelope

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            error = envelope(
                await execute_tool("delete_device", {"device_id": 7, "portal": "initech"})
            )

        assert error["code"] == "INVALID_REQUEST"
        assert [r.getMessage() for r in caplog.records if r.name == "lm_mcp.audit"] == [
            "Write operation failed: delete_device args={'device_id': 7, 'portal': 'initech'}"
        ]

    @pytest.mark.asyncio
    async def test_vault_read_failure_is_logged_and_returned(self, two_portals, tmp_path, caplog):
        from lm_mcp.server import execute_tool
        from tests.envelope import envelope

        (tmp_path / "portals.json").unlink()
        with caplog.at_level(logging.ERROR, logger="lm_mcp.server"):
            error = envelope(await execute_tool("get_device", {"device_id": 1, "portal": "acme"}))

        assert (error["code"], error["details"]["exception"]) == (
            "UPSTREAM_ERROR",
            "FileNotFoundError",
        )
        assert error["details"]["portal"] is None
        assert [r.getMessage() for r in caplog.records if r.name == "lm_mcp.server"] == [
            "Binding portal 'acme' for get_device failed"
        ]


def _guide_block(heading: str) -> str:
    """The first fenced bash block under ``heading`` in MULTIPORTAL.md."""
    text = (REPO / "MULTIPORTAL.md").read_text()
    section = text.split(f"\n{heading}\n", 1)[1]
    return re.search(r"```bash\n(.*?)```", section, re.S).group(1)


class TestMultiportalGuide:
    """MULTIPORTAL.md's commands run as written where they are commands."""

    @pytest.mark.asyncio
    async def test_clone_command_serves_the_portal_argument_over_stdio(self, tmp_path):
        vault = tmp_path / "portals.json"
        vault.write_text(
            json.dumps(
                {
                    "acme": {"portal": "acme.example.com", "bearer_token": "t1"},
                    "globex": {"portal": "globex.example.com", "bearer_token": "t2"},
                }
            )
        )
        # The launcher runs `uv run --project`. The stdio client hands the child only
        # HOME, PATH and the like, so the UV_ settings (CI's UV_PYTHON per matrix leg)
        # are passed on; without them uv would rebuild this run's .venv for another Python.
        uv_settings = {key: value for key, value in os.environ.items() if key.startswith("UV_")}
        params = StdioServerParameters(
            command="bash",
            args=["-c", _guide_block("## Try it from a clone")],
            cwd=str(REPO),
            env={**uv_settings, "LM_PORTALS_FILE": str(vault)},
        )

        with (tmp_path / "server.log").open("w") as errlog, anyio.fail_after(120):
            async with (
                stdio_client(params, errlog=errlog) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                listed = {tool.name: tool for tool in (await session.list_tools()).tools}
                listing = await session.call_tool("get_portals", {})
                refused = await session.call_tool(
                    "get_device", {"device_id": 1, "portal": "initech"}
                )

        assert _properties(listed["get_device"])["portal"]["type"] == "string"
        assert "portal" not in _properties(listed["get_session_context"])
        assert [p["name"] for p in json.loads(listing.content[0].text)["portals"]] == [
            "acme",
            "globex",
        ]
        assert refused.isError
        assert json.loads(refused.content[0].text)["error"]["code"] == "INVALID_REQUEST"
