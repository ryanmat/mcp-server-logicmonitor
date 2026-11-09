# Description: Tests for the audit log tools against the filter behavior verified on live portals.
# Description: Covers get_audit_logs kind="all" and kind="change", their ceilings and actors.

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from tests.envelope import envelope

BASE = "https://test.logicmonitor.com/santaba/rest"
URL = f"{BASE}/setting/accesslogs"
LONG_USERNAMES = ",".join(f"long-user-example-{i:03d}@subdomain.example.com" for i in range(40))


@pytest.fixture
def auth():
    """Create a BearerAuth instance for testing."""
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
    )


def _row(i, username, desc, t):
    """A synthetic audit row in the shape /setting/accesslogs returns (from PR #63)."""
    return {
        "id": f"row{i}",
        "username": username,
        "ip": "192.0.2.10",
        "happenedOn": t,
        "happenedOnLocal": "2026-10-01 10:00:00 UTC",
        "description": desc,
        "sessionId": None,
    }


def _filter(route, n=-1):
    """The filter query parameter of the n-th recorded call."""
    return parse_qs(urlparse(str(route.calls[n].request.url)).query).get("filter", [""])[0]


async def _logs(client, **kwargs):
    from lm_mcp.tools.audit import get_audit_logs

    return await get_audit_logs(client, **kwargs)


class TestAuditLogsAll:
    """kind="all": the filters the accesslogs API honors, sent through list_tool."""

    @respx.mock
    async def test_returns_rows_with_the_epoch_and_local_times(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(1, "user-a@example.com", "user-a@example.com signs in via SAML", 2),
                        _row(2, "user-a@example.com", "Edit the dashboard Board-A", 1),
                    ],
                    "total": 2,
                },
            )
        )

        data = json.loads((await _logs(client))[0].text)

        assert data["kind"] == "all"
        assert data["count"] == 2
        assert data["audit_logs"][0]["happened_on"] == 2
        assert data["audit_logs"][0]["timestamp"] == "2026-10-01 10:00:00 UTC"
        assert data["has_more"] is False

    @respx.mock
    async def test_time_window_filters_happened_on_as_epoch(self, client):
        """happenedOnLocal is a display string the API ignores in a filter."""
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await _logs(client, start_time=1700000000, end_time=1700003600, exclude_system=False)

        assert _filter(route) == "happenedOn>:1700000000,happenedOn<:1700003600"

    @respx.mock
    async def test_username_list_becomes_an_or_list(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await _logs(client, username="user-a@example.com, user-b@example.com")

        assert _filter(route) == 'username:"user-a@example.com"|"user-b@example.com"'

    @respx.mock
    async def test_action_is_a_description_match(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await _logs(client, action="Action=Delete")

        assert _filter(route) == 'description~"Action=Delete"'

    @respx.mock
    async def test_a_second_text_is_matched_after_the_fetch(self, client):
        """The API applies one description~ clause; resource_type is matched on the page."""
        route = respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(1, "u", '"Action=Delete"; "Type=Device"; "Device=d-1"', 2),
                        _row(2, "u", '"Action=Delete"; "Type=SDT"; "Description= Delete SDT"', 1),
                    ],
                    "total": 2,
                },
            )
        )

        data = json.loads(
            (await _logs(client, action="Action=Delete", resource_type="Type=SDT"))[0].text
        )

        assert _filter(route) == 'description~"Action=Delete"'
        assert [r["id"] for r in data["audit_logs"]] == ["row2"]
        assert data["dropped"] == 1
        assert "'Type=SDT' was matched after the fetch" in data["note"]

    @respx.mock
    async def test_system_actors_are_dropped_by_default_and_paging_follows_the_page(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(1, "System:ActiveDiscovery", '"Action=Update"; "Type=Instance"', 3),
                        _row(2, "System::AutoGroupMembership", " host(id=1,name =x) add to G", 2),
                        _row(3, "user-a@example.com", "Create a dashboard Board-B", 1),
                    ],
                    "total": -4,
                },
            )
        )

        data = json.loads((await _logs(client, limit=3))[0].text)

        assert "filter" not in route.calls[0].request.url.params
        assert [r["username"] for r in data["audit_logs"]] == ["user-a@example.com"]
        assert data["dropped"] == 2
        assert data["has_more"] is True
        assert data["next_offset"] == 3

    @respx.mock
    async def test_exclude_system_false_keeps_system_actors(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200, json={"items": [_row(1, "System:ActiveDiscovery", "x", 1)], "total": 1}
            )
        )

        data = json.loads((await _logs(client, exclude_system=False))[0].text)

        assert [r["id"] for r in data["audit_logs"]] == ["row1"]

    @respx.mock
    async def test_a_named_system_user_is_never_excluded(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(
                200, json={"items": [_row(1, "System:ActiveDiscovery", '"Action=Update"', 3)]}
            )
        )

        data = json.loads((await _logs(client, username="System:ActiveDiscovery"))[0].text)

        assert _filter(route) == 'username:"System:ActiveDiscovery"'
        assert [r["id"] for r in data["audit_logs"]] == ["row1"]

    @respx.mock
    async def test_a_user_that_looks_like_a_system_prefix_is_kept(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(1, "System:ActiveDiscovery", '"Action=Update"', 3),
                        _row(2, "system.admin@example.com", "Create a dashboard Board-A", 2),
                    ],
                    "total": 2,
                },
            )
        )

        data = json.loads((await _logs(client))[0].text)

        assert [r["username"] for r in data["audit_logs"]] == ["system.admin@example.com"]

    @respx.mock
    async def test_a_stripped_username_carries_its_own_note(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        data = json.loads((await _logs(client, username="user-a*"))[0].text)

        assert _filter(route) == 'username:"user-a"'
        assert "usernames match exactly" in data["note"]

    @pytest.mark.parametrize(
        ("kwargs", "expect"),
        [
            ({"username": "*"}, "username"),
            ({"username": " , *"}, "username"),
            ({"offset": 9990, "limit": 50}, "10000"),
            ({"username": LONG_USERNAMES}, "HTTP 500"),
            ({"kind": "change", "username": LONG_USERNAMES}, "HTTP 500"),
            ({"kind": "change", "offset": 9900}, "10000"),
            ({"kind": "login"}, "kind"),
            ({"change_type": "delete"}, "change_type"),
        ],
        ids=[
            "wildcard-only-username",
            "empty-username-list",
            "offset-ceiling",
            "filter-ceiling",
            "change-filter-ceiling",
            "change-offset-ceiling",
            "unknown-kind",
            "change-type-without-change",
        ],
    )
    async def test_refused_before_any_call_and_not_logged(self, client, caplog, kwargs, expect):
        with respx.mock(assert_all_called=False) as mock:
            route = mock.get(URL).mock(return_value=httpx.Response(200, json={"items": []}))
            with caplog.at_level("ERROR", logger="lm_mcp.tools"):
                error = envelope(await _logs(client, **kwargs))

        assert error["code"] == "INVALID_REQUEST"
        assert expect in error["message"]
        assert not route.called
        assert "unhandled error in tool handler" not in caplog.text

    @respx.mock
    @pytest.mark.parametrize("kind", ["all", "change"])
    async def test_a_malformed_body_reaches_handle_error(self, client, caplog, kind):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200, content=b"<html>not json", headers={"content-type": "application/json"}
            )
        )

        with caplog.at_level("ERROR", logger="lm_mcp.tools"):
            error = envelope(await _logs(client, kind=kind))

        assert error["code"] != "INVALID_REQUEST"
        assert "unhandled error in tool handler" in caplog.text


