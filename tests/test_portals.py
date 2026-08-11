# Description: Tests for multi-portal mode — the portal registry, the portal
# Description: tools, and the read-only-by-default write gate.
import json

import pytest

from lm_mcp import portals, server
from lm_mcp.tools import format_response, require_write_permission


@pytest.fixture
def reset_portals():
    """Reset the process-local portal registry and the global client around each test."""

    def _clear():
        portals._state.update(
            {
                "portals": {},
                "clients": {},
                "active": None,
                "active_writable": False,
                "loaded": False,
            }
        )
        server._set_client(None)

    _clear()
    yield
    _clear()


def _vault(tmp_path, data: dict) -> str:
    p = tmp_path / "portals.json"
    p.write_text(json.dumps(data))
    return str(p)


def _multi(monkeypatch, vault_path: str) -> None:
    monkeypatch.setenv("LM_MULTI_PORTAL", "true")
    monkeypatch.setenv("LM_PORTALS_FILE", vault_path)


def test_names_lists_metadata_without_leaking_secrets(tmp_path, monkeypatch, reset_portals):
    vault = _vault(
        tmp_path,
        {
            "acme": {"portal": "acme.example.com", "bearer_token": "BEARER-SENTINEL"},
            "globex": {
                "portal": "globex.example.com",
                "access_id": "id",
                "access_key": "ACCESSKEY-SENTINEL",
                "writable": True,
            },
        },
    )
    _multi(monkeypatch, vault)

    rows = portals.names()
    blob = json.dumps(rows)
    # metadata is present...
    assert {r["name"] for r in rows} == {"acme", "globex"}
    assert {r["name"]: r["auth"] for r in rows} == {"acme": "bearer", "globex": "lmv1"}
    assert {r["name"]: r["writable"] for r in rows}["globex"] is True
    # ...but no token/key material ever is
    assert "BEARER-SENTINEL" not in blob
    assert "ACCESSKEY-SENTINEL" not in blob


def test_activate_sets_active_and_installs_client(tmp_path, monkeypatch, reset_portals):
    vault = _vault(tmp_path, {"acme": {"portal": "acme.example.com", "bearer_token": "tok"}})
    _multi(monkeypatch, vault)

    result = portals.activate("acme")
    assert result == {"active": "acme", "portal": "acme.example.com", "writable": False}
    assert portals.has_active() is True
    assert portals.active()["active"] == "acme"
    # the global client is now set, so data tools can run
    assert server.get_client() is not None


def test_activate_unknown_portal_raises(tmp_path, monkeypatch, reset_portals):
    vault = _vault(tmp_path, {"acme": {"portal": "acme.example.com", "bearer_token": "tok"}})
    _multi(monkeypatch, vault)

    with pytest.raises(ValueError, match="not found"):
        portals.activate("does-not-exist")


def test_reload_picks_up_added_and_removed_portals(tmp_path, monkeypatch, reset_portals):
    p = tmp_path / "portals.json"
    p.write_text(json.dumps({"acme": {"portal": "acme.example.com", "bearer_token": "t"}}))
    _multi(monkeypatch, str(p))

    assert {r["name"] for r in portals.names()} == {"acme"}

    p.write_text(
        json.dumps(
            {
                "acme": {"portal": "acme.example.com", "bearer_token": "t"},
                "globex": {"portal": "globex.example.com", "bearer_token": "t2"},
            }
        )
    )
    out = portals.reload()
    assert out["reloaded"] is True
    assert out["count"] == 2
    assert {r["name"] for r in out["portals"]} == {"acme", "globex"}


def test_reload_keeps_active_when_present_and_clears_when_removed(
    tmp_path, monkeypatch, reset_portals
):
    p = tmp_path / "portals.json"
    p.write_text(
        json.dumps(
            {
                "acme": {"portal": "acme.example.com", "bearer_token": "t"},
                "globex": {"portal": "globex.example.com", "bearer_token": "t2"},
            }
        )
    )
    _multi(monkeypatch, str(p))

    portals.activate("acme")
    portals.reload()
    assert portals.active()["active"] == "acme"  # still present -> kept

    p.write_text(json.dumps({"globex": {"portal": "globex.example.com", "bearer_token": "t2"}}))
    portals.reload()
    assert portals.active()["active"] is None  # removed -> cleared
    with pytest.raises(RuntimeError, match="No portal selected"):
        server.get_client()


