# Description: Tests for the audit log tools against the filter behavior verified on live portals.
# Description: Covers get_audit_logs kinds all, change, login and api_token, ceilings and actors.

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
TOKENS_URL = f"{BASE}/setting/admins/apitokens"
# A 20-character access ID, the length every live token on the sandbox carries.
ACCESS_ID = "Ab12Cd34Ef56Gh78Ij90"
# The portal login wordings from PR #63; the sandbox shows "log in. 2FA Mode" (2026-11-09).
LOGIN_WORDINGS = (
    "signs in via",
    "log in. 2FA Mode",
    "logged in through lmsupport",
    "could not log into the system",
    "Session timed out for SSO",
    "signs out",
)


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


def _by_wording(rows, totals=None):
    """Answer each login-wording query with that wording's rows, cut to the size asked for."""

    def answer(request):
        flt = request.url.params.get("filter", "")
        size = int(request.url.params.get("size", 50))
        for wording, wording_rows in rows.items():
            if f'description~"{wording}"' in flt:
                total = (totals or {}).get(wording, len(wording_rows))
                return httpx.Response(200, json={"items": wording_rows[:size], "total": total})
        return httpx.Response(200, json={"items": [], "total": 0})

    return answer


def _wordings_sent(route):
    """The login wording each recorded call asked for."""
    sent = []
    for call in route.calls:
        flt = call.request.url.params.get("filter", "")
        sent.append(flt.split('description~"', 1)[1].rstrip('"'))
    return sent


class TestAuditLogsAll:
    """R2.11 kind="all": the filters the accesslogs API honors, sent through list_tool."""

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
            ({"kind": "change", "offset": 9990}, "10000"),
            ({"kind": "logins"}, "kind"),
            ({"change_type": "delete"}, "change_type"),
            ({"kind": "login", "success_only": True, "failed_only": True}, "success_only"),
            ({"success_only": True}, "success_only"),
            ({"kind": "change", "failed_only": True}, "failed_only"),
            ({"kind": "login", "action": "Action=Delete"}, "action"),
            ({"kind": "api_token", "resource_type": "Type=Device"}, "resource_type"),
            ({"kind": "login", "access_id": ACCESS_ID}, "access_id"),
            ({"token_id": 267}, "token_id"),
            ({"kind": "api_token", "access_id": "**"}, "access_id"),
            ({"kind": "login", "offset": 9990}, "10000"),
            ({"kind": "login", "username": LONG_USERNAMES}, "HTTP 500"),
            ({"kind": "api_token", "offset": 9990}, "10000"),
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
            "success-only-with-failed-only",
            "success-only-without-login",
            "failed-only-without-login",
            "action-with-login",
            "resource-type-with-api-token",
            "access-id-without-api-token",
            "token-id-without-api-token",
            "wildcard-only-access-id",
            "login-offset-ceiling",
            "login-filter-ceiling",
            "api-token-offset-ceiling",
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
    @pytest.mark.parametrize("kind", ["all", "change", "login", "api_token"])
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
    """R2.11 kind="change": the verb read from the description, over a pool of the newest rows."""

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
    async def test_the_pool_shrinks_to_fit_under_the_offset_ceiling(self, client):
        """Near the 10,000-row ceiling the pool reads only the rows left, not a refusal."""
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        data = json.loads((await _logs(client, kind="change", offset=9600, limit=50))[0].text)

        assert route.calls[0].request.url.params["size"] == "400"
        assert data["change_logs"] == []

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


