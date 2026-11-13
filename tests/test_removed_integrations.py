# Description: R1.2 to R1.4 and R1.6: no watsonx, HuggingFace, AWX, Terraform runner or dead module.
# Description: Covers the registry, the server's dispatch state, bootstrap and the stdio start.

from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

import lm_mcp
from lm_mcp import registry, server
from lm_mcp.prompts import PROMPTS
from lm_mcp.resources import get_resource_content
from lm_mcp.tools import is_error_result
from lm_mcp.transport.bootstrap import Backends

_SRC = Path(lm_mcp.__file__).parent
_REPO = Path(__file__).resolve().parent.parent

# Word-bounded where a plain substring overmatches: "TestOrchestrationGuide" holds "torch".
# The Terraform runner is named by its settings and internals, not by the word terraform,
# which get_terraform_imports keeps.
_REMOVED_WORDS = re.compile(
    r"watsonx|huggingface|granite|\btorch\b|\bhf_|\bttm\b|nl_summary"
    r"|awx|ansible|\baap\b|remediate_workflow"
    r"|tf_runner|tf_tool|terraformrunner|terraform_config"
    r"|\btf_(workspace_dir|terraform_binary|timeout|auto_approve_enabled)\b",
    re.IGNORECASE,
)

_TERRAFORM_RUNNER_TOOLS = [
    "terraform_init",
    "terraform_validate",
    "terraform_plan",
    "terraform_apply",
    "terraform_destroy",
    "terraform_import",
    "terraform_output",
    "terraform_state_list",
    "terraform_state_show",
    "terraform_write_config",
]

_SUMMARIZING_COMPOSITES = ["triage", "health_check", "portal_overview", "capacity_plan", "diagnose"]

_REMOVED_TOOLS = [
    "watsonx_summarize",
    "test_awx_connection",
    "get_job_templates",
    "get_job_template",
    "launch_job",
    "get_job_status",
    "get_job_output",
    "cancel_job",
    "relaunch_job",
    "get_inventories",
    "get_inventory_hosts",
    "launch_workflow",
    "get_workflow_status",
    "get_workflow_templates",
    "get_projects",
    "get_credentials",
    "get_organizations",
    "get_job_events",
    "get_hosts",
    *_TERRAFORM_RUNNER_TOOLS,
]


def _tool(name: str):
    return next(tool for tool in registry.TOOLS if tool.name == name)


@pytest.mark.parametrize("manifest", ["WATSONX_TOOLS", "AWX_TOOLS", "TF_TOOLS"])
def test_registry_has_no_removed_manifest(manifest):
    assert not hasattr(registry, manifest)


@pytest.mark.parametrize("name", _REMOVED_TOOLS)
def test_removed_tool_is_not_registered(name):
    assert name not in {tool.name for tool in registry.TOOLS}


def test_no_tool_carries_the_terraform_prefix():
    terraform = {tool.name for tool in registry.TOOLS if tool.name.startswith("terraform_")}

    assert terraform == set()


@pytest.mark.parametrize("name", _REMOVED_TOOLS)
def test_removed_tool_has_no_handler(name):
    with pytest.raises(ValueError, match="Unknown tool"):
        registry.get_tool_handler(name)


@pytest.mark.parametrize(
    "attribute",
    [
        "get_watsonx_client",
        "_set_watsonx_client",
        "_watsonx_client",
        "WATSONX_TOOL_NAMES",
        "get_awx_client",
        "_set_awx_client",
        "_awx_client",
        "AWX_TOOL_NAMES",
        "get_tf_runner",
        "_set_tf_runner",
        "_tf_runner",
        "TF_TOOL_NAMES",
    ],
)
def test_server_holds_no_removed_integration_state(attribute):
    assert not hasattr(server, attribute)


@pytest.mark.parametrize(
    "module",
    [
        "lm_mcp.tools.watsonx",
        "lm_mcp.client.watsonx",
        "lm_mcp.ibm_config",
        "lm_mcp.client.huggingface",
        "lm_mcp.hf_config",
        "lm_mcp.tools.ansible",
        "lm_mcp.client.awx",
        "lm_mcp.awx_config",
        "lm_mcp.client.terraform",
        "lm_mcp.terraform_config",
        "lm_mcp.config_warnings",
        "lm_mcp.tools.metric_presets",
        "lm_mcp.completions",
        "lm_mcp.validation",
        "lm_mcp.resources.examples",
    ],
)
def test_removed_module_does_not_import(module):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


