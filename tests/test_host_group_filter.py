# Description: Guards the hostGroupIds filter form across src/lm_mcp and the resources.
# Description: hostGroupIds:N is list membership; hostGroupIds~N is a substring of the joined ids.

from __future__ import annotations

import re
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src" / "lm_mcp"

# tools/__init__.py records why alerts do not filter on this field; it sends nothing.
ALERTS_NOTE = SOURCE_ROOT / "tools" / "__init__.py"

SUBSTRING_FORM = re.compile(r"hostGroupIds\s*~")


def _source_files() -> list[Path]:
    return sorted(
        path
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _substring_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [line.strip() for line in lines if SUBSTRING_FORM.search(line)]


class TestPattern:
    """The guard's pattern catches every spelling of the form and nothing else."""

    @pytest.mark.parametrize(
        "text",
        ["hostGroupIds~5", 'f"hostGroupIds~{group_id}"', "hostGroupIds ~ 5", 'hostGroupIds~"5"'],
    )
    def test_matches_the_substring_form(self, text):
        assert SUBSTRING_FORM.search(text)

    @pytest.mark.parametrize(
        "text",
        ["hostGroupIds:5", "hostGroupIds", 'monitorObjectGroups~"a/b"', '"hostGroupIds": "1,2"'],
    )
    def test_leaves_other_text_alone(self, text):
        assert not SUBSTRING_FORM.search(text)


class TestSourceTree:
    """No file under src/lm_mcp sends or teaches hostGroupIds~."""

    def test_walk_reaches_the_modules_that_carried_the_form(self):
        files = {path.relative_to(SOURCE_ROOT).as_posix() for path in _source_files()}

        assert {
            "tools/topology.py",
            "resources/filters.py",
            "resources/guides.py",
            "resources/schemas.py",
        } <= files

    def test_no_file_carries_the_substring_form(self):
        offenders = {
            path.relative_to(SOURCE_ROOT).as_posix(): _substring_lines(path)
            for path in _source_files()
            if path != ALERTS_NOTE and _substring_lines(path)
        }

        assert offenders == {}

    def test_the_alerts_note_is_the_one_exemption(self):
        assert _substring_lines(ALERTS_NOTE) == [
            "The LM API hostGroupIds~ filter does not reliably restrict alerts to a"
        ]


class TestDeviceResourcesTeachMembership:
    """The device resources teach the form the 2026-10-30 probe found exact."""

    def test_filter_field_offers_only_the_membership_operator(self):
        from lm_mcp.resources.filters import get_filter_content

        field = get_filter_content("devices")["fields"]["hostGroupIds"]

        assert field["operators"] == [":"]
        assert field["examples"] == ["hostGroupIds:5"]

    def test_common_query_uses_the_membership_form(self):
        from lm_mcp.resources.filters import get_filter_content

        queries = get_filter_content("devices")["common_queries"]

        assert {"description": "Devices in specific group", "filter": "hostGroupIds:5"} in queries

    def test_schema_offers_only_the_membership_operator(self):
        from lm_mcp.resources.schemas import ALL_SCHEMAS

        assert ALL_SCHEMAS["devices"]["fields"]["hostGroupIds"]["operators"] == [":"]

    def test_guide_example_and_note_teach_membership(self):
        from lm_mcp.resources.guides import COMMON_QUERY_EXAMPLES

        example = next(
            item
            for item in COMMON_QUERY_EXAMPLES["examples"]
            if item["description"] == "Find devices in a specific group"
        )

        assert example["filter"] == "hostGroupIds:5"
        assert "membership" in example["notes"]
        assert "Use ~" not in example["notes"]


class TestAlertResourceTeachesTheFilterAlertsHonor:
    """/alert/alerts ignores hostGroupIds in both forms (live, 2026-11-06).

    An id that matches nothing returned the same alerts as no filter, while the
    same filter on /device/devices returned 0. monitorObjectGroups is what
    resolve_group_filter sends.
    """

    def test_fields_do_not_offer_host_group_ids(self):
        from lm_mcp.resources.filters import get_filter_content

        assert "hostGroupIds" not in get_filter_content("alerts")["fields"]

    def test_group_query_uses_monitor_object_groups(self):
        from lm_mcp.resources.filters import get_filter_content

        query = next(
            item
            for item in get_filter_content("alerts")["common_queries"]
            if "in a group" in item["description"]
        )

        assert query["filter"] == (
            'monitorObjectGroups~"Kubernetes Cluster: rm-aks-cluster",cleared:false'
        )

    def test_group_field_says_host_group_ids_is_ignored(self):
        from lm_mcp.resources.filters import get_filter_content

        description = get_filter_content("alerts")["fields"]["monitorObjectGroups"]["description"]

        assert "hostGroupIds" in description
        assert "ignore" in description
