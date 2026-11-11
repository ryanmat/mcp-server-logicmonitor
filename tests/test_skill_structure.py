# Description: Structural validation tests for Claude Code skill files.
# Description: Verifies YAML frontmatter, allowed tools, and registry consistency.

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lm_mcp.registry import TOOLS

SKILLS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "skills"

# Build a set of the core tool names from the registry for cross-referencing
ALL_REGISTRY_TOOLS = {tool.name for tool in TOOLS}

# Expected skills (directory names under .claude/skills/)
EXPECTED_SKILLS = [
    "lm-apm",
    "lm-capacity",
    "lm-edwin",
    "lm-health",
    "lm-logs",
    "lm-portal",
    "lm-triage",
    "lm-remediate",
]

# A backticked identifier in a skill body, bare or called: `get_devices`, `triage(...)`.
_BACKTICKED_NAME = re.compile(r"`([a-z][a-z0-9_]*)(?:\([^`\n]*\))?`")

# A backticked identifier is a tool name when it is registered, was a 4.3.0 tool, or
# starts with a tool verb; list_ is the prefix 5.0 retired.
_TOOL_PREFIXES = (
    "get_",
    "create_",
    "update_",
    "delete_",
    "run_",
    "trigger_",
    "analyze_",
    "execute_",
    "list_",
)
_NAMES_430 = set(
    (Path(__file__).resolve().parent / "fixtures" / "tool_names-4.3.0.txt").read_text().split()
)

# The tools each rewritten skill's recipe is built on.
_RECIPE_TOOLS = {
    "lm-apm": {"get_apm_services", "get_apm_service_alerts", "get_device_data", "analyze_metric"},
    "lm-capacity": {"get_devices", "analyze_metric", "get_otlp_metric_names"},
    "lm-edwin": {"get_edwin_insights", "get_edwin_insight", "analyze_metric", "triage"},
    "lm-health": {"get_devices", "health_check", "analyze_metric"},
    "lm-logs": {
        "get_log_pipelines",
        "get_tracked_log_queries",
        "get_log_query_groups",
        "get_log_partitions",
        "get_log_usage",
    },
    "lm-portal": {"portal_overview", "analyze_alerts", "get_collectors"},
    "lm-remediate": {
        "diagnose",
        "get_remediationsources",
        "execute_remediation",
        "get_diagnostic_remediation_results",
        "get_action_chains",
        "get_edwin_tools",
        "edwin_run_tool",
    },
    "lm-triage": {"triage", "analyze_alerts"},
}

_PREFIX = "mcp__logicmonitor__"


def _parse_frontmatter(text: str) -> dict:
    """Parse simple YAML frontmatter without external dependencies.

    Handles scalar values and lists (- item lines). Sufficient for
    skill frontmatter which uses name, description, argument-hint,
    and allowed-tools fields.
    """
    result = {}
    current_key = None
    for line in text.split("\n"):
        # List item under current key
        if line.startswith("  - ") and current_key is not None:
            result[current_key].append(line.strip("- ").strip())
            continue
        # Key: value pair
        kv_match = re.match(r"^(\S[\w-]+):\s*(.*)", line)
        if kv_match:
            key = kv_match.group(1)
            value = kv_match.group(2).strip().strip('"').strip("'")
            if value:
                result[key] = value
                current_key = None
            else:
                # Empty value means a list follows
                result[key] = []
                current_key = key
    return result


def _load_skill_frontmatter(skill_dir: Path) -> dict:
    """Parse YAML frontmatter from a SKILL.md file.

    Reads the file and extracts content between the opening and closing
    '---' delimiters.
    """
    skill_file = skill_dir / "SKILL.md"
    text = skill_file.read_text()
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match, f"No YAML frontmatter found in {skill_file}"
    return _parse_frontmatter(match.group(1))


def _get_all_skill_dirs() -> list[Path]:
    """Return paths for all expected skill directories."""
    return [SKILLS_DIR / name for name in EXPECTED_SKILLS]


class TestSkillFileStructure:
    """Structural validation for all skill SKILL.md files."""

    @pytest.fixture(autouse=True)
    def _load_skills(self):
        """Load frontmatter for all skills once per test class."""
        self.skills = {}
        for skill_dir in _get_all_skill_dirs():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                self.skills[skill_dir.name] = _load_skill_frontmatter(skill_dir)

    def test_all_skills_have_yaml_frontmatter(self):
        """Every expected skill directory has a SKILL.md with YAML frontmatter."""
        for name in EXPECTED_SKILLS:
            assert name in self.skills, f"Skill '{name}' missing or has no frontmatter"

    def test_all_skills_have_name(self):
        """Every skill frontmatter contains a 'name' field."""
        for name, fm in self.skills.items():
            assert "name" in fm, f"Skill '{name}' missing 'name' in frontmatter"

    def test_all_skills_have_description(self):
        """Every skill frontmatter contains a 'description' field."""
        for name, fm in self.skills.items():
            assert "description" in fm, f"Skill '{name}' missing 'description' in frontmatter"

    def test_all_skills_have_allowed_tools(self):
        """Every skill frontmatter contains an 'allowed-tools' list."""
        for name, fm in self.skills.items():
            assert "allowed-tools" in fm, f"Skill '{name}' missing 'allowed-tools' in frontmatter"
            assert isinstance(fm["allowed-tools"], list), (
                f"Skill '{name}' 'allowed-tools' is not a list"
            )
            assert len(fm["allowed-tools"]) > 0, f"Skill '{name}' 'allowed-tools' is empty"

    def test_skill_allowed_tools_exist_in_registry(self):
        """Each frontmatter tool maps to a registry tool.

        Skill files reference tools as 'mcp__logicmonitor__<tool_name>'.
        This test strips the prefix and checks against TOOLS.
        """
        prefix = "mcp__logicmonitor__"
        for name, fm in self.skills.items():
            for tool_ref in fm.get("allowed-tools", []):
                assert tool_ref.startswith(prefix), (
                    f"Skill '{name}' tool '{tool_ref}' missing expected prefix"
                )
                tool_name = tool_ref[len(prefix) :]
                assert tool_name in ALL_REGISTRY_TOOLS, (
                    f"Skill '{name}' references tool '{tool_name}' which does not exist in TOOLS"
                )

    def test_lm_remediate_skill_exists(self):
        """The lm-remediate skill directory and SKILL.md exist."""
        skill_file = SKILLS_DIR / "lm-remediate" / "SKILL.md"
        assert skill_file.exists(), "lm-remediate/SKILL.md does not exist"