@pytest.mark.parametrize("name", _SUMMARIZING_COMPOSITES)
def test_composite_schema_has_no_summarize_argument(name):
    assert "summarize" not in _tool(name).inputSchema["properties"]


@pytest.mark.parametrize("name", _SUMMARIZING_COMPOSITES)
def test_composite_handler_has_no_summarize_argument(name):
    assert "summarize" not in inspect.signature(registry.get_tool_handler(name)).parameters


@pytest.mark.parametrize("module", ["registry.py", "tools/workflows.py"])
def test_module_names_neither_summarize_nor_ttm(module):
    text = (_SRC / module).read_text()

    assert re.findall(r"\bsummarize\b|\bttm\b", text, flags=re.IGNORECASE) == []


@pytest.mark.parametrize("category", ["watsonx", "ansible"])
def test_tool_categories_have_no_removed_category(category):
    categories = json.loads(get_resource_content("lm://guide/tool-categories"))["categories"]

    assert category not in categories


@pytest.mark.parametrize("backend", ["watsonx", "awx", "terraform"])
def test_backends_have_no_removed_field(backend):
    assert backend not in {field.name for field in dataclasses.fields(Backends)}


def test_remediate_workflow_prompt_is_not_registered():
    assert "remediate_workflow" not in {prompt.name for prompt in PROMPTS}


def test_example_playbooks_are_gone():
    assert not (_REPO / "examples" / "playbooks").exists()


