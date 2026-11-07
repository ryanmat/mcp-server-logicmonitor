# Description: Guards the removal of the optional integrations the 5.0 server no longer carries.
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
from lm_mcp.resources import get_resource_content
from lm_mcp.tools import is_error_result
from lm_mcp.transport.bootstrap import Backends

_SRC = Path(lm_mcp.__file__).parent
_REPO = Path(__file__).resolve().parent.parent

# Word-bounded where a plain substring would match an ordinary word: "orchestration" holds "torch".
_REMOVED_WORDS = re.compile(
    r"watsonx|huggingface|granite|\btorch\b|\bhf_|\bttm\b|nl_summary", re.IGNORECASE
)

_SUMMARIZING_COMPOSITES = ["triage", "health_check", "portal_overview", "capacity_plan", "diagnose"]


def _tool(name: str):
    return next(tool for tool in registry.TOOLS if tool.name == name)


def test_registry_has_no_watsonx_manifest():
    assert not hasattr(registry, "WATSONX_TOOLS")


def test_no_registered_tool_is_watsonx_summarize():
    names = {tool.name for tool in (*registry.TOOLS, *registry.AWX_TOOLS, *registry.TF_TOOLS)}

    assert "watsonx_summarize" not in names


def test_watsonx_summarize_has_no_handler():
    with pytest.raises(ValueError, match="Unknown tool"):
        registry.get_tool_handler("watsonx_summarize")


@pytest.mark.parametrize(
    "attribute",
    ["get_watsonx_client", "_set_watsonx_client", "_watsonx_client", "WATSONX_TOOL_NAMES"],
)
def test_server_holds_no_watsonx_state(attribute):
    assert not hasattr(server, attribute)


@pytest.mark.parametrize(
    "module",
    [
        "lm_mcp.tools.watsonx",
        "lm_mcp.client.watsonx",
        "lm_mcp.ibm_config",
        "lm_mcp.client.huggingface",
        "lm_mcp.hf_config",
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


def test_forecast_metric_methods_are_the_statistical_ones():
    method = _tool("forecast_metric").inputSchema["properties"]["method"]

    assert method["enum"] == ["auto", "linear", "holt_winters"]


@pytest.mark.parametrize("module", ["registry.py", "tools/forecasting.py", "tools/workflows.py"])
def test_module_names_neither_summarize_nor_ttm(module):
    text = (_SRC / module).read_text()

    assert re.findall(r"\bsummarize\b|\bttm\b", text, flags=re.IGNORECASE) == []


def test_tool_categories_have_no_watsonx_category():
    categories = json.loads(get_resource_content("lm://guide/tool-categories"))["categories"]

    assert "watsonx" not in categories


def test_backends_have_no_watsonx_field():
    assert "watsonx" not in {field.name for field in dataclasses.fields(Backends)}


async def test_execute_tool_reports_watsonx_summarize_as_unknown(monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

    result = await server.execute_tool("watsonx_summarize", {"data": "x"})

    assert is_error_result(result)
    assert "Unknown tool: watsonx_summarize" in result[0].text


def test_stdio_start_with_watsonx_settings_logs_nothing_about_watsonx(tmp_path):
    """A real server process with stdin at EOF ignores the settings and exits cleanly."""
    env = {
        **os.environ,
        "LM_PORTAL": "test.logicmonitor.com",
        "LM_BEARER_TOKEN": "test-token",
        "LM_MULTI_PORTAL": "false",
        "WATSONX_API_KEY": "test-key",
        "WATSONX_PROJECT_ID": "test-project",
    }

    done = subprocess.run(
        [sys.executable, "-m", "lm_mcp.server"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=60,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert "watsonx" not in (done.stdout + done.stderr).lower()


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


def test_src_names_no_removed_integration():
    naming = {
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if _REMOVED_WORDS.search(path.read_text())
    }

    assert naming == set()


def test_tests_name_no_removed_integration():
    """This file names them by necessity, and is the one exception."""
    tests = _REPO / "tests"
    naming = {
        path.relative_to(tests).as_posix()
        for path in tests.rglob("*")
        if path.suffix in {".py", ".json", ".md", ".txt"}
        and path != Path(__file__).resolve()
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
        "documentation/client-setup.md",
        "documentation/tools.md",
        ".github/workflows/test.yml",
        ".github/dependabot.yml",
    ],
)
def test_public_file_names_no_removed_integration(name):
    assert _REMOVED_WORDS.findall((_REPO / name).read_text()) == []