class TestSystemActors:
    """System-actor matching is case-sensitive and needs a name with no @ or space."""

    @pytest.mark.parametrize(
        ("username", "is_system"),
        [
            ("System:ActiveDiscovery", True),
            ("System::AutoGroupMembership", True),
            ("System.NetScan", True),
            ("LogicMonitor Internal", True),
            ("AZURE auto-delete", True),
            ("system.admin@example.com", False),
            ("System.Admin@example.com", False),
            ("System:user-x@example.com", False),
            ("System: Admin", False),
            ("SYSTEM:ActiveDiscovery", False),
            ("user-a@example.com", False),
        ],
    )
    def test_system_actor_match_is_case_sensitive(self, username, is_system):
        from lm_mcp.tools.audit import SYSTEM_ACTOR

        assert bool(SYSTEM_ACTOR.match(username)) is is_system


class TestAuditLogsChange:
    """kind="change": the verb read from the description, over a pool of the newest rows."""

    @respx.mock
    async def test_classifies_and_filters_changes(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(1, "System:ActiveDiscovery", '"Action=Update"; "Type=Instance"', 9),
                        _row(2, "user-a@example.com", "user-a@example.com signs in via SAML", 8),
                        _row(3, "user-a@example.com", '"Action=Delete"; "Type=Device"', 7),
                        _row(4, "user-a@example.com", "Create a dashboard Board-C", 6),
                        _row(5, "user-a@example.com", "Note (ACK) added to (LMD1) by (u).", 5),
                        _row(6, "user-b@example.com", "Edit the widget W-1 of dashboard B", 4),
                    ]
                },
            )
        )

        data = json.loads((await _logs(client, kind="change"))[0].text)
        deletes = json.loads((await _logs(client, kind="change", change_type="delete"))[0].text)

        assert data["kind"] == "change"
        assert [(r["id"], r["change_type"]) for r in data["change_logs"]] == [
            ("row3", "delete"),
            ("row4", "create"),
            ("row6", "update"),
        ]
        assert [r["id"] for r in deletes["change_logs"]] == ["row3"]

    @respx.mock
    async def test_a_named_system_user_returns_its_changes(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200, json={"items": [_row(1, "System:ActiveDiscovery", '"Action=Update"', 3)]}
            )
        )

        data = json.loads(
            (await _logs(client, kind="change", username="System:ActiveDiscovery"))[0].text
        )

        assert [(r["id"], r["change_type"]) for r in data["change_logs"]] == [("row1", "update")]

    @respx.mock
    async def test_system_actors_are_excluded_by_default(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(1, "System:ActiveDiscovery", '"Action=Update"', 3),
                        _row(2, "system.admin@example.com", '"Action=Delete"', 2),
                    ]
                },
            )
        )

        data = json.loads((await _logs(client, kind="change"))[0].text)

        assert [r["id"] for r in data["change_logs"]] == ["row2"]

    @pytest.mark.parametrize("change_type", ["updated", "updated*", "login"])
    async def test_an_unknown_change_type_is_refused_before_any_call(self, client, change_type):
        """A typo such as "updated" would otherwise match nothing and read as no changes."""
        with respx.mock(assert_all_called=False) as mock:
            route = mock.get(URL).mock(return_value=httpx.Response(200, json={"items": []}))
            error = envelope(await _logs(client, kind="change", change_type=change_type))

        assert error["code"] == "INVALID_REQUEST"
        assert "create, update, delete, import" in error["message"]
        assert not route.called

    @respx.mock
    @pytest.mark.parametrize("change_type", ["create", "UPDATE", " delete ", "import"])
    async def test_known_change_types_are_accepted(self, client, change_type):
        respx.get(URL).mock(return_value=httpx.Response(200, json={"items": []}))

        data = json.loads((await _logs(client, kind="change", change_type=change_type))[0].text)

        assert data["change_logs"] == []

    @respx.mock
    async def test_change_type_wildcards_are_stripped_then_validated(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200, json={"items": [_row(1, "user-a@example.com", '"Action=Update"', 1)]}
            )
        )

        data = json.loads((await _logs(client, kind="change", change_type="update*"))[0].text)

        assert [r["change_type"] for r in data["change_logs"]] == ["update"]
        assert "Wildcard" in data["note"]

    @respx.mock
    async def test_stopping_at_limit_with_rows_left_reads_has_more_with_the_note(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(1, "user-a@example.com", '"Action=Delete"', 3),
                        _row(2, "user-a@example.com", '"Action=Update"', 2),
                        _row(3, "user-a@example.com", '"Action=Add"', 1),
                    ]
                },
            )
        )

        data = json.loads((await _logs(client, kind="change", limit=1))[0].text)

        assert [r["id"] for r in data["change_logs"]] == ["row1"]
        assert (data["scanned"], data["has_more"]) == (1, True)
        assert "narrow start_time/end_time" in data["note"]

    @respx.mock
    async def test_a_short_pool_read_whole_is_complete(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200, json={"items": [_row(1, "user-a@example.com", '"Action=Delete"', 3)]}
            )
        )

        data = json.loads((await _logs(client, kind="change", limit=5))[0].text)

        assert (data["scanned"], data["has_more"]) == (1, False)
        assert "note" not in data

    @respx.mock
    async def test_a_full_pool_short_of_limit_says_older_changes_exist(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(i, "System:ActiveDiscovery", '"Action=Update"', 300 - i)
                        for i in range(200)
                    ]
                },
            )
        )

        data = json.loads((await _logs(client, kind="change", limit=5))[0].text)

        assert route.calls[0].request.url.params["size"] == "200"
        assert data["change_logs"] == []
        assert data["has_more"] is True
        assert "newest 200" in data["note"]

    @respx.mock
    async def test_a_full_pool_holding_every_row_is_complete(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(i, "System:ActiveDiscovery", '"Action=Update"', 300 - i)
                        for i in range(200)
                    ],
                    "total": 200,
                },
            )
        )

        data = json.loads((await _logs(client, kind="change", limit=5))[0].text)

        assert data["has_more"] is False
        assert "note" not in data

    @respx.mock
    async def test_a_short_pool_with_a_negative_total_reads_has_more(self, client):
        respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={"items": [_row(1, "user-a@example.com", '"Action=Delete"', 3)], "total": -5},
            )
        )

        data = json.loads((await _logs(client, kind="change", limit=5))[0].text)

        assert (data["scanned"], data["has_more"]) == (1, True)
        assert "note" in data

    @respx.mock
    async def test_reports_the_filter_sent(self, client):
        respx.get(URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        data = json.loads(
            (
                await _logs(
                    client, kind="change", resource_type="dashboard", username="user-a@example.com"
                )
            )[0].text
        )

        assert data["filter"] == 'username:"user-a@example.com",description~"dashboard"'


class TestChangeClassification:
    @pytest.mark.parametrize(
        ("desc", "expected"),
        [
            ('"Action=Delete"; "Type=Device"', "delete"),
            ('"Action=Add"; "Type=Dashboard"', "create"),
            ('"Action=Import"; "Type=DataSource"', "import"),
            ("Edit the widget W-1 of dashboard Board-C", "update"),
            ("Rename the dashboard Board-C", "update"),
            ('"Action=Enable"; "Type=Collector"', "update"),
            ('"Action=Export"; "Type=Dashboard"', None),
            ('"Action=Login"', None),
            ('"Action=Fetch"; "Type=Report"', None),
            ('"Action=Acknowledge"; "Type=Alert"', None),
            ('"Action=Schedule"; "Type=Report"', None),
            ("Enable 2FA Request for user-a@example.com", None),
            ("Update rejected by API request: path '/device/devices'", None),
            ("Enable the collector collector-example-1", "update"),
        ],
    )
    def test_only_known_verbs_are_changes(self, desc, expected):
        from lm_mcp.tools.audit import change_type_of

        assert change_type_of(desc) == expected


class TestGetLoginAudit:
    """Tests for get_login_audit tool."""

    @respx.mock
    async def test_get_login_audit_returns_logins(self, client):
        """get_login_audit returns login events."""
        from lm_mcp.tools.audit import get_login_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "username": "admin",
                            "ip": "192.168.1.1",
                            "happenedOn": "login",
                            "description": "User logged in successfully",
                            "happenedOnLocal": 1702400000,
                        },
                        {
                            "id": 2,
                            "username": "baduser",
                            "ip": "10.0.0.1",
                            "happenedOn": "login",
                            "description": "Login failed - invalid password",
                            "happenedOnLocal": 1702400100,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_login_audit(client)

        data = json.loads(result[0].text)
        assert len(data["login_logs"]) == 2
        assert data["login_logs"][0]["status"] == "success"
        assert data["login_logs"][1]["status"] == "failed"

    @respx.mock
    async def test_get_login_audit_failed_only(self, client):
        """get_login_audit can filter to failed logins."""
        from lm_mcp.tools.audit import get_login_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "username": "admin",
                            "description": "User logged in successfully",
                            "happenedOn": "login",
                        },
                        {
                            "id": 2,
                            "username": "baduser",
                            "description": "Login failed",
                            "happenedOn": "login",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_login_audit(client, failed_only=True)

        data = json.loads(result[0].text)
        assert len(data["login_logs"]) == 1
        assert data["login_logs"][0]["username"] == "baduser"


class TestGetChangeAudit:
    """Tests for get_change_audit tool."""

    @respx.mock
    async def test_get_change_audit_returns_changes(self, client):
        """get_change_audit returns configuration changes."""
        from lm_mcp.tools.audit import get_change_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "username": "admin",
                            "happenedOn": "create",
                            "description": "Created device server01",
                            "happenedOnLocal": 1702400000,
                            "ip": "192.168.1.1",
                        },
                        {
                            "id": 2,
                            "username": "admin",
                            "happenedOn": "delete",
                            "description": "Deleted dashboard test",
                            "happenedOnLocal": 1702400100,
                            "ip": "192.168.1.1",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_change_audit(client)

        data = json.loads(result[0].text)
        assert len(data["change_logs"]) == 2
        assert data["change_logs"][0]["action"] == "create"
        assert data["change_logs"][1]["action"] == "delete"
