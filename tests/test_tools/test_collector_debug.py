# Description: Tests for collector_debug's builder, allowlist, argument checks, masking and parse.
# Description: Hostile-input cases from PR #97 and its 2026-10-31 review; no transport is called.
# ruff: noqa: E501  (expected command lines and masked text are kept on one line to stay readable)

import dataclasses
import json
import logging
import time
from pathlib import Path

import pytest

from lm_mcp.exceptions import (
    AuthenticationError,
    LMError,
    LMPermissionError,
    RateLimitError,
    ServerError,
)
from lm_mcp.logging import is_sensitive_key
from lm_mcp.tools import collector_debug as cd
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
    describe_failure,
    parse_health_check,
    parse_reply,
    redact,
    target_from_record,
)

# Collector 161's stored health check, read live on 2026-11-12 (docs/validation/probes-2026-11.md,
# Step 72): 39 blocks, a WARN and a DISABLED checkpoint, one script at status 1.
LIVE_HEALTH = (Path(__file__).parent.parent / "fixtures" / "collector_health_check.txt").read_text()
# Built in two parts, so the repository's private-key hook does not read a test as a key.
PEM_BEGIN = "-----BEGIN RSA " + "PRIVATE KEY-----"
PEM_END = "-----END RSA " + "PRIVATE KEY-----"
PGP_BEGIN = "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----"


def assert_linear(work, make, small: int = 50_000, large: int = 200_000) -> None:
    """Four times the input takes about four times as long; a square would take sixteen.

    The best of three runs at each size is compared, the margin is wide for a loaded machine,
    and a small run under 10 ms counts as 10 ms, so timer noise on tiny runs does not decide.
    """

    def best(text: str) -> float:
        times = []
        for _ in range(3):
            started = time.perf_counter()
            work(text)
            times.append(time.perf_counter() - started)
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
            ("wmi", {"query": "select * from Win32_Process where User = 'svc'"},
             "!wmi h=10.0.0.5 select * from Win32_Process where User = 'svc'"),
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
            ("fe80::1", "https://[fe80::1]:8443/health"),
            ("[fe80::1]", "https://[FE80::1]/health"),
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
         ("wmi", {"query": "select * from X where Name = 'a' !restart"}),
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
