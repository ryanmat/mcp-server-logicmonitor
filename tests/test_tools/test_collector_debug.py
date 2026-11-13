# Description: Tests for collector_debug (spec R3.9): builder, allowlist, checks, masking, parse,
# Description: transport. Hostile inputs from PR #97 and its reviews; transport replies are live-shaped.
# ruff: noqa: E501  (expected command lines and masked text are kept on one line to stay readable)

import asyncio
import dataclasses
import gc
import json
import logging
import time
from pathlib import Path

import httpx
import pytest
import respx

from lm_mcp.client import build_client
from lm_mcp.exceptions import (
    AuthenticationError,
    LMError,
    LMPermissionError,
    RateLimitError,
    ServerError,
)
from lm_mcp.logging import is_sensitive_key
from lm_mcp.tools import collector_debug as cd
from lm_mcp.tools import is_error_result
from lm_mcp.tools.collector_debug import (
    ALLOWED_HEADS,
    BLOCKED,
    BUDGET_DEFAULT,
    BUDGET_MAX,
    COMMANDS,
    OUTPUT_DEFAULT,
    OUTPUT_MAX,
    Target,
    ToolRejectionError,
    build_cmdline,
    check_cmdline,
    check_request,
    collector_debug,
    describe_failure,
    parse_health_check,
    parse_reply,
    redact,
    target_from_record,
)
from tests.envelope import envelope

FIXTURES = Path(__file__).parent.parent / "fixtures"
# Collector 161's stored health check, read live on 2026-11-12 (docs/validation/probes-2026-11.md,
# Step 72): 39 blocks, a WARN and a DISABLED checkpoint, one script at status 1.
LIVE_HEALTH = (FIXTURES / "collector_health_check.txt").read_text()
# Live POST /debug and GET /debug/{sessionId} exchanges (probes-2026-11.md, Step 73), verbatim.
LIVE = json.loads((FIXTURES / "collector_debug_exchanges.json").read_text())
# Built in two parts, so the repository's private-key hook does not read a test as a key.
PEM_BEGIN = "-----BEGIN RSA " + "PRIVATE KEY-----"
PEM_END = "-----END RSA " + "PRIVATE KEY-----"
PGP_BEGIN = "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----"


def assert_linear(work, make, small: int = 50_000, large: int = 200_000) -> None:
    """Four times the input takes about four times as long; a square would take sixteen.

    The best of three runs at each size is compared, each with the garbage collector paused so
    a collection pause is not read as growth, the margin is wide for a loaded machine, and a
    small run under 10 ms counts as 10 ms, so timer noise on tiny runs does not decide.
    """

    def best(text: str) -> float:
        times = []
        for _ in range(3):
            gc.collect()
            gc.disable()
            try:
                started = time.perf_counter()
                work(text)
                times.append(time.perf_counter() - started)
            finally:
                gc.enable()
        return min(times)

    fast, slow = best(make(small)), best(make(large))
    assert slow < 5.0, (fast, slow)
    assert slow / max(fast, 0.01) < 8, (fast, slow)


T = Target(collector_id=7, host="10.0.0.5", portal_host="portal-a.example.net")
NO_DEVICE = Target(collector_id=7, portal_host="portal-a.example.net")
PORTAL = "portal-a.example.net"

# Shapes from a live read of the sandbox (docs/validation/probes-2026-11.md, Step 71): a served
# device names its collector as a positive int; a cloud resource answers -2 and a service -4.
SERVED = {
    "id": 1786,
    "name": "127.0.0.1",
    "displayName": "example-ubuntu",
    "currentCollectorId": 26,
}
CLOUD = {
    "id": 9196,
    "name": "LMAZUREACCOUNT-1",
    "displayName": "example-azure",
    "currentCollectorId": -2,
}
SERVICE = {
    "id": 1966,
    "name": "example-imageprovider",
    "displayName": "example-imageprovider",
    "currentCollectorId": -4,
}


def request(command="uptime", **kw):
    """check_request with the tool's defaults for whatever the case does not set."""
    values = {
        "collector_id": 7,
        "device_id": None,
        "args": None,
        "budget_seconds": BUDGET_DEFAULT,
        "max_output_chars": OUTPUT_DEFAULT,
        "portal_host": PORTAL,
    }
    values.update(kw)
    return check_request(command, **values)


class TestBuilder:
    @pytest.mark.parametrize(
        "command,args,expected",
        [
            ("uptime", {}, "!uptime"),
            ("health_check", {}, "!shealthcheck func=detail collector=7"),
            ("perf", {}, "!perf type=ds dsFilterColumn=nan"),
            ("perf", {"h": "device-example-*"}, "!perf type=ds dsFilterColumn=nan h=device-example-*"),
            ("perf", {"type": "queue"}, "!perf type=queue"),
            ("getconfig", {"key": "collector.wmi.threadpool"}, "!getconfig collector.wmi.threadpool"),
            ("getconfig", {"key": "collector.snmp.timeout"}, "!getconfig collector.snmp.timeout"),
            ("ping", {"count": 4}, "!ping count=4 10.0.0.5"),
            ("nslookup", {}, "!nslookup 10.0.0.5"),
            ("snmpdiagnose", {}, "!snmpdiagnose 10.0.0.5"),
            ("snmpget", {"oids": [".1.3.6.1.2.1.1.5.0"]}, "!snmpget 10.0.0.5 .1.3.6.1.2.1.1.5.0"),
            ("snmpwalk", {}, "!snmpwalk 10.0.0.5 .1.3.6.1.2.1.1"),
            ("wmi", {}, "!wmi h=10.0.0.5 select * from Win32_Service"),
            ("wmi", {"query": "SELECT Name, State FROM Win32_Service WHERE Name = 'Spooler'"},
             "!wmi h=10.0.0.5 SELECT Name, State FROM Win32_Service WHERE Name = 'Spooler'"),
            ("wmi", {"query": "select * from Win32_Service where State != 'Running'"},
             "!wmi h=10.0.0.5 select * from Win32_Service where State != 'Running'"),
            ("winrm", {"useSSL": "false"}, "!winrm host=10.0.0.5 useSSL=false"),
            ("cim", {"class": "CIM_ComputerSystem"}, "!cim h=10.0.0.5 c=CIM_ComputerSystem"),
            ("http", {"url": "https://10.0.0.5/health"}, "!http https://10.0.0.5/health"),
            ("http", {"url": "http://10.0.0.5:8080/status?verbose=1"}, "!http http://10.0.0.5:8080/status?verbose=1"),
            ("sslcerts", {"port": 443}, "!sslcerts 10.0.0.5 443"),
            ("tlist", {"h": "10.0.0.5"}, "!tlist h=10.0.0.5"),
            ("aplist", {}, "!aplist status=failed"),
            ("splist", {"hostname": "device-example-1"}, "!splist hostname=device-example-1"),
            ("logsurf", {"files": ["wrapper.log", "watchdog.log"]}, "!logsurf level=error n=50 wrapper.log watchdog.log"),
            ("checkserverconnectivity", {}, "!checkserverconnectivity portal-a.example.net"),
            ("reportercache", {}, "!reportercache"), ("avslist", {}, "!avslist"),
            ("firewallstatus", {}, "!firewallstatus"), ("ipaddress", {}, "!ipaddress"),
            ("tasklist", {}, "!tasklist"), ("adlist", {}, "!adlist"), ("nsplist", {}, "!nsplist"),
            ("dxlist", {}, "!dxlist"), ("tplist", {}, "!tplist"), ("macaddress", {}, "!macaddress 10.0.0.5"),
            ("wmi", {"query": "select Name, ProcessId from Win32_Process where Name = 'svchost.exe'"},
             "!wmi h=10.0.0.5 select Name, ProcessId from Win32_Process where Name = 'svchost.exe'"),
            ("snmpwalk", {"oid": ".1.3.6.1.2.1.2"}, "!snmpwalk 10.0.0.5 .1.3.6.1.2.1.2"),
            ("logsurf", {"n": ""}, "!logsurf level=error n=50 wrapper.log"),
            ("logsurf", {"files": ["wrapper.log", "wrapper.log"]}, "!logsurf level=error n=50 wrapper.log"),
            ("http", {"url": "https://10.0.0.5/x?author=a&oauth_state=b&sessions=3&page=2"},
             "!http https://10.0.0.5/x?author=a&oauth_state=b&sessions=3&page=2"),
        ],
    )  # fmt: skip
    def test_composes_the_documented_shape(self, command, args, expected):
        assert build_cmdline(command, args, T) == expected

    @pytest.mark.parametrize(
        "command,args,target,why",
        [
            ("groovy", {}, T, "unknown or disallowed"),
            # The target host comes from the device record only.
            ("ping", {}, NO_DEVICE, "device_id is required"),
            ("ping", {"host": "10.0.0.9"}, T, "'host' is not accepted"),
            ("snmpwalk", {"host": "10.0.0.9"}, T, "'host' is not accepted"),
            # The portal check is pinned to the configured portal.
            ("checkserverconnectivity", {"host": "attacker.example.net"}, T, "'host' is not accepted"),
            ("checkserverconnectivity", {}, Target(collector_id=7), "portal host is not known"),
            # Unknown keys are refused per command, naming the keys it takes.
            ("ping", {"bogus": "x", "community": "public"}, T, "ping takes count, type; not bogus, community"),
            ("uptime", {"verbose": True}, T, "uptime takes no arguments; not verbose"),
            ("nslookup", {"extra_hosts": ["other.example.net"]}, T, "not extra_hosts"),
            ("snmpwalk", {"oid": ".1"}, T, "root of the tree"),
            ("snmpwalk", {"oid": "1.3.6.1"}, T, "root of the tree"),
            ("tlist", {}, T, "must be filtered"),
            # The URL must name the device, with no credentials.
            ("http", {"url": "10.0.0.5"}, T, "http:// or https://"),
            ("http", {"url": "ftp://10.0.0.5/x"}, T, "http:// or https://"),
            ("http", {"url": "http://169.254.169.254/latest/meta-data/"}, T, "must point at the device itself"),
            ("http", {"url": "https://device-example-2.example.net/"}, T, "must point at the device itself"),
            ("http", {"url": "https://admin:s3cret@10.0.0.5/"}, T, "user information"),
            ("http", {"url": "https://admin@10.0.0.5/"}, T, "user information"),
            ("http", {"url": "https://10.0.0.5/?password=s3cret"}, T, "credential-named parameter 'password'"),
            ("http", {"url": "https://10.0.0.5/x?a=1&apiKey=s3cret"}, T, "credential-named parameter 'apiKey'"),
            ("http", {"url": "https://10.0.0.5/x?access_token=s3cret"}, T, "credential-named parameter"),
            ("http", {"url": "https://10.0.0.5/x?user_name=admin"}, T, "credential-named parameter"),
            ("http", {"url": "https://10.0.0.5:99999/"}, T, "not a valid URL"),
            ("http", {"url": "http:///x"}, T, "must name the device's host"),
            ("http", {"url": "https://10.0.0.5/a b"}, T, "whitespace"),
            ("http", {}, T, "'url' is required"),
            ("sslcerts", {}, T, "'port' is required"),
            # One anchored WQL SELECT, never a key=value token.
            ("wmi", {"query": "delete from x"}, T, "one WQL SELECT"),
            ("wmi", {"query": "select a from b; select c from d"}, T, "one WQL SELECT"),
            ("wmi", {"query": "select * from Win32_Service h=evilhost"}, T, "one WQL SELECT"),
            ("wmi", {"query": "select * from Win32_Service where Name = 'x' h=evilhost"}, T, "key=value"),
            ("wmi", {"query": "select * from Win32_Service where Name='x'"}, T, "key=value"),
            ("wmi", {"query": "select * from Win32_Service where Name = `x`"}, T, "character the tool does not allow"),
            # getconfig reads only thread-pool and timeout keys.
            ("getconfig", {"key": "proxy.pass"}, T, "thread pool or timeout"),
            ("getconfig", {"key": "collector.wmi.threadpool.x"}, T, "thread pool or timeout"),
            ("getconfig", {"key": "wmi.threadpool"}, T, "thread pool or timeout"),
            ("getconfig", {}, T, "'key' is required"),
            ("logsurf", {"files": ["../secrets.txt"]}, T, "may only name"),
            ("perf", {"type": "cpu", "dsFilterColumn": "nan"}, T, "only to type=ds"),
            ("ping", {"count": 500}, T, "between"),
            ("ping", {"count": True}, T, "whole number"),
            ("snmpwalk", {"oid": "1.03.6.1"}, T, "invalid value"),
            ("snmpwalk", {"oid": ".1.3.6.01"}, T, "invalid value"),
            ("snmpwalk", {"oid": "\u0661.\u0663.\u0666.\u0661"}, T, "invalid value"),
            ("snmpwalk", {"oid": ".1.3.6.1."}, T, "invalid value"),
            ("http", {"url": "http://10.0.0.5/#key=abc"}, T, "fragment"),
            ("http", {"url": "http://10.0.0.5/x;pw=1"}, T, "';' parameters"),
            ("http", {"url": "http://10.0.0.5/x?a=1;pw=x"}, T, "';' parameters"),
            ("http", {"url": "http://10.0.0.5/x?authorization=abc"}, T, "credential-named parameter"),
            ("http", {"url": "http://10.0.0.5/x?authCode=abc"}, T, "credential-named parameter 'authCode'"),
            ("http", {"url": "http://10.0.0.5/a\x00b"}, T, "printable ASCII"),
            ("http", {"url": "http://10.0.0.5/a\x7fb"}, T, "printable ASCII"),
            ("http", {"url": "http://10.0.0.5/?q=\u202e"}, T, "printable ASCII"),
            ("ping", {"count": float("inf")}, T, "whole number"),
            ("sslcerts", {"port": 1.5}, T, "whole number"),
            ("snmpget", {"oids": [f".1.3.6.1.2.1.1.{i}.0" for i in range(11)]}, T, "1 to 10 values"),
            ("snmpdiagnose", {"oids": [f".1.3.6.1.2.1.1.{i}.0" for i in range(6)]}, T, "0 to 5 values"),
            ("http", {"url": "http://10.0.0.5/x?pw=1"}, T, "credential-named parameter 'pw'"),
            ("http", {"url": "http://10.0.0.5/x?jwt=1"}, T, "credential-named parameter 'jwt'"),
            ("http", {"url": "http://10.0.0.5/x?sid=1"}, T, "credential-named parameter 'sid'"),
            ("http", {"url": "http://10.0.0.5/x?bearer=1"}, T, "credential-named parameter 'bearer'"),
            ("http", {"url": "http://10.0.0.5/x?auth=1"}, T, "credential-named parameter 'auth'"),
            ("http", {"url": "http://10.0.0.5/x?accessToken=1"}, T, "credential-named parameter"),
            ("http", {"url": "http://10.0.0.5/" + "a" * 2100}, T, "longer than 2048"),
            ("logsurf", {"files": {"wrapper.log": 1}}, T, "must be a list"),
            # Every list item and every enumerated value is checked, so none can add a parameter.
            ("snmpget", {"oids": ["h=x"]}, T, "not a valid value for 'oids'"),
            ("snmpdiagnose", {"oids": [".1.3.6.1.2.1.1.5.0", "h=x"]}, T, "not a valid value for 'oids'"),
            ("ping", {"type": "all h=x"}, T, "'type' must be one of"),
            ("perf", {"h": "x h=y"}, T, "'h' has an invalid value"),
        ],
    )  # fmt: skip
    def test_refuses_before_sending(self, command, args, target, why):
        with pytest.raises(ToolRejectionError, match=why):
            build_cmdline(command, args, target)

    @pytest.mark.parametrize(
        "host,url",
        [
            ("device-example-1.example.net", "https://DEVICE-EXAMPLE-1.example.net/health"),
            ("2001:db8::1", "https://[2001:db8::1]:8443/health"),
            ("[2001:db8::1]", "https://[2001:DB8::1]/health"),
            ("DEVICE-EXAMPLE-1.example.net", "https://device-example-1.example.net/health"),
        ],
    )
    def test_url_host_match_ignores_case_and_brackets(self, host, url):
        target = Target(collector_id=7, host=host)
        assert build_cmdline("http", {"url": url}, target) == f"!http {url}"

    def test_url_with_a_trailing_dot_host_is_another_host(self):
        with pytest.raises(ToolRejectionError, match="device itself"):
            build_cmdline("http", {"url": "https://10.0.0.5./"}, T)

    @pytest.mark.parametrize("name", ["cookie", "otp", "accesskey", "authcode", "adminPw", "dbPwd"])
    def test_more_credential_query_names_are_refused(self, name):
        with pytest.raises(ToolRejectionError, match="credential-named parameter"):
            build_cmdline("http", {"url": f"https://10.0.0.5/x?{name}=1"}, T)

    @pytest.mark.parametrize("name", ["priv", "snmp.priv", "snmp.auth", "ssh.key"])
    def test_query_names_the_audit_log_masks_are_refused(self, name):
        """The URL check refuses every name lm_mcp.logging.is_sensitive_key masks, so the
        audit line and the URL guard read one credential rule."""
        with pytest.raises(ToolRejectionError, match=f"credential-named parameter '{name}'"):
            build_cmdline("http", {"url": f"https://10.0.0.5/x?{name}=1"}, T)