@pytest.mark.asyncio
async def test_write_gate_blocks_read_only_portal(tmp_path, monkeypatch, reset_portals):
    vault = _vault(tmp_path, {"acme": {"portal": "acme.example.com", "bearer_token": "t"}})
    _multi(monkeypatch, vault)
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    portals.activate("acme")  # not writable

    @require_write_permission
    async def _do_write():
        return format_response({"ok": True})

    # Error responses are rendered as human-readable text, not JSON.
    text = (await _do_write())[0].text
    assert "read-only" in text


@pytest.mark.asyncio
async def test_write_gate_allows_writable_portal(tmp_path, monkeypatch, reset_portals):
    vault = _vault(
        tmp_path, {"acme": {"portal": "acme.example.com", "bearer_token": "t", "writable": True}}
    )
    _multi(monkeypatch, vault)
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    portals.activate("acme")  # writable

    @require_write_permission
    async def _do_write():
        return format_response({"ok": True})

    payload = json.loads((await _do_write())[0].text)
    assert payload == {"ok": True}


@pytest.mark.asyncio
async def test_use_portal_tool_returns_clean_error_for_unknown(
    tmp_path, monkeypatch, reset_portals
):
    from lm_mcp.tools import portals as portal_tools

    vault = _vault(tmp_path, {"acme": {"portal": "acme.example.com", "bearer_token": "t"}})
    _multi(monkeypatch, vault)

    text = (await portal_tools.use_portal("nope"))[0].text
    assert "not found" in text


def test_single_portal_mode_still_requires_a_portal(monkeypatch, reset_portals):
    """Guard: turning portal optional must not weaken single-portal validation."""
    from pydantic import ValidationError

    from lm_mcp.config import LMConfig

    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)
    monkeypatch.delenv("LM_PORTAL", raising=False)
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-1234")
    with pytest.raises(ValidationError):
        LMConfig()


def test_load_refuses_when_multi_portal_disabled(tmp_path, monkeypatch, reset_portals):
    """A vault in the environment must not let portal tools hijack single-portal mode."""
    vault = _vault(tmp_path, {"acme": {"portal": "acme.example.com", "bearer_token": "t"}})
    monkeypatch.setenv("LM_PORTAL", "internal.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-1234")
    monkeypatch.setenv("LM_PORTALS_FILE", vault)
    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

    with pytest.raises(RuntimeError, match="LM_MULTI_PORTAL"):
        portals.load()
    with pytest.raises(RuntimeError, match="LM_MULTI_PORTAL"):
        portals.activate("acme")
    # the configured single-portal client was never replaced
    assert server._client is None


@pytest.mark.asyncio
async def test_use_portal_tool_errors_in_single_portal_mode(tmp_path, monkeypatch, reset_portals):
    from lm_mcp.tools import portals as portal_tools

    vault = _vault(tmp_path, {"acme": {"portal": "acme.example.com", "bearer_token": "t"}})
    monkeypatch.setenv("LM_PORTAL", "internal.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-1234")
    monkeypatch.setenv("LM_PORTALS_FILE", vault)
    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

    text = (await portal_tools.use_portal("acme"))[0].text
    assert text.startswith("Error:")
    assert "LM_MULTI_PORTAL" in text


@pytest.mark.asyncio
async def test_write_gate_reports_no_portal_selected(tmp_path, monkeypatch, reset_portals):
    """Before use_portal, the write gate must say so instead of claiming read-only."""
    vault = _vault(tmp_path, {"acme": {"portal": "acme.example.com", "bearer_token": "t"}})
    _multi(monkeypatch, vault)
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

    @require_write_permission
    async def _do_write():
        return format_response({"ok": True})

    text = (await _do_write())[0].text
    assert "No portal selected" in text
    assert "use_portal" in text
