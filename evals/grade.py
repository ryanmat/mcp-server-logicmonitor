# Description: Grades search_tools on evals/search/queries.json and skill runs under evals/skills.
# Description: Exit 0 when both search configs pass and every skill transcript present passes.

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FIXTURE = Path(__file__).resolve().parent / "search" / "queries.json"
SKILLS = Path(__file__).resolve().parent / "skills"

# A query's expected tool must rank within the first TOP results, in PASS_RATE of the
# queries a config grades.
TOP = 3
PASS_RATE = 0.9

# The two configs graded: the default surface, with the write gate off and on.
CONFIGS = {"read-only": "false", "write-enabled": "true"}

# A skill run's transcript is graded on the logicmonitor tools it called, by this prefix.
TOOL_PREFIX = "mcp__logicmonitor__"

# The model that judges a transcript's prose against its scenario's rubric: Claude Opus 5,
# the cost-efficient tier. It runs through `claude -p` on the Claude Code login, and only
# under --judge; a plain run reads the verdicts recorded beside the transcripts.
JUDGE_MODEL = "claude-opus-5"
JUDGE_SYSTEM = (
    "You grade the final answer an AI assistant gave after it ran a LogicMonitor runbook. "
    "Judge each rubric item from the answer and the tool results alone. An item is met only "
    "when the answer itself shows it; a claim the tool results do not carry is not evidence. "
    "Give one sentence of reason for each item."
)

# A rubric item must be met in RUBRIC_PASS_RATE of the graded scenarios (14 of 16 when all
# are run), and STRICT_ITEM in every one.
RUBRIC_PASS_RATE = 14 / 16
STRICT_ITEM = "states_unchecked"


class FixtureError(Exception):
    """A scenario or transcript the grader cannot read as one."""


class JudgeError(Exception):
    """The judge did not return a verdict from JUDGE_MODEL."""


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


def _read_transcript(path: Path) -> tuple[set[str], str, list[str]]:
    """A Claude Code transcript's logicmonitor calls, final answer and tool results.

    Reads `claude -p --output-format stream-json` output and session files alike: both
    carry the conversation as assistant and user rows of content blocks. The answer is the
    result row's text, or without one the assistant text after the last tool call.
    """
    called: dict[str, str] = {}
    evidence: list[str] = []
    texts: list[str] = []
    final: str | None = None
    try:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("type") == "result":
                final = row.get("result")
            if row.get("type") not in ("assistant", "user"):
                continue
            content = row["message"]["content"]
            for block in content if isinstance(content, list) else []:
                if row["type"] == "assistant" and block["type"] == "tool_use":
                    texts = []
                    if block["name"].startswith(TOOL_PREFIX):
                        called[block["id"]] = block["name"].removeprefix(TOOL_PREFIX)
                elif row["type"] == "assistant" and block["type"] == "text":
                    texts.append(block["text"])
                elif block["type"] == "tool_result" and block["tool_use_id"] in called:
                    body = block["content"]
                    if not isinstance(body, str):
                        body = "\n".join(part.get("text", "") for part in body)
                    evidence.append(f"{called[block['tool_use_id']]} returned:\n{body}")
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
        raise FixtureError(f"{path}: not a Claude Code transcript ({error!r})") from error
    return set(called.values()), "\n".join(texts) if final is None else final, evidence


