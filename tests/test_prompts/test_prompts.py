# Description: Tests for the three MCP workflow prompts and the tool names their text cites.
# Description: Covers listing, rendering with and without arguments, and the template table.

from __future__ import annotations

import re

import pytest

from lm_mcp.prompts import PROMPTS, get_prompt_messages
from lm_mcp.registry import TOOLS

_BACKTICKED_NAME = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)*)`")

_REMOVED_PROMPTS = (
    "health_check",
    "alert_summary",
    "sdt_planning",
    "cost_optimization",
    "audit_review",
    "alert_correlation",
    "collector_health",
    "troubleshoot_device",
    "top_talkers",
    "rca_workflow",
    "capacity_forecast",
)

# Each prompt's full argument set, with values its text must echo, and the phrases its
# text carries in their place when rendered with no arguments.
_RENDER_CASES: dict[str, tuple[dict[str, str], list[str]]] = {
    "incident_triage": (
        {"severity": "sev-7341", "time_window_hours": "7342"},
        ["Severity filter: all severities", "Time window: Last 24 hours"],
    ),
    "capacity_review": (
        {"group_id": "7343", "threshold_percent": "7344"},
        ["Device group: all groups", "Alert threshold: 80%"],
    ),
    "remediation": (
        {"host_id": "7345", "remediation_source_id": "7346", "alert_id": "7347"},
        [
            "Host ID: not specified",
            "Remediation Source ID: not specified",
            "Alert ID: not specified (optional)",
        ],
    ),
}


async def _render(name: str, arguments: dict[str, str] | None) -> str:
    from lm_mcp.server import get_prompt

    result = await get_prompt(name, arguments)
    assert len(result.messages) == 1
    return result.messages[0].content.text


async def test_list_prompts_returns_exactly_the_three():
    """R1.7: list_prompts serves incident_triage, capacity_review and remediation, no other."""
    from lm_mcp.server import list_prompts

    names = [prompt.name for prompt in await list_prompts()]

    assert sorted(names) == ["capacity_review", "incident_triage", "remediation"]


@pytest.mark.parametrize("name", sorted(_RENDER_CASES))
async def test_prompt_renders_with_every_argument(name):
    """Each prompt's text carries every argument value it was given."""
    arguments, _ = _RENDER_CASES[name]
    (prompt,) = [p for p in PROMPTS if p.name == name]
    assert set(arguments) == {argument.name for argument in prompt.arguments or []}

    text = await _render(name, arguments)

    for value in arguments.values():
        assert value in text


@pytest.mark.parametrize("name", sorted(_RENDER_CASES))
async def test_prompt_renders_without_arguments(name):
    """Each prompt renders with no arguments and states its defaults."""
    _, defaults = _RENDER_CASES[name]

    text = await _render(name, None)

    for phrase in defaults:
        assert phrase in text


@pytest.mark.parametrize("name", [prompt.name for prompt in PROMPTS])
def test_prompt_text_cites_only_registered_tools(name):
    """R1.7: every backticked snake_case name in a prompt's text is a registered tool."""
    tool_names = {tool.name for tool in TOOLS}
    text = get_prompt_messages(name, {}).messages[0].content.text

    cited = set(_BACKTICKED_NAME.findall(text))

    assert cited - tool_names == set()


def test_removed_prompts_are_unknown():
    """R1.7: get_prompt_messages refuses each of the eleven removed prompt names."""
    for name in _REMOVED_PROMPTS:
        with pytest.raises(ValueError, match="Unknown prompt"):
            get_prompt_messages(name, {})


def test_get_workflow_is_not_a_tool():
    """R1.7: get_workflow is neither registered nor dispatchable."""
    from lm_mcp.registry import get_tool_handler

    assert "get_workflow" not in {tool.name for tool in TOOLS}
    with pytest.raises(ValueError, match="Unknown tool"):
        get_tool_handler("get_workflow")


def test_templates_match_prompts():
    """The template table and PROMPTS name the same prompts."""
    from lm_mcp.prompts.registry import _TEMPLATES

    assert set(_TEMPLATES) == {prompt.name for prompt in PROMPTS}


def test_get_prompt_messages_returns_one_user_message():
    """get_prompt_messages wraps the template text in one user message."""
    result = get_prompt_messages("incident_triage", {"severity": "critical"})

    assert result.description == "LogicMonitor incident triage workflow"
    assert len(result.messages) == 1
    assert result.messages[0].role == "user"
    assert isinstance(result.messages[0].content.text, str)
    assert len(result.messages[0].content.text) > 0


def test_unknown_prompt_raises_value_error():
    """get_prompt_messages refuses a name no prompt has."""
    with pytest.raises(ValueError, match="Unknown prompt"):
        get_prompt_messages("bogus_prompt", {})
