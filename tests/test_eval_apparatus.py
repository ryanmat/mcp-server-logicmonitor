# Description: Tests for evals/grade.py, the search_tools and skill-scenario grader, and setup.py.
# Description: Runs the grader end to end on small fixtures and checks its exit codes.

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx
import yaml

ROOT = Path(__file__).resolve().parent.parent
GRADER = ROOT / "evals" / "grade.py"
QUERIES = ROOT / "evals" / "search" / "queries.json"


def _grade(tmp_path: Path, entries: list[dict]) -> subprocess.CompletedProcess:
    """Run the grader as the Eval command runs it, on a fixture of entries."""
    fixture = tmp_path / "queries.json"
    fixture.write_text(json.dumps(entries))
    return subprocess.run(
        [sys.executable, str(GRADER), "--fixture", str(fixture)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )


def test_two_found_queries_pass_with_exit_0(tmp_path):
    """Each query's expected tool in the top three under both configs, nothing refused."""
    result = _grade(
        tmp_path,
        [
            {
                "query": "get_terraform_imports",
                "expected": "get_terraform_imports",
                "forbidden": [],
            },
            {"query": "get_reference", "expected": "get_reference", "forbidden": []},
        ],
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "read-only: 2 of 2 graded in the top 3 (2 needed), 0 refused" in result.stdout
    assert "write-enabled: 2 of 2 graded in the top 3 (2 needed), 0 refused" in result.stdout
    assert result.stdout.count("HIT") == 4


def test_a_missed_query_fails_with_a_nonzero_exit(tmp_path):
    """Two graded queries need both found: one miss fails the run with a nonzero exit."""
    result = _grade(
        tmp_path,
        [
            {
                "query": "get_terraform_imports",
                "expected": "get_terraform_imports",
                "forbidden": [],
            },
            {"query": "zzzz qqqq", "expected": "get_devices", "forbidden": []},
        ],
    )

    assert result.returncode == 1
    assert "read-only: 1 of 2 graded in the top 3 (2 needed), 0 refused" in result.stdout
    assert "MISS" in result.stdout


def test_a_forbidden_tool_in_the_top_three_is_a_miss(tmp_path):
    """A query passes only when no tool it forbids ranks in the top three."""
    result = _grade(
        tmp_path,
        [{"query": "triage", "expected": "triage", "forbidden": ["triage"]}],
    )

    assert result.returncode == 1
    assert "read-only: 0 of 1 graded in the top 3 (1 needed), 0 refused" in result.stdout


def test_a_pending_query_is_skipped_until_its_tool_exists(tmp_path):
    """A Phase C query names a tool the registry lacks: it is listed and not graded."""
    result = _grade(
        tmp_path,
        [
            {"query": "get_reference", "expected": "get_reference", "forbidden": []},
            {"query": "zzzz", "expected": "search_logs", "forbidden": [], "pending": True},
        ],
    )

    assert result.returncode == 0, result.stdout
    assert "PENDING" in result.stdout
    assert "read-only: 1 of 1 graded in the top 3 (1 needed), 0 refused" in result.stdout


def test_a_write_tool_is_not_graded_where_the_config_refuses_it(tmp_path):
    """Writes off, create_sdt is not offered: n/a there, graded with writes on."""
    result = _grade(
        tmp_path,
        [{"query": "create_sdt", "expected": "create_sdt", "forbidden": []}],
    )

    assert "read-only: 0 of 0 graded" in result.stdout
    assert "write-enabled: 1 of 1 graded in the top 3 (1 needed)" in result.stdout


def test_an_unregistered_tool_that_is_not_pending_is_a_fixture_error(tmp_path):
    """A typo in the fixture stops the grade with exit 2 instead of counting a miss."""
    result = _grade(tmp_path, [{"query": "x", "expected": "get_devicez", "forbidden": []}])

    assert result.returncode == 2
    assert "get_devicez" in result.stderr


@pytest.mark.parametrize("field", ["query", "expected", "forbidden"])
def test_the_search_fixture_has_53_complete_entries(field):
    """R7.1: the forty queries, less search_logs (dropped by ruling), and one query for each
    Phase C family; each names its query, expected tool and forbidden tools."""
    entries = json.loads(QUERIES.read_text())

    assert len(entries) == 53
    assert all(field in entry for entry in entries)


def test_the_search_fixture_names_registered_tools_and_holds_no_pending_entry():
    """Phase C exit: every expected and forbidden tool is registered, and no entry waits on a
    tool to be built."""
    from lm_mcp.registry import TOOLS

    registered = {tool.name for tool in TOOLS}
    entries = json.loads(QUERIES.read_text())

    assert [e["expected"] for e in entries if e["expected"] not in registered] == []
    assert [name for e in entries for name in e["forbidden"] if name not in registered] == []
    assert [e["query"] for e in entries if "pending" in e] == []


def test_ci_grades_the_search_eval():
    """R7.1: a CI leg runs the grader on the committed fixture, so a ranking regression fails CI."""
    job = yaml.safe_load((ROOT / ".github" / "workflows" / "test.yml").read_text())["jobs"]["test"]
    versions = job["strategy"]["matrix"]["python-version"]
    legs = {None} | {f"matrix.python-version == '{version}'" for version in versions}

    (step,) = [s for s in job["steps"] if s.get("run") == "uv run python evals/grade.py"]
    assert step.get("if") in legs


# --- Skill scenarios (R7.2) ---

SKILLS = ROOT / "evals" / "skills"
SKILL_NAMES = sorted(path.name for path in (ROOT / ".claude" / "skills").iterdir())
RUBRIC_ITEMS = ("answers_question", "cites_evidence", "states_unchecked")
ANSWER = "CPU is at 12 percent on web-01 (health_check). I did not check memory or disk."
SCENARIO = {
    "skill": "lm-health",
    "user": "/lm-health 89818",
    "state": "Device 89818 exists.",
    "setup": False,
    "required_tools": ["health_check", "get_device_properties"],
    "forbidden_tools": ["restart_collector"],
    "rubric": {item: f"The answer meets {item}." for item in RUBRIC_ITEMS},
}


def _transcript(calls: list[str], answer: str = ANSWER) -> str:
    """A `claude -p --output-format stream-json` transcript: the row and block shapes of a
    live run (2026-11-13), one tool call and its result per name, then the answer."""
    rows: list[dict] = [{"type": "system", "subtype": "init", "model": "claude-fable-5-2"}]
    for number, name in enumerate(calls):
        tool_id = f"toolu_{number:02d}"
        call = {
            "type": "tool_use",
            "id": tool_id,
            "name": f"mcp__logicmonitor__{name}",
            "input": {},
            "caller": {"type": "direct"},
        }
        result = {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": [{"type": "text", "text": '{"total": 14}'}],
        }
        rows.append({"type": "assistant", "message": {"role": "assistant", "content": [call]}})
        rows.append({"type": "user", "message": {"role": "user", "content": [result]}})
    text = {"type": "text", "text": answer}
    rows.append({"type": "assistant", "message": {"role": "assistant", "content": [text]}})
    rows.append({"type": "result", "subtype": "success", "is_error": False, "result": answer})
    return "".join(json.dumps(row) + "\n" for row in rows)


def _verdict(transcript: str, rubric: dict, unmet: tuple[str, ...] = ()) -> dict:
    """The verdict record the grader keeps beside a transcript, keyed on what it judged."""
    graded = transcript.encode() + json.dumps(rubric, sort_keys=True).encode()
    return {
        "judge": "claude-opus-5",
        "graded_sha256": hashlib.sha256(graded).hexdigest(),
        "items": {item: {"met": item not in unmet, "reason": "r"} for item in rubric},
    }


def _skills(
    tmp_path: Path,
    calls: list[str] | None,
    *,
    unmet: tuple[str, ...] = (),
    judged: bool = True,
    scenario: dict = SCENARIO,
    name: str = "lm-health",
) -> Path:
    """A skills directory holding one scenario and, with calls given, its transcript."""
    skill = tmp_path / "skills" / name
    (skill / "runs").mkdir(parents=True, exist_ok=True)
    (skill / "scenario-1.json").write_text(json.dumps(scenario))
    if calls is not None:
        transcript = _transcript(calls)
        (skill / "runs" / "scenario-1.jsonl").write_text(transcript)
        if judged:
            verdict = _verdict(transcript, scenario["rubric"], unmet)
            (skill / "runs" / "scenario-1.verdict.json").write_text(json.dumps(verdict))
    return tmp_path / "skills"


def _grade_skills(
    tmp_path: Path, skills: Path, *args: str, env: dict | None = None
) -> subprocess.CompletedProcess:
    """Run the grader on a skills directory, with a one-query search fixture beside it."""
    fixture = tmp_path / "queries.json"
    fixture.write_text(
        json.dumps([{"query": "get_reference", "expected": "get_reference", "forbidden": []}])
    )
    return subprocess.run(
        [sys.executable, str(GRADER), "--fixture", str(fixture), "--skills", str(skills), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        env=env,
    )


def test_the_committed_scenarios_pass_with_no_transcripts():
    """Step 88's completion: sixteen scenarios, none run, each skipped with a note, exit 0."""
    result = subprocess.run(
        [sys.executable, str(GRADER)], capture_output=True, text=True, cwd=ROOT, timeout=120
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("SKIPPED") == 16
    assert "lm-triage/scenario-1: no transcript" in result.stdout
    assert "skills: 0 of 16 scenarios graded, 16 skipped" in result.stdout


def test_a_transcript_with_its_required_tools_and_a_recorded_verdict_passes(tmp_path):
    """A stream-json transcript that called both required tools, judged met on all items."""
    skills = _skills(tmp_path, ["health_check", "get_device_properties", "get_devices"])

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS    lm-health/scenario-1: tools ok; rubric 3 of 3" in result.stdout
    assert "skills: 1 of 1 scenarios graded, 0 skipped" in result.stdout
    assert "states_unchecked 1 of 1 (1 needed)" in result.stdout


def test_a_missing_required_tool_fails_the_run(tmp_path):
    """R7.2: every required tool appears in every scenario."""
    skills = _skills(tmp_path, ["health_check"])

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == 1
    assert "FAIL    lm-health/scenario-1: missing get_device_properties" in result.stdout


def test_a_forbidden_tool_fails_the_run(tmp_path):
    """A registered tool the scenario forbids, called beside the required ones."""
    skills = _skills(tmp_path, ["health_check", "get_device_properties", "restart_collector"])

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == 1
    assert "forbidden restart_collector" in result.stdout


def test_a_removed_or_renamed_tool_fails_the_run_without_being_listed(tmp_path):
    """R7.2: no scenario calls a removed or renamed tool. Every such name is absent from the
    registry (tests/test_changelog_names.py), so the grader refuses any unregistered call."""
    skills = _skills(tmp_path, ["health_check", "get_device_properties", "get_trace_services"])

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == 1
    assert "not in the 5.0 registry: get_trace_services" in result.stdout


@pytest.mark.parametrize("stale", [False, True])
def test_a_transcript_with_no_current_verdict_fails_until_it_is_judged(tmp_path, stale):
    """A plain run calls no model: prose with no verdict, or one recorded for an earlier
    transcript, is ungraded and fails."""
    skills = _skills(tmp_path, ["health_check", "get_device_properties"], judged=stale)
    if stale:
        with (skills / "lm-health" / "runs" / "scenario-1.jsonl").open("a") as transcript:
            transcript.write(json.dumps({"type": "system", "subtype": "hook_started"}) + "\n")

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == 1
    assert "prose not judged (run with --judge)" in result.stdout


def test_the_unchecked_item_unmet_in_one_scenario_fails_the_run(tmp_path):
    """Step 89's threshold: no scenario fails the "states what it did not check" item."""
    for number in range(8):
        unmet = ("states_unchecked",) if number == 0 else ()
        skills = _skills(
            tmp_path, ["health_check", "get_device_properties"], unmet=unmet, name=f"s{number}"
        )

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == 1
    assert "states_unchecked 7 of 8 (8 needed)" in result.stdout


@pytest.mark.parametrize(("failing", "code"), [(1, 0), (2, 1)])
def test_another_item_passes_at_14_of_16_of_the_graded_scenarios(tmp_path, failing, code):
    """Step 89's threshold, 14 of 16, scaled to the scenarios graded: 7 of 8 here."""
    for number in range(8):
        unmet = ("cites_evidence",) if number < failing else ()
        skills = _skills(
            tmp_path, ["health_check", "get_device_properties"], unmet=unmet, name=f"s{number}"
        )

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == code, result.stdout
    assert math.ceil(14 / 16 * 8) == 7
    assert f"cites_evidence {8 - failing} of 8 (7 needed)" in result.stdout


def test_a_scenario_naming_an_unregistered_tool_is_a_fixture_error(tmp_path):
    """A typo in required_tools stops the grade with exit 2, transcript or not."""
    scenario = SCENARIO | {"required_tools": ["health_chek"]}
    skills = _skills(tmp_path, None, scenario=scenario)

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == 2
    assert "health_chek" in result.stderr


def test_a_session_transcript_is_read_like_a_stream_json_one(tmp_path):
    """A session file from ~/.claude/projects has no result row and repeats each request in
    api-request-blob rows: the answer is the text after the last tool call, and only
    assistant rows count as calls."""
    skills = _skills(tmp_path, ["health_check", "get_device_properties"], judged=False)
    path = skills / "lm-health" / "runs" / "scenario-1.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    blob = {
        "type": "api-request-blob",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t", "name": "mcp__logicmonitor__get_trace_services"}
            ],
        },
    }
    transcript = "".join(json.dumps(row) + "\n" for row in [*rows[:-1], blob])
    path.write_text(transcript)
    verdict = _verdict(transcript, SCENARIO["rubric"])
    (path.parent / "scenario-1.verdict.json").write_text(json.dumps(verdict))

    result = _grade_skills(tmp_path, skills)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS    lm-health/scenario-1: tools ok; rubric 3 of 3" in result.stdout


# --- The judge: `claude -p` on claude-opus-5, called only under --judge ---


def _fake_claude(tmp_path: Path, output: dict, exit_code: int = 0) -> dict:
    """Put a `claude` on PATH that logs its argv and stdin and prints output: the keys of a
    live `claude -p --output-format json --json-schema` result (2026-11-13)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "log = {'argv': sys.argv[1:], 'stdin': sys.stdin.read()}\n"
        "open(os.environ['FAKE_CLAUDE_LOG'], 'w').write(json.dumps(log))\n"
        "print(os.environ['FAKE_CLAUDE_OUT'])\n"
        "sys.exit(int(os.environ['FAKE_CLAUDE_EXIT']))\n"
    )
    script.chmod(0o755)
    return os.environ | {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_CLAUDE_LOG": str(tmp_path / "claude-call.json"),
        "FAKE_CLAUDE_OUT": json.dumps(output),
        "FAKE_CLAUDE_EXIT": str(exit_code),
    }


def _judge_output(model: str = "claude-opus-5", **changes: object) -> dict:
    items = {item: {"met": True, "reason": "The answer shows it."} for item in RUBRIC_ITEMS}
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(items),
        "structured_output": items,
        "modelUsage": {model: {"inputTokens": 2, "outputTokens": 417, "costUSD": 0.0224}},
        "total_cost_usd": 0.0224,
    } | changes


def test_the_judge_flag_asks_claude_opus_5_and_records_the_verdict(tmp_path):
    """--judge sends the user line, the tool results, the answer and the rubric to
    `claude -p --model claude-opus-5` under a JSON schema, and keeps the verdict."""
    skills = _skills(tmp_path, ["health_check", "get_device_properties"], judged=False)
    env = _fake_claude(tmp_path, _judge_output())

    result = _grade_skills(tmp_path, skills, "--judge", env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    call = json.loads((tmp_path / "claude-call.json").read_text())
    argv = call["argv"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert sorted(schema["required"]) == sorted(RUBRIC_ITEMS)
    assert argv[argv.index("--output-format") + 1] == "json"
    for sent in ("/lm-health 89818", ANSWER, '{"total": 14}', "The answer meets cites_evidence."):
        assert sent in call["stdin"]
    transcript = (skills / "lm-health" / "runs" / "scenario-1.jsonl").read_text()
    recorded = json.loads((skills / "lm-health" / "runs" / "scenario-1.verdict.json").read_text())
    assert recorded == _verdict(transcript, SCENARIO["rubric"]) | {"items": recorded["items"]}
    assert recorded["items"]["states_unchecked"] == {"met": True, "reason": "The answer shows it."}
    assert _grade_skills(tmp_path, skills).returncode == 0


@pytest.mark.parametrize(
    ("output", "exit_code", "message"),
    [
        (_judge_output(is_error=True), 0, "the judge reported an error"),
        (_judge_output(model="claude-sonnet-5-5"), 0, "ran on claude-sonnet-5-5"),
        (_judge_output(structured_output={"answers_question": {"met": True}}), 0, "verdict"),
        (_judge_output(), 1, "exit 1"),
    ],
)
def test_a_judge_that_fails_is_an_apparatus_error(tmp_path, output, exit_code, message):
    """An error result, another model, an incomplete verdict or a nonzero exit: exit 2 and
    no verdict recorded."""
    skills = _skills(tmp_path, ["health_check", "get_device_properties"], judged=False)
    env = _fake_claude(tmp_path, output, exit_code)

    result = _grade_skills(tmp_path, skills, "--judge", env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert message in result.stderr
    assert not (skills / "lm-health" / "runs" / "scenario-1.verdict.json").exists()


def test_the_judge_flag_without_claude_on_path_is_an_apparatus_error(tmp_path):
    skills = _skills(tmp_path, ["health_check", "get_device_properties"], judged=False)
    (tmp_path / "empty").mkdir()

    result = _grade_skills(
        tmp_path, skills, "--judge", env=os.environ | {"PATH": str(tmp_path / "empty")}
    )

    assert result.returncode == 2
    assert "claude" in result.stderr


def test_the_judge_flag_leaves_a_current_verdict_alone(tmp_path):
    """A transcript already judged is not judged again: no call reaches claude."""
    skills = _skills(tmp_path, ["health_check", "get_device_properties"])
    env = _fake_claude(tmp_path, _judge_output())

    result = _grade_skills(tmp_path, skills, "--judge", env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "claude-call.json").exists()


# --- The committed scenario fixtures ---


def _allowed_tools(skill: str) -> set[str]:
    text = (ROOT / ".claude" / "skills" / skill / "SKILL.md").read_text()
    frontmatter = yaml.safe_load(text.split("---")[1])
    return {name.removeprefix("mcp__logicmonitor__") for name in frontmatter["allowed-tools"]}


@pytest.mark.parametrize("skill", SKILL_NAMES)
def test_each_skill_has_two_complete_scenarios(skill):
    """R7.2: the user line, the state, the required and forbidden tools and the rubric's
    three items; a required tool is one the skill may call, and is not also forbidden."""
    from lm_mcp.registry import TOOLS

    registered = {tool.name for tool in TOOLS}
    paths = sorted((SKILLS / skill).glob("scenario-*.json"))

    assert [path.name for path in paths] == ["scenario-1.json", "scenario-2.json"]
    for path in paths:
        scenario = json.loads(path.read_text())
        assert scenario["skill"] == skill
        assert scenario["user"].startswith(f"/{skill}")
        assert scenario["state"]
        assert isinstance(scenario["setup"], bool)
        assert tuple(scenario["rubric"]) == RUBRIC_ITEMS
        assert all(scenario["rubric"].values())
        required, forbidden = set(scenario["required_tools"]), set(scenario["forbidden_tools"])
        assert required
        assert required <= _allowed_tools(skill)
        assert forbidden <= registered
        assert not required & forbidden


def test_a_scenario_forbids_every_write_tool_its_skill_may_call():
    """The runs take no operator confirmation, so a write tool called in one is a failure."""
    from lm_mcp.registry import TOOLS
    from lm_mcp.server import writes_to_portal

    writes = {tool.name for tool in TOOLS if writes_to_portal(tool)}
    for path in sorted(SKILLS.glob("*/scenario-*.json")):
        scenario = json.loads(path.read_text())
        expected = _allowed_tools(scenario["skill"]) & writes
        assert expected <= set(scenario["forbidden_tools"]), path


# --- evals/skills/setup.py ---

_API = "https://lmryanmatuszewski.logicmonitor.com/santaba/rest"


def _setup_module():
    spec = importlib.util.spec_from_file_location("skill_eval_setup", SKILLS / "setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sandbox_client(monkeypatch):
    """The client production builds, for the sandbox host and a placeholder token."""
    from lm_mcp.client import build_client
    from lm_mcp.config import reset_config

    monkeypatch.setenv("LM_PORTAL", "lmryanmatuszewski.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "lmb_test_token")
    reset_config()
    yield build_client(
        "lmryanmatuszewski.logicmonitor.com",
        bearer_token="lmb_test_token",
        access_id=None,
        access_key=None,
    )
    reset_config()


@respx.mock
async def test_setup_creates_the_eval_device_when_the_portal_has_none(sandbox_client):
    setup = _setup_module()
    listing = respx.get(f"{_API}/device/devices").mock(
        return_value=httpx.Response(200, json={"total": 0, "items": []})
    )
    created = respx.post(f"{_API}/device/devices").mock(
        return_value=httpx.Response(200, json={"id": 715051, "displayName": setup.DEVICE_NAME})
    )

    async with sandbox_client:
        line = await setup.ensure_state(sandbox_client)

    assert listing.calls.last.request.url.params["filter"] == f'displayName:"{setup.DEVICE_NAME}"'
    body = json.loads(created.calls.last.request.content)
    assert body["displayName"] == setup.DEVICE_NAME == "lm-mcp-eval-host"
    assert body["name"] == "192.0.2.10"
    assert body["preferredCollectorId"] == setup.COLLECTOR_ID
    assert line == "created lm-mcp-eval-host (id 715051)"


@respx.mock
async def test_setup_run_again_creates_nothing(sandbox_client):
    setup = _setup_module()
    respx.get(f"{_API}/device/devices").mock(
        return_value=httpx.Response(
            200, json={"total": 1, "items": [{"id": 715051, "displayName": setup.DEVICE_NAME}]}
        )
    )
    created = respx.post(f"{_API}/device/devices").mock(return_value=httpx.Response(200, json={}))

    async with sandbox_client:
        line = await setup.ensure_state(sandbox_client)

    assert not created.called
    assert line == "found lm-mcp-eval-host (id 715051)"


def test_setup_refuses_a_portal_that_is_not_the_sandbox():
    """Sandbox only: with LM_PORTAL naming another portal the script stops before any request."""
    env = os.environ | {"LM_PORTAL": "acme.logicmonitor.com", "LM_BEARER_TOKEN": "lmb_test_token"}

    result = subprocess.run(
        [sys.executable, str(SKILLS / "setup.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        env=env,
    )

    assert result.returncode == 2
    assert "refusing to run against acme.logicmonitor.com" in result.stderr
