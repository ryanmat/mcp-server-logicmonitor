# Description: Tests for the per-call portal binding (spec R2.12): execute_tool binds the
# Description: client, write flag and portal name in a ContextVar, and stamps results with it.

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import patch

import httpx
import pytest
import respx
from mcp.types import TextContent

from lm_mcp import portals
from lm_mcp.tools import ErrorContent, format_response, require_write_permission

ACME = "https://acme.example.com/santaba/rest"
GLOBEX = "https://globex.example.com/santaba/rest"


@pytest.fixture
def two_portals(tmp_path, monkeypatch, reset_portals):
    """Multi-portal mode over a plaintext vault with a writable acme and a read-only globex."""
    vault = tmp_path / "portals.json"
    vault.write_text(
        json.dumps(
            {
                "acme": {"portal": "acme.example.com", "bearer_token": "t1", "writable": True},
                "globex": {"portal": "globex.example.com", "bearer_token": "t2"},
            }
        )
    )
    monkeypatch.setenv("LM_MULTI_PORTAL", "true")
    monkeypatch.setenv("LM_PORTALS_FILE", str(vault))
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    monkeypatch.delenv("LM_PORTAL", raising=False)
    monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)


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

        assert "No portal selected" in error["message"]
        assert error["details"]["portal"] is None

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
