# Description: Holds the text under src/ and tests/ to what a reader of the repository can follow.
# Description: Nothing there cites a ruling id or a file the repository leaves out.

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".py", ".json", ".txt", ".md", ".yml", ".yaml", ".toml"}

# Each pattern is assembled from pieces so this file does not match itself.
UNFOLLOWABLE = {
    "a ruling id": re.compile("rul" + r"-[0-9a-f]{6,}"),
    "a path under the ignored docs directory": re.compile(r"\bdo" + "cs/"),
    "a probe record's file name": re.compile("probes" + r"-20\d\d-\d\d"),
    "a numbered item of an unpublished review": re.compile("the review" + ", item"),
}


def _tracked_text() -> list[Path]:
    return sorted(
        path
        for top in ("src", "tests")
        for path in (ROOT / top).rglob("*")
        if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts
    )


@pytest.mark.parametrize("what", sorted(UNFOLLOWABLE))
def test_src_and_tests_cite_nothing_a_reader_cannot_open(what: str) -> None:
    pattern = UNFOLLOWABLE[what]
    hits = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in _tracked_text()
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if pattern.search(line)
    ]

    assert hits == [], f"{what} in {len(hits)} lines"


def test_the_sweep_reads_both_trees() -> None:
    tops = {path.relative_to(ROOT).parts[0] for path in _tracked_text()}

    assert tops == {"src", "tests"}
