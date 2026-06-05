# Description: Annotation-driven tool category filtering for lm-mcp.
# Description: Maps tool annotations to logical categories for the LM_MCP_CATEGORIES env var.

from __future__ import annotations

from mcp.types import Tool

# Workflow is a curated frozenset, not annotation-derived, because composite
# tools share the _READ_ONLY annotation with simple gets and cannot be
# distinguished structurally.
WORKFLOW_TOOLS: frozenset[str] = frozenset(
    {
        "triage",
        "diagnose",
        "portal_overview",
        "health_check",
        "capacity_plan",
        "score_alert_noise",
        "score_device_health",
        "correlate_alerts",
        "correlate_changes",
        "correlate_metrics",
        "detect_change_points",
        "detect_seasonality",
        "calculate_availability",
        "calculate_error_budget",
        "classify_trend",
        "forecast_metric",
        "compare_to_baseline",
        "save_baseline",
        "analyze_blast_radius",
        "detect_site_outage",
        "audit_network_monitoring_coverage",
        "search_tools",
        "update_logicmodule",
    }
)

KNOWN_CATEGORIES: frozenset[str] = frozenset(
    {"read", "write", "delete", "export", "import", "session", "workflow"}
)


def categorize(tool: Tool) -> set[str]:
    """Return the set of logical categories a tool belongs to.

    Categories:
    - workflow: curated composite tools (triage, diagnose, ...)
    - export: tool name starts with "export_"
    - import: tool name starts with "import_"
    - read: read-only tool that talks to LM (openWorldHint=True)
    - write: mutating tool (not read-only, not destructive, not import/export)
    - delete: destructive tool
    - session: session-scoped tool (closed-world)

    A single tool may belong to multiple categories (e.g., triage is both
    "workflow" and "read"). Composition is by union here; filtering uses
    intersection at the call site.
    """
    annotations = tool.annotations
    cats: set[str] = set()

    if tool.name in WORKFLOW_TOOLS:
        cats.add("workflow")

    if tool.name.startswith("export_"):
        cats.add("export")
    elif tool.name.startswith("import_"):
        cats.add("import")

    if annotations is None:
        return cats

    if annotations.readOnlyHint and annotations.openWorldHint:
        cats.add("read")
    if annotations.destructiveHint:
        cats.add("delete")
    if not annotations.openWorldHint:
        cats.add("session")
    if (
        not annotations.readOnlyHint
        and not annotations.destructiveHint
        and annotations.openWorldHint
        and "import" not in cats
        and "export" not in cats
    ):
        cats.add("write")

    return cats


def filter_by_categories(tools: list[Tool], csv: str) -> tuple[list[Tool], list[str]]:
    """Filter tools by category CSV. Returns (filtered_tools, unknown_tokens).

    Tokens are case-insensitive. Unknown tokens are returned for caller logging
    but do not error — the caller decides how to surface them.

    If no valid categories are requested, the input list is returned unchanged
    (defensive: do not silently empty the surface on an all-typo input).
    """
    if not csv:
        return tools, []

    requested = {c.strip().lower() for c in csv.split(",") if c.strip()}
    unknown = sorted(requested - KNOWN_CATEGORIES)
    valid = requested & KNOWN_CATEGORIES

    if not valid:
        return tools, unknown

    filtered = [t for t in tools if categorize(t) & valid]
    return filtered, unknown


def tool_in_categories(tool_name: str, tools_index: dict[str, Tool], csv: str) -> bool:
    """Check whether a single named tool would survive the category filter."""
    if not csv:
        return True
    requested = {c.strip().lower() for c in csv.split(",") if c.strip()}
    valid = requested & KNOWN_CATEGORIES
    if not valid:
        return True
    tool = tools_index.get(tool_name)
    if tool is None:
        return True
    return bool(categorize(tool) & valid)