class TestWhereGrammar:
    """The 2026-10-31 review, item 2: a WHERE clause cannot carry a command head or a
    key=value token, since check_cmdline reads only the head of the line."""

    @pytest.mark.parametrize(
        "where",
        [
            "Name = 'a' !restart",  # the review's first shape: a command head after a comparison
            "Name = 'a' ! = 'b'",
            "Name = 'a!'",
            "!Name = 'a'",
            "Name !! 'a'",
        ],
    )
    def test_a_bang_is_allowed_only_directly_before_an_equals(self, where):
        with pytest.raises(ToolRejectionError, match="'!' is allowed only as '!='"):
            build_cmdline("wmi", {"query": f"select * from Win32_Service where {where}"}, T)

    @pytest.mark.parametrize(
        "where",
        [
            "Name = 'a' 'h'=evilhost",  # the review's second shape: a quoted key
            "Name = 'a=b'",
            "State == 'x'",
            "Name = 'a' %=x",
            "(Name)= 'a'",
            "Name='x'",
        ],
    )
    def test_an_equals_needs_a_space_or_an_operator_before_it(self, where):
        with pytest.raises(ToolRejectionError, match="key=value"):
            build_cmdline("wmi", {"query": f"select * from Win32_Service where {where}"}, T)

    @pytest.mark.parametrize(
        "where",
        [
            "Name = 'Spooler'",
            "State != 'Running'",
            "State <> 'Running'",
            "ProcessId >= 4",
            "ProcessId <= 4",
            "ProcessId > 4 AND ProcessId < 9",
            "Name LIKE 'svc%'",
        ],
    )
    def test_comparison_operators_build(self, where):
        query = f"select * from Win32_Service where {where}"
        assert build_cmdline("wmi", {"query": query}, T) == f"!wmi h=10.0.0.5 {query}"


class TestAllowlist:
    def test_the_allowlist_has_29_heads_one_per_command(self):
        assert len(ALLOWED_HEADS) == 29
        assert len(COMMANDS) == 29

    def test_every_command_builds_an_allowlisted_head(self):
        minimal = {
            "getconfig": {"key": "collector.wmi.timeout"},
            "tlist": {"c": "wmi"},
            "snmpget": {"oids": [".1.3.6.1.2.1.1.5.0"]},
            "cim": {"class": "CIM_ComputerSystem"},
            "http": {"url": "https://10.0.0.5/"},
            "sslcerts": {"port": 443},
        }
        heads = {build_cmdline(name, minimal.get(name, {}), T).split()[0][1:] for name in COMMANDS}
        assert heads == ALLOWED_HEADS

    def test_no_allowlisted_head_is_blocked(self):
        assert not (ALLOWED_HEADS & BLOCKED)

    def test_debughistory_is_not_offered(self):
        assert "debughistory" not in COMMANDS

    @pytest.mark.parametrize("command", sorted(COMMANDS))
    def test_every_command_refuses_a_key_it_does_not_take_and_names_its_keys(self, command):
        takes = ", ".join(sorted(COMMANDS[command].keys)) or "no arguments"
        with pytest.raises(ToolRejectionError, match=f"^{command} takes {takes}; not zzz$"):
            build_cmdline(command, {"zzz": 1}, T)

    @pytest.mark.parametrize(
        "line",
        [
            "!groovy println 1",
            "!restart",
            "!shealthcheck func=detail collector=7\n!restart",
            "!wmi username=x password=y h=10.0.0.5 select * from a",
            "!snmpwalk community=public 10.0.0.5 .1.3.6.1.2.1.1",
            "!http https://10.0.0.5/?password=s3cret",
            "!http https://10.0.0.5/?x=1&token=s3cret",
            "uptime",
            # The final check is an allowlist, with the two fixed forms.
            "!debughistory",
            "!getconfig proxy.pass",
            "!shealthcheck func=trigger",
            "!shealthcheck func=detail collector=7 extra",
            " !uptime",
        ],
    )
    def test_final_guard(self, line):
        with pytest.raises(ToolRejectionError):
            check_cmdline(line)

    def test_argument_names_must_be_strings(self):
        with pytest.raises(ToolRejectionError, match="argument names must be strings"):
            build_cmdline("ping", {1: "x"}, T)

    def test_a_builder_type_fault_is_a_refusal(self, monkeypatch):
        """A builder that trips on a value of the wrong type refuses; it never escapes."""

        def trips(a, t):
            raise TypeError("unsupported operand")

        monkeypatch.setitem(
            COMMANDS, "uptime", dataclasses.replace(COMMANDS["uptime"], build=trips)
        )
        with pytest.raises(ToolRejectionError, match="wrong type"):
            build_cmdline("uptime", {}, T)


class TestArgumentTypes:
    """Odd argument types are refusals, never unexpected errors."""

    @pytest.mark.parametrize(
        "command,args,why",
        [("snmpget", {"oids": 5}, "'oids' must be a list"),
         ("snmpdiagnose", {"oids": {"a": 1}}, "'oids' must be a list"),
         ("snmpwalk", {"oid": "1.3.6.1." + "9" * 4400}, "invalid value"),
         ("ping", {"count": [1]}, "whole number"),
         ("logsurf", {"files": 5}, "must be a list")],
    )  # fmt: skip
    def test_odd_values_are_refused(self, command, args, why):
        with pytest.raises(ToolRejectionError, match=why):
            build_cmdline(command, args, T)

    @pytest.mark.parametrize("value,expected", [("7", 7), (7, 7), ("\u00b2", None), (-3, None),
                                                ("1234567890123", None), (True, None)])  # fmt: skip
    def test_counts_are_plain_digits(self, value, expected):
        assert cd._count(value) == expected

    @pytest.mark.parametrize(
        "oid", [".1.3.6.1.2", ".1.3.6.1.2.1", ".1.3.6.1.4", "1.3.6.1.4.1", "0", "2", ".1"]
    )
    def test_the_tops_of_the_tree_are_refused(self, oid):
        with pytest.raises(ToolRejectionError, match="walk a subtree"):
            build_cmdline("snmpwalk", {"oid": oid}, T)

    @pytest.mark.parametrize("h", ["*", "*.*", "%", "[*]", "*-*"])
    def test_a_filter_with_no_letter_or_digit_is_unfiltered(self, h):
        with pytest.raises(ToolRejectionError, match="must be filtered"):
            build_cmdline("tlist", {"h": h}, T)


class TestRequest:
    """Everything the caller passes is checked before any call is made."""

    @pytest.mark.parametrize("name", ["collector_id", "device_id"])
    @pytest.mark.parametrize("value", [0, -4, True, 7.0, "7", 10**13])
    def test_ids_must_be_positive_whole_numbers(self, name, value):
        with pytest.raises(ToolRejectionError, match=f"'{name}' must be a positive whole number"):
            request(**{name: value})

    @pytest.mark.parametrize(
        "kwargs",
        [{"budget_seconds": float("nan")}, {"budget_seconds": float("inf")},
         {"budget_seconds": "soon"}, {"budget_seconds": True}, {"budget_seconds": 10**400},
         {"max_output_chars": float("nan")}, {"max_output_chars": "1e9"},
         {"max_output_chars": float("-inf")}],
    )  # fmt: skip
    def test_budgets_must_be_finite_numbers(self, kwargs):
        with pytest.raises(ToolRejectionError, match="must be finite numbers"):
            request(**kwargs)

    @pytest.mark.parametrize(
        "budget,cap,expected",
        [(0.1, 10, (2.0, 500)), (999, 20_000, (BUDGET_MAX, 20_000)), (15, 1_000.7, (15.0, 1_000))],
    )
    def test_budget_and_output_are_clamped(self, budget, cap, expected):
        req = request(budget_seconds=budget, max_output_chars=cap)
        assert (req.budget_seconds, req.max_output_chars) == expected

    @pytest.mark.parametrize(
        "url", ["http://[::1", "http://[10.0.0.5]/", "https://10.0.0.5:99999/"]
    )
    def test_an_http_url_that_does_not_parse_is_refused(self, url):
        with pytest.raises(ToolRejectionError, match="not a valid URL"):
            request("http", collector_id=None, device_id=5, args={"url": url})

    @pytest.mark.parametrize("command", [["uptime"], {"x": 1}, "groovy", None])
    def test_an_unknown_command_is_refused(self, command):
        with pytest.raises(ToolRejectionError, match="unknown or disallowed command"):
            request(command)

    @pytest.mark.parametrize("args", [["x"], "count=4", 5])
    def test_args_must_be_an_object(self, args):
        with pytest.raises(ToolRejectionError, match="'args' must be an object"):
            request(args=args)

    def test_a_device_probe_needs_device_id(self):
        with pytest.raises(ToolRejectionError, match="ping needs device_id"):
            request("ping", collector_id=7)

    def test_a_collector_or_device_is_required(self):
        with pytest.raises(ToolRejectionError, match=r"collector_id \(or device_id\) is required"):
            request("uptime", collector_id=None)

    @pytest.mark.parametrize(
        "command,args",
        [("ping", {"count": 999}), ("ping", {"count": float("inf")}), ("ping", {"bogus": 1}),
         ("wmi", {"query": "select * from X h=evil"}),
         ("wmi", {"query": "select * from Win32_Service where Name = 'a' !restart"}),
         ("http", {"url": "https://admin:x@10.0.0.42/"}), ("http", {"url": "https://10.0.0.42/?password=x"}),
         ("http", {"url": "ftp://10.0.0.42/"})],
    )  # fmt: skip
    def test_argument_values_are_checked_before_the_device_is_read(self, command, args):
        with pytest.raises(ToolRejectionError):
            request(command, collector_id=None, device_id=42, args=args)

    @pytest.mark.parametrize("url", ["https://10.0.0.42:99999/", "http://[::1/x", "http://[x]/"])
    def test_a_url_that_does_not_parse_is_refused_before_the_device_is_read(self, caplog, url):
        """The same refusal the builder gives, and nothing swallowed on the way to it."""
        with (
            caplog.at_level(logging.DEBUG),
            pytest.raises(ToolRejectionError, match="not a valid URL"),
        ):
            request("http", collector_id=None, device_id=42, args={"url": url})
        assert caplog.records == []

    def test_the_portal_check_needs_the_portal_host(self):
        with pytest.raises(ToolRejectionError, match="portal host is not known"):
            request("checkserverconnectivity", portal_host=None)

    def test_a_good_request_is_returned_checked(self):
        req = request("ping", collector_id=None, device_id=42, args={"count": 4})
        assert req == cd.Request(
            command="ping", args={"count": 4}, collector_id=None, device_id=42,
            budget_seconds=BUDGET_DEFAULT, max_output_chars=OUTPUT_DEFAULT,
        )  # fmt: skip


class TestTargetFromRecord:
    """The device record, not the caller, names the host and the collector."""

    def test_the_record_names_the_host_and_the_collector(self):
        assert target_from_record("ping", SERVED, None, PORTAL) == Target(
            collector_id=26, host="127.0.0.1", portal_host=PORTAL
        )

    @pytest.mark.parametrize(
        "record_id", [-4, -2, None, -7, True, 7.0, "1234567890123", "\u00b2", 10**13]
    )
    def test_a_device_with_no_collector_is_refused(self, record_id):
        record = {**SERVICE, "currentCollectorId": record_id}
        with pytest.raises(ToolRejectionError, match="names no collector"):
            target_from_record("ping", record, None, PORTAL)

    @pytest.mark.parametrize("record", [SERVICE, CLOUD])
    def test_live_collectorless_records_are_refused_even_with_a_collector_given(self, record):
        with pytest.raises(ToolRejectionError, match="names no collector"):
            target_from_record("ping", record, 7, PORTAL)

    def test_a_digit_string_collector_id_on_the_record_is_read(self):
        record = {**SERVED, "currentCollectorId": "7"}
        assert target_from_record("ping", record, None, PORTAL).collector_id == 7

    def test_a_probe_cannot_run_on_another_collector(self):
        with pytest.raises(
            ToolRejectionError, match=r"collector that serves the device \(26\), not collector 99"
        ):
            target_from_record("ping", SERVED, 99, PORTAL)

    def test_a_device_is_bound_to_its_collector_for_every_command(self):
        with pytest.raises(ToolRejectionError, match="collector that serves the device"):
            target_from_record("uptime", SERVED, 99, PORTAL)

    def test_a_collector_command_given_a_device_runs_on_its_collector(self):
        assert target_from_record("uptime", SERVED, None, PORTAL) == Target(
            collector_id=26, host=None, portal_host=PORTAL
        )

    def test_a_collector_command_given_a_collectorless_device_needs_a_collector(self):
        with pytest.raises(ToolRejectionError, match="names no collector"):
            target_from_record("uptime", SERVICE, None, PORTAL)

    def test_a_collector_command_given_a_collectorless_device_and_a_collector_runs_there(self):
        assert target_from_record("uptime", SERVICE, 7, PORTAL).collector_id == 7

    @pytest.mark.parametrize("name", ["bad host; !restart", "-n", "", None, "a b"])
    def test_a_device_name_that_is_not_a_plain_host_is_refused(self, name):
        with pytest.raises(ToolRejectionError, match="plain hostname"):
            target_from_record("ping", {**SERVED, "name": name}, None, PORTAL)

    @pytest.mark.parametrize("record", [[1, 2], None, "x"])
    def test_a_device_record_that_is_not_an_object_is_refused(self, record):
        with pytest.raises(ToolRejectionError, match="could not be read"):
            target_from_record("ping", record, None, PORTAL)

    def test_a_long_device_name_is_refused_by_the_final_guard(self):
        record = {**SERVED, "name": "d" * 3000}
        target = target_from_record("ping", record, None, PORTAL)
        with pytest.raises(ToolRejectionError, match="longer than 2048"):
            build_cmdline("ping", {}, target)


