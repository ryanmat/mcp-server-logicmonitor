# Description: Tests for search_tools: the operator filters, tokenized scoring and categories.
# Description: Results come only from the tools the server lists under the current config.

from __future__ import annotations

import json

import pytest

from lm_mcp.categories import writes_to_portal
from lm_mcp.config import get_config, reset_config
from lm_mcp.registry import TOOLS
from lm_mcp.resources.guides import TOOL_CATEGORIES
from lm_mcp.server import PORTAL_TOOLS, _filter_tools
from lm_mcp.tools.workflows import search_tools
from tests.envelope import envelope

_SETTINGS = (
    "LM_ENABLED_TOOLS",
    "LM_DISABLED_TOOLS",
    "LM_MCP_CATEGORIES",
    "LM_ENABLE_WRITE_OPERATIONS",
    "LM_MULTI_PORTAL",
)


@pytest.fixture
def configure(monkeypatch):
    """Set one config from settings over a clean default; return the tools it lists."""

    def apply(**settings: str) -> set[str]:
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-bearer-token-value")
        for name in _SETTINGS:
            monkeypatch.delenv(name, raising=False)
        for name, value in settings.items():
            monkeypatch.setenv(name, value)
        reset_config()
        return {tool.name for tool in _filter_tools(list(TOOLS), get_config())}

    return apply


async def _names(query: str, **kwargs) -> list[str]:
    result = await search_tools(None, query=query, limit=300, **kwargs)
    return [match["name"] for match in json.loads(result[0].text)["matches"]]


@pytest.mark.parametrize(
    ("settings", "query", "removed"),
    [
        ({"LM_ENABLED_TOOLS": "get_*"}, "alerts", "analyze_alerts"),
        ({"LM_DISABLED_TOOLS": "get_alerts"}, "get_alerts", "get_alerts"),
        ({"LM_MCP_CATEGORIES": "workflow"}, "alerts", "get_alerts"),
        ({}, "delete device", "delete_device"),
        ({"LM_ENABLE_WRITE_OPERATIONS": "true"}, "list portals", "list_portals"),
    ],
    ids=["enabled", "disabled", "categories", "write-gate", "single-portal"],
)
async def test_results_hold_only_the_tools_the_config_lists(configure, settings, query, removed):
    """R2.8: each filter the server applies to tools/list applies to the search first."""
    listed = configure(**settings)

    names = await _names(query)

    assert removed not in listed
    assert names
    assert set(names) <= listed


async def test_writes_off_name_no_write_tool(configure):
    """With the write gate off, no result is a tool that changes the portal."""
    configure()
    writers = {tool.name for tool in TOOLS if writes_to_portal(tool)}

    names = await _names("delete update create acknowledge device alert sdt")

    assert names
    assert not set(names) & writers


async def test_multi_portal_mode_finds_the_portal_tools(configure):
    """The portal tools are listed, and found, only in multi-portal mode."""
    configure(LM_MULTI_PORTAL="true", LM_PORTALS_FILE="/nonexistent/portals.yaml")

    names = await _names("list portals")

    assert set(PORTAL_TOOLS) & set(names)


async def test_cpu_usage_ranks_the_metric_readers_above_every_update_tool(configure):
    """R2.8: tokenized scoring with stopwords puts the readers first even with writes on."""
    configure(LM_ENABLE_WRITE_OPERATIONS="true")

    names = await _names("cpu usage high on server")

    updates = [i for i, name in enumerate(names) if name.startswith("update_")]
    for reader in ("analyze_metric", "get_device_data"):
        assert reader in names
        assert all(names.index(reader) < i for i in updates), names[:10]


async def test_a_query_of_stopwords_matches_nothing(configure):
    """Words such as 'the', 'on' and 'of' score no tool."""
    configure()

    assert await _names("the on of for a") == []


async def test_a_rare_word_outweighs_a_common_one(configure):
    """'cpu' names three tools and 'device' dozens: one cpu match beats device in a name."""
    configure()

    names = await _names("cpu device")

    assert names.index("analyze_metric") < names.index("get_device")


async def test_a_plural_matches_its_singular(configure):
    """'property' finds get_device_properties and 'alerts' finds get_alert_details' alert."""
    configure()

    assert "get_device_properties" in await _names("property")
    assert "get_alert_details" in await _names("alerts details")


async def test_an_exact_tool_name_ranks_first(configure):
    """get_device and get_devices stem to the same words; the full name decides."""
    configure()

    assert (await _names("get_device"))[0] == "get_device"
    assert (await _names("get_devices"))[0] == "get_devices"


def test_the_category_enum_is_the_tools_doc_taxonomy():
    """R2.8: category takes exactly the keys documentation/tools.md is generated from."""
    (tool,) = [t for t in TOOLS if t.name == "search_tools"]

    assert tool.inputSchema["properties"]["category"]["enum"] == list(TOOL_CATEGORIES["categories"])


async def test_an_unknown_category_is_invalid_request(configure):
    configure()

    result = await search_tools(None, query="alert", category="nonexistent_cat")

    error = envelope(result)
    assert error["code"] == "INVALID_REQUEST"
    assert "alerts" in error["message"]


async def test_a_category_narrows_the_listed_tools(configure):
    """A category's results are its tools the config lists: alerts without the writers."""
    listed = configure()
    alerts = set(TOOL_CATEGORIES["categories"]["alerts"]["tools"])

    names = await _names("alert", category="alerts")

    assert names
    assert set(names) <= alerts & listed
