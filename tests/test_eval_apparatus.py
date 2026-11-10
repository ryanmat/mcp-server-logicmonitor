# Description: Tests for the search_tools eval grader in evals/grade.py.
# Description: Runs the grader end to end on small fixtures and checks its exit codes.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
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
            {"query": "terraform_generate", "expected": "terraform_generate", "forbidden": []},
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
            {"query": "terraform_generate", "expected": "terraform_generate", "forbidden": []},
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
def test_the_search_fixture_has_forty_complete_entries(field):
    """R7.1: forty queries, each naming its query, expected tool and forbidden tools."""
    entries = json.loads(QUERIES.read_text())

    assert len(entries) == 40
    assert all(field in entry for entry in entries)


def test_ci_grades_the_search_eval():
    """R7.1: a CI leg runs the grader on the committed fixture, so a ranking regression fails CI."""
    job = yaml.safe_load((ROOT / ".github" / "workflows" / "test.yml").read_text())["jobs"]["test"]
    versions = job["strategy"]["matrix"]["python-version"]
    legs = {None} | {f"matrix.python-version == '{version}'" for version in versions}

    (step,) = [s for s in job["steps"] if s.get("run") == "uv run python evals/grade.py"]
    assert step.get("if") in legs