@pytest.mark.parametrize("name", _REMOVED_TOOLS)
async def test_execute_tool_reports_removed_tool_as_unknown(name, monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

    result = await server.execute_tool(name, {})

    assert is_error_result(result)
    assert f"Unknown tool: {name}" in result[0].text


def _start_stdio(settings: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a real server process with stdin at EOF, single-portal unless settings say otherwise."""
    env = {
        **os.environ,
        "LM_PORTAL": "test.logicmonitor.com",
        "LM_BEARER_TOKEN": "test-token",
        "LM_MULTI_PORTAL": "false",
        **settings,
    }
    return subprocess.run(
        [sys.executable, "-m", "lm_mcp.server"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"WATSONX_API_KEY": "test-key", "WATSONX_PROJECT_ID": "test-project"},
        {"AWX_URL": "https://aap.example.com", "AWX_TOKEN": "test-token"},
    ],
    ids=["watsonx", "awx"],
)
def test_stdio_start_with_removed_settings_logs_nothing_about_them(settings, tmp_path):
    """A real server process with stdin at EOF ignores the settings and exits cleanly."""
    done = _start_stdio(settings, tmp_path)

    assert done.returncode == 0, done.stderr
    assert _REMOVED_WORDS.findall(done.stdout + done.stderr) == []


def test_multi_portal_start_with_terraform_settings_logs_nothing_about_terraform(tmp_path):
    """A multi-portal start with a category filter and TF_WORKSPACE_DIR set logs no Terraform."""
    portals_file = tmp_path / "portals.json"
    portals_file.write_text('{"acme": {"portal": "acme.example.com", "bearer_token": "t"}}')

    done = _start_stdio(
        {
            "LM_MULTI_PORTAL": "true",
            "LM_PORTALS_FILE": str(portals_file),
            "LM_MCP_CATEGORIES": "read,session",
            "TF_WORKSPACE_DIR": str(tmp_path),
        },
        tmp_path,
    )

    assert done.returncode == 0, done.stderr
    assert re.findall("terraform", done.stdout + done.stderr, flags=re.IGNORECASE) == []


def test_src_starts_no_process_except_the_vault_decrypt():
    """R1.4: no module spawns a process, apart from portals.py running age on the vault."""
    texts = {path.relative_to(_SRC).as_posix(): path.read_text() for path in _SRC.rglob("*.py")}

    assert {name for name, text in texts.items() if "create_subprocess" in text} == set()
    assert {name for name, text in texts.items() if "subprocess" in text} == {"portals.py"}


def test_pyproject_declares_only_the_http_extra():
    project = tomllib.loads((_REPO / "pyproject.toml").read_text())["project"]

    assert set(project["optional-dependencies"]) == {"http"}


def test_dev_group_pins_no_model_dependency():
    groups = tomllib.loads((_REPO / "pyproject.toml").read_text())["dependency-groups"]
    pinned = {re.split(r"[<>=!~\[ ]", entry)[0] for entry in groups["dev"]}

    assert pinned.isdisjoint({"ibm-watsonx-ai", "pandas", "torch", "transformers"})


def test_ci_has_no_huggingface_job():
    workflow = yaml.safe_load((_REPO / ".github/workflows/test.yml").read_text())

    assert "huggingface" not in workflow["jobs"]


def test_dependabot_ignores_nothing_for_uv():
    config = yaml.safe_load((_REPO / ".github/dependabot.yml").read_text())
    (uv,) = [update for update in config["updates"] if update["package-ecosystem"] == "uv"]

    assert "ignore" not in uv


def _locked_package_names() -> set[str]:
    lock = tomllib.loads((_REPO / "uv.lock").read_text())
    return {package["name"] for package in lock["package"]}


def test_lock_holds_no_model_dependency():
    removed = {"torch", "transformers", "granite-tsfm", "accelerate", "ibm-watsonx-ai", "pandas"}

    assert _locked_package_names().isdisjoint(removed)


def _lm_mcp_declared_names() -> set[str]:
    """Every name lm-mcp's own lock entry declares: runtime, extras, dev, and their metadata."""
    lock = tomllib.loads((_REPO / "uv.lock").read_text())
    (entry,) = [package for package in lock["package"] if package["name"] == "lm-mcp"]
    metadata = entry["metadata"]
    lists = [
        entry.get("dependencies", []),
        *entry.get("optional-dependencies", {}).values(),
        *entry.get("dev-dependencies", {}).values(),
        metadata.get("requires-dist", []),
        *metadata.get("requires-dev", {}).values(),
    ]
    return {dependency["name"] for listed in lists for dependency in listed}


def test_lock_declares_no_direct_dotenv():
    """R1.6: lm-mcp declares no python-dotenv; pydantic-settings and uvicorn[standard] need it."""
    declared = _lm_mcp_declared_names()

    assert "pydantic-settings" in declared
    assert "python-dotenv" not in declared


def test_lock_stays_under_eighty_packages():
    assert len(_locked_package_names()) < 80


def test_src_names_no_removed_integration():
    naming = {
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if _REMOVED_WORDS.search(path.read_text())
    }

    assert naming == set()


def test_tests_name_no_removed_integration():
    """This file names them by necessity, as does the 4.3.0 tool list that the CHANGELOG
    rename table is checked against, and Edwin AI's captured data model, whose record
    types include its own Ansible integration (ansibleEdaEvent, ansiblePlaybook,
    ansibleWorkflow); those three files are the exceptions."""
    tests = _REPO / "tests"
    exempt = {
        Path(__file__).resolve(),
        tests / "fixtures" / "tool_names-4.3.0.txt",
        tests / "fixtures" / "edwin_metadata.json",
    }
    naming = {
        path.relative_to(tests).as_posix()
        for path in tests.rglob("*")
        if path.suffix in {".py", ".json", ".md", ".txt"}
        and path not in exempt
        and _REMOVED_WORDS.search(path.read_text())
    }

    assert naming == set()


@pytest.mark.parametrize(
    "name",
    [
        "pyproject.toml",
        "server.json",
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "MULTIPORTAL.md",
        "deploy/k8s/deployment.yaml",
        "documentation/client-setup.md",
        "documentation/tools.md",
        ".github/workflows/test.yml",
        ".github/dependabot.yml",
        ".claude/skills/lm-remediate/SKILL.md",
    ],
)
def test_public_file_names_no_removed_integration(name):
    assert _REMOVED_WORDS.findall(_without_pointer_section(name)) == []


# The README section that says where Terraform runs and Ansible launches belong (R4.5).
_POINTER_HEADING = "### What the server does not do\n"


def _without_pointer_section(name: str) -> str:
    """A public file's text, less the README section that points to other servers."""
    text = (_REPO / name).read_text()
    if name != "README.md":
        return text
    start = text.index(_POINTER_HEADING)
    end = text.index("\n#", start + len(_POINTER_HEADING))
    return text[:start] + text[end:]


def test_readme_pointer_section_names_no_tool_or_setting():
    """The section names other servers and CLIs, not a tool or setting this server had."""
    text = (_REPO / "README.md").read_text()
    start = text.index(_POINTER_HEADING)
    section = text[start : text.index("\n#", start + len(_POINTER_HEADING))]
    assert re.findall(r"`(awx_[a-z_]+|[A-Z]+_[A-Z_]+|terraform_[a-z]+)`", section) == []
