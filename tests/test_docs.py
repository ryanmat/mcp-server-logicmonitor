# Description: Guards the public setup doc and the CHANGELOG links against the code they describe.
# Description: Config blocks parse and list what they say; every release has a chained compare link.

from __future__ import annotations

import json
import re
import textwrap
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / "documentation" / "client-setup.md"
CHANGELOG = ROOT / "CHANGELOG.md"
REPO_URL = "https://github.com/ryanmat/mcp-server-logicmonitor"

# A fenced block, at the margin or indented under a numbered step.
_FENCE = re.compile(r"^([ \t]*)```(\w*)\n(.*?)^\1```", re.MULTILINE | re.DOTALL)


def _sections() -> list[tuple[str, str]]:
    """The setup doc's ## sections as (heading, body)."""
    parts = re.split(r"^## (.+)$", SETUP.read_text(), flags=re.MULTILINE)
    return list(zip(parts[1::2], parts[2::2], strict=True))


def _blocks(text: str) -> list[tuple[str, str]]:
    """Each fenced block's language and body, its indentation removed."""
    return [(lang, textwrap.dedent(indent + body)) for indent, lang, body in _FENCE.findall(text)]


def _config(lang: str, body: str) -> dict[str, Any]:
    return json.loads(body) if lang == "json" else tomllib.loads(body)


def _server_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """The logicmonitor entries of a parsed config, whatever the client's top-level key."""
    entries = []
    for key in ("mcpServers", "servers", "mcp_servers"):
        if "logicmonitor" in config.get(key, {}):
            entries.append(config[key]["logicmonitor"])
    return entries


def _env(entry: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in entry.get("env", {}).items()}


def _bash_env(body: str) -> dict[str, str]:
    """The LM_ variables a shell block passes with -e or --env."""
    return dict(re.findall(r"(?:-e|--env) (LM_[A-Z_]+)=(\S+)", body))