class TestAuditLogsLogin:
    """R2.11 kind="login": one query per portal login wording, merged newest first."""

    @respx.mock
    async def test_queries_each_login_wording_once_and_merges_newest_first(self, client):
        rows = {
            "log in. 2FA Mode": [
                _row(1, "user-a@example.com", "user-a@example.com log in. 2FA Mode : Sms", 50)
            ],
            "signs in via": [
                _row(2, "user-b@example.com", "user-b@example.com signs in via SAML", 40)
            ],
            "could not log into the system": [
                _row(3, "user-c", "user-c could not log into the system", 60)
            ],
            "Session timed out for SSO": [
                _row(4, "user-d@example.com", "Session timed out for SSO user-d@example.com", 30)
            ],
            "signs out": [_row(5, "user-a@example.com", "user-a@example.com signs out", 70)],
            "logged in through lmsupport": [
                _row(6, "lmsupport", "lmsupport logged in through lmsupport", 20)
            ],
        }
        route = respx.get(URL).mock(side_effect=_by_wording(rows))

        data = json.loads((await _logs(client, kind="login"))[0].text)

        assert sorted(_wordings_sent(route)) == sorted(LOGIN_WORDINGS)
        assert [r["id"] for r in data["login_logs"]] == [
            "row5",
            "row3",
            "row1",
            "row2",
            "row4",
            "row6",
        ]
        assert [(r["status"], r["method"]) for r in data["login_logs"]] == [
            ("logout", None),
            ("failed", "password"),
            ("success", "Local + 2FA (Sms)"),
            ("success", "SAML"),
            ("failed", "SSO"),
            ("success", "LM Support"),
        ]
        assert data["kind"] == "login"
        assert (data["total"], data["count"], data["has_more"]) == (6, 6, False)
        assert "total_note" not in data

    @respx.mock
    async def test_a_row_two_wordings_return_is_reported_once(self, client):
        shared = _row(1, "user-a@example.com", "user-a@example.com log in. 2FA Mode : Sms", 50)
        respx.get(URL).mock(
            side_effect=_by_wording({"log in. 2FA Mode": [shared], "signs in via": [shared]})
        )

        data = json.loads((await _logs(client, kind="login"))[0].text)

        assert [r["id"] for r in data["login_logs"]] == ["row1"]
        assert data["total"] == 1

    @respx.mock
    @pytest.mark.parametrize(
        ("flag", "wordings"),
        [
            ("success_only", ["signs in via", "log in. 2FA Mode", "logged in through lmsupport"]),
            ("failed_only", ["could not log into the system", "Session timed out for SSO"]),
        ],
    )
    async def test_success_only_and_failed_only_query_their_wordings_alone(
        self, client, flag, wordings
    ):
        route = respx.get(URL).mock(side_effect=_by_wording({}))

        await _logs(client, kind="login", **{flag: True})

        assert sorted(_wordings_sent(route)) == sorted(wordings)

    @respx.mock
    async def test_a_wording_with_older_rows_makes_total_a_lower_bound(self, client):
        rows = {
            "log in. 2FA Mode": [
                _row(1, "user-a@example.com", "user-a@example.com log in. 2FA Mode : Sms", 50)
            ],
            "signs out": [_row(2, "user-a@example.com", "user-a@example.com signs out", 70)],
        }
        respx.get(URL).mock(side_effect=_by_wording(rows, totals={"signs out": -2}))

        data = json.loads((await _logs(client, kind="login"))[0].text)

        assert data["has_more"] is True
        assert data["total"] == 2
        assert "lower bound" in data["total_note"]
        assert "More login rows exist" in data["note"]

    @respx.mock
    async def test_offset_pages_the_merged_rows(self, client):
        """Each wording is read from its newest row to offset + limit, then merged and cut."""
        rows = {
            "log in. 2FA Mode": [
                _row(i, "user-a@example.com", "user-a@example.com log in. 2FA Mode : Sms", t)
                for i, t in ((1, 90), (3, 70), (5, 50))
            ],
            "signs out": [
                _row(i, "user-a@example.com", "user-a@example.com signs out", t)
                for i, t in ((2, 80), (4, 60), (6, 40))
            ],
        }
        route = respx.get(URL).mock(side_effect=_by_wording(rows))

        data = json.loads((await _logs(client, kind="login", limit=2, offset=2))[0].text)

        assert {c.request.url.params["size"] for c in route.calls} == {"4"}
        assert {c.request.url.params["offset"] for c in route.calls} == {"0"}
        assert [r["id"] for r in data["login_logs"]] == ["row3", "row4"]
        assert (data["offset"], data["count"], data["total"]) == (2, 2, 6)
        assert data["has_more"] is True
        assert "total_note" not in data

    @respx.mock
    async def test_username_and_window_go_into_every_wording_query(self, client):
        """A stripped username carries the exact-match note, not the substring one."""
        route = respx.get(URL).mock(side_effect=_by_wording({}))

        data = json.loads(
            (
                await _logs(
                    client,
                    kind="login",
                    username="admin*",
                    start_time=1794000000,
                    end_time=1794086400,
                )
            )[0].text
        )

        assert len(route.calls) == len(LOGIN_WORDINGS)
        for n in range(len(route.calls)):
            assert _filter(route, n).startswith(
                'username:"admin",happenedOn>:1794000000,happenedOn<:1794086400,description~"'
            )
        assert "usernames match exactly" in data["note"]
        assert "substring" not in data["note"]


