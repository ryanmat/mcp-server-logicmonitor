# Description: Grades search_tools against evals/search/queries.json under two configs.
# Description: Exit 0 when each config ranks 90 percent of its graded queries and refuses none.

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FIXTURE = Path(__file__).resolve().parent / "search" / "queries.json"

# A query's expected tool must rank within the first TOP results, in PASS_RATE of the
# queries a config grades.
TOP = 3
PASS_RATE = 0.9

# The two configs graded: the default surface, with the write gate off and on.
CONFIGS = {"read-only": "false", "write-enabled": "true"}

# Settings that would change the surface from the default; the grade clears them.
_FILTER_SETTINGS = (
    "LM_ENABLED_TOOLS",
    "LM_DISABLED_TOOLS",
    "LM_MCP_CATEGORIES",
    "LM_MULTI_PORTAL",
)


def _use_config(writes: str) -> set[str]:
    """Point the server's config at one graded config; return the tools it offers."""
    from lm_mcp.config import get_config, reset_config
    from lm_mcp.server import _filter_tools, collect_tools

    for name in _FILTER_SETTINGS:
        os.environ.pop(name, None)
    os.environ["LM_PORTAL"] = "eval.logicmonitor.com"
    os.environ["LM_BEARER_TOKEN"] = "eval-placeholder-token"
    os.environ["LM_ENABLE_WRITE_OPERATIONS"] = writes
    reset_config()
    return {tool.name for tool in _filter_tools(collect_tools(), get_config())}


async def _search(query: str) -> list[str]:
    """The names search_tools returns for a query, best first."""
    from lm_mcp.tools.workflows import search_tools

    result = await search_tools(None, query=query)
    return [match["name"] for match in json.loads(result[0].text)["matches"]]


def _grade_config(name: str, writes: str, entries: list[dict], registered: set[str]) -> bool:
    """Print one config's table and summary line; return whether it passes."""
    offered = _use_config(writes)
    hits = graded = refused = 0
    for entry in entries:
        expected = entry["expected"]
        results = asyncio.run(_search(entry["query"]))
        top = results[:TOP]
        refused_here = [tool for tool in results if tool not in offered]
        refused += len(refused_here)
        if expected not in registered:
            verdict = "PENDING"
        elif expected not in offered:
            verdict = "n/a"
        else:
            graded += 1
            hit = expected in top and not set(entry["forbidden"]) & set(top)
            hits += hit
            verdict = "HIT" if hit else "MISS"
        note = f"  refused: {', '.join(refused_here)}" if refused_here else ""
        print(f"{name:<13} {verdict:<7} {entry['query']!r} -> {expected}; top {top}{note}")
    needed = math.ceil(PASS_RATE * graded)
    print(
        f"{name}: {hits} of {graded} graded in the top {TOP} ({needed} needed), {refused} refused"
    )
    return hits >= needed and refused == 0


def main(argv: list[str] | None = None) -> int:
    """Grade the fixture under each config: 0 both pass, 1 one fails, 2 a bad fixture."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args(argv)

    from lm_mcp.registry import TOOLS

    registered = {tool.name for tool in TOOLS}
    entries = json.loads(args.fixture.read_text())
    unknown = [
        e["expected"] for e in entries if e["expected"] not in registered and not e.get("pending")
    ]
    if unknown:
        print(f"unregistered tools not marked pending: {', '.join(unknown)}", file=sys.stderr)
        return 2

    passed = [_grade_config(name, writes, entries, registered) for name, writes in CONFIGS.items()]
    return 0 if all(passed) else 1


if __name__ == "__main__":
    sys.exit(main())
