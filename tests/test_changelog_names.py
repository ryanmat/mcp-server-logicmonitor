# Description: Guards the R2.13 CHANGELOG rename table against the 4.3.0 tools and the registry.
# Description: Each 4.3.0 name 5.0 does not register has one row naming its 5.0 tool or "removed".
from __future__ import annotations

import re
from pathlib import Path

import pytest

from lm_mcp.registry import TOOLS, get_tool_handler

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
# The 306 keys of tests/fixtures/tool_list.json at the v4.3.0 tag, one per line.
NAMES_430 = ROOT / "tests" / "fixtures" / "tool_names-4.3.0.txt"
TABLE_HEADER = "| 4.3.0 tool | 5.0 tool | Replacement |"
# The release section that holds the table.
SECTION = "## [5.0.0]"
ROW = re.compile(r"^\| `(?P<old>[a-z0-9_]+)` \| (?P<new>`[a-z0-9_]+`|removed) \| (?P<note>.+) \|$")

# The same tool under a new name. Every other row of the table reads "removed".
RENAMES = {
    "list_session_history": "get_session_history",
    "current_portal": "get_current_portal",
    "reload_portals": "run_portal_reload",
    "list_portals": "get_portals",
    "list_sdts": "get_sdts",
    "get_trace_services": "get_apm_services",
    "get_trace_service_alerts": "get_apm_service_alerts",
}
# Tools that start a portal-side job or action and keep their 4.3.0 names.
KEPT_VERBS = ("run_netscan", "run_report", "execute_diagnostic", "execute_remediation")


def _registered() -> set[str]:
    return {tool.name for tool in TOOLS}


def _names_430() -> set[str]:
    return set(NAMES_430.read_text().split())


def _release_section() -> str:
    """The 5.0.0 section of the CHANGELOG, the release the rename table belongs to."""
    text = CHANGELOG.read_text()
    marker = f"\n{SECTION} - "
    assert marker in text, f"CHANGELOG.md has no {SECTION} section"
    start = text.index(marker) + 1
    return text[start : text.index("\n## [", start + 1)]


def _table() -> dict[str, str]:
    """Map each row's 4.3.0 name to its 5.0 cell: a tool name, or "removed"."""
    lines = _release_section().splitlines()
    headers = [i for i, line in enumerate(lines) if line.startswith("| 4.3.0 tool |")]
    assert len(headers) == 1, f"expected one rename table in {SECTION}, found {len(headers)}"
    assert lines[headers[0]] == TABLE_HEADER
    table: dict[str, str] = {}
    for line in lines[headers[0] + 2 :]:
        if not line.startswith("|"):
            break
        match = ROW.match(line)
        assert match, f"row does not parse: {line}"
        assert match["old"] not in table, f"two rows for {match['old']}"
        table[match["old"]] = match["new"].strip("`")
    return table


def test_the_4_3_0_name_list_holds_the_released_tools() -> None:
    names = _names_430()
    assert len(names) == 306
    assert {"forecast_metric", "list_session_history", "reload_portals"} <= names


def test_every_4_3_0_name_5_0_does_not_register_has_a_row() -> None:
    missing = sorted(_names_430() - _registered() - _table().keys())
    assert missing == []


def test_every_row_names_a_4_3_0_tool_5_0_does_not_register() -> None:
    table = _table()
    assert sorted(table.keys() - _names_430()) == []
    assert sorted(table.keys() & _registered()) == []


def test_every_5_0_cell_is_a_registered_tool_or_removed() -> None:
    allowed = _registered() | {"removed"}
    assert [(old, new) for old, new in _table().items() if new not in allowed] == []


def test_only_the_renames_name_a_5_0_tool() -> None:
    assert {old: new for old, new in _table().items() if new != "removed"} == RENAMES


@pytest.mark.parametrize(("old", "new"), sorted(RENAMES.items()))
def test_renamed_tool_is_registered_under_its_new_name_only(old: str, new: str) -> None:
    registered = _registered()
    assert new in registered
    assert old not in registered
    assert get_tool_handler(new).__name__ == new


@pytest.mark.parametrize("name", KEPT_VERBS)
def test_job_and_action_tools_keep_their_verbs(name: str) -> None:
    assert name in _registered()
    assert name not in _table()


def test_no_tool_carries_the_list_prefix() -> None:
    assert sorted(name for name in _registered() if name.startswith("list_")) == []


def test_readme_names_no_tool_5_0_does_not_register() -> None:
    """R4.5: no name the README quotes, alone or as a call, is a 4.3.0 tool 5.0 lacks."""
    quoted = set(re.findall(r"`([a-z][a-z0-9_]*)[`(]", (ROOT / "README.md").read_text()))
    assert sorted(quoted & (_names_430() - _registered())) == []
