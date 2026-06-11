# Description: Generate documentation/tools.md from the tool registry and guard it from drift.
# Description: Fails when a tool is added, removed, renamed, re-described, or recategorized.

from __future__ import annotations

from pathlib import Path

from lm_mcp.logging import is_write_tool
from lm_mcp.registry import AWX_TOOLS, TF_TOOLS, TOOLS, WATSONX_TOOLS
from lm_mcp.resources.guides import TOOL_CATEGORIES

DOC = Path(__file__).parent.parent / "documentation" / "tools.md"
# Hand-written usage prose that is not derivable from the registry. Kept as a fixture (data,
# not code) so it renders verbatim; edit it, then regenerate the doc.
APPENDIX = Path(__file__).parent / "fixtures" / "tools_usage_appendix.md"

# Short, scannable headings per category key. The full TOOL_CATEGORIES description renders as a
# subtitle line below each heading. Unmapped keys fall back to a title-cased key.
_TITLES = {
    "workflows": "Composite Workflows",
    "universal_reference": "Universal Reference",
    "discovery": "Discovery",
    "devices": "Devices",
    "alerts": "Alerts",
    "alert_rules": "Alert Rules",
    "sdts": "Scheduled Downtime (SDT)",
    "collectors": "Collectors",
    "networking": "Networking",
    "datasources": "DataSources",
    "dashboards": "Dashboards",
    "websites": "Websites",
    "reports": "Reports",
    "escalations": "Escalations",
    "integrations": "Integrations",
    "users": "Users and Access",
    "topology": "Topology",
    "audit": "Audit",
    "cost": "Cost Optimization",
    "logimodules": "LogicModules",
    "netscans": "Netscans",
    "ops": "Ops, OIDs, and Services",
    "batchjobs": "Batch Jobs",
    "exports": "Exports",
    "imports": "Imports",
    "ingestion": "Ingestion",
    "otlp_metrics": "OTLP Metrics",
    "correlation": "Correlation and Anomalies",
    "traces": "APM Traces",
    "ml_analysis": "ML and Statistical Analysis",
    "session": "Session and Baselines",
    "ansible": "Ansible Automation Platform",
    "terraform": "Terraform",
    "remediation": "Remediation",
    "watsonx": "IBM watsonx.ai",
}


def _tool_index() -> dict:
    """Map tool name -> Tool across the full advertisable surface (core plus conditionals)."""
    index: dict = {}
    for tool in [*TOOLS, *AWX_TOOLS, *WATSONX_TOOLS, *TF_TOOLS]:
        index[tool.name] = tool
    return index


def _cell(text: str) -> str:
    """Collapse whitespace and escape pipes so a description is a safe single table cell."""
    return " ".join((text or "").split()).replace("|", "\\|")


def render_tools_doc() -> str:
    """Render tools.md from TOOL_CATEGORIES (order/grouping) and the registry (content)."""
    index = _tool_index()
    total = len(index)

    lines: list[str] = [
        "# LogicMonitor MCP Server: Tool Reference",
        "",
        "<!-- GENERATED FILE. Do not edit by hand. "
        "Regenerate: uv run python tests/test_tools_doc.py -->",
        "",
        f"Reference for all {total} tools the LogicMonitor MCP server can advertise (core plus "
        "the optional Ansible Automation Platform, Terraform, and IBM watsonx.ai integrations). "
        "The **Write** column shows whether a tool requires `LM_ENABLE_WRITE_OPERATIONS=true`.",
        "",
        "This file is generated from the tool registry (`src/lm_mcp/registry.py`) and the domain "
        "index (`lm://guide/tool-categories`), and kept in sync by `tests/test_tools_doc.py`. At "
        "runtime, discover tools with the `search_tools` tool.",
        "",
        "Back to the [README](../README.md).",
        "",
    ]

    for key, category in TOOL_CATEGORIES["categories"].items():
        lines.append(f"## {_TITLES.get(key, key.replace('_', ' ').title())}")
        lines.append("")
        lines.append(category["description"])
        lines.append("")
        lines.append("| Tool | Description | Write |")
        lines.append("|------|-------------|-------|")
        for name in category["tools"]:
            tool = index.get(name)
            description = _cell(tool.description if tool is not None else "")
            write = "Yes" if is_write_tool(name) else "No"
            lines.append(f"| `{name}` | {description} | {write} |")
        lines.append("")

    body = "\n".join(lines).rstrip()
    appendix = APPENDIX.read_text(encoding="utf-8").strip()
    return body + "\n\n" + appendix + "\n"


def test_every_tool_is_categorized() -> None:
    """Every advertisable tool appears in TOOL_CATEGORIES, and every listed tool exists.

    A new tool added to the registry without a TOOL_CATEGORIES entry fails here, which forces
    it to be categorized (and therefore documented) before it can ship.
    """
    registered = set(_tool_index())
    listed = [name for cat in TOOL_CATEGORIES["categories"].values() for name in cat["tools"]]
    listed_set = set(listed)

    missing = sorted(registered - listed_set)
    stale = sorted(listed_set - registered)
    assert not missing, f"tools in the registry but missing from TOOL_CATEGORIES: {missing}"
    assert not stale, f"tools in TOOL_CATEGORIES but not in the registry: {stale}"

    dupes = sorted({n for n in listed if listed.count(n) > 1})
    assert not dupes, f"tools listed in more than one TOOL_CATEGORIES category: {dupes}"


def test_tools_doc_in_sync() -> None:
    """documentation/tools.md matches what the registry would generate.

    Any added/removed tool, renamed tool, changed description, recategorization, or flipped
    write gate fails this test. If the change is intentional, regenerate with:
        uv run python tests/test_tools_doc.py
    """
    expected = render_tools_doc()
    actual = DOC.read_text(encoding="utf-8")
    assert actual == expected, (
        "documentation/tools.md is out of sync with the tool registry. "
        "Regenerate: uv run python tests/test_tools_doc.py"
    )


if __name__ == "__main__":
    DOC.write_text(render_tools_doc(), encoding="utf-8")
    print(f"wrote {DOC} ({len(render_tools_doc().splitlines())} lines, {len(_tool_index())} tools)")