class TestRedaction:
    @pytest.mark.parametrize(
        "text,expected",
        [
            # an unquoted value runs to the line end, or to where the next key= or key: starts
            ("password=abc next", "password=***"),
            ("wmi.pass=my secret pass", "wmi.pass=***"),
            ("wmi.pass=hun,ter2 next", "wmi.pass=***"),
            ("password=hun;ter2", "password=***"),
            ("password=abc, user=x", "password=***, user=x"),
            ("token=x,secret=y;apikey=z", "token=***,secret=***;apikey=***"),
            ("clientSecret=a aws.secretKey=b apiToken=c", "clientSecret=*** aws.secretKey=*** apiToken=***"),
            ("-Dpassword=s3cret -Dwmi.pass=x", "-Dpassword=*** -Dwmi.pass=***"),
            ("accessToken: x dbPassword=y", "accessToken: ***"),
            ("password=x dbPassword=y", "password=*** dbPassword=***"),
            ("password: hunter two", "password: ***"),
            ("password:hunter two", "password:***"),
            ("password = hunter two\nnext", "password = ***\nnext"),
            ("password: abc:def", "password: ***"),
            ("snmp.community: public", "snmp.community: ***"),
            ("ssh.pass: abc", "ssh.pass: ***"),
            ("wmi.pass=hunter2", "wmi.pass=***"),
            ("x dbPassword=y", "x dbPassword=***"),
            ("x-api-key: abc", "x-api-key: ***"),
            ("-Djavax.net.ssl.keyStorePassword=changeit", "-Djavax.net.ssl.keyStorePassword=***"),
            ("a.b.password=x ns:token=y", "a.b.password=*** ns:token=***"),
            ("user=alice state=Running", "user=alice state=Running"),
            # one-case compound keys, as LogicMonitor property names are case-insensitive
            ("wmiPass=x -Dpass=y x_pw=z x-pw=1", "wmiPass=*** -Dpass=*** x_pw=*** x-pw=***"),
            ("<ns:pw>x</ns:pw> SID=S-1-5-21-1", "<ns:pw>***</ns:pw> SID=S-1-5-21-1"),
            ("snmp.authtoken=hunter2", "snmp.authtoken=***"),
            ("SNMP.PRIVTOKEN: x", "SNMP.PRIVTOKEN: ***"),
            ("azure.clientsecret=x DBPASSWORD=y", "azure.clientsecret=*** DBPASSWORD=***"),
            ("snmpcommunity=x adminpassword=y", "snmpcommunity=*** adminpassword=***"),
            # the review, item 1: dotted property keys the audit log masks are masked here too
            ("meraki.api.key=abc123def", "meraki.api.key=***"),
            ("ssh.key=abc123def", "ssh.key=***"),
            ("api.key: abc123def", "api.key: ***"),
            ('{"name":"meraki.api.key","value":"abc123def"}', '{"name":"meraki.api.key","value":"***"}'),
            ("snmp.auth=x snmp.priv=y", "snmp.auth=*** snmp.priv=***"),
            ("<snmp.priv>x</snmp.priv>", "<snmp.priv>***</snmp.priv>"),
            # an undotted key, an identifier and a word that only holds a credential word stay
            ("key=abc device.id=7 sort.keyword=x snmp.authid=3", "key=abc device.id=7 sort.keyword=x snmp.authid=3"),
            # quoted values, with escapes, on one line; an empty one is kept, as it is a finding
            ('authToken="a b c" tail', 'authToken="***" tail'),
            ('{"password": "s3cret"}', '{"password": "***"}'),
            ("'password': 'x'", "'password': '***'"),
            ('"api_key":"k1"', '"api_key":"***"'),
            ('"password":"hun\\"ter2", "x": 1', '"password":"***", "x": 1'),
            ('password="hun', "password=***"),
            ('password="', "password=***"),
            ("password=abc<br>next", "password=***<br>next"),
            ('password="a\nnext"', 'password=***\nnext"'),
            ('"password": ""', '"password": ""'),
            ("wmi.pass= wmi.user=admin", "wmi.pass= wmi.user=admin"),
            # an unquoted value inside a JSON string stops at that string's closing quote
            ('{"detail": "proxy pass: none", "status": "OK"}', '{"detail": "proxy pass: ***", "status": "OK"}'),
            ('{"token":null,"status":"ok"}', '{"token":***,"status":"ok"}'),
            # flags
            ("--password s3cret", "--password ***"),
            ('--password "two words" next', '--password "***" next'),
            ("--password hun ter2", "--password ***"),
            ("--Dpassword hunter2", "--Dpassword ***"),
            # headers and bearer tokens
            ("Authorization: Basic dXNlcjpw", "Authorization: ***"),
            ("Authorization: Bearer abc.def", "Authorization: ***"),
            ("Authorization: abc123", "Authorization: ***"),
            ("Authorization=Basic abc", "Authorization=***"),
            ('{"Authorization": "Bearer abc"}', '{"Authorization": "***"}'),
            ("log: Bearer abc.def ok", "log: Bearer *** ok"),
            # base64 padding never reads as the next key
            ("Authorization: Basic YWRtaW46aHVudGVyMg==", "Authorization: ***"),
            ("Authorization: Bearer abc123=", "Authorization: ***"),
            ("token: abc def==", "token: ***"),
            ("password: correct horse=battery", "password: ***"),
            ("password=abc def== user=x", "password=*** user=x"),
            # markup and JSON punctuation end a value, so the rest still reads true
            ('<add key="Conn" value="Server=x;Password=hunter2"/> <add key="Mode" value="prod"/>',
             '<add key="Conn" value="Server=x;Password=***"/> <add key="Mode" value="prod"/>'),
            ('<label for="password">Password:</label><input name="p">',
             '<label for="password">Password:</label><input name="p">'),
            ('{"token": null, "host": "h"}', '{"token": ***, "host": "h"}'),
            # single-dash flags, and the other words the URL check refuses
            ("keytool -storepass changeit -keypass x", "keytool -storepass *** -keypass ***"),
            ("https://h/x?sig=SECRETSIG&a=1", "https://h/x?sig=***&a=1"),
            ("pw=hunter2 otp=123456", "pw=*** otp=***"),
            ("curl -u admin:hunter2 https://h/ --user ops:s3cret", "curl -u admin:*** https://h/ --user ops:***"),
            # arrays and objects under a secret key, on one line or several
            ('{"snmp.community": ["public", "private", "s3cret"], "a": 1}', '{"snmp.community": ***, "a": 1}'),
            ('"password": [\n  "a",\n  "b"\n],\n"x": 1', '"password": ***,\n"x": 1'),
            ('{"token": {"v": "x", "w": ["y"]}}', '{"token": ***}'),
            ('{"a":{"password":1}}', '{"a":{"password":***}}'),
            # pwd as a key in every form, except a working directory
            ('{"pwd":"hunter2"} pwd: hunter2', '{"pwd":"***"} pwd: ***'),
            ("<pwd>hunter2</pwd>", "<pwd>***</pwd>"),
            ('<add key="pwd" value="x"/>', '<add key="pwd" value="***"/>'),
            ("pwd: ~/work pwd: C:\\Users", "pwd: ~/work pwd: C:\\Users"),
            # name and value as elements (Hadoop, Spring, .NET)
            ("<property><name>x.password</name><value>hunter2</value></property>",
             "<property><name>x.password</name><value>***</value></property>"),
            ("<entry>\n  <key>password</key>\n  <value>s3cret</value>\n</entry>",
             "<entry>\n  <key>password</key>\n  <value>***</value>\n</entry>"),
            ("<name>password</name><value><![CDATA[hunter2]]></value>",
             "<name>password</name><value>***</value>"),
            ("<name>password</name><value><string>hunter2</string></value>",
             "<name>password</name><value>***</value>"),
            ("<property><name>x.user</name><value>admin</value></property>",
             "<property><name>x.user</name><value>admin</value></property>"),
            # without braces, a value field is paired only with a nearby secret name
            ("name: token, value: 1\n" + "x " * 400 + "\nvalue: 2", "name: token, value: ***\n" + "x " * 400 + "\nvalue: 2"),
            # URL authority ends where an authority cannot go on
            ("url=http://10.0.0.5,owner=ops@example.net", "url=http://10.0.0.5,owner=ops@example.net"),
            ('{"url":"http://10.0.0.5","owner":"ops@example.net"}', '{"url":"http://10.0.0.5","owner":"ops@example.net"}'),
            ("https:\\/\\/admin:hunter2@10.0.0.5\\/x", "https:\\/\\/admin:***@10.0.0.5\\/x"),
            # stops at /> and a bearer word inside another word is not a bearer token
            ("<p password=x/>tail", "<p password=***/>tail"),
            ("forebearer note", "forebearer note"),
            # ODBC
            ("Driver=x;Pwd=hunter2;Uid=a", "Driver=x;Pwd=***;Uid=a"),
            ("pwd={hun;ter2};uid=a", "pwd=***;uid=a"),
            ("pwd = x", "pwd = ***"),
            # name/value pairs in one tag or object, in any order, across lines and fields
            ('<property name="wmi.pass" value="hunter2"/>', '<property name="wmi.pass" value="***"/>'),
            ('<property value="hunter2" name="wmi.pass"/>', '<property value="***" name="wmi.pass"/>'),
            ('<property name="password" type="string" value="hunter2"/>', '<property name="password" type="string" value="***"/>'),
            ('{"name": "wmi.pass", "value": "x"}', '{"name": "wmi.pass", "value": "***"}'),
            ('{"name":"wmi.pass","type":"custom","value":"hunter2"}', '{"name":"wmi.pass","type":"custom","value":"***"}'),
            ('{\n "name": "wmi.pass",\n "value": "hunter2"\n}', '{\n "name": "wmi.pass",\n "value": "***"\n}'),
            ('<p name="wmi.pass" value="x"/>next', '<p name="wmi.pass" value="***"/>next'),
            ('<property name="wmi.user" value="admin"/>', '<property name="wmi.user" value="admin"/>'),
            ('{"name": "wmi.pass", "value": ""}', '{"name": "wmi.pass", "value": ""}'),
            # inside one object or tag, the value goes with the name however far apart
            ('{"name":"db.password","description":"' + "d" * 600 + '","value":"hunter2"}',
             '{"name":"db.password","description":"' + "d" * 600 + '","value":"***"}'),
            ('<p name="db.password" note="' + "d" * 600 + '" value="hunter2"/>',
             '<p name="db.password" note="' + "d" * 600 + '" value="***"/>'),
            ('{"name":"' + "a" * 600 + '.password","value":"hunter2"}',
             '{"name":"' + "a" * 600 + '.password","value":"***"}'),
            ("authCode=x auth_code: y", "authCode=*** auth_code: ***"),
            ('name="wmi.pass" value=hunter2', 'name="wmi.pass" value=***'),
            ("key: wmi.pass, value: hunter2", "key: wmi.pass, value: ***"),
            # a value on the next, indented line
            ("password:\n  hunter2", "password:\n  ***"),
            ('{\n "password":\n   "x",\n "a": 1\n}', '{\n "password":\n   "***",\n "a": 1\n}'),
            ("password:\n  user: x", "password:\n  user: x"),
            ("password:\nnext", "password:\nnext"),
            # element content, by tag or by a name/key attribute: children, CDATA, line breaks
            ("<password>p1</password>", "<password>***</password>"),
            ("<snmp.community>c1</snmp.community>", "<snmp.community>***</snmp.community>"),
            ('<Password type="x">hunter2</Password>', '<Password type="x">***</Password>'),
            ('<entry key="wmi.pass">x</entry>', '<entry key="wmi.pass">***</entry>'),
            ('<entry key="wmi.pass"><value>x</value></entry>', '<entry key="wmi.pass">***</entry>'),
            ('<property name="password"><value>x</value></property>', '<property name="password">***</property>'),
            ("<password><![CDATA[x y]]></password>", "<password>***</password>"),
            ("<password>\n hunter2\n</password>", "<password>***</password>"),
            ("<ns:password>x</ns:password>", "<ns:password>***</ns:password>"),
            ("<password></password>", "<password></password>"),
            ('<entry key="wmi.user">admin</entry>', '<entry key="wmi.user">admin</entry>'),
            # URLs: userinfo is masked; a port and path that hold an '@' are left alone
            ("http://admin:s3cret@10.0.0.5/x", "http://admin:***@10.0.0.5/x"),
            ("http://u:p@ss@h/x", "http://u:***@h/x"),
            ("http://u:pa%2Fss@h/x", "http://u:***@h/x"),
            ("https://admin:123456@10.0.0.5/", "https://admin:***@10.0.0.5/"),
            ("https://tok123@10.0.0.5:8443/x@y", "https://***@10.0.0.5:8443/x@y"),
            ("https://admin:s3cret@10.0.0.5/api/users/bob@example.net", "https://admin:***@10.0.0.5/api/users/bob@example.net"),
            ("https://tok123@h/x", "https://***@h/x"),
            ("https://h/x?email=a@example.net", "https://h/x?email=a@example.net"),
            ("https://registry.example.net/@scope/pkg", "https://registry.example.net/@scope/pkg"),
            ("http://10.0.0.1:8080/api/users/admin@example.net", "http://10.0.0.1:8080/api/users/admin@example.net"),
            ("https://[fe80::1]:8443/a/b@c", "https://[fe80::1]:8443/a/b@c"),
            ("https://h/a:b@c", "https://h/a:b@c"),
            # private keys
            (f"{PEM_BEGIN}\nMIIabc\n{PEM_END}\nnext", f"{PEM_BEGIN}***{PEM_END}\nnext"),
            (f"{PGP_BEGIN}\nlQOYBF\n-----END PGP", f"{PGP_BEGIN}***-----END PGP"),
            # other credential words
            ("credential=abc signature=def", "credential=*** signature=***"),
            ("session_id=hunter2 jwt=x", "session_id=*** jwt=***"),
            # not secrets
            ("tokenizer=on passwordless=true superpass=x", "tokenizer=on passwordless=true superpass=x"),
            ("compass=north bypass=1 passes=3 tokens=5", "compass=north bypass=1 passes=3 tokens=5"),
            ("password=\nnext_line", "password=\nnext_line"),
            ("pwd: /usr/local/bin", "pwd: /usr/local/bin"),
        ],
    )  # fmt: skip
    def test_masks_secret_values(self, text, expected):
        assert redact(text) == expected

    @pytest.mark.parametrize(
        "key",
        ["password", "passwd", "pass", "passphrase", "secret", "token", "community", "credential",
         "credentials", "signature", "authorization", "cookie", "bearer", "apikey", "api_key",
         "api-key", "accesskey", "access_key", "access-key", "privatekey", "private_key",
         "private-key", "secretkey", "secret_key", "secret-key", "sessionid", "session_id",
         "session-id", "storepass", "keypass", "authcode", "auth_code", "auth-code", "jwt", "pw",
         "pwd", "sig", "otp", "key", "api.key", "auth", "priv"],
    )  # fmt: skip
    def test_each_credential_word_is_masked(self, key):
        """Written out, not read from the code, so dropping a word fails here."""
        assert redact(f"svc.{key}=hunter2") == f"svc.{key}=***"

    @pytest.mark.parametrize(
        "key",
        ["snmp.auth", "snmp.priv", "snmp.community", "snmp.authToken", "snmp.privToken", "ssh.key",
         "ssh.pass", "wmi.pass", "meraki.api.key", "api.key", "aws.secretKey", "jdbc.pass",
         "esx.pass", "x.signature", "a.sig", "x.credentials", "device.id", "sort.keyword",
         "snmp.authid"],
    )  # fmt: skip
    def test_a_dotted_key_is_secret_wherever_the_audit_rule_says_so(self, key):
        """One credential rule decides the audit line and the masked output (the review, item 1)."""
        assert cd._is_secret_key(key) or not is_sensitive_key(key)

    def test_long_values_fail_closed(self):
        """A value longer than a pattern reads is masked whole, not left in the clear."""
        long = "z" * 5000
        assert long not in redact(f'{{"name": "api.token", "value": "{long}"}}')
        assert long not in redact(f"<password>{long}</password>")
        assert long not in redact(f"<password>{long}<b>{long}</b></password>")
        assert "z" not in redact(f"<password>{long}")  # no closing tag at all
        assert "z" not in redact('"password": [' + '"z", ' * 2000 + "]")

    def test_values_parsed_from_output_are_masked(self):
        assert cd.redact_values({"a": ["password=x", {"b": "token: y"}], "n": 3}) == {
            "a": ["password=***", {"b": "token: ***"}],
            "n": 3,
        }

    def test_parsed_keys_and_name_value_pairs_are_masked(self):
        data = {
            "proxy.pass": "hunter2",
            "empty_password": "",
            "ssh.key": "k",
            "row": {"name": "wmi.pass", "value": "x"},
            "prop": {"name": "snmp.priv", "value": "y"},
        }
        assert cd.redact_values(data) == {
            "proxy.pass": "***",
            "empty_password": "",
            "ssh.key": "***",
            "row": {"name": "wmi.pass", "value": "***"},
            "prop": {"name": "snmp.priv", "value": "***"},
        }

    def test_the_live_health_check_masks_nothing_it_needs(self):
        """A real reply holds no secret: masking it changes only what reads as one."""
        assert redact(LIVE_HEALTH) == LIVE_HEALTH

    @pytest.mark.parametrize(
        "unit",
        ["-", "a-", "a_", "a=", "a:", "a://", 'x="', 'name="a-', "<a-", "<a ", "--a-", "a=b ",
         "pwd=", "pwd={;", "pwd={ ", "<password><![CDATA[", '<entry key="wmi.pass">', "<password>",
         "password=", 'password="', "password: a ", "Authorization: ", "Bearer ", "http://a:",
         "http://a:1/b@", '{"name": "password", ', '"value": "', PEM_BEGIN,
         "a=\"x\", ", "password: [", '"password": {"a": ', "<name>password</name><value>",
         "name: token, value: ", "curl -u a:", "a://x,", "<pw>", "<a.pw>x", "<ssh.key>"],
    )  # fmt: skip
    def test_hostile_output_is_masked_in_linear_time(self, unit):
        """Output is the device's: masking time must grow with its length, not its square."""
        assert_linear(redact, lambda n: (unit * (n // len(unit) + 1))[:n])


class TestUnclosedTags:
    """The review, item 6: many distinct unclosed tags cost one scan for closing tags."""

    @staticmethod
    def unclosed(n: int) -> str:
        units, size, i = [], 0, 0
        while size < n:
            unit = f"<a{i}.pw>x"
            units.append(unit)
            size += len(unit)
            i += 1
        return "".join(units)

    def test_100k_characters_of_unclosed_tags_mask_under_three_tenths_of_a_second(self):
        text = self.unclosed(100_000)
        best = []
        for _ in range(3):
            started = time.perf_counter()
            masked = redact(text)
            best.append(time.perf_counter() - started)
        assert min(best) < 0.3, best
        assert "x" not in masked and masked.count("***") == text.count("x")

    def test_the_closing_tags_are_found_in_one_pass(self, monkeypatch):
        calls = []
        real = cd._closing_tags

        def counted(text):
            calls.append(len(text))
            return real(text)

        monkeypatch.setattr(cd, "_closing_tags", counted)
        redact(self.unclosed(20_000))
        assert len(calls) == 1

    def test_unclosed_tags_mask_in_linear_time(self):
        assert_linear(redact, self.unclosed)

    @pytest.mark.parametrize(
        "text,expected",
        [("<a.pw>x<b>y</b></a.pw>tail", "<a.pw>***</a.pw>tail"),
         ("<a.pw>x</a.pw><a.pw>y</a.pw>", "<a.pw>***</a.pw><a.pw>***</a.pw>"),
         ("</a.pw><a.pw>x", "</a.pw><a.pw>***"),
         ("<a.pw>x</a.pwd>y", "<a.pw>***</a.pwd>y"),
         ("<a.pw>x<a.pw>y</a.pw>", "<a.pw>***</a.pw>")],
    )  # fmt: skip
    def test_a_tag_masks_to_its_own_next_close(self, text, expected):
        assert redact(text) == expected


class TestParser:
    def test_rates_lead_and_are_sorted(self):
        p = parse_health_check(LIVE_HEALTH)
        top = p["methods_by_all_nan_rate"][0]
        assert (top["method"], top["all_nan"], top["attempts"], top["all_nan_pct"]) == (
            "SCRIPT", 66191, 2313056, 2.86,
        )  # fmt: skip
        assert top["checkpoint_status"] == "OK"
        rates = [m["all_nan_pct"] for m in p["methods_by_all_nan_rate"]]
        assert rates == sorted(rates, reverse=True)
        assert {"SNMP", "WMI", "CIM"} <= set(p["idle_methods"])

    def test_not_ok_holds_the_live_warn_disabled_and_failed_script(self):
        p = parse_health_check(LIVE_HEALTH)
        assert {(n["check"], n.get("status")) for n in p["not_ok"]} == {
            ("module.SnmpTrap", "DISABLED"),
            ("Agent_Check0033_CollectorWorkLoad.groovy", None),
            ("basic.Memory", "WARN"),
        }
        assert p["not_ok_total"] == 3
        assert any(n.get("detail") == "script status 1" for n in p["not_ok"])

    def test_modules_by_nan_name_the_device_and_facts_are_read(self):
        """A live row is one module on one device, so each row carries its device."""
        p = parse_health_check(LIVE_HEALTH)
        assert p["nan_by_module"][0] == {
            "module": "Kubernetes_KSM_PersistentVolumes",
            "method": "script",
            "device_id": 451973,
            "nan_instances": 1,
            "timeout_instances": 0,
            "dropped_instances": 0,
        }
        rows = [(r["module"], r["device_id"]) for r in p["nan_by_module"]]
        assert len(rows) == 10 and len(set(rows)) == 10
        assert p["facts"]["basic.Version"] == "Collector #161 version is 40000 and size Large"
        assert p["facts"]["biz.InstanceCount"] == "The collector has 2558 instances"
        assert p["last_run_started"] == "Thu Nov 12 09:09:16 PST 2026"
        assert p["checks_parsed"] == 39

    def test_a_live_reply_has_no_unreadable_checkpoints(self):
        assert parse_health_check(LIVE_HEALTH)["checkpoints_unreadable"] == []

    def test_a_truncated_reply_names_the_cut_block_unreadable(self):
        """The review, item 4: a cut array is reported, never read as a clean block."""
        cut = LIVE_HEALTH[: LIVE_HEALTH.index('"name": "cogs.DSTableByNan"') + 200]
        p = parse_health_check(cut)
        assert p["checkpoints_unreadable"] == ["Agent_Check0041_CogsPerformanceCheck.groovy"]
        assert p["methods_by_all_nan_rate"] and p["nan_by_module"] == []

    @pytest.mark.parametrize(
        "body",
        ['[{"name": "basic.Memory", "detail": "free memory is 0 MB", "status": "WARN"},]',  # trailing comma
         '[{"name": "basic.Memory", "detail": "free memory is 0 MB", "status": "WARN"}',  # never closes
         '[{"name": "basic.Memory", "detail": "free memory is 0 MB", "status": "WARN"',
         "oops",
         "",
         "[" * 100_000 + "]" * 100_000],
    )  # fmt: skip
    def test_an_unreadable_array_is_never_read_as_clean(self, body):
        p = parse_health_check(f"=====x=====\n:checkpoints:{body}\n")
        assert p["checks_parsed"] == 1 and p["not_ok"] == []
        assert p["checkpoints_unreadable"] == ["x"]

    @pytest.mark.parametrize(
        "body,exception",
        [('[{"name": "basic.Memory", "status": "WARN"},]', ValueError),
         ("[" * 100_000 + "]" * 100_000, RecursionError)],
    )  # fmt: skip
    def test_an_array_that_does_not_decode_is_logged_with_its_stack(self, caplog, body, exception):
        with caplog.at_level(logging.WARNING, logger="lm_mcp.tools.collector_debug"):
            p = parse_health_check(f"=====x=====\n:checkpoints:{body}\n")
        assert p["checkpoints_unreadable"] == ["x"]
        (record,) = [r for r in caplog.records if r.name == "lm_mcp.tools.collector_debug"]
        assert record.levelno == logging.WARNING and "x" in record.getMessage()
        assert record.exc_info is not None and issubclass(record.exc_info[0], exception)

    def test_a_rate_that_is_not_a_number_is_left_out_without_an_error(self, caplog):
        body = '{"name": "biz.DataSource.WMI", "detail": "1 of 2 tasks (1.2.3%) returned NaN", "status": "OK"}'
        with caplog.at_level(logging.DEBUG, logger="lm_mcp.tools.collector_debug"):
            p = parse_health_check(f"=====x=====\n:checkpoints:[{body}]\n")
        assert p["methods_by_all_nan_rate"] == [] and caplog.records == []

    def test_unreadable_blocks_are_capped(self):
        reply = "".join(f"=====b{i}=====\n:checkpoints:[{{\n" for i in range(40))
        p = parse_health_check(reply)
        assert len(p["checkpoints_unreadable"]) == cd.PARSE_LIST_MAX
        assert p["checkpoints_unreadable"][0] == "b0"

    def test_empty_reply(self):
        p = parse_health_check("")
        assert p["checks_parsed"] == 0 and p["checkpoints_unreadable"] == []

    def test_results_are_capped(self):
        rows = ",".join(
            f'{{"name": "c{i}", "detail": "{"d" * 1000}", "status": "WARN"}}' for i in range(1000)
        )
        p = parse_health_check(f"=====x=====\n:checkpoints:[{rows}]\n")
        assert len(p["not_ok"]) == cd.PARSE_LIST_MAX and p["not_ok_total"] == 1000
        assert all(len(n["detail"]) <= cd.PARSE_TEXT_MAX for n in p["not_ok"])

    @pytest.mark.parametrize(
        "body",
        ['{"name": "cogs.DSTableByNan", "detail": [{"nanDsi": "5", "dsName": "M", "deviceId": "x"}], "status": "OK"}',
         '{"name": "biz.DataSource.WMI", "detail": "1 of 2 tasks (1.2.3%) returned NaN", "status": "OK"}',
         '{"name": "module.Collector", "detail": {"a": [1, 2]}, "status": "OK"}'],
    )  # fmt: skip
    def test_odd_values_do_not_break_the_parse(self, body):
        p = parse_health_check(f"=====x=====\n:checkpoints:[{body}]\n")
        assert p["checks_parsed"] == 1 and p["checkpoints_unreadable"] == []

    def test_structured_details_are_masked_after_the_parse(self):
        body = '{"name": "module.Collector", "detail": {"proxy.pass": "hunter2"}, "status": "OK"}'
        p = cd.redact_values(parse_health_check(f"=====x=====\n:checkpoints:[{body}]\n"))
        assert "hunter2" not in json.dumps(p) and "proxy.pass" in p["facts"]["module.Collector"]

    def test_a_long_digit_run_in_a_detail_is_parsed_in_linear_time(self):
        def reply(n: int) -> str:
            body = f'{{"name": "biz.DataSource.X", "detail": "{"1" * n} of 2", "status": "OK"}}'
            return f"=====c=====\n:checkpoints:[{body}]\n"

        assert_linear(parse_health_check, reply)

    @pytest.mark.parametrize(
        "unit",
        ["is scheduled at x, finished at y, ", "is scheduled at ", "1", "1 of ", "=====a=====\n",
         "=", ":checkpoints:[", '{"name": "biz.DataSource.X", "detail": "',
         "=====a=====\n:checkpoints:[\n"],
    )  # fmt: skip
    def test_hostile_replies_are_parsed_in_linear_time(self, unit):
        """The reply is the collector's: the parse grows with its length, not faster."""
        assert_linear(
            parse_health_check, lambda n: "=====c=====\n" + (unit * (n // len(unit) + 1))[:n]
        )


class TestFailureLogging:
    """The review, item 3: every swallowed exception is logged before it becomes a status."""

    LOGGER = "lm_mcp.tools.collector_debug"

    def records(self, caplog):
        return [r for r in caplog.records if r.name == self.LOGGER]

    @pytest.mark.parametrize(
        "error,status,detail",
        [(RateLimitError("Too many requests", retry_after=30), "rate_limited", "rate limit"),
         (AuthenticationError("Authentication failed"), "error", "API credentials"),
         (LMPermissionError("Permission denied"), "refused", "Debug permission"),
         (LMError("Remote debug is disabled on this collector", code="HTTP_400"), "disabled", "debug.disable"),
         (LMError("Unknown debug command !foo", code="HTTP_400"), "unsupported", "does not support"),
         (ServerError("Internal error"), "error", "ServerError")],
    )  # fmt: skip
    def test_an_lm_error_is_logged_at_warning_with_the_portals_words(
        self, caplog, error, status, detail
    ):
        with caplog.at_level(logging.DEBUG, logger=self.LOGGER):
            failure = describe_failure(error)
        assert failure["status"] == status and detail in failure["detail"]
        (record,) = self.records(caplog)
        assert record.levelno == logging.WARNING and record.exc_info is None
        assert error.code in record.getMessage() and error.message in record.getMessage()

    def test_the_portals_details_are_in_the_log_line(self, caplog):
        error = LMPermissionError("Permission denied")
        error.details = "Token lacks the collector Debug permission"
        with caplog.at_level(logging.WARNING, logger=self.LOGGER):
            describe_failure(error)
        (record,) = self.records(caplog)
        assert "Token lacks the collector Debug permission" in record.getMessage()

    def test_a_secret_in_the_portals_words_is_masked_in_the_log_and_the_body(self, caplog):
        error = LMError("bad request: password=hunter2", code="HTTP_400", details="token=s3cret")
        with caplog.at_level(logging.WARNING, logger=self.LOGGER):
            failure = describe_failure(error)
        assert "hunter2" not in caplog.text and "s3cret" not in caplog.text
        assert "hunter2" not in json.dumps(failure) and "s3cret" not in json.dumps(failure)
        assert failure["error_body"] == "token=***"

    def test_any_other_exception_is_logged_with_its_stack(self, caplog):
        try:
            raise RuntimeError("poll loop bug")
        except RuntimeError as e:
            error = e
        with caplog.at_level(logging.WARNING, logger=self.LOGGER):
            failure = describe_failure(error)
        assert failure == {
            "status": "error",
            "detail": "RuntimeError",
            "error_body": "poll loop bug",
        }
        (record,) = self.records(caplog)
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None and record.exc_info[1] is error

    def test_a_parse_fault_is_logged_and_leaves_the_answer_standing(self, caplog):
        def trips(_text):
            raise ValueError("bad block")

        with caplog.at_level(logging.WARNING, logger=self.LOGGER):
            result = parse_reply(trips, "output")
        assert result == {"parse_error": "ValueError"}
        (record,) = self.records(caplog)
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None and record.exc_info[0] is ValueError

    def test_a_parse_reads_at_most_the_output_cap_and_masks_its_result(self):
        seen = []

        def parse(text):
            seen.append(len(text))
            return {"proxy.pass": "hunter2", "n": 1}

        result = parse_reply(parse, "x" * (OUTPUT_MAX + 10))
        assert seen == [OUTPUT_MAX]
        assert result == {"parsed": {"proxy.pass": "***", "n": 1}, "parse_partial": True}

    def test_a_short_reply_is_parsed_whole(self, caplog):
        with caplog.at_level(logging.DEBUG, logger=self.LOGGER):
            result = parse_reply(parse_health_check, LIVE_HEALTH)
        assert result["parsed"]["checks_parsed"] == 39 and "parse_partial" not in result
        assert self.records(caplog) == []


# ---------------------------------------------------------------- the tool and its transport

PORTAL_HOST = "test.logicmonitor.com"
# The device the live !ping ran against (probes-2026-11.md, Step 73), as its record reads.
PROBED = {"id": 89818, "name": "127.0.0.1", "displayName": "example-vm", "currentCollectorId": 82}
# A device on a routable address, for http, which never reaches a loopback host.
WEB = {"id": 42, "name": "10.0.0.42", "displayName": "example-web", "currentCollectorId": 82}
# The portal's 403 body, as test_execute_tool copies it from a live read.
FORBIDDEN = {"errorMessage": "Permission denied", "errorCode": 1403, "errorDetail": None}
LOGGER = "lm_mcp.tools.collector_debug"


@pytest.fixture
def client(monkeypatch):
    """The client production builds, for a single portal with writes on."""
    monkeypatch.setenv("LM_PORTAL", PORTAL_HOST)
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)
    from lm_mcp.config import get_config

    config = get_config()
    return build_client(
        config.portal,
        bearer_token=config.bearer_token,
        access_id=config.access_id,
        access_key=config.access_key,
    )


@pytest.fixture
def fast_polls(monkeypatch):
    monkeypatch.setattr(cd, "POLL_SECONDS", 0.01)
    cd._POSTS.clear()
    cd._GETS.clear()


def portal_error(status: int, message: str) -> dict:
    """An error body in the portal's shape (LIVE["post_unknown_command"])."""
    return {
        "status": status,
        "body": {"errorMessage": message, "errorCode": 1000 + status, "errorDetail": None},
    }


def mount(
    replies=None, *, answer_form="with", post_error=None, post_body=None, device=None, pending=0
):
    """The debug API as the live portal answers it (LIVE). The POST gives a session id. A poll on
    the read that is not answering says cancelled; the first `pending` polls on the answering
    read say the agent is still working (HTTP 202); then the reply for the command line. replies
    maps a command-line prefix to its output, or to "slow" for a session that never answers.
    Returns the command lines sent."""
    seen: list[str] = []
    polls = [0]
    sid = LIVE["post_accepted"]["body"]["sessionId"]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/santaba/rest")
        if request.method == "POST" and path == "/debug":
            cmdline = json.loads(request.content)["cmdline"]
            seen.append(cmdline)
            if post_error:
                return httpx.Response(post_error["status"], json=post_error["body"])
            body = (
                post_body
                if post_body is not None
                else {**LIVE["post_accepted"]["body"], "cmdline": cmdline}
            )
            return httpx.Response(200, json=body)
        if path == f"/debug/{sid}":
            form = "with" if "collectorId" in request.url.params else "without"
            if form != answer_form:
                return httpx.Response(200, json=LIVE["poll_cancelled"]["body"])
            polls[0] += 1
            out = next((v for k, v in (replies or {}).items() if seen[-1].startswith(k)), "ok")
            if polls[0] <= pending or out == "slow":
                return httpx.Response(202, json=LIVE["poll_pending"]["body"])
            return httpx.Response(200, json={**LIVE["poll_answer_ping"]["body"], "output": out})
        if path.startswith("/device/devices/") and device is not None:
            return httpx.Response(200, json=device)
        return httpx.Response(
            404, json={"errorMessage": "unmocked", "errorCode": 1404, "errorDetail": None}
        )

    respx.route(host=PORTAL_HOST).mock(side_effect=handler)
    return seen


async def run(client, **kw):
    """Call the tool. An answer returns its body; an error returns the envelope's details with
    its code, message and retry_after. _is_error is read from the result type."""
    result = await collector_debug(client, **kw)
    if is_error_result(result):
        error = envelope(result)
        data = {**(error["details"] or {}), "code": error["code"], "message": error["message"]}
        data["retry_after"] = error["retry_after"]
    else:
        data = json.loads(result[0].text)
    data["_is_error"] = is_error_result(result)
    return data


def posted(collector: int | None = None) -> list[dict]:
    """The POST /debug calls respx saw, with their collectorId."""
    return [
        {"collectorId": c.request.url.params.get("collectorId"), **json.loads(c.request.content)}
        for c in respx.calls
        if c.request.method == "POST"
    ]


@pytest.mark.usefixtures("fast_polls")
class TestTool:
    @respx.mock
    async def test_answers_and_parses_the_live_health_check(self, client):
        seen = mount({"!shealthcheck": LIVE_HEALTH})
        data = await run(client, command="health_check", collector_id=161)
        assert data["status"] == "answered" and not data["_is_error"]
        assert seen == ["!shealthcheck func=detail collector=161"] and data["cmdline"] == seen[0]
        assert data["parsed"]["methods_by_all_nan_rate"][0]["method"] == "SCRIPT"
        assert data["parsed"]["checkpoints_unreadable"] == []
        assert data["output_chars"] == len(LIVE_HEALTH)
        assert len(data["output"]) == 4000 and data["truncated"] is True
        assert data["read_form"] == "with" and data["group"] == "collector"

    @pytest.mark.parametrize("form", ["with", "without"])
    @respx.mock
    async def test_either_read_can_be_the_one_that_answers(self, client, form):
        uptime = LIVE["poll_answer_uptime"]["body"]["output"]
        mount({"!uptime": uptime}, answer_form=form)
        data = await run(client, command="uptime", collector_id=82)
        assert (
            data["status"] == "answered" and data["output"] == uptime and data["read_form"] == form
        )

    @respx.mock
    async def test_both_reads_are_asked_on_every_poll(self, client):
        """Live, either read says cancelled while the other answers, on one portal."""
        mount({"!uptime": "uptime=1h"}, answer_form="without", pending=2)
        data = await run(client, command="uptime", collector_id=82)
        reads = [
            "collectorId" in c.request.url.params for c in respx.calls if c.request.method == "GET"
        ]
        assert reads == [True, False] * 3
        assert data["status"] == "answered" and data["api_calls"] == 7

    @respx.mock
    async def test_the_live_ping_runs_on_the_records_collector_against_its_host(self, client):
        ping = LIVE["poll_answer_ping"]["body"]["output"]
        seen = mount({"!ping": ping}, device=PROBED)
        data = await run(client, command="ping", device_id=89818)
        assert seen == ["!ping 127.0.0.1"]
        assert posted() == [{"collectorId": "82", "cmdline": "!ping 127.0.0.1"}]
        assert data["collector_id"] == 82 and data["output"] == ping
        assert data["device"] == {"device_id": 89818, "host_used": "127.0.0.1"}
        assert data["group"] == "device"

    @respx.mock
    async def test_a_caller_host_cannot_override_the_record(self, client):
        mount(device=PROBED)
        data = await run(client, command="ping", device_id=89818, args={"host": "10.0.0.9"})
        assert data["code"] == "REJECTED_BY_TOOL" and data["status"] == "rejected_by_tool"
        assert "'host' is not accepted" in data["message"]
        assert not respx.calls

    @respx.mock
    async def test_a_device_probe_without_device_id_sends_nothing(self, client):
        mount()
        data = await run(client, command="ping", collector_id=82)
        assert data["code"] == "REJECTED_BY_TOOL" and "needs device_id" in data["message"]
        assert not respx.calls

    @pytest.mark.parametrize("name", ["bad host; !restart", "-n"])
    @respx.mock
    async def test_a_record_host_that_is_not_plain_is_refused(self, client, name):
        seen = mount(device={**PROBED, "name": name})
        data = await run(client, command="ping", device_id=89818)
        assert data["code"] == "REJECTED_BY_TOOL" and "plain hostname" in data["message"]
        assert seen == []

    @pytest.mark.parametrize(
        "command,args",
        [("ping", {"count": 999}), ("ping", {"count": float("inf")}), ("ping", {"bogus": 1}),
         ("wmi", {"query": "select * from X h=evil"}),
         ("wmi", {"query": "select * from Win32_Service where Name = 'a' !restart"}),
         ("http", {"url": "https://admin:x@127.0.0.1/"}), ("http", {"url": "https://127.0.0.1/?password=x"}),
         ("http", {"url": "ftp://127.0.0.1/"})],
    )  # fmt: skip
    @respx.mock
    async def test_values_are_refused_before_the_device_is_read(self, client, command, args):
        mount(device=PROBED)
        data = await run(client, command=command, device_id=89818, args=args)
        assert data["code"] == "REJECTED_BY_TOOL" and data["_is_error"]
        assert not respx.calls

    @respx.mock
    async def test_http_runs_only_against_the_device_record(self, client):
        seen = mount({"!http": "HTTP/1.1 200 OK"}, device=WEB)
        ok = await run(
            client, command="http", device_id=42, args={"url": "https://10.0.0.42/health"}
        )
        refused = await run(
            client,
            command="http",
            device_id=42,
            args={"url": "http://169.254.169.254/latest/meta-data/"},
        )
        assert ok["status"] == "answered" and refused["code"] == "REJECTED_BY_TOOL"
        assert seen == ["!http https://10.0.0.42/health"]

    @respx.mock
    async def test_the_portal_check_targets_the_configured_portal(self, client):
        seen = mount({"!checkserverconnectivity": "PING: Fail, HTTP: OK"})
        data = await run(client, command="checkserverconnectivity", collector_id=82)
        assert seen == [f"!checkserverconnectivity {PORTAL_HOST}"] and data["status"] == "answered"

    @respx.mock
    async def test_an_unknown_key_names_the_keys_the_command_takes(self, client):
        mount(device=PROBED)
        data = await run(
            client, command="ping", device_id=89818, args={"bogus": "x", "community": "public"}
        )
        assert "ping takes count, type; not bogus, community" in data["message"]
        assert not respx.calls

    @respx.mock
    async def test_args_must_be_an_object(self, client):
        mount()
        data = await run(client, command="uptime", collector_id=82, args=["x"])
        assert data["code"] == "REJECTED_BY_TOOL" and "'args' must be an object" in data["message"]

    @respx.mock
    async def test_output_is_masked(self, client):
        mount({"!logsurf": "connecting with password=hunter2 to host"})
        data = await run(client, command="logsurf", collector_id=82)
        assert "hunter2" not in json.dumps(data) and "password=***" in data["output"]

    @respx.mock
    async def test_a_probe_cannot_run_on_another_collector(self, client):
        seen = mount(device=PROBED)
        data = await run(client, command="ping", device_id=89818, collector_id=99)
        assert "collector that serves the device (82), not collector 99" in data["message"]
        assert seen == []

    @pytest.mark.parametrize("record", [SERVICE, CLOUD])
    @respx.mock
    async def test_a_live_collectorless_device_is_refused(self, client, record):
        seen = mount(device=record)
        data = await run(client, command="ping", device_id=record["id"])
        assert data["code"] == "REJECTED_BY_TOOL" and "names no collector" in data["message"]
        assert seen == []

    @pytest.mark.parametrize(
        "kwargs",
        [{"budget_seconds": float("nan")}, {"budget_seconds": float("inf")},
         {"max_output_chars": float("nan")}, {"budget_seconds": "soon"}],
    )  # fmt: skip
    @respx.mock
    async def test_budgets_that_are_not_finite_are_refused_before_any_call(self, client, kwargs):
        mount()
        data = await run(client, command="uptime", collector_id=82, **kwargs)
        assert data["code"] == "REJECTED_BY_TOOL" and "finite" in data["message"]
        assert not respx.calls

    @pytest.mark.parametrize(
        "kwargs",
        [{"collector_id": "abc"}, {"collector_id": -5}, {"collector_id": 0},
         {"collector_id": True}, {"device_id": "42"}, {"device_id": 4.0}],
    )  # fmt: skip
    @respx.mock
    async def test_ids_are_checked_before_any_call(self, client, kwargs):
        mount(device=PROBED)
        data = await run(client, command="ping", **{"device_id": 89818, **kwargs})
        assert data["code"] == "REJECTED_BY_TOOL" and "positive whole number" in data["message"]
        assert not respx.calls

    @respx.mock
    async def test_the_portals_words_are_masked_in_the_error(self, client):
        mount(post_error=portal_error(400, "bad request: password=hunter2"))
        data = await run(client, command="uptime", collector_id=82)
        assert data["_is_error"] and "hunter2" not in json.dumps(data)
        assert "password=***" in data["message"]

    @respx.mock
    async def test_a_pending_status_is_masked(self, client):
        def handler(request):
            if request.method == "POST":
                return httpx.Response(200, json=LIVE["post_accepted"]["body"])
            return httpx.Response(
                202,
                json={
                    **LIVE["poll_pending"]["body"],
                    "errorMessage": "agent has fetched the task, password=hunter2",
                },
            )

        respx.route(host=PORTAL_HOST).mock(side_effect=handler)
        data = await run(client, command="uptime", collector_id=82, budget_seconds=2)
        assert data["status"] == "no_reply"
        assert "password=***" in data["detail"] and "hunter2" not in json.dumps(data)

    @respx.mock
    async def test_budget_and_output_are_clamped(self, client):
        mount({"!uptime": "x" * 3000})
        data = await run(
            client, command="uptime", collector_id=82, budget_seconds=1000, max_output_chars=600
        )
        assert data["budget_seconds"] == BUDGET_MAX
        assert (
            len(data["output"]) == 600
            and data["truncated"] is True
            and data["output_chars"] == 3000
        )

    @respx.mock
    async def test_bad_api_credentials_are_not_called_a_missing_permission(self, client):
        mount(post_error=portal_error(401, "Authentication failed"))
        data = await run(client, command="uptime", collector_id=82)
        assert data["status"] == "error" and data["code"] == "AUTH_FAILED"
        assert "API credentials" in data["detail"]

    @respx.mock
    async def test_refused_without_the_debug_permission(self, client):
        mount(post_error={"status": 403, "body": FORBIDDEN})
        data = await run(client, command="uptime", collector_id=82)
        assert data["status"] == "refused" and data["code"] == "AUTH_FAILED" and data["_is_error"]
        assert data["message"].startswith("uptime: refused: ")

    @respx.mock
    async def test_the_live_unknown_command_reply_is_unsupported(self, client):
        mount(post_error=LIVE["post_unknown_command"])
        data = await run(client, command="nsplist", collector_id=82)
        assert data["status"] == "unsupported" and data["code"] == "INVALID_REQUEST"
        assert "Unknown debug command !nosuchcmd" in data["message"]

    @respx.mock
    async def test_the_live_unknown_collector_reply_carries_the_portals_words(self, client):
        mount(post_error=LIVE["post_unknown_collector"])
        data = await run(client, command="uptime", collector_id=999999)
        assert data["status"] == "error" and data["_is_error"]
        assert "No such collector<id=999999>" in data["message"]

    @respx.mock
    async def test_debug_disabled_on_the_collector(self, client):
        mount(post_error=portal_error(400, "remote debug is disabled on this collector"))
        data = await run(client, command="uptime", collector_id=82)
        assert data["status"] == "disabled" and data["code"] == "FEATURE_DISABLED"

    @respx.mock
    async def test_an_answer_is_not_an_error(self, client):
        mount({"!uptime": "uptime=1h"})
        data = await run(client, command="uptime", collector_id=82)
        assert data["status"] == "answered" and not data["_is_error"]

    @respx.mock
    async def test_no_reply_inside_the_budget_is_a_result(self, client):
        mount({"!uptime": "slow"})
        data = await run(client, command="uptime", collector_id=82, budget_seconds=2)
        assert data["status"] == "no_reply" and not data["_is_error"]
        assert "waiting for response" in data["detail"] and data["elapsed_ms"] < 3500

    @respx.mock
    async def test_the_live_still_working_reply_keeps_polling(self, client):
        mount({"!ping": LIVE["poll_answer_ping"]["body"]["output"]}, device=PROBED, pending=3)
        data = await run(client, command="ping", device_id=89818)
        assert data["status"] == "answered" and data["output"].startswith("Sent: 10")

    @respx.mock
    async def test_a_usage_reply_is_flagged_as_the_commands_fault(self, client):
        mount({"!sslcerts": "Usage: !sslcerts [timeout=XX] host port"}, device=PROBED)
        data = await run(client, command="sslcerts", device_id=89818, args={"port": 443})
        assert data["status"] == "answered" and "not the device" in data["note"]

    @pytest.mark.parametrize("reply", ["cpu usage: 12%", "<title>Invalid URL</title>"])
    @respx.mock
    async def test_a_device_reply_is_not_read_as_a_usage_banner(self, client, reply):
        mount({"!http": reply}, device=WEB)
        data = await run(client, command="http", device_id=42, args={"url": "http://10.0.0.42/"})
        assert data["status"] == "answered" and "note" not in data

    @respx.mock
    async def test_an_unknown_config_key_is_flagged(self, client):
        mount({"!getconfig": "Configuration key [collector.zzz.threadpool] not found"})
        data = await run(
            client, command="getconfig", collector_id=82, args={"key": "collector.zzz.threadpool"}
        )
        assert data["status"] == "answered" and "agent.conf key" in data["note"]

    @respx.mock
    async def test_an_unknown_command_lists_the_safe_set(self, client):
        mount()
        data = await run(client, command="restart", collector_id=82)
        assert data["code"] == "REJECTED_BY_TOOL" and "Commands: " in data["message"]
        assert "uptime" in data["message"] and not respx.calls

    @respx.mock
    async def test_a_collector_is_required(self, client):
        mount()
        data = await run(client, command="uptime")
        assert data["code"] == "REJECTED_BY_TOOL" and not respx.calls

    @respx.mock
    async def test_the_servers_own_post_budget(self, client, monkeypatch):
        monkeypatch.setattr(cd, "POST_LIMIT", 0)
        mount()
        data = await run(client, command="uptime", collector_id=82)
        assert data["status"] == "rate_limited" and data["code"] == "RATE_LIMITED"
        assert not respx.calls

    @respx.mock
    async def test_the_servers_own_get_budget(self, client, monkeypatch):
        monkeypatch.setattr(cd, "GET_LIMIT", 0)
        mount({"!uptime": "uptime=1h"})
        data = await run(client, command="uptime", collector_id=82)
        assert data["status"] == "no_reply" and "GET budget" in data["detail"]
        assert "may still run it" in data["detail"] and not data["_is_error"]

    @respx.mock
    async def test_no_session_id_is_an_error(self, client):
        mount(post_body={"output": "", "cmdline": "!uptime", "cmdContext": ""})
        data = await run(client, command="uptime", collector_id=82)
        assert data["status"] == "error" and data["code"] == "UPSTREAM_ERROR"
        assert "no session id" in data["detail"]

    @respx.mock
    async def test_the_output_floor_is_500_characters(self, client):
        mount({"!uptime": "x" * 3000})
        data = await run(client, command="uptime", collector_id=82, max_output_chars=10)
        assert len(data["output"]) == 500 and data["truncated"] is True

    @respx.mock
    async def test_the_budget_floor_is_two_seconds(self, client):
        mount({"!uptime": "uptime=1h"})
        data = await run(client, command="uptime", collector_id=82, budget_seconds=0)
        assert data["status"] == "answered" and data["budget_seconds"] == 2.0

    @respx.mock
    async def test_masked_output_that_grows_is_still_capped(self, client):
        mount({"!logsurf": "pass=x\n" * (OUTPUT_MAX // 7)})
        data = await run(client, command="logsurf", collector_id=82, max_output_chars=10**9)
        assert data["output_chars"] <= OUTPUT_MAX
        assert len(data["output"]) == OUTPUT_MAX and data["truncated"] is True

    @respx.mock
    async def test_the_output_is_capped_at_the_maximum(self, client):
        mount({"!uptime": "x" * (OUTPUT_MAX + 500)})
        data = await run(client, command="uptime", collector_id=82, max_output_chars=10**9)
        assert len(data["output"]) == OUTPUT_MAX and data["truncated"] is True
        assert data["output_chars"] == OUTPUT_MAX + 500

    @respx.mock
    async def test_truncated_follows_what_is_shown_after_masking(self, client):
        mount({"!logsurf": "pass=x\n" * 2857})  # 19,999 characters that mask to more
        grown = await run(client, command="logsurf", collector_id=82)
        assert grown["output_chars"] < OUTPUT_DEFAULT and grown["truncated"] is True
        mount({"!logsurf": "password=" + "y" * 25_000 + "\ntail"})
        cut = await run(client, command="logsurf", collector_id=82)
        assert cut["output"] == "password=***" and cut["truncated"] is True
        mount({"!logsurf": "password=" + "y" * 15_000 + "\ntail"})
        shrunk = await run(client, command="logsurf", collector_id=82)
        assert shrunk["output"] == "password=***\ntail" and shrunk["truncated"] is False

    @respx.mock
    async def test_a_masked_value_does_not_break_the_health_check_parse(self, client):
        """The parse reads the raw reply, and only its result is masked."""
        reply = LIVE_HEALTH.replace(
            '"detail": "The host has total 8192 MB physical memory and free memory is 0 MB',
            '"detail": "The host has total 8192 MB physical memory and <password>hunter2',
        )
        mount({"!shealthcheck": reply})
        data = await run(client, command="health_check", collector_id=161)
        memory = next(n for n in data["parsed"]["not_ok"] if n["check"] == "basic.Memory")
        assert memory["detail"].startswith(
            "The host has total 8192 MB physical memory and <password>***"
        )
        assert data["parsed"]["methods_by_all_nan_rate"][0]["method"] == "SCRIPT"
        assert "hunter2" not in json.dumps(data)

    @respx.mock
    async def test_a_long_health_check_is_parsed_as_far_as_the_cut(self, client):
        mount({"!shealthcheck": LIVE_HEALTH + "x" * OUTPUT_MAX})
        data = await run(client, command="health_check", collector_id=161)
        assert data["parsed"]["checks_parsed"] == 39 and data["parse_partial"] is True

    @respx.mock
    async def test_a_parse_fault_leaves_the_answer_standing(self, client, monkeypatch, caplog):
        def broken(text):
            raise RecursionError

        monkeypatch.setattr(cd, "parse_health_check", broken)
        mount({"!shealthcheck": LIVE_HEALTH})
        with caplog.at_level(logging.ERROR, logger=LOGGER):
            data = await run(client, command="health_check", collector_id=161)
        assert data["status"] == "answered" and not data["_is_error"]
        assert data["parse_error"] == "RecursionError" and data["output"]
        assert any(r.exc_info for r in caplog.records if r.name == LOGGER)

    @respx.mock
    async def test_a_failure_reads_as_an_error_to_composite_callers(self, client):
        from lm_mcp.tools import call_sub_tool

        mount(post_error={"status": 403, "body": FORBIDDEN})
        with pytest.raises(RuntimeError, match="uptime: refused"):
            await call_sub_tool(collector_debug, client, command="uptime", collector_id=82)

    async def test_a_transport_refusal_is_rejected_by_the_tool(self, client, monkeypatch):
        async def refused(*a, **kw):
            return {"status": "rejected_by_tool", "detail": "not a debug command"}

        monkeypatch.setattr(cd, "run_debug", refused)
        data = await run(client, command="uptime", collector_id=82)
        assert data["code"] == "REJECTED_BY_TOOL" and "not a debug command" in data["message"]

    @respx.mock
    async def test_a_device_record_that_is_not_an_object_is_refused(self, client):
        respx.get(f"https://{PORTAL_HOST}/santaba/rest/device/devices/49").mock(
            return_value=httpx.Response(200, json=[1, 2])
        )
        data = await run(client, command="ping", device_id=49)
        assert data["code"] == "REJECTED_BY_TOOL" and "could not be read" in data["message"]

    @respx.mock
    async def test_a_missing_device_is_not_found(self, client):
        respx.get(f"https://{PORTAL_HOST}/santaba/rest/device/devices/48").mock(
            return_value=httpx.Response(
                404, json={"errorMessage": "No such device", "errorCode": 1404, "errorDetail": None}
            )
        )
        data = await run(client, command="ping", device_id=48)
        assert data["code"] == "NOT_FOUND" and not [
            c for c in respx.calls if c.request.method == "POST"
        ]


@pytest.mark.usefixtures("fast_polls")
class TestRunDebug:
    """run_debug guards itself, whoever calls it."""

    async def test_a_spent_budget_sends_nothing_and_says_so(self, client):
        with respx.mock(assert_all_called=False) as router:
            route = router.route(host=PORTAL_HOST).mock(httpx.Response(200, json={}))
            result = await cd.run_debug(client, 82, "!uptime", time.monotonic() - 1)
        assert result["status"] == "error" and result["envelope"]["code"] == "TIMEOUT"
        assert "nothing was sent" in result["detail"] and route.call_count == 0

    async def test_it_refuses_an_unchecked_line_without_a_call(self, client):
        with respx.mock(assert_all_called=False) as router:
            route = router.route(host=PORTAL_HOST).mock(httpx.Response(200, json={}))
            result = await cd.run_debug(client, 82, "!restart", time.monotonic() + 5)
        assert (
            result["status"] == "rejected_by_tool" and "changes the collector" in result["detail"]
        )
        assert route.call_count == 0

    @respx.mock
    async def test_it_cuts_the_output_before_masking(self, client, monkeypatch):
        seen = []
        monkeypatch.setattr(cd, "redact", lambda text: seen.append(len(text)) or text)
        mount({"!uptime": "y" * (OUTPUT_MAX * 3)})
        result = await cd.run_debug(client, 82, "!uptime", time.monotonic() + 5)
        assert result["status"] == "answered"
        assert seen == [OUTPUT_MAX + cd._MASK_MARGIN] and len(result["output"]) == OUTPUT_MAX
        assert result["output_chars"] == OUTPUT_MAX * 3 and result["truncated"] is True

    @pytest.mark.parametrize(
        "secret",
        ["http://bob:hunter2@10.0.0.1/x", '{"name": "db.password", "value": "hunter2"}',
         '<add key="DbPassword" value="hunter2"/>', "mongodb://bob:hunter2@10.0.0.1/db"],
    )  # fmt: skip
    @respx.mock
    async def test_a_secret_the_cut_splits_is_still_masked(self, client, secret):
        keep = 1000
        cut_at = secret.index("hunter2") + 3  # the cut lands inside the value
        mount({"!uptime": "x" * (keep - cut_at) + secret + " tail"})
        result = await cd.run_debug(client, 82, "!uptime", time.monotonic() + 5, keep=keep)
        assert "hun" not in result["output"] and len(result["output"]) <= keep


@pytest.mark.usefixtures("fast_polls")
class TestBudget:
    """The device read, the POST and every poll are held to the time budget, and a budget
    that ends the call is logged with its stack trace."""

    @staticmethod
    def slow(paths: tuple[str, ...]):
        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path.removeprefix("/santaba/rest")
            if any(path.startswith(p) for p in paths) and not (
                request.method == "GET" and path == "/debug"
            ):
                await asyncio.sleep(30)
            if request.method == "POST":
                return httpx.Response(200, json=LIVE["post_accepted"]["body"])
            if path.startswith("/device/devices/"):
                return httpx.Response(200, json=PROBED)
            return httpx.Response(200, json=LIVE["poll_answer_uptime"]["body"])

        return handler

    def budget_records(self, caplog):
        return [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING]

    @respx.mock
    async def test_a_slow_post_is_cut_off_at_the_budget(self, client, caplog):
        respx.route(host=PORTAL_HOST).mock(side_effect=self.slow(("/debug",)))
        started = time.monotonic()
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            data = await run(client, command="uptime", collector_id=82, budget_seconds=2)
        assert data["status"] == "no_reply" and "did not accept the command" in data["detail"]
        assert time.monotonic() - started < 3
        (record,) = self.budget_records(caplog)
        assert record.exc_info and isinstance(record.exc_info[1], cd._BudgetSpentError)

    @respx.mock
    async def test_a_slow_device_read_is_cut_off_at_the_budget(self, client, caplog):
        respx.route(host=PORTAL_HOST).mock(side_effect=self.slow(("/device/devices/",)))
        started = time.monotonic()
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            data = await run(client, command="ping", device_id=89818, budget_seconds=2)
        assert data["status"] == "error" and data["code"] == "TIMEOUT" and data["_is_error"]
        assert "device record" in data["detail"] and "nothing was sent" in data["detail"]
        assert time.monotonic() - started < 3
        assert not [c for c in respx.calls if c.request.method == "POST"]
        (record,) = self.budget_records(caplog)
        assert record.exc_info and isinstance(record.exc_info[1], cd._BudgetSpentError)

    @respx.mock
    async def test_a_slow_poll_is_cut_off_at_the_budget(self, client, caplog):
        respx.route(host=PORTAL_HOST).mock(
            side_effect=self.slow((f"/debug/{LIVE['post_accepted']['body']['sessionId']}",))
        )
        started = time.monotonic()
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            data = await run(client, command="uptime", collector_id=82, budget_seconds=2)
        assert data["status"] == "no_reply"
        assert time.monotonic() - started < 3
        (record,) = self.budget_records(caplog)
        assert record.exc_info and isinstance(record.exc_info[1], cd._BudgetSpentError)

    @respx.mock
    async def test_a_still_working_poll_is_logged_with_its_stack(self, client, caplog):
        mount({"!uptime": "uptime=1h"}, pending=1)
        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            data = await run(client, command="uptime", collector_id=82)
        assert data["status"] == "answered"
        (record,) = [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.DEBUG]
        assert record.exc_info is not None and "API_ERROR_1202" in str(record.exc_info[1].code)


class TestWithin:
    async def test_a_spent_budget_refuses_before_calling(self):
        """No call starts once the deadline has passed, and the coroutine is closed."""
        calls = []

        async def call():
            calls.append(1)

        coro = call()
        with pytest.raises(cd._BudgetSpentError):
            await cd._within(time.monotonic() - 1, coro)
        assert calls == [] and coro.cr_frame is None


class TestWriteGate:
    async def test_disabled_writes_refuse_before_any_call(self, client, monkeypatch):
        from lm_mcp.config import reset_config
        from lm_mcp.registry import get_tool_handler

        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        reset_config()
        handler = get_tool_handler("collector_debug")
        with respx.mock(assert_all_called=False) as router:
            route = router.route(host=PORTAL_HOST).mock(httpx.Response(200, json={}))
            result = await handler(client, command="uptime", collector_id=82)
        assert envelope(result)["code"] == "WRITE_DISABLED" and route.call_count == 0

    def test_it_is_audited_as_a_write(self):
        from lm_mcp.logging import is_write_tool

        assert is_write_tool("collector_debug")


class TestRegistry:
    @staticmethod
    def tool():
        from lm_mcp.registry import TOOLS

        return next(t for t in TOOLS if t.name == "collector_debug")

    def test_the_command_enum_is_the_allowlisted_set(self):
        assert sorted(self.tool().inputSchema["properties"]["command"]["enum"]) == sorted(COMMANDS)

    def test_the_args_description_names_every_commands_keys(self):
        text = self.tool().inputSchema["properties"]["args"]["description"]
        for name, command in COMMANDS.items():
            if command.keys:
                assert f"{name}: " in text, name
                for key in command.keys:
                    assert key in text.split(f"{name}: ", 1)[1].split(". ", 1)[0], (name, key)

    def test_it_is_a_destructive_write(self):
        annotations = self.tool().annotations
        assert annotations.readOnlyHint is False and annotations.destructiveHint is True

    def test_it_is_listed_with_the_collector_tools(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        assert "collector_debug" in TOOL_CATEGORIES["categories"]["collectors"]["tools"]

    def test_the_handler_is_the_tool(self):
        from lm_mcp.registry import get_tool_handler

        assert get_tool_handler("collector_debug") is collector_debug


class TestSecurityReview:
    """The 2026-11-12 security review (docs/validation/collector-debug-review-2026-11.md),
    one test group per finding folded into the module."""

    # H1: one prefix followed by one long run made two masking patterns quadratic; a call then
    # held the event loop for 32.6 s against a 2 s budget.
    @pytest.mark.parametrize(
        "prefix",
        [
            "-u ",
            "--user ",
            "--user=",
            "-u=",
            "-----BEGIN ",
            "-----BEGIN RSA ",
            "password=",
            "Authorization: ",
            "http://",
            '<entry key="',
        ],
    )
    @pytest.mark.parametrize("filler", ["=", " ", "A", ":"])
    def test_one_prefix_then_one_long_run_masks_in_linear_time(self, prefix, filler):
        assert_linear(redact, lambda n: prefix + filler * n, small=20_000, large=80_000)

    @pytest.mark.parametrize("unit", ["PRIVATE KEY", "PRIVATE KEY ", "RSA PRIVATE KEY"])
    def test_a_pem_header_of_repeated_words_masks_in_linear_time(self, unit):
        assert_linear(
            redact,
            lambda n: "-----BEGIN " + (unit * (n // len(unit) + 1))[:n],
            small=20_000,
            large=80_000,
        )

    @pytest.mark.parametrize(
        "text,expected",
        [("curl -u admin:hunter2 https://h/", "curl -u admin:*** https://h/"),
         ("--user=ops:s3cret", "--user=ops:***"),
         (f"{PEM_BEGIN}\nMIIabc\n{PEM_END}", f"{PEM_BEGIN}***{PEM_END}")],
    )  # fmt: skip
    def test_the_bounded_patterns_still_mask(self, text, expected):
        assert redact(text) == expected

    # M1 and M2: http never reaches a loopback, unspecified, link-local or cloud metadata host,
    # which a device record named for one would otherwise point it at.
    @pytest.mark.parametrize(
        "host",
        ["127.0.0.1", "127.8.9.1", "::1", "[::1]", "0.0.0.0", "::", "localhost", "LOCALHOST",
         "api.localhost", "169.254.169.254", "169.254.1.7", "fe80::1", "[fe80::1]",
         "100.100.100.200", "fd00:ec2::254", "192.0.0.192", "::ffff:127.0.0.1",
         "metadata", "metadata.google.internal", "127.1", "2130706433", "0x7f000001"],
    )  # fmt: skip
    def test_http_never_reaches_a_loopback_link_local_or_metadata_host(self, host):
        url_host = f"[{host.strip('[]')}]" if ":" in host else host
        target = Target(collector_id=7, host=host)
        with pytest.raises(ToolRejectionError, match="loopback, link-local or cloud metadata"):
            build_cmdline("http", {"url": f"http://{url_host}/"}, target)

    @pytest.mark.parametrize(
        "host", ["10.0.0.5", "192.168.1.20", "fe80example.net", "metadata-db-01", "2001:db8::5"]
    )
    def test_http_still_reaches_an_ordinary_device_host(self, host):
        url_host = f"[{host}]" if ":" in host else host
        cmdline = build_cmdline(
            "http", {"url": f"https://{url_host}:8443/x"}, Target(collector_id=7, host=host)
        )
        assert cmdline == f"!http https://{url_host}:8443/x"

    def test_other_probes_still_run_on_a_loopback_device(self):
        """A device named 127.0.0.1 is the collector host itself; ping and snmp reach it."""
        target = Target(collector_id=82, host="127.0.0.1")
        assert build_cmdline("ping", {}, target) == "!ping 127.0.0.1"

    @respx.mock
    async def test_a_loopback_url_is_refused_before_the_device_is_read(self, client):
        mount(device=PROBED)
        data = await run(
            client,
            command="http",
            device_id=89818,
            args={"url": "http://127.0.0.1:8500/v1/kv/?recurse"},
        )
        assert data["code"] == "REJECTED_BY_TOOL" and "loopback" in data["message"]
        assert not respx.calls

    @respx.mock
    async def test_a_metadata_device_record_is_refused_after_the_read(self, client):
        """A record renamed to the metadata address (by create_device or update_device)."""
        seen = mount(device={**WEB, "name": "169.254.169.254"})
        data = await run(
            client,
            command="http",
            device_id=42,
            args={"url": "http://169.254.169.254/latest/meta-data/"},
        )
        assert data["code"] == "REJECTED_BY_TOOL" and seen == []

    # M3: a WQL or CIM class that changes the device, walks its disks or holds secrets by design.
    @pytest.mark.parametrize(
        "query,why",
        [("select * from Win32_Product", "Win32_Product is not queried"),
         ("SELECT Name FROM win32_product WHERE Name = 'x'", "win32_product is not queried"),
         ("select * from CIM_DataFile where Drive = 'c:'", "CIM_DataFile is not queried"),
         ("select * from CIM_Directory", "CIM_Directory is not queried"),
         ("select * from Win32_Directory", "Win32_Directory is not queried"),
         ("select * from Win32_Environment", "Win32_Environment is not queried"),
         ("select * from Win32_Process", "CommandLine"),
         ("select Name, CommandLine from Win32_Process", "CommandLine"),
         ("select * from Win32_NTLogEvent", "WHERE")],
    )  # fmt: skip
    def test_a_risky_wmi_class_is_refused(self, query, why):
        with pytest.raises(ToolRejectionError, match=why):
            build_cmdline("wmi", {"query": query}, T)

    @pytest.mark.parametrize(
        "query",
        ["select Name, ProcessId from Win32_Process",
         "select * from Win32_NTLogEvent where Logfile = 'System' AND EventCode = 41",
         "select * from Win32_Service"],
    )  # fmt: skip
    def test_the_useful_shapes_of_those_classes_still_build(self, query):
        assert build_cmdline("wmi", {"query": query}, T) == f"!wmi h=10.0.0.5 {query}"

    @pytest.mark.parametrize("cls", ["CIM_DataFile", "cim_directory", "Win32_Product"])
    def test_a_risky_cim_class_is_refused(self, cls):
        with pytest.raises(ToolRejectionError, match="class"):
            build_cmdline("cim", {"class": cls}, T)

    # L1: an undotted compound key the audit log masks is masked in the output too.
    @pytest.mark.parametrize(
        "key",
        ["snmp_auth", "ssh_key", "sshKey", "snmpPriv", "snmp-auth", "privKey", "authKey", "x_auth"],
    )
    def test_an_undotted_compound_key_follows_the_audit_rule(self, key):
        assert is_sensitive_key(key)
        assert redact(f"{key}=hunter2") == f"{key}=***"

    @pytest.mark.parametrize(
        "text", ["key=abc", "auth: ok", "priv=3", "device_id=7", "sort_keyword=x"]
    )
    def test_a_bare_word_or_identifier_is_not_masked(self, text):
        assert redact(text) == text

    # L2: one-letter password and community flags, a cut that splits a secret, and the SNMP
    # tables that hold communities and users.
    @pytest.mark.parametrize(
        "text,expected",
        [("sqlcmd -S db -U sa -P Sup3rS3cret -Q x", "sqlcmd -S db -U sa -P *** -Q x"),
         ("sshpass -p hunter2 ssh host", "sshpass -p *** ssh host"),
         ("snmpwalk -v2c -c private 10.0.0.5", "snmpwalk -v2c -c *** 10.0.0.5")],
    )  # fmt: skip
    def test_one_letter_secret_flags_are_masked(self, text, expected):
        assert redact(text) == expected

    def test_a_checkpoint_detail_is_masked_before_it_is_cut(self):
        detail = "x" * (cd.PARSE_TEXT_MAX - 20) + " http://admin:hunter2@10.0.0.5/"
        body = json.dumps({"name": "module.Collector", "detail": detail, "status": "OK"})
        p = parse_health_check(f"=====x=====\n:checkpoints:[{body}]\n")
        assert "hunter2" not in json.dumps(p) and "hun" not in p["facts"]["module.Collector"]
        assert len(p["facts"]["module.Collector"]) <= cd.PARSE_TEXT_MAX

    @respx.mock
    async def test_a_pending_status_is_masked_before_it_is_cut(self, client):
        words = "agent has fetched the task, " + "x" * 155 + " http://admin:hunter2@10.0.0.5/"
        assert words.index("hunter2") + 3 == 200  # the 200-character cut lands inside the value

        def handler(request):
            if request.method == "POST":
                return httpx.Response(200, json=LIVE["post_accepted"]["body"])
            return httpx.Response(202, json={**LIVE["poll_pending"]["body"], "errorMessage": words})

        respx.route(host=PORTAL_HOST).mock(side_effect=handler)
        cd._POSTS.clear()
        cd._GETS.clear()
        data = await run(client, command="uptime", collector_id=82, budget_seconds=2)
        assert data["status"] == "no_reply" and "hun" not in data["detail"]

    @pytest.mark.parametrize("oid", [".1.3.6.1.6.3", ".1.3.6.1.6"])
    def test_a_walk_above_the_community_and_user_tables_is_refused(self, oid):
        with pytest.raises(ToolRejectionError, match="community or user"):
            build_cmdline("snmpwalk", {"oid": oid}, T)

    @pytest.mark.parametrize(
        "oid", [".1.3.6.1.6.3.18", ".1.3.6.1.6.3.18.1.1", "1.3.6.1.6.3.15.1.2.2"]
    )
    @pytest.mark.parametrize("command", ["snmpwalk", "snmpget", "snmpdiagnose"])
    def test_the_snmp_community_and_user_tables_are_refused(self, oid, command):
        args = {"oid": oid} if command == "snmpwalk" else {"oids": [oid]}
        with pytest.raises(ToolRejectionError, match="community or user"):
            build_cmdline(command, args, T)

    # L3: a decodable array of things that are not checkpoints is not read as clean.
    @pytest.mark.parametrize(
        "array",
        ['[{"name": "basic.Memory", "detail": "90% used"}]', '[1, "FAILED", null]',
         '[{"name": "basic.Memory", "detail": "x", "status": 3}]'],
    )  # fmt: skip
    def test_entries_that_are_not_checkpoints_make_the_block_unreadable(self, array):
        p = parse_health_check(f"=====x=====\n:checkpoints:{array}\n")
        assert p["checkpoints_unreadable"] == ["x"]

    # L4: a builder fault is logged with its stack before it becomes a refusal.
    def test_a_builder_fault_is_logged_with_its_stack(self, monkeypatch, caplog):
        def trips(a, t):
            raise TypeError("unsupported operand")

        monkeypatch.setitem(
            COMMANDS, "uptime", dataclasses.replace(COMMANDS["uptime"], build=trips)
        )
        with caplog.at_level(logging.ERROR, logger=LOGGER), pytest.raises(ToolRejectionError):
            build_cmdline("uptime", {}, T)
        (record,) = [r for r in caplog.records if r.name == LOGGER]
        assert record.exc_info and isinstance(record.exc_info[1], TypeError)

    async def test_a_line_the_final_guard_refuses_in_run_debug_is_logged(self, client, caplog):
        with (
            respx.mock(assert_all_called=False) as router,
            caplog.at_level(logging.WARNING, logger=LOGGER),
        ):
            router.route(host=PORTAL_HOST).mock(httpx.Response(200, json={}))
            result = await cd.run_debug(client, 82, "!restart", time.monotonic() + 5)
        assert result["status"] == "rejected_by_tool"
        (record,) = [r for r in caplog.records if r.name == LOGGER]
        assert record.levelno == logging.WARNING and "!restart" in record.getMessage()

    # L5: a comparison operator stands alone, and no second command head rides on a line.
    @pytest.mark.parametrize(
        "where",
        [
            "h!=evilhost",
            "h>=evilhost",
            "h<=evilhost",
            "Name = 'a' !=x",
            "Name ='x'",
            "ProcessId >=4",
        ],
    )
    def test_an_operator_with_an_equals_stands_alone_between_spaces(self, where):
        with pytest.raises(ToolRejectionError, match="key=value"):
            build_cmdline("wmi", {"query": f"select * from Win32_Service where {where}"}, T)

    @pytest.mark.parametrize(
        "line", ["!uptime !restart", "!ping 10.0.0.5 !groovy", "!perf type=ds\t!restart"]
    )
    def test_the_final_guard_refuses_a_second_command_head(self, line):
        with pytest.raises(ToolRejectionError):
            check_cmdline(line)

    def test_a_not_equals_comparison_is_not_a_second_head(self):
        check_cmdline("!wmi h=10.0.0.5 select * from Win32_Service where State != 'Running'")

    # L7: what was sent, where, is logged before it is sent.
    @respx.mock
    async def test_the_command_line_collector_and_host_are_logged_before_sending(
        self, client, caplog, monkeypatch
    ):
        monkeypatch.setattr(cd, "POLL_SECONDS", 0.01)
        cd._POSTS.clear()
        cd._GETS.clear()
        mount({"!ping": "Sent: 1"}, device=PROBED)
        with caplog.at_level(logging.INFO, logger=LOGGER):
            await run(client, command="ping", device_id=89818)
        (record,) = [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]
        message = record.getMessage()
        assert "!ping 127.0.0.1" in message and "collector 82" in message
        assert "device 89818" in message and "host 127.0.0.1" in message

    # Threat 3: portal words with a line break cannot forge a second log line.
    def test_portal_words_are_logged_on_one_line(self, caplog):
        error = LMError("bad request\nWARNING forged line", code="HTTP_400", details="a\r\nb")
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            describe_failure(error)
        (record,) = [r for r in caplog.records if r.name == LOGGER]
        assert "\n" not in record.getMessage() and "\r" not in record.getMessage()


class TestSecurityReviewRecheck:
    """The re-check of the folded module (collector-debug-review-2026-11.md, Re-verification)."""

    # R1: a parent class returns its subclasses' rows, so the parents of the refused classes
    # are refused too, and CIM_Process follows Win32_Process's column rule.
    @pytest.mark.parametrize(
        "query",
        ["select * from CIM_Product", "select * from CIM_Job", "select Command from cim_setting", "select * from CIM_LogicalFile", "select * from CIM_LogicalElement",
         "select * from CIM_ManagedSystemElement", "select * from CIM_SystemResource",
         "select * from Win32_ShortcutFile", "select * from Win32_CodecFile", "select * from cim_process",
         "select Name, CommandLine from CIM_Process"],
    )  # fmt: skip
    def test_a_parent_or_subclass_of_a_refused_class_is_refused(self, query):
        with pytest.raises(ToolRejectionError, match="is not queried"):
            build_cmdline("wmi", {"query": query}, T)

    @pytest.mark.parametrize(
        "cls",
        [
            "CIM_LogicalFile",
            "cim_product",
            "Win32_Process",
            "CIM_Process",
            "CIM_Setting",
            "cim_job",
        ],
    )
    def test_cim_refuses_the_parents_and_the_process_classes(self, cls):
        with pytest.raises(ToolRejectionError, match="class"):
            build_cmdline("cim", {"class": cls}, T)

    # R2: a refused column cannot be read back through the WHERE clause.
    @pytest.mark.parametrize(
        "where",
        [
            "CommandLine LIKE '%-P S%'",
            "commandline = 'x'",
            "Name = 'a' AND (CommandLine LIKE 'x%')",
        ],
    )
    def test_a_refused_column_in_the_where_clause_is_refused(self, where):
        with pytest.raises(ToolRejectionError, match="CommandLine"):
            build_cmdline(
                "wmi", {"query": f"select Name, ProcessId from Win32_Process where {where}"}, T
            )

    def test_a_refused_column_name_inside_quotes_is_a_value(self):
        query = "select Name, ProcessId from Win32_Process where Name = 'CommandLine'"
        assert build_cmdline("wmi", {"query": query}, T) == f"!wmi h=10.0.0.5 {query}"

    # Notes: command lines in other classes, and classes that enumerate a domain.
    @pytest.mark.parametrize(
        "query,why",
        [("select Command from Win32_StartupCommand", "Win32_StartupCommand is not queried"),
         ("select * from Win32_ScheduledJob", "Win32_ScheduledJob is not queried"),
         ("select * from Win32_UserAccount", "WHERE"),
         ("select * from Win32_Group", "WHERE")],
    )  # fmt: skip
    def test_command_columns_and_domain_wide_classes(self, query, why):
        with pytest.raises(ToolRejectionError, match=why):
            build_cmdline("wmi", {"query": query}, T)

    def test_a_local_account_query_builds(self):
        query = "select Name from Win32_UserAccount where LocalAccount = True"
        assert build_cmdline("wmi", {"query": query}, T) == f"!wmi h=10.0.0.5 {query}"

    # R4: an IPvFuture literal is refused as a value, with no traceback logged.
    def test_an_ipvfuture_url_is_refused_without_a_traceback(self, caplog):
        with (
            caplog.at_level(logging.DEBUG, logger=LOGGER),
            pytest.raises(ToolRejectionError, match="loopback"),
        ):
            request("http", collector_id=None, device_id=5, args={"url": "http://[v1.a:b]/"})
        assert [r for r in caplog.records if r.name == LOGGER] == []

    # R3 and R7: names that resolve to loopback or metadata, wildcard DNS, the 0.0.0.0/8 range,
    # platform endpoints, and an IPv4 address carried inside an IPv6 form.
    @pytest.mark.parametrize(
        "host",
        ["localhost.localdomain", "ip6-localhost", "ip6-loopback", "localhost4", "localhost6",
         "instance-data", "instance-data.ec2.internal", "metadata.tencentyun.com", "metadata.goog",
         "169.254.169.254.nip.io", "127.0.0.1.sslip.io", "localtest.me", "app.lvh.me",
         "0.0.0.1", "0.1.2.3", "168.63.129.16", "fd00:ec2::23", "::7f00:1", "::127.0.0.1",
         "::ffff:0:7f00:1", "64:ff9b::a9fe:a9fe", "64:ff9b:1::a9fe:a9fe", "2002:a9fe:a9fe::"],
    )  # fmt: skip
    def test_http_never_reaches_these_hosts_either(self, host):
        url_host = f"[{host}]" if ":" in host else host
        with pytest.raises(ToolRejectionError, match="loopback, link-local or cloud metadata"):
            build_cmdline("http", {"url": f"http://{url_host}/"}, Target(collector_id=7, host=host))

    @pytest.mark.parametrize(
        "host", ["64:ff9b::a00:5", "2002:a00:5::", "nip.io.example.net", "myinstance-data.net"]
    )
    def test_an_ordinary_embedded_or_lookalike_host_still_builds(self, host):
        url_host = f"[{host}]" if ":" in host else host
        cmdline = build_cmdline(
            "http", {"url": f"http://{url_host}/"}, Target(collector_id=7, host=host)
        )
        assert cmdline == f"!http http://{url_host}/"

    # R5: the -C community flag, and a portal error body masked before it is cut.
    def test_a_capital_c_community_flag_is_masked(self):
        assert redact("check_snmp -H h -C s3cretcomm -o x") == "check_snmp -H h -C *** -o x"

    def test_the_error_body_is_masked_before_it_is_cut(self):
        words = "x" * 3983 + " http://admin:hunter2@10.0.0.5/"
        assert words.index("hunter2") < 4000 < words.index("hunter2") + len("hunter2")
        failure = describe_failure(LMError(words, code="HTTP_400"))
        assert "hun" not in failure["error_body"] and len(failure["error_body"]) <= 4000

    # Note: a second head of any name characters.
    def test_the_final_guard_refuses_a_second_head_of_any_name(self):
        with pytest.raises(ToolRejectionError):
            check_cmdline("!uptime !_x")


# The classes the sandbox's own WMI datasources collect from (probes-2026-11.md), as
# their collectorAttribute.queryClass spells them.
PROBED_CLASSES = [
    "Win32_OperatingSystem",
    "Win32_PerfFormattedData_NETFramework_NETCLRLoading",
    "Win32_PerfFormattedData_NETFramework_NETCLRMemory",
    "Win32_PerfRawData_ClussvcPerfProvider_ClusterMulticastRequestResponseMessages",
    "Win32_PerfRawData_ClussvcPerfProvider_ClusterResourceControlManager",
    "Win32_PerfRawData_Counters_VMwareBlast",
    "Win32_PerfRawData_DirectoryServices_DirectoryServices",
    "Win32_PerfRawData_GmoPerfProvider_HyperVVMSaveSnapshotandRestore",
    "Win32_PerfRawData_HvStats_HyperVHypervisorVirtualProcessor",
    "Win32_PerfRawData_LocalSessionManager_TerminalServices",
    "Win32_PerfRawData_MSExchangeCalendarAttendant_MSExchangeCalendarAttendant",
    "Win32_PerfRawData_MSExchangeRpcClientAccess_MSExchangeRpcClientAccess",
    "Win32_PerfRawData_MSMQ_MSMQQueue",
    "Win32_PerfRawData_MSMQ_MSMQService",
    "Win32_PerfRawData_MSSQLLYNCLOCAL_MSSQLLYNCLOCALDatabases",
    "Win32_PerfRawData_MediaPerf_LSMEDIAInformational",
    "Win32_PerfRawData_MediaPerf_LSMEDIAOperations",
    "Win32_PerfRawData_MediaPerf_LSMEDIAPlanning",
    "Win32_PerfRawData_MediationPerf_LSMediationServerinboundCalls",
    "Win32_PerfRawData_MediationPerf_LSMediationServeroutboundCalls",
    "Win32_PerfRawData_NETFramework_NETCLRExceptions",
    "Win32_PerfRawData_NETFramework_NETCLRLocksAndThreads",
    "Win32_PerfRawData_NvspNicStats_HyperVVirtualNetworkAdapter",
    "Win32_PerfRawData_NvspPortStats_HyperVVirtualSwitchPort",
    "Win32_PerfRawData_NvspSwitchStats_HyperVVirtualSwitch",
    "Win32_PerfRawData_PerfDisk_LogicalDisk",
    "Win32_PerfRawData_PerfDisk_PhysicalDisk",
    "Win32_PerfRawData_PerfNet_Server",
    "Win32_PerfRawData_PerfOS_Memory",
    "Win32_PerfRawData_PerfOS_System",
    "Win32_PerfRawData_PerfProc_Process",
    "Win32_PerfRawData_S4Perf_LSSipEpsSipDialogs",
    "Win32_PerfRawData_S4Perf_LSSipEpsSipEpsConnections",
    "Win32_PerfRawData_S4Perf_LSSipEpsSipEpsTransactions",
    "Win32_PerfRawData_SQLSERVERAGENT_SQLAgentJobs",
    "Win32_PerfRawData_Tcpip_NetworkInterface",
    "Win32_PerfRawData_Tcpip_TCP",
    "Win32_PerfRawData_Tcpip_TCPv4",
    "Win32_PerfRawData_Tcpip_UDP",
    "Win32_PerfRawData_Tcpip_UDPv4",
    "Win32_PerfRawData_UcwaPerf_LSWEBUCWA",
    "Win32_PerfRawData_W3SVC_WebService",
    "Win32_PerfRawData_WSIPPerf_LSSIPPeers",
    "Win32_PrintJob",
    "Win32_Service",
    "Win32_Volume",
    "win32_PerfRawData_apppoolcountersprovider_apppoolwas",
    "win32_logicaldisk",
    "win32_perfrawdata_dns_dns",
]


def _refusal(command, args):
    with pytest.raises(ToolRejectionError) as caught:
        build_cmdline(command, args, T)
    return str(caught.value)


class TestWmiAllowlist:
    """R3.9: wmi and cim read only allowlisted classes, and Win32_Process only by listed columns."""

    def test_the_allowlist_is_the_probed_classes_and_97s_cases(self):
        allowed = {name.lower() for name in cd.WMI_CLASSES}
        assert len(PROBED_CLASSES) == 49
        assert allowed == {c.lower() for c in PROBED_CLASSES} | {
            "win32_process",
            "cim_computersystem",
            "win32_ntlogevent",
            "win32_useraccount",
            "win32_group",
        }

    @pytest.mark.parametrize("cls", [*PROBED_CLASSES, "CIM_ComputerSystem", "WIN32_SERVICE"])
    def test_an_allowlisted_class_builds_with_wmi_and_cim(self, cls):
        query = f"select * from {cls}"
        assert build_cmdline("wmi", {"query": query}, T) == f"!wmi h=10.0.0.5 {query}"
        assert build_cmdline("cim", {"class": cls}, T) == f"!cim h=10.0.0.5 c={cls}"

    def test_the_default_query_still_builds(self):
        assert build_cmdline("wmi", {}, T) == "!wmi h=10.0.0.5 select * from Win32_Service"

    @pytest.mark.parametrize(
        "cls",
        ["CIM_LogicalElement", "CIM_ManagedSystemElement", "CIM_Setting", "CIM_Job", "CIM_Process",
         "Win32_BIOS", "Win32_StartupCommand", "Win32_ScheduledJob", "Win32_Product", "X"],
    )  # fmt: skip
    def test_any_other_class_is_refused_naming_the_allowed_classes(self, cls):
        message = _refusal("wmi", {"query": f"select Name from {cls}"})
        assert f"the class {cls} is not queried" in message
        for written in cd.WMI_CLASSES.values():
            assert written.name in message, written.name
        message = _refusal("cim", {"class": cls})
        assert f"the class {cls} is not queried" in message
        for key, written in cd.WMI_CLASSES.items():
            whole = written.columns is None and key not in cd._WHERE_CLASSES
            assert (written.name in message) is whole, written.name

    @pytest.mark.parametrize(
        "query,bad",
        [("select * from Win32_Process", "*"),
         ("select Name, CommandLine from Win32_Process", "CommandLine"),
         ("select Name, Owner from Win32_Process", "Owner"),
         ("select Name from Win32_Process where commandline LIKE '%-p%'", "commandline"),
         ("select Name from Win32_Process where User = 'svc'", "User"),
         ("select Name from win32_process where Name = 'a' AND (UserName = 'b')", "UserName")],
    )  # fmt: skip
    def test_win32_process_reads_only_its_listed_columns(self, query, bad):
        message = _refusal("wmi", {"query": query})
        assert f"{bad} is not one of them" in message
        assert "Win32_Process is read only by these columns" in message
        for column in cd.WMI_CLASSES["win32_process"].columns:
            assert column in message
        assert len(cd.WMI_CLASSES["win32_process"].columns) == 44
        assert "CommandLine" not in cd.WMI_CLASSES["win32_process"].columns

    @pytest.mark.parametrize(
        "query",
        ["select Name, ProcessId, WorkingSetSize from Win32_Process where Name = 'svchost.exe' AND ThreadCount > 10",
         "select name from win32_process where processid = 4",
         "select Name from Win32_Process where Name LIKE 'sql%' OR NOT Priority = 8",
         "select ExecutablePath from Win32_Process where ExecutablePath IS NOT NULL",
         "select Name from Win32_Process where Name = 'CommandLine' AND SessionId = 0"],
    )  # fmt: skip
    def test_listed_columns_and_wql_words_build(self, query):
        assert build_cmdline("wmi", {"query": query}, T) == f"!wmi h=10.0.0.5 {query}"

    @pytest.mark.parametrize("cls", ["Win32_Process", "win32_process"])
    def test_cim_refuses_a_class_read_by_its_columns(self, cls):
        message = _refusal("cim", {"class": cls})
        assert "Win32_Process is not queried with cim" in message

    @pytest.mark.parametrize(
        "cls,written",
        [
            ("Win32_NTLogEvent", "Win32_NTLogEvent"),
            ("win32_useraccount", "Win32_UserAccount"),
            ("WIN32_GROUP", "Win32_Group"),
        ],
    )
    def test_cim_refuses_a_class_read_only_with_a_where_clause(self, cls, written):
        message = _refusal("cim", {"class": cls})
        assert f"{written} is read only with a WHERE clause, which cim cannot carry" in message
        assert f"select * from {written} where " in message

    # A quote after an odd run of backslashes is escaped in WQL and closes the string read
    # literally, so the two readings would split the clause differently.
    @pytest.mark.parametrize(
        "query",
        [
            "select Name from Win32_Process where Name = 'a\\' AND Name = ' OR CommandLine LIKE '%1%'",
            "select Name from Win32_Service where Name = 'O\\'Brien'",
            "select Name from Win32_Service where PathName = 'C:\\\\\\' OR Name = 'x'",
        ],
    )
    def test_a_quote_escaped_with_a_backslash_is_refused(self, query):
        assert "a quote after an odd number of backslashes" in _refusal("wmi", {"query": query})

    @pytest.mark.parametrize(
        "unit", ["'", "\\\\''", "x\\\\'"], ids=["quotes", "pairs-and-quotes", "even-runs"]
    )
    def test_the_backslash_check_is_linear_in_the_clause(self, unit):
        assert_linear(
            cd._check_where, lambda n: "Name = " + unit * (n // len(unit)), 100_000, 400_000
        )

    @pytest.mark.parametrize(
        "query",
        [
            "select Name from Win32_Service where PathName = 'C:\\\\'",
            "select Name from Win32_Service where PathName LIKE 'C:\\\\Windows\\\\%'",
            "select Name from Win32_Process where ExecutablePath = 'C:\\\\x.exe' AND Name = 'x.exe'",
        ],
    )
    def test_an_escaped_backslash_before_a_quote_still_builds(self, query):
        assert build_cmdline("wmi", {"query": query}, T) == f"!wmi h=10.0.0.5 {query}"

    @pytest.mark.parametrize(
        "query",
        [
            "select * from Win32_NTLogEvent",
            "select Name from Win32_UserAccount",
            "select * from win32_group",
        ],
    )
    def test_the_where_classes_keep_their_where_requirement(self, query):
        assert "is read only with a WHERE clause" in _refusal("wmi", {"query": query})

    def test_the_registry_says_which_classes_wmi_and_cim_read(self):
        from lm_mcp.registry import TOOLS

        tool = next(t for t in TOOLS if t.name == "collector_debug")
        text = tool.inputSchema["properties"]["args"]["description"]
        wmi = text.split("wmi: ", 1)[1].split(". ", 1)[0]
        for words in (
            "Win32_Service",
            "Win32_PerfRawData",
            "CIM_ComputerSystem",
            "Win32_Process",
            "CommandLine",
            "any other class is refused",
        ):
            assert words in wmi, words
        cim = text.split("cim: ", 1)[1].split(". ", 1)[0]
        assert "Win32_Process" in cim and "WHERE clause" in cim