def _skill_text(name: str) -> tuple[dict, str]:
    """A skill's parsed frontmatter and the body after it."""
    text = (SKILLS_DIR / name / "SKILL.md").read_text()
    _, frontmatter, body = text.split("---", 2)
    return _parse_frontmatter(frontmatter), body


def _allowed(name: str) -> set[str]:
    return {ref.removeprefix(_PREFIX) for ref in _skill_text(name)[0]["allowed-tools"]}


def _body_tool_names(name: str) -> set[str]:
    """The tool names a skill body cites in backticks."""
    named = set(_BACKTICKED_NAME.findall(_skill_text(name)[1]))
    return {
        word
        for word in named
        if word in ALL_REGISTRY_TOOLS or word in _NAMES_430 or word.startswith(_TOOL_PREFIXES)
    }


def test_expected_skills_are_the_skill_directories():
    """R2.14: the guards below iterate EXPECTED_SKILLS, so it lists every skill there is."""
    present = sorted(path.name for path in SKILLS_DIR.iterdir() if path.is_dir())
    assert present == sorted(EXPECTED_SKILLS)


@pytest.mark.parametrize("name", EXPECTED_SKILLS)
def test_skill_body_names_only_registered_tools(name):
    """R2.14: every tool name a skill body cites is a registered tool."""
    assert sorted(_body_tool_names(name) - ALL_REGISTRY_TOOLS) == []


@pytest.mark.parametrize("name", EXPECTED_SKILLS)
def test_skill_body_names_exactly_its_allowed_tools(name):
    """R2.14: a skill's body calls the tools its allowed-tools grant, and only those."""
    assert sorted(_body_tool_names(name) & ALL_REGISTRY_TOOLS) == sorted(_allowed(name))


@pytest.mark.parametrize("name", sorted(_RECIPE_TOOLS))
def test_rewritten_skill_is_built_on_its_recipe_tools(name):
    """R2.14: each rewritten skill grants and names the 5.0 tools its recipe uses."""
    tools = _RECIPE_TOOLS[name]
    assert sorted(tools - _allowed(name)) == []
    assert sorted(tools - _body_tool_names(name)) == []


def test_lm_capacity_reads_otel_series_through_analyze_metric():
    """R2.14, R3.2: lm-capacity's OTel branch calls analyze_metric with source="otlp"."""
    assert 'source="otlp"' in _skill_text("lm-capacity")[1]


def _step(name: str, heading: str) -> str:
    """One '### ' section of a skill body, from its heading to the next one."""
    body = _skill_text(name)[1]
    start = body.index(f"### {heading}")
    end = body.find("\n### ", start + 1)
    return body[start:] if end == -1 else body[start:end]


def test_lm_capacity_argument_hint_names_the_workload():
    """lm-capacity takes a device or an OTel workload, so its argument hint names both."""
    hint = _skill_text("lm-capacity")[0]["argument-hint"]
    assert "device" in hint
    assert "workload" in hint


def test_lm_capacity_breach_step_quotes_the_no_threshold_reason():
    """Step 8 reads analyze_metric's answer to a forecast with no threshold, by its text."""
    from lm_mcp.tools.analyze_metric import holt_winters_forecast, linear_forecast

    # Two days at 30-minute samples, enough for Holt-Winters to fit its daily season.
    stamps = [i * 1800 for i in range(96)]
    values = [50.0 + (i % 48) / 4 for i in range(96)]
    reasons = {
        linear_forecast(values, stamps, None)["reason"],
        holt_winters_forecast(values, stamps, None)["reason"],
    }
    assert len(reasons) == 1
    (reason,) = reasons
    # The paragraph that lists the reasons a method gives in place of a crossing.
    paragraphs = _step("lm-capacity", "Step 8").split("\n\n")
    (reason_list,) = [p for p in paragraphs if "Where a method has no" in p]
    assert f"`{reason}`" in reason_list


def test_lm_edwin_says_a_ci_with_one_alert_forms_no_device_cluster():
    """Step 4 compares triage's clusters with Edwin's grouping; one alert forms no cluster."""
    from lm_mcp.tools.analyze_alerts import cluster_by_device

    alert = {
        "id": "LMA1",
        "monitorObjectName": "ci-a",
        "monitorObjectType": "device",
        "monitorObjectId": 7,
        "startEpoch": 1,
    }
    assert cluster_by_device([alert]) == []
    assert cluster_by_device([alert, {**alert, "id": "LMA2"}]) != []
    assert "forms no device cluster" in _step("lm-edwin", "Step 4")
