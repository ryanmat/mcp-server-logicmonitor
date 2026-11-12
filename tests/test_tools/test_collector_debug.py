# Description: Tests for collector_debug's command builder, allowlist and argument checks.
# Description: Hostile-input cases from PR #97 and its 2026-10-31 review; no transport is called.
# ruff: noqa: E501  (expected command lines are kept on one line to stay readable)

import dataclasses

import pytest

from lm_mcp.tools import collector_debug as cd
from lm_mcp.tools.collector_debug import (
    ALLOWED_HEADS,
    BLOCKED,
    BUDGET_DEFAULT,
    BUDGET_MAX,
    COMMANDS,
    OUTPUT_DEFAULT,
    Target,
    ToolRejectionError,
    build_cmdline,
    check_cmdline,
    check_request,
    target_from_record,
)

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
