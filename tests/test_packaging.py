# Description: Tests for what the source distribution ships and for CI and pre-commit hygiene.
# Description: Builds a real sdist with uv and reads the workflow and hook config files.

from __future__ import annotations

import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
_SDIST_TOP_LEVEL = {"README.md", "LICENSE", "CHANGELOG.md", "pyproject.toml", "PKG-INFO"}
# Hatchling adds the root .gitignore to every sdist (its default build data force-includes
# each VCS ignore file), and no include or exclude option removes it.
_FORCED_BY_HATCHLING = {".gitignore"}


@pytest.fixture(scope="module")
def sdist_members(tmp_path_factory) -> list[str]:
    """Build the sdist from the working tree and return its member paths below the top folder."""
    uv = shutil.which("uv")
    assert uv, "uv is not on PATH"
    out = tmp_path_factory.mktemp("sdist")
    subprocess.run(
        [uv, "build", "--sdist", "--out-dir", str(out)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    (archive,) = out.glob("*.tar.gz")
    with tarfile.open(archive) as tar:
        names = [m.name for m in tar.getmembers() if m.isfile()]
    return [name.split("/", 1)[1] for name in names]


def test_sdist_holds_only_the_package_and_its_metadata(sdist_members):
    """R1.10: the sdist ships src/, the five metadata files and hatchling's .gitignore."""
    outside = sorted(
        path
        for path in sdist_members
        if not path.startswith("src/") and path not in _SDIST_TOP_LEVEL | _FORCED_BY_HATCHLING
    )

    assert outside == []
    assert "src/lm_mcp/server.py" in sdist_members
    assert set(sdist_members) >= _SDIST_TOP_LEVEL


def test_pre_commit_ruff_is_the_locked_ruff():
    """R1.10: the ruff hook runs the ruff version uv.lock pins, the one CI runs."""
    hooks = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text())
    (ruff_repo,) = [r for r in hooks["repos"] if r["repo"].endswith("/ruff-pre-commit")]
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text())
    (ruff,) = [p for p in lock["package"] if p["name"] == "ruff"]

    assert ruff_repo["rev"] == f"v{ruff['version']}"


def test_test_workflow_has_no_build_branch_and_no_dist_upload():
    """R1.10: test.yml runs on main and pull requests only, and uploads no dist artifact."""
    workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "test.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    steps = [step for job in workflow["jobs"].values() for step in job["steps"]]

    assert triggers["push"]["branches"] == ["main"]
    assert [s for s in steps if "upload-artifact" in s.get("uses", "")] == []
    assert [s for s in steps if (s.get("with") or {}).get("name") == "dist"] == []