class TestAuditLogsApiToken:
    """R2.11 kind="api_token": rows naming API token <accessId>, that exact id only."""

    @respx.mock
    async def test_keeps_only_rows_naming_the_exact_access_id(self, client):
        """Row wordings from the sandbox read of 2026-11-09, the access IDs replaced."""
        route = respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(
                            1,
                            "svc-deploy",
                            '"Action=Update"; "Type=Device"; "Device=web-01 (42)"; '
                            f'"Description=(monitored by collector <7, c-1>),   }},  via API '
                            f'token {ACCESS_ID}"',
                            3,
                        ),
                        _row(
                            2,
                            "svc-deploy",
                            f"Throttled API request: API token {ACCESS_ID} attempted to access "
                            "path '/santaba/rest/log/search' with Method: POST",
                            2,
                        ),
                        _row(
                            3,
                            ACCESS_ID,
                            f"Failed API request: Bearer API token {ACCESS_ID} attempted to "
                            "access path '/santaba/rest/alert/alerts' with Method: GET",
                            1,
                        ),
                        _row(
                            4,
                            "svc-other",
                            f"Throttled API request: API token {ACCESS_ID}Zz attempted to access "
                            "path '/santaba/rest/device/devices' with Method: POST",
                            0,
                        ),
                    ],
                    "total": 4,
                },
            )
        )

        data = json.loads((await _logs(client, kind="api_token", access_id=ACCESS_ID))[0].text)
        rows = data["api_token_logs"]

        assert _filter(route) == f'description~"API token {ACCESS_ID}"'
        assert [r["id"] for r in rows] == ["row1", "row2", "row3"]
        assert data["dropped"] == 1
        assert [r["event"] for r in rows] == ["change", "throttled", "rejected"]
        assert {r["access_id"] for r in rows} == {ACCESS_ID}
        assert (rows[1]["path"], rows[1]["method"]) == ("/santaba/rest/log/search", "POST")
        assert (rows[2]["path"], rows[2]["method"]) == ("/santaba/rest/alert/alerts", "GET")
        assert (rows[0]["path"], rows[0]["method"]) == (None, None)
        assert (data["kind"], data["access_id"]) == ("api_token", ACCESS_ID)
        assert (data["total"], data["has_more"]) == (4, False)

    @respx.mock
    async def test_access_id_is_sanitized_and_carries_its_note(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        data = json.loads(
            (await _logs(client, kind="api_token", access_id=f"*{ACCESS_ID}*"))[0].text
        )

        assert _filter(route) == f'description~"API token {ACCESS_ID}"'
        assert "access_id matches the whole access ID" in data["note"]

    @respx.mock
    async def test_token_id_is_read_through_the_id_lookup(self, client):
        tokens = respx.get(TOKENS_URL).mock(
            return_value=httpx.Response(
                200, json={"items": [{"id": 267, "accessId": ACCESS_ID}], "total": 1}
            )
        )
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        data = json.loads((await _logs(client, kind="api_token", token_id=267))[0].text)

        assert tokens.calls.last.request.url.params["filter"] == "id:267"
        assert tokens.calls.last.request.url.params["size"] == "1"
        assert _filter(route) == f'description~"API token {ACCESS_ID}"'
        assert data["access_id"] == ACCESS_ID

    @pytest.mark.parametrize(
        "items",
        [[], [{"id": 268, "accessId": ACCESS_ID}], [{"id": 267, "accessId": ""}]],
        ids=["no-token", "another-id", "no-access-id"],
    )
    async def test_a_token_id_the_lookup_does_not_confirm_is_not_found(self, client, items):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(TOKENS_URL).mock(
                return_value=httpx.Response(200, json={"items": items, "total": len(items)})
            )
            route = mock.get(URL).mock(return_value=httpx.Response(200, json={"items": []}))

            error = envelope(await _logs(client, kind="api_token", token_id=267))

        assert error["code"] == "NOT_FOUND"
        assert "API token 267" in error["message"]
        assert not route.called

    @respx.mock
    async def test_access_id_wins_over_token_id(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await _logs(client, kind="api_token", access_id=ACCESS_ID, token_id=267)

        assert _filter(route) == f'description~"API token {ACCESS_ID}"'

    @respx.mock
    async def test_without_an_id_every_token_row_pages_through(self, client):
        route = respx.get(URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _row(
                            1,
                            "svc-deploy",
                            f"Throttled API request: API token {ACCESS_ID} attempted to access "
                            "path '/santaba/rest/log/search' with Method: POST",
                            2,
                        )
                    ],
                    "total": -12,
                },
            )
        )

        data = json.loads(
            (await _logs(client, kind="api_token", username="svc-deploy", limit=1, offset=10))[
                0
            ].text
        )

        assert _filter(route) == 'username:"svc-deploy",description~"API token"'
        assert route.calls.last.request.url.params["size"] == "1"
        assert route.calls.last.request.url.params["offset"] == "10"
        assert data["has_more"] is True
        assert "dropped" not in data
        assert "access_id" not in data


class TestAuditToolsMerged:
    """R2.3, R2.13: get_audit_logs carries four kinds; the three audit tools leave."""

    @pytest.mark.parametrize("name", ["get_login_audit", "get_change_audit", "get_api_token_audit"])
    def test_the_three_audit_tools_are_gone(self, name):
        from lm_mcp.registry import TOOLS, get_tool_handler

        assert name not in {t.name for t in TOOLS}
        with pytest.raises(ValueError, match="Unknown tool"):
            get_tool_handler(name)

    def test_get_audit_logs_declares_the_kinds_and_their_arguments(self):
        from lm_mcp.registry import TOOLS

        (tool,) = [t for t in TOOLS if t.name == "get_audit_logs"]
        props = tool.inputSchema["properties"]
        assert props["kind"]["enum"] == ["all", "change", "login", "api_token"]
        assert props["success_only"]["type"] == props["failed_only"]["type"] == "boolean"
        assert props["access_id"]["type"] == "string"
        assert props["token_id"]["type"] == "integer"