def _listed(monkeypatch, env: dict[str, str]) -> list[str]:
    """The tools the server lists under a config block's environment."""
    from lm_mcp.config import LMConfig
    from lm_mcp.registry import TOOLS
    from lm_mcp.server import _filter_tools

    for name in list(__import__("os").environ):
        if name.startswith(("LM_", "EDWIN_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("LM_PORTAL", "yourcompany.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "a-bearer-token-value")
    for name, value in env.items():
        if not value.startswith(("${", "$", "<")):
            monkeypatch.setenv(name, value)
    return [tool.name for tool in _filter_tools(list(TOOLS), LMConfig())]


def _all_config_blocks() -> list[tuple[str, str]]:
    return [(lang, body) for lang, body in _blocks(SETUP.read_text()) if lang in ("json", "toml")]


class TestSetupConfigBlocks:
    """R4.5: every config block in documentation/client-setup.md is one a client can read."""

    def test_the_doc_has_json_and_toml_blocks(self) -> None:
        langs = {lang for lang, _ in _all_config_blocks()}
        assert langs == {"json", "toml"}

    @pytest.mark.parametrize(("lang", "body"), _all_config_blocks())
    def test_block_parses(self, lang: str, body: str) -> None:
        assert _config(lang, body)

    @pytest.mark.parametrize(("lang", "body"), _all_config_blocks())
    def test_block_starts_this_server_or_reaches_its_endpoint(self, lang: str, body: str) -> None:
        config = _config(lang, body)
        entries = _server_entries(config)
        if not entries:
            assert "command" in config, "a bare entry block carries a command"
            entries = [config]
        for entry in entries:
            url = entry.get("url") or entry.get("httpUrl")
            if url:
                assert url.endswith("/mcp")
            else:
                assert entry["command"] == "uvx"
                assert entry["args"] == ["--from", "lm-mcp", "lm-mcp-server"]

    def test_no_dropped_client_is_described(self) -> None:
        text = SETUP.read_text()
        assert re.findall(r"\b(Continue|Cline|Aider)\b", text) == []


def _config_blocks(text: str) -> list[tuple[str, str]]:
    """The blocks in ``text`` that configure a client: JSON, TOML and shell commands."""
    return [(lang, body) for lang, body in _blocks(text) if lang in ("json", "toml", "bash")]


def _write_section(heading: str) -> bool:
    return "write" in heading.lower()


class TestReadOnlyFirst:
    """R4.5: each client section shows a read-only configuration; writes come after them all."""

    def test_the_write_section_follows_every_client_section(self) -> None:
        headings = [heading for heading, _ in _sections()]
        writes = [i for i, h in enumerate(headings) if _write_section(h)]
        connects = [i for i, h in enumerate(headings) if h.startswith("Connect")]
        assert writes and connects
        assert min(writes) > max(connects)

    @pytest.mark.parametrize(
        ("heading", "body"),
        [(h, b) for h, b in _sections() if not _write_section(h) and _config_blocks(b)],
    )
    def test_first_block_leaves_writes_off(self, heading: str, body: str) -> None:
        lang, first = _config_blocks(body)[0]
        if lang == "bash":
            env = _bash_env(first)
        else:
            entries = _server_entries(_config(lang, first))
            env = {k: v for entry in entries for k, v in _env(entry).items()}
        assert env.get("LM_ENABLE_WRITE_OPERATIONS", "false") != "true", heading


def _filtered_envs() -> list[dict[str, str]]:
    """The env of every block that narrows the tool list."""
    envs = []
    for lang, body in _all_config_blocks():
        try:
            config = _config(lang, body)
        except (json.JSONDecodeError, tomllib.TOMLDecodeError):
            continue  # test_block_parses fails on this block by name
        for entry in _server_entries(config):
            env = _env(entry)
            if "LM_ENABLED_TOOLS" in env or "LM_MCP_CATEGORIES" in env:
                envs.append(env)
    return envs


class TestFilteredExamples:
    """The narrowed examples list what they name, and few enough tools for a capped client."""

    def test_the_doc_has_a_surgical_example(self) -> None:
        assert any("LM_ENABLED_TOOLS" in env for env in _filtered_envs())

    @pytest.mark.parametrize("env", _filtered_envs())
    def test_every_named_tool_is_listed(self, env: dict[str, str], monkeypatch) -> None:
        named = [n for n in env.get("LM_ENABLED_TOOLS", "").split(",") if n and "*" not in n]
        listed = _listed(monkeypatch, env)
        assert [n for n in named if n not in listed] == []

    @pytest.mark.parametrize("env", _filtered_envs())
    def test_lists_at_most_forty_tools(self, env: dict[str, str], monkeypatch) -> None:
        assert 0 < len(_listed(monkeypatch, env)) <= 40


def _changelog_versions() -> list[str]:
    return re.findall(r"^## \[([^\]]+)\]", CHANGELOG.read_text(), flags=re.MULTILINE)


def _changelog_links() -> dict[str, str]:
    return dict(re.findall(r"^\[([^\]]+)\]: (\S+)$", CHANGELOG.read_text(), flags=re.MULTILINE))


class TestChangelogLinks:
    """R4.5: each CHANGELOG section links to its compare view, starting where the last ended."""

    def test_every_section_has_a_link(self) -> None:
        links = _changelog_links()
        assert [v for v in _changelog_versions() if v not in links] == []

    def test_compare_links_chain_from_the_first_release(self) -> None:
        versions = _changelog_versions()
        links = _changelog_links()
        assert versions[-1] == "0.1.0"
        assert links["0.1.0"] == f"{REPO_URL}/releases/tag/v0.1.0"
        previous_ref = "v0.1.0"
        for version in reversed(versions[:-1]):
            match = re.fullmatch(rf"{REPO_URL}/compare/(\S+)\.\.\.(\S+)", links[version])
            assert match, f"{version}: {links[version]}"
            assert match[1] == previous_ref, version
            if version == "Unreleased":
                assert match[2] == "HEAD"
            else:
                assert match[2] == f"v{version}" or re.fullmatch(r"[0-9a-f]{12}", match[2]), version
            previous_ref = match[2]


def _counts(monkeypatch) -> dict[str, int]:
    """The per-configuration tool counts the docs state, computed from the registry and filter."""
    from lm_mcp import server
    from lm_mcp.categories import writes_to_portal
    from lm_mcp.registry import TOOLS

    default = len(_listed(monkeypatch, {}))
    multi = len(_listed(monkeypatch, {"LM_MULTI_PORTAL": "true", "LM_PORTALS_FILE": "/p.json"}))
    monkeypatch.setattr(server, "_edwin_client", object())
    with_edwin = len(_listed(monkeypatch, {}))
    monkeypatch.setattr(server, "_edwin_client", None)
    annotations = [tool.annotations for tool in TOOLS if tool.annotations is not None]
    return {
        "default": default,
        "multi_portal": multi,
        "edwin_extra": with_edwin - default,
        "write_gated": sum(writes_to_portal(tool) for tool in TOOLS),
        "destructive": sum(bool(a.destructiveHint) for a in annotations),
        "workflow": len(_listed(monkeypatch, {"LM_MCP_CATEGORIES": "workflow"})),
        "writes_on": len(_listed(monkeypatch, {"LM_ENABLE_WRITE_OPERATIONS": "true"})),
    }


# Each documented count: the file, a pattern whose group is the number, and what it counts.
_DOCUMENTED_COUNTS = [
    ("README.md", r"a client sees (\d+) of them", "default"),
    ("README.md", r"\((\d+) in multi-portal mode", "multi_portal"),
    ("README.md", r"(\d+) more with Edwin credentials", "edwin_extra"),
    ("README.md", r"Before one of the (\d+) destructive tools", "destructive"),
    ("SECURITY.md", r"leaves the (\d+) tools whose annotations", "write_gated"),
    ("SECURITY.md", r"The (\d+) tools annotated `destructiveHint`", "destructive"),
    ("documentation/client-setup.md", r"lists (\d+) of its 273 tools", "default"),
    ("documentation/client-setup.md", r"`workflow` lists (\d+) tools", "workflow"),
    ("documentation/client-setup.md", r"grows from (\d+) to \d+", "default"),
    ("documentation/client-setup.md", r"grows from \d+ to (\d+)", "writes_on"),
]


@pytest.mark.parametrize(("doc", "pattern", "key"), _DOCUMENTED_COUNTS)
def test_documented_count_matches_the_server(doc: str, pattern: str, key: str, monkeypatch) -> None:
    """Chunk W review: each per-configuration count a doc states is the one the server lists."""
    stated = re.findall(pattern, (ROOT / doc).read_text())
    assert len(stated) == 1, f"{doc}: {pattern!r} matched {len(stated)} times"
    assert int(stated[0]) == _counts(monkeypatch)[key]