def _judge(scenario: dict, answer: str, evidence: list[str]) -> dict[str, dict]:
    """Ask JUDGE_MODEL whether the answer meets each rubric item: {item: {met, reason}}."""
    claude = shutil.which("claude")
    if claude is None:
        raise JudgeError("--judge runs the judge through `claude -p`; no claude is on PATH")
    rubric = scenario["rubric"]
    item = {
        "type": "object",
        "properties": {"met": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["met", "reason"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": dict.fromkeys(rubric, item),
        "required": list(rubric),
        "additionalProperties": False,
    }
    prompt = "\n\n".join(
        [
            f"The user asked:\n{scenario['user']}",
            f"The portal state the request assumed:\n{scenario['state']}",
            "The tool results the assistant received:\n" + ("\n\n".join(evidence) or "(none)"),
            f"The assistant's final answer:\n{answer}",
            "The rubric items:\n" + "\n".join(f"- {name}: {text}" for name, text in rubric.items()),
        ]
    )
    command = [claude, "-p", "--model", JUDGE_MODEL, "--output-format", "json"]
    command += ["--json-schema", json.dumps(schema), "--system-prompt", JUDGE_SYSTEM]
    command += ["--tools", "", "--safe-mode", "--strict-mcp-config", "--no-session-persistence"]
    run = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=600)
    if run.returncode != 0:
        raise JudgeError(f"claude -p ended with exit {run.returncode}: {run.stderr.strip()[-300:]}")
    try:
        output = json.loads(run.stdout)
    except json.JSONDecodeError as error:
        raise JudgeError(f"claude -p printed no JSON result: {run.stdout[:300]!r}") from error
    if output.get("is_error") or output.get("subtype") != "success":
        raise JudgeError(f"the judge reported an error: {output.get('result')}")
    models = sorted(output.get("modelUsage") or {})
    if JUDGE_MODEL not in models:
        raise JudgeError(f"the judge ran on {', '.join(models) or 'no model'}, not {JUDGE_MODEL}")
    items = output.get("structured_output")
    complete = isinstance(items, dict) and all(
        isinstance(items.get(name), dict)
        and isinstance(items[name].get("met"), bool)
        and isinstance(items[name].get("reason"), str)
        for name in rubric
    )
    if not complete:
        raise JudgeError(f"the judge returned no verdict for every rubric item: {items!r}")
    return {name: {"met": items[name]["met"], "reason": items[name]["reason"]} for name in rubric}


def _prose_verdict(transcript: Path, scenario: dict, judge: bool) -> dict[str, dict] | None:
    """The recorded verdict for this transcript and rubric; with judge set, a missing or
    stale one is asked of the judge and recorded. None when the prose stays unjudged."""
    record = transcript.with_suffix(".verdict.json")
    rubric = json.dumps(scenario["rubric"], sort_keys=True).encode()
    key = hashlib.sha256(transcript.read_bytes() + rubric).hexdigest()
    if record.exists():
        kept = json.loads(record.read_text())
        if kept.get("graded_sha256") == key and kept.get("judge") == JUDGE_MODEL:
            return kept["items"]
    if not judge:
        return None
    _, answer, evidence = _read_transcript(transcript)
    items = _judge(scenario, answer, evidence)
    verdict = {"judge": JUDGE_MODEL, "graded_sha256": key, "items": items}
    record.write_text(json.dumps(verdict, indent=2) + "\n")
    return items


def _grade_skills(root: Path, registered: set[str], judge: bool) -> bool:
    """Print one line per scenario under root and the summary; return whether they pass.

    A scenario with no transcript at runs/<scenario>.jsonl is skipped. One with a transcript
    passes its tool check when every required tool was called and no forbidden or
    unregistered one was; a tool 5.0 removed or renamed is unregistered.
    """
    scenarios = []
    for path in sorted(root.glob("*/scenario-*.json")):
        scenario = json.loads(path.read_text())
        named = set(scenario["required_tools"]) | set(scenario["forbidden_tools"])
        if named - registered:
            unknown = ", ".join(sorted(named - registered))
            raise FixtureError(f"{path}: tools the registry does not hold: {unknown}")
        scenarios.append((path, scenario))

    graded = failed = 0
    met: dict[str, int] = {}
    for path, scenario in scenarios:
        label = f"{path.parent.name}/{path.stem}"
        transcript = path.parent / "runs" / f"{path.stem}.jsonl"
        if not transcript.exists():
            print(f"{'skills':<13} {'SKIPPED':<7} {label}: no transcript")
            continue
        graded += 1
        called, _, _ = _read_transcript(transcript)
        problems = []
        if missing := sorted(set(scenario["required_tools"]) - called):
            problems.append(f"missing {', '.join(missing)}")
        if forbidden := sorted(set(scenario["forbidden_tools"]) & called):
            problems.append(f"forbidden {', '.join(forbidden)}")
        if unregistered := sorted(called - registered):
            problems.append(f"not in the 5.0 registry: {', '.join(unregistered)}")
        items = _prose_verdict(transcript, scenario, judge)
        for name in scenario["rubric"]:
            met[name] = met.get(name, 0) + bool(items and items[name]["met"])
        if items is None:
            prose = "prose not judged (run with --judge)"
        else:
            unmet = [name for name in items if not items[name]["met"]]
            prose = f"rubric {len(items) - len(unmet)} of {len(items)}"
            prose += f" (unmet: {', '.join(unmet)})" if unmet else ""
        bad = bool(problems) or items is None
        failed += bad
        tools = "; ".join(problems) or "tools ok"
        print(f"{'skills':<13} {'FAIL' if bad else 'PASS':<7} {label}: {tools}; {prose}")

    skipped = len(scenarios) - graded
    print(f"skills: {graded} of {len(scenarios)} scenarios graded, {skipped} skipped")
    needed = {
        name: graded if name == STRICT_ITEM else math.ceil(RUBRIC_PASS_RATE * graded)
        for name in met
    }
    if met:
        counts = [f"{name} {met[name]} of {graded} ({needed[name]} needed)" for name in met]
        print(f"skills: {', '.join(counts)}")
    return failed == 0 and all(met[name] >= needed[name] for name in met)


def main(argv: list[str] | None = None) -> int:
    """Grade the search fixture under each config, then the skill scenarios.

    0 all pass, 1 a threshold or a scenario fails, 2 a bad fixture or a judge that failed.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--skills", type=Path, default=SKILLS)
    parser.add_argument(
        "--judge",
        action="store_true",
        help=f"ask {JUDGE_MODEL} to judge transcripts that have no current verdict",
    )
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
    try:
        passed.append(_grade_skills(args.skills, registered, args.judge))
    except (FixtureError, JudgeError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0 if all(passed) else 1


if __name__ == "__main__":
    sys.exit(main())
