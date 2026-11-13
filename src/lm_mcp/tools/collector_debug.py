# Description: collector_debug: run one allowlisted collector debug command, write-gated, and
# Description: return what the collector said, masked and time-boxed against hostile replies.

"""Collector debug: one allowlisted debug command, sent to a collector and read back.

It is gated as a destructive write. Every allowed command is meant to read, but the call runs it
on the collector and opens a debug session the portal records in its Audit Log, and http sends
a GET that a device can act on, so collector_debug needs LM_ENABLE_WRITE_OPERATIONS.

Callers never send free text. They name a command from COMMANDS and pass that command's typed
arguments; any other argument key is refused, and this module builds the command line.

- Nothing in COMMANDS changes the collector, runs code on its host or takes a credential, and
  check_cmdline refuses any line whose head is not one of the 29 in ALLOWED_HEADS, whoever
  built it. getconfig and the stored health check are sent only in their fixed forms.
- The target is never the caller's to choose. Device probes take the host from the device
  record (a ``host`` argument is refused) and run on the collector the record names, since a
  private address means something else inside another collector's network; an http URL must
  name that same host, and checkserverconnectivity targets the configured portal.
- No credentials. Protocol probes run on the device's stored properties, so a URL with user
  information or a credential-named query parameter is refused, and a credential written as a
  parameter anywhere in the line is refused again by check_cmdline.
- A WMI query is one WQL SELECT. The collector reads any key=value token on the line as a
  parameter of !wmi, so the WHERE clause allows ``!`` only as ``!=``, and each operator that
  holds ``=`` stands alone between spaces: no command head and no parameter can ride in it.
- wmi and cim read only the classes in WMI_CLASSES, and a class with a column list, such as
  Win32_Process, only by those columns, in the SELECT list and the WHERE clause.
- Output is the device's and so hostile input. redact() masks the secret values a collector or
  device prints (key=value, key: value, JSON, XML, URL user information, PEM blocks) by the
  credential rule the audit log uses, and every scan grows with the length of the text, never
  with its square, so a hostile reply cannot hold the server.
- The stored health check (!shealthcheck func=detail) is sectioned text: "=====name=====" blocks,
  each with "is scheduled at ..., finished at ..., status N", optional detail, and a
  ":checkpoints:" JSON array of {name, detail, status}. parse_health_check() leads with each
  method's all-NaN rate, since a collector can show every checkpoint OK with a tenth of a
  method's tasks returning nothing, and names any block whose array it cannot read.
- A failure is logged before it becomes a status: describe_failure() logs an LMError at WARNING
  with the portal's words and anything else with its stack trace, and parse_reply() logs a parse
  fault with its stack trace and leaves the answer standing.
- One wall-clock budget per call holds the device read, the POST and every poll, each cut off by
  asyncio.timeout. A command the collector does not answer in time returns no_reply.
- Honest states: answered and no_reply are results; refused, disabled, unsupported, rate_limited
  and error come back in the error envelope with the call's record in its details, and a
  request refused before anything is sent is REJECTED_BY_TOOL. Never a guessed success.

Transport, as the sandbox portal answered on 2026-11-12 (docs/validation/probes-2026-11.md):

- POST /debug?collectorId=N with {"cmdline": ...} returns a session id; the collector fetches the
  command on its next check-in, and GET /debug/{sessionId} reads the result.
- On one portal, the read with collectorId and the read without it have each said "cancelled"
  while the other answered, from one session to the next, so both are asked on every poll.
- While the collector runs the command, a read answers HTTP 202 with errorCode 1202 ("agent has
  fetched the task, waiting for response"); a single word such as "cancelled" or "pending" is a
  session status, not output.
- #97 gives the portal's limits as 200 POSTs and 500 GETs a minute, a figure the probes here did
  not measure; this module counts its own calls and stops short of both.
"""

from __future__ import annotations

import asyncio
import bisect
import ipaddress
import json
import logging
import math
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast
from urllib.parse import SplitResult, parse_qsl, urlsplit

import httpx
from mcp.types import TextContent

from lm_mcp.exceptions import AuthenticationError, LMError, LMPermissionError, RateLimitError
from lm_mcp.logging import is_sensitive_key
from lm_mcp.tools import format_response, handle_error, lm_error_code, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

logger = logging.getLogger(__name__)

BUDGET_DEFAULT = 15.0
BUDGET_MIN = 2.0
BUDGET_MAX = 60.0
OUTPUT_DEFAULT = 20_000
OUTPUT_MIN = 500
OUTPUT_MAX = 100_000  # the most of a reply a parse reads or a caller is shown
HEALTH_SHOWN_MAX = 4_000  # raw characters shown beside the parsed health check
MAX_CMDLINE = 2048
_ID_MAX = 10**12  # the largest id or count read as one

# Never sent, whatever builds the command line: each changes the collector, its host or a
# target, runs code, or reads a credential.
BLOCKED = frozenset({
    "restart", "sbshutdown", "reload", "svc", "upgradeproxy", "register", "keepagentalive",
    "reducelog", "loglevel", "log4jloglevel", "sconfig", "tcancel", "tremove", "groovy", "posh",
    "java", "jcmd", "syswmic", "typeperf", "logman", "cp", "put", "replace", "unzip", "dumpheap",
    "packetcapture", "packetcapture2", "uploadlog", "hostproperty", "wmimethod", "syslogsender",
    "checkcredential", "jdbc", "healthcheckv2", "decryptfilesha", "digest", "etw", "account",
    "debughistory",
})  # fmt: skip
# A credential key written as a parameter (key=value) anywhere in the line, not only at a word
# start after whitespace. "User = 'x'" in a WQL comparison is not a parameter and passes.
_CREDENTIAL_RE = re.compile(
    r"(?<![A-Za-z0-9])(password|passwd|pass|pwd|authToken|privToken|community|username|user"
    r"|security|secret|token|apikey|api_key)=",
    re.IGNORECASE,
)


class ToolRejectionError(ValueError):
    """The request was refused by this tool before anything was sent."""


class CommandLineRejectionError(ToolRejectionError):
    """The composed command line, not one argument, was refused (see check_cmdline)."""


@dataclass(frozen=True)
class Target:
    """Where a command runs and what it may point at, fixed before any argument is read."""

    collector_id: int
    host: str | None = None  # the device record's host, for device probes
    portal_host: str | None = None  # the configured portal, for checkserverconnectivity


# ---------------------------------------------------------------- argument values

# A letter, digit or "[" first, so a name such as "-n" cannot read as an option.
_HOST_RE = re.compile(r"^[A-Za-z0-9\[][A-Za-z0-9._:\-\[\]%]*$")
_GLOB_RE = re.compile(r"^[A-Za-z0-9._:\-*?\[\]%]+$")
# [0-9], not \d, which also matches other scripts' digits; no leading zeros.
_OID_RE = re.compile(r"^\.?(0|[1-9][0-9]{0,9})(\.(0|[1-9][0-9]{0,9})){0,63}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_CLASS_RE = re.compile(r"^[A-Za-z0-9_]+$")
# The root and the tops of mgmt, mib-2, private and enterprises: a walk there is the whole device.
_ROOT_OIDS = {(0,), (1,), (2,), (1, 3), (1, 3, 6), (1, 3, 6, 1), (1, 3, 6, 1, 2),
              (1, 3, 6, 1, 2, 1), (1, 3, 6, 1, 4), (1, 3, 6, 1, 4, 1)}  # fmt: skip
# SNMP-USER-BASED-SM-MIB (users and their keys) and SNMP-COMMUNITY-MIB (community strings):
# reading either returns the device's own credentials, and walking a parent of one reads it.
_SECRET_OIDS = ((1, 3, 6, 1, 6, 3, 15), (1, 3, 6, 1, 6, 3, 18))
LOG_FILES = ("wrapper.log", "sbproxy.log", "watchdog.log")


def _oid_arcs(oid: str) -> tuple[int, ...]:
    return tuple(int(part) for part in oid.strip(".").split("."))


def _check_oid(oid: str, *, walk: bool) -> None:
    """Refuse an OID in the SNMP community or user tables, and for a walk, one above them."""
    arcs = _oid_arcs(oid)
    for secret in _SECRET_OIDS:
        if arcs[: len(secret)] == secret or (walk and secret[: len(arcs)] == arcs):
            raise ToolRejectionError(
                f"'{oid}' reads the SNMP community or user tables, which hold the device's "
                "credentials"
            )


def _device(t: Target) -> str:
    if not t.host:
        raise ToolRejectionError("device_id is required: the target is the device record's host")
    return t.host


def _required(args: dict[str, Any], key: str) -> str:
    value = str(args.get(key) or "").strip()
    if not value:
        raise ToolRejectionError(f"'{key}' is required")
    return value


def _opt(
    args: dict[str, Any],
    key: str,
    allowed: tuple[str, ...] | None = None,
    pattern: re.Pattern[str] | None = None,
) -> str | None:
    value = args.get(key)
    if value in (None, ""):
        return None
    text = str(value).strip()
    if allowed is not None and text not in allowed:
        raise ToolRejectionError(f"'{key}' must be one of {', '.join(allowed)}")
    if pattern is not None and not pattern.match(text):
        raise ToolRejectionError(f"'{key}' has an invalid value")
    return text


def _int(
    args: dict[str, Any], key: str, lo: int, hi: int, default: int | None = None
) -> int | None:
    value = args.get(key)
    if value is None or value == "":
        value = default
    if value is None:
        return None
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise ToolRejectionError(f"'{key}' must be a whole number")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as e:
        raise ToolRejectionError(f"'{key}' must be a whole number") from e
    if not lo <= number <= hi:
        raise ToolRejectionError(f"'{key}' must be between {lo} and {hi}")
    return number


def _list(args: dict[str, Any], key: str, pattern: re.Pattern[str], lo: int, hi: int) -> list[str]:
    raw = args.get(key) or []
    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()
    if not isinstance(raw, list):
        raise ToolRejectionError(f"'{key}' must be a list")
    items = [str(x).strip() for x in raw if str(x).strip()]
    if not lo <= len(items) <= hi:
        raise ToolRejectionError(f"'{key}' takes {lo} to {hi} values")
    for item in items:
        if not pattern.match(item):
            raise ToolRejectionError(f"'{item}' is not a valid value for '{key}'")
    return items


def _count(value: Any) -> int | None:
    """A non-negative whole number from an int or an ASCII digit string, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= _ID_MAX else None
    if isinstance(value, str):
        text = value.strip()
        if text.isascii() and text.isdigit() and len(text) <= 12:
            return int(text) if int(text) <= _ID_MAX else None
    return None


def _join(*parts: Any) -> str:
    return " ".join(str(p) for p in parts if p not in (None, ""))


def _kv(name: str, value: Any) -> str | None:
    return None if value in (None, "") else f"{name}={value}"


# ---------------------------------------------------------------- builders


def _b_ping(a: dict[str, Any], t: Target) -> str:
    kind = _opt(a, "type", ("default", "all", "proxy", "sys", "java"))
    return _join("!ping", _kv("type", kind), _kv("count", _int(a, "count", 1, 20)), _device(t))


def _b_snmpwalk(a: dict[str, Any], t: Target) -> str:
    oid = _opt(a, "oid", pattern=_OID_RE) or ".1.3.6.1.2.1.1"
    if _oid_arcs(oid) in _ROOT_OIDS:
        raise ToolRejectionError(
            "walking from the root of the tree, or the top of mib-2 or enterprises, is "
            "refused; walk a subtree"
        )
    _check_oid(oid, walk=True)
    return _join("!snmpwalk", _kv("timeout", _int(a, "timeout", 1, 120)), _device(t), oid)


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_WQL_RE = re.compile(
    rf"^SELECT\s+(?P<cols>\*|{_IDENT}(\s*,\s*{_IDENT})*)\s+FROM\s+(?P<cls>{_IDENT})"
    r"(\s+WHERE\s+(?P<where>.+))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WmiClass:
    """A WMI or CIM class wmi and cim read: its name as written, and, for a class read by its
    columns alone, those columns (None: every column, and *) and why the others are not read."""

    name: str
    columns: tuple[str, ...] | None = None
    why: str = ""


# The classes LogicMonitor's WMI datasources collect from, as the sandbox portal's 59 name them
# in collectorAttribute.queryClass (docs/validation/probes-2026-11.md). A query on a class also
# returns its subclasses' rows, which is why the CIM parent classes (CIM_LogicalElement,
# CIM_ManagedSystemElement and the like) are left out.
_DATASOURCE_CLASSES = (
    "Win32_Service",
    "Win32_OperatingSystem",
    "Win32_Volume",
    "Win32_LogicalDisk",
    "Win32_PrintJob",
    "Win32_PerfRawData_PerfProc_Process",
    "Win32_PerfRawData_PerfOS_Memory",
    "Win32_PerfRawData_PerfOS_System",
    "Win32_PerfRawData_PerfDisk_LogicalDisk",
    "Win32_PerfRawData_PerfDisk_PhysicalDisk",
    "Win32_PerfRawData_PerfNet_Server",
    "Win32_PerfRawData_Tcpip_NetworkInterface",
    "Win32_PerfRawData_Tcpip_TCP",
    "Win32_PerfRawData_Tcpip_TCPv4",
    "Win32_PerfRawData_Tcpip_UDP",
    "Win32_PerfRawData_Tcpip_UDPv4",
    "Win32_PerfRawData_W3SVC_WebService",
    "Win32_PerfRawData_apppoolcountersprovider_apppoolwas",
    "Win32_PerfRawData_DNS_DNS",
    "Win32_PerfRawData_DirectoryServices_DirectoryServices",
    "Win32_PerfRawData_LocalSessionManager_TerminalServices",
    "Win32_PerfRawData_MSMQ_MSMQQueue",
    "Win32_PerfRawData_MSMQ_MSMQService",
    "Win32_PerfRawData_SQLSERVERAGENT_SQLAgentJobs",
    "Win32_PerfRawData_MSSQLLYNCLOCAL_MSSQLLYNCLOCALDatabases",
    "Win32_PerfRawData_Counters_VMwareBlast",
    "Win32_PerfFormattedData_NETFramework_NETCLRLoading",
    "Win32_PerfFormattedData_NETFramework_NETCLRMemory",
    "Win32_PerfRawData_NETFramework_NETCLRExceptions",
    "Win32_PerfRawData_NETFramework_NETCLRLocksAndThreads",
    "Win32_PerfRawData_ClussvcPerfProvider_ClusterMulticastRequestResponseMessages",
    "Win32_PerfRawData_ClussvcPerfProvider_ClusterResourceControlManager",
    "Win32_PerfRawData_GmoPerfProvider_HyperVVMSaveSnapshotandRestore",
    "Win32_PerfRawData_HvStats_HyperVHypervisorVirtualProcessor",
    "Win32_PerfRawData_NvspNicStats_HyperVVirtualNetworkAdapter",
    "Win32_PerfRawData_NvspPortStats_HyperVVirtualSwitchPort",
    "Win32_PerfRawData_NvspSwitchStats_HyperVVirtualSwitch",
    "Win32_PerfRawData_MSExchangeCalendarAttendant_MSExchangeCalendarAttendant",
    "Win32_PerfRawData_MSExchangeRpcClientAccess_MSExchangeRpcClientAccess",
    "Win32_PerfRawData_MediaPerf_LSMEDIAInformational",
    "Win32_PerfRawData_MediaPerf_LSMEDIAOperations",
    "Win32_PerfRawData_MediaPerf_LSMEDIAPlanning",
    "Win32_PerfRawData_MediationPerf_LSMediationServerinboundCalls",
    "Win32_PerfRawData_MediationPerf_LSMediationServeroutboundCalls",
    "Win32_PerfRawData_S4Perf_LSSipEpsSipDialogs",
    "Win32_PerfRawData_S4Perf_LSSipEpsSipEpsConnections",
    "Win32_PerfRawData_S4Perf_LSSipEpsSipEpsTransactions",
    "Win32_PerfRawData_UcwaPerf_LSWEBUCWA",
    "Win32_PerfRawData_WSIPPerf_LSSIPPeers",
)
# Every column Microsoft's Win32_Process class reference declares but CommandLine, whose
# arguments can carry passwords.
_PROCESS_COLUMNS = (
    "Caption", "CreationClassName", "CreationDate", "CSCreationClassName", "CSName",
    "Description", "ExecutablePath", "ExecutionState", "Handle", "HandleCount", "InstallDate",
    "KernelModeTime", "MaximumWorkingSetSize", "MinimumWorkingSetSize", "Name",
    "OSCreationClassName", "OSName", "OtherOperationCount", "OtherTransferCount", "PageFaults",
    "PageFileUsage", "ParentProcessId", "PeakPageFileUsage", "PeakVirtualSize",
    "PeakWorkingSetSize", "Priority", "PrivatePageCount", "ProcessId", "QuotaNonPagedPoolUsage",
    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaPeakPagedPoolUsage",
    "ReadOperationCount", "ReadTransferCount", "SessionId", "Status", "TerminationDate",
    "ThreadCount", "UserModeTime", "VirtualSize", "WindowsVersion", "WorkingSetSize",
    "WriteOperationCount", "WriteTransferCount",
)  # fmt: skip
# Every class wmi reads, by lower-case name; cim reads those with no column list and no WHERE
# requirement. Beside the datasource classes: PR #97's Win32_Process (by its columns) and
# CIM_ComputerSystem, and the three classes read only with a WHERE clause.
WMI_CLASSES = {
    entry.name.lower(): entry
    for entry in (
        *(WmiClass(name) for name in _DATASOURCE_CLASSES),
        WmiClass(
            "Win32_Process",
            _PROCESS_COLUMNS,
            "its others hold a command line (CommandLine), whose arguments can carry passwords",
        ),
        WmiClass("CIM_ComputerSystem"),
        WmiClass("Win32_NTLogEvent"),
        WmiClass("Win32_UserAccount"),
        WmiClass("Win32_Group"),
    )
}
# WQL words a WHERE clause holds beside column names.
_WQL_WORDS = frozenset({"and", "or", "not", "like", "is", "isa", "null", "true", "false"})
# Classes read only with a WHERE clause, as their rows run to a whole event log or domain:
# the name as written, and an example clause.
_WHERE_CLASSES = {
    "win32_ntlogevent": ("Win32_NTLogEvent", "Logfile = 'System'"),
    "win32_useraccount": ("Win32_UserAccount", "LocalAccount = True"),
    "win32_group": ("Win32_Group", "LocalAccount = True"),
}
_QUOTED_VALUE_RE = re.compile(r"'[^']*'?")
_WHERE_CHARS_RE = re.compile(r"^[A-Za-z0-9_ '%.,:\\/\-<>=!()]+$")


def _check_where(where: str) -> None:
    """Refuse a WHERE clause that could carry a command head or a key=value token.

    ``!`` stands only directly before ``=`` (``!=``), so no ``!restart`` rides after a
    comparison. Each operator that holds ``=`` (``=``, ``<=``, ``>=``, ``!=``) stands alone, with
    a space on each side (``Name = 'x'``), so no token reads as key=value, quoted or not. No quote
    follows an odd run of backslashes: WQL reads that quote as escaped, so a reading that takes
    every quote as a delimiter would split the clause into other strings and other column names.
    """
    if not _WHERE_CHARS_RE.match(where):
        raise ToolRejectionError("the WHERE clause holds a character the tool does not allow")
    backslashes = 0  # the run of backslashes just before ch
    for i, ch in enumerate(where):
        if ch == "'" and backslashes % 2:
            raise ToolRejectionError(
                "in the WHERE clause a quote after an odd number of backslashes is not allowed; "
                "write a literal backslash as two"
            )
        backslashes = backslashes + 1 if ch == "\\" else 0
        if ch == "!" and where[i + 1 : i + 2] != "=":
            raise ToolRejectionError("in the WHERE clause '!' is allowed only as '!='")
        if ch == "=":
            # The operator (=, <=, >=, !=) stands alone, with a space on each side.
            start = i - 1 if i > 0 and where[i - 1] in "<>!" else i
            if start == 0 or where[start - 1] != " " or where[i + 1 : i + 2] != " ":
                raise ToolRejectionError(
                    "a key=value token in the query would become a !wmi parameter; "
                    "write comparisons with a space on each side of the operator, "
                    "e.g. Name = 'x'"
                )


def _wmi_class(name: str, command: str) -> WmiClass:
    """The allowlisted class a wmi or cim call names; any other is refused, naming the classes
    that command reads."""
    entry = WMI_CLASSES.get(name.lower())
    if entry is None:
        readable = [
            e.name
            for key, e in WMI_CLASSES.items()
            if command == "wmi" or (e.columns is None and key not in _WHERE_CLASSES)
        ]
        raise ToolRejectionError(
            f"the class {name} is not queried: {command} reads only these classes: "
            + ", ".join(sorted(readable, key=str.lower))
        )
    return entry


def _b_wmi(a: dict[str, Any], t: Target) -> str:
    """One WQL SELECT: SELECT * | cols FROM Class [WHERE ...], with no key=value token."""
    query = " ".join(str(a.get("query") or "select * from Win32_Service").split())
    match = _WQL_RE.match(query)
    if not match:
        raise ToolRejectionError(
            "'query' must be one WQL SELECT: SELECT * | col[, col] FROM Class [WHERE ...]"
        )
    entry = _wmi_class(match.group("cls"), "wmi")
    where = match.group("where")
    if entry.name.lower() in _WHERE_CLASSES and not where:
        written, example = _WHERE_CLASSES[entry.name.lower()]
        raise ToolRejectionError(f"{written} is read only with a WHERE clause, e.g. {example}")
    if entry.columns is not None:
        allowed = {c.lower() for c in entry.columns}
        # Outside its quoted values, a name in the WHERE clause that is not a WQL word is a
        # column it tests.
        tested = [
            w
            for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", _QUOTED_VALUE_RE.sub(" ", where or ""))
            if w.lower() not in _WQL_WORDS
        ]
        names = [c.strip() for c in match.group("cols").split(",")] + tested
        bad = next((n for n in names if n.lower() not in allowed), None)
        if bad is not None:
            raise ToolRejectionError(
                f"{entry.name} is read only by these columns, in the SELECT list and the WHERE "
                f"clause, as {entry.why}: {', '.join(entry.columns)}; {bad} is not one "
                "of them"
            )
    if where:
        _check_where(where)
    auth = _opt(a, "authType", ("NTLMv2", "Kerberos"))
    return _join("!wmi", f"h={_device(t)}", _kv("authType", auth), query)


def _b_winrm(a: dict[str, Any], t: Target) -> str:
    return _join(
        "!winrm",
        f"host={_device(t)}",
        _kv("auth", _opt(a, "auth", ("Negotiate", "Kerberos"))),
        _kv("useSSL", _opt(a, "useSSL", ("true", "false"))),
        _kv("certCheck", _opt(a, "certCheck", ("true", "false"))),
        _kv("timeout", _int(a, "timeout", 1, 120)),
    )


# Query parameter names that carry a credential, beside every name the audit log masks
# (lm_mcp.logging.is_sensitive_key). Long words match anywhere in the name (accessToken,
# db_password); short ones match only as a whole word of it (pw, auth, sid), so author,
# oauth_state or sessions stay allowed.
_SECRET_PARAM_ANYWHERE = (
    "password", "passwd", "passphrase", "secret", "token", "apikey", "credential", "signature",
    "bearer", "privatekey", "community", "authorization", "accesskey", "authcode",
)  # fmt: skip
_SECRET_PARAM_WORDS = {
    "pw", "pwd", "pass", "key", "auth", "session", "sessionid", "sid", "sig", "user", "username",
    "login", "jwt", "otp", "cookie",
}  # fmt: skip


def _is_secret_param(name: str) -> bool:
    if is_sensitive_key(name):
        return True
    flat = re.sub(r"[^a-z0-9]", "", name.lower())
    if any(word in flat for word in _SECRET_PARAM_ANYWHERE):
        return True
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    words = {w for w in re.split(r"[^a-z0-9]+", spaced.lower()) if w}
    return bool(words & _SECRET_PARAM_WORDS)


def _bare(host: str) -> str:
    return host.strip("[]").lower()


# Hosts http refuses, by address or by a known name. A device named for one would point the
# probe at the collector host's own loopback services, or at a cloud metadata service from
# inside the network. A DNS name outside these lists that resolves to one is not caught.
_METADATA_ADDRESSES = frozenset(
    ipaddress.ip_address(a)
    for a in (
        "100.100.100.200",  # Alibaba Cloud
        "fd00:ec2::254",  # AWS, IPv6
        "fd00:ec2::23",  # EKS Pod Identity
        "192.0.0.192",  # Oracle Cloud
        "168.63.129.16",  # Azure WireServer
    )
)
_LOOPBACK_NAMES = frozenset({
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback", "localhost4",
    "localhost6", "localhost4.localdomain4", "localhost6.localdomain6",
})  # fmt: skip
_METADATA_NAMES = frozenset({
    "metadata", "metadata.google.internal", "metadata.goog", "instance-data",
    "instance-data.ec2.internal", "metadata.tencentyun.com",
})  # fmt: skip
# Public DNS that answers any name under it with the address written in the name.
_WILDCARD_DNS = ("nip.io", "sslip.io", "xip.io", "localtest.me", "lvh.me")
_THIS_NETWORK = ipaddress.ip_network("0.0.0.0/8")
# IPv6 forms that carry an IPv4 address in their low 32 bits: IPv4-compatible, SIIT, and NAT64.
_IPV4_IN_LOW_BITS = tuple(
    ipaddress.ip_network(n) for n in ("::/96", "::ffff:0:0:0/96", "64:ff9b::/96", "64:ff9b:1::/48")
)
_IPV6_LITERAL_RE = re.compile(r"^[0-9a-f:.]+(?:%[\w.-]+)?$")
_DOTTED_QUAD_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])$"
)
# 127.1, 2130706433, 0x7f000001: forms a resolver reads as an address but no device is named.
_NUMERIC_HOST_RE = re.compile(r"^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){0,3}$")


def _unreachable_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address in _METADATA_ADDRESSES
    ):
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return address in _THIS_NETWORK
    carried = [address.ipv4_mapped, address.sixtofour, *(address.teredo or ())]
    if any(address in network for network in _IPV4_IN_LOW_BITS):
        carried.append(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    return any(v4 is not None and _unreachable_address(v4) for v4 in carried)


def _unreachable_http_host(host: str) -> bool:
    """True for a host http refuses: loopback, unspecified, link-local or a cloud
    metadata service, by name, by address or carried inside an IPv6 address; a name under a
    public DNS that answers with the address written in it; an address in a numeric form other
    than four decimal parts; and a bracketed literal that is not IPv6 (IPvFuture)."""
    bare = _bare(host).rstrip(".")
    if (
        bare in _LOOPBACK_NAMES
        or bare.endswith(".localhost")
        or bare in _METADATA_NAMES
        or any(bare == d or bare.endswith(f".{d}") for d in _WILDCARD_DNS)
    ):
        return True
    if _NUMERIC_HOST_RE.match(bare) and not _DOTTED_QUAD_RE.match(bare):
        return True
    if ":" in bare and not _IPV6_LITERAL_RE.match(bare):
        return True
    if not (_DOTTED_QUAD_RE.match(bare) or ":" in bare):
        return False
    # urlsplit has checked a bracketed literal, and the URL's host equals the device's.
    return _unreachable_address(ipaddress.ip_address(bare))


def _parse_url(url: str) -> SplitResult:
    """Split a URL, or refuse it: a port out of range or a broken IPv6 literal is not a URL."""
    try:
        parts = urlsplit(url)
        _ = parts.port  # raises on a malformed port
    except ValueError as e:
        raise ToolRejectionError("'url' is not a valid URL") from e
    return parts


def _b_http(a: dict[str, Any], t: Target) -> str:
    """An HTTP(S) GET to the device itself: the URL's host must be the device record's host."""
    device = _device(t)
    url = _required(a, "url")
    if re.search(r"\s", url):
        raise ToolRejectionError("'url' cannot contain whitespace")
    parts = _parse_url(url)
    if parts.scheme not in ("http", "https"):
        raise ToolRejectionError("'url' must start with http:// or https://")
    if "#" in url:
        raise ToolRejectionError("'url' cannot carry a fragment (#...)")
    if ";" in parts.path or ";" in parts.query:
        raise ToolRejectionError("'url' cannot carry ';' parameters")
    if "@" in parts.netloc:
        raise ToolRejectionError("'url' cannot carry user information (user:password@)")
    if not parts.hostname:
        raise ToolRejectionError("'url' must name the device's host")
    if _bare(parts.hostname) != _bare(device):
        raise ToolRejectionError(
            f"'url' must point at the device itself ({device}), not another host"
        )
    if _unreachable_http_host(device):
        raise ToolRejectionError(
            f"'url' points at {device}, a loopback, link-local or cloud metadata address, "
            "which http does not reach"
        )
    for name, _value in parse_qsl(parts.query, keep_blank_values=True):
        if _is_secret_param(name):
            raise ToolRejectionError(f"'url' carries a credential-named parameter '{name}'")
    return _join("!http", _kv("timeout", _int(a, "timeout", 1, 120)), url)


def _b_perf(a: dict[str, Any], _t: Target) -> str:
    kind = _opt(a, "type", ("cpu", "queue", "ds")) or "ds"
    column = _opt(a, "dsFilterColumn", ("nan", "timeout", "queue", "dropped", "avg_exec"))
    if kind != "ds" and column:
        raise ToolRejectionError("'dsFilterColumn' applies only to type=ds")
    if kind == "ds" and not column:
        column = "nan"
    return _join(
        "!perf",
        f"type={kind}",
        _kv("dsFilterColumn", column),
        _kv("ds", _opt(a, "ds", pattern=_GLOB_RE)),
        _kv("h", _opt(a, "h", pattern=_GLOB_RE)),
    )


def _b_tlist(a: dict[str, Any], _t: Target) -> str:
    host = _opt(a, "h", pattern=_GLOB_RE)
    method = _opt(a, "c", pattern=_KEY_RE)
    if (not host or not re.search(r"[A-Za-z0-9]", host)) and not method:
        raise ToolRejectionError(
            "!tlist must be filtered with 'h' (host) or 'c' (method); unfiltered it is huge"
        )
    return _join("!tlist", _kv("c", method), _kv("h", host))


def _b_logsurf(a: dict[str, Any], _t: Target) -> str:
    level = _opt(a, "level", ("all", "trace", "debug", "info", "warn", "error")) or "error"
    count = _int(a, "n", 1, 500, default=50)
    files = a.get("files") or ["wrapper.log"]
    if isinstance(files, str):
        files = files.split()
    if not isinstance(files, list):
        raise ToolRejectionError(f"'files' must be a list naming {', '.join(LOG_FILES)}")
    for f in files:
        if f not in LOG_FILES:
            raise ToolRejectionError(f"'files' may only name {', '.join(LOG_FILES)}")
    unique = list(dict.fromkeys(files))
    return _join("!logsurf", f"level={level}", f"n={count}", *unique)


def _fixed(cmd: str) -> Callable[[dict[str, Any], Target], str]:
    return lambda _a, _t: cmd


def _b_health(_a: dict[str, Any], t: Target) -> str:
    return f"!shealthcheck func=detail collector={t.collector_id}"


# agent.conf keys getconfig may read: the thread pool and timeout of one collection method.
# Nothing else is read, so no other setting, credential or proxy value can be asked for.
_CONFIG_KEY_RE = re.compile(r"^collector\.[a-z][a-z0-9]*\.(threadpool|timeout)$")


def _b_getconfig(a: dict[str, Any], _t: Target) -> str:
    key = _required(a, "key")
    if not _CONFIG_KEY_RE.match(key):
        raise ToolRejectionError(
            "'key' must be a collection method's thread pool or timeout, "
            "e.g. collector.wmi.threadpool or collector.snmp.timeout"
        )
    return _join("!getconfig", key)


def _b_portal(_a: dict[str, Any], t: Target) -> str:
    if not t.portal_host:
        raise ToolRejectionError("the configured portal host is not known to this client")
    return _join("!checkserverconnectivity", t.portal_host)


def _b_aplist(a: dict[str, Any], _t: Target) -> str:
    states = ("failed", "done", "waiting", "executing", "duplicate", "unknown")
    status = _opt(a, "status", states) or "failed"
    return _join("!aplist", _kv("h", _opt(a, "h", pattern=_GLOB_RE)), f"status={status}")


def _b_splist(a: dict[str, Any], _t: Target) -> str:
    return _join("!splist", _kv("hostname", _opt(a, "hostname", pattern=_HOST_RE)))


def _b_tplist(a: dict[str, Any], _t: Target) -> str:
    states = ("WAITING", "EXECUTING", "DONE", "FAILED", "EMPTY")
    host = _kv("h", _opt(a, "h", pattern=_GLOB_RE))
    return _join("!tplist", host, _kv("status", _opt(a, "status", states)))


def _b_nslookup(_a: dict[str, Any], t: Target) -> str:
    return _join("!nslookup", _device(t))


def _b_mac(_a: dict[str, Any], t: Target) -> str:
    return _join("!macaddress", _device(t))


def _oids(a: dict[str, Any], lo: int, hi: int) -> list[str]:
    oids = _list(a, "oids", _OID_RE, lo, hi)
    for oid in oids:
        _check_oid(oid, walk=False)
    return oids


def _b_snmpdiagnose(a: dict[str, Any], t: Target) -> str:
    return _join("!snmpdiagnose", _device(t), *_oids(a, 0, 5))


def _b_snmpget(a: dict[str, Any], t: Target) -> str:
    return _join("!snmpget", _device(t), *_oids(a, 1, 10))


def _b_cim(a: dict[str, Any], t: Target) -> str:
    cls = _opt(a, "class", pattern=_CLASS_RE) or _required(a, "class")
    entry = _wmi_class(cls, "cim")
    if entry.name.lower() in _WHERE_CLASSES:
        written, example = _WHERE_CLASSES[entry.name.lower()]
        raise ToolRejectionError(
            f"{written} is read only with a WHERE clause, which cim cannot carry; read it with "
            f"wmi, e.g. select * from {written} where {example}"
        )
    if entry.columns is not None:
        raise ToolRejectionError(
            f"the class {entry.name} is not queried with cim, which returns every column; read "
            f"it with wmi by its columns, e.g. select Name from {entry.name}"
        )
    return _join("!cim", f"h={_device(t)}", f"c={cls}")


def _b_sslcerts(a: dict[str, Any], t: Target) -> str:
    port = _int(a, "port", 1, 65535)
    if port is None:
        raise ToolRejectionError("'port' is required")
    return _join("!sslcerts", _device(t), port)


# ---------------------------------------------------------------- the command set


@dataclass(frozen=True)
class Command:
    """One allowlisted command: its group, whether it probes a device, its builder, and the
    argument keys it takes."""

    group: str
    needs_device: bool
    build: Callable[[dict[str, Any], Target], str]
    keys: frozenset[str] = frozenset()


def _cmd(
    group: str,
    needs_device: bool,
    build: Callable[[dict[str, Any], Target], str],
    *keys: str,
) -> Command:
    return Command(group, needs_device, build, frozenset(keys))


COMMANDS: dict[str, Command] = {
    "uptime": _cmd("collector", False, _fixed("!uptime")),
    "health_check": _cmd("collector", False, _b_health),
    "perf": _cmd("collector", False, _b_perf, "type", "dsFilterColumn", "ds", "h"),
    "getconfig": _cmd("collector", False, _b_getconfig, "key"),
    "reportercache": _cmd("collector", False, _fixed("!reportercache")),
    "checkserverconnectivity": _cmd("collector", False, _b_portal),
    "avslist": _cmd("collector", False, _fixed("!avslist")),
    "firewallstatus": _cmd("collector", False, _fixed("!firewallstatus")),
    "ipaddress": _cmd("collector", False, _fixed("!ipaddress")),
    "tasklist": _cmd("collector", False, _fixed("!tasklist")),
    "logsurf": _cmd("collector", False, _b_logsurf, "level", "n", "files"),
    "adlist": _cmd("tasks", False, _fixed("!adlist")),
    "aplist": _cmd("tasks", False, _b_aplist, "h", "status"),
    "splist": _cmd("tasks", False, _b_splist, "hostname"),
    "tplist": _cmd("tasks", False, _b_tplist, "h", "status"),
    "nsplist": _cmd("tasks", False, _fixed("!nsplist")),
    "dxlist": _cmd("tasks", False, _fixed("!dxlist")),
    "tlist": _cmd("tasks", False, _b_tlist, "h", "c"),
    "ping": _cmd("device", True, _b_ping, "type", "count"),
    "nslookup": _cmd("device", True, _b_nslookup),
    "macaddress": _cmd("device", True, _b_mac),
    "snmpdiagnose": _cmd("device", True, _b_snmpdiagnose, "oids"),
    "snmpget": _cmd("device", True, _b_snmpget, "oids"),
    "snmpwalk": _cmd("device", True, _b_snmpwalk, "oid", "timeout"),
    "wmi": _cmd("device", True, _b_wmi, "query", "authType"),
    "winrm": _cmd("device", True, _b_winrm, "auth", "useSSL", "certCheck", "timeout"),
    "cim": _cmd("device", True, _b_cim, "class"),
    "http": _cmd("device", True, _b_http, "url", "timeout"),
    "sslcerts": _cmd("device", True, _b_sslcerts, "port"),
}

# The command heads the builders produce, and the exact forms of the two that take a key.
ALLOWED_HEADS = frozenset({
    "uptime", "shealthcheck", "perf", "getconfig", "reportercache", "checkserverconnectivity",
    "avslist", "firewallstatus", "ipaddress", "tasklist", "logsurf", "adlist", "aplist", "splist",
    "tplist", "nsplist", "dxlist", "tlist", "ping", "nslookup", "macaddress", "snmpdiagnose",
    "snmpget", "snmpwalk", "wmi", "winrm", "cim", "http", "sslcerts",
})  # fmt: skip
# A second command head after the first: whitespace, then "!" and a letter ("!=" is a comparison).
_SECOND_HEAD_RE = re.compile(r"\s![A-Za-z0-9_]")
_FIXED_FORMS = {
    "shealthcheck": re.compile(r"^!shealthcheck func=detail collector=[0-9]{1,12}$"),
    "getconfig": re.compile(r"^!getconfig collector\.[a-z][a-z0-9]*\.(threadpool|timeout)$"),
}


def check_args(command: str, args: dict[Any, Any]) -> None:
    """Refuse an unknown command, a host argument and any key the command does not take."""
    if command not in COMMANDS:
        raise ToolRejectionError(f"unknown or disallowed command '{command}'")
    keys = COMMANDS[command].keys
    if any(not isinstance(k, str) for k in args):
        raise ToolRejectionError("argument names must be strings")
    if "host" in args:
        raise ToolRejectionError(
            "'host' is not accepted: device probes take the host from device_id, and "
            "checkserverconnectivity targets the configured portal"
        )
    unknown = sorted(set(args) - keys)
    if unknown:
        takes = ", ".join(sorted(keys)) or "no arguments"
        raise ToolRejectionError(f"{command} takes {takes}; not {', '.join(unknown)}")


def build_cmdline(command: str, args: dict[str, Any], target: Target) -> str:
    """Compose the command line for a named command, or raise ToolRejectionError."""
    args = args or {}
    check_args(command, args)
    try:
        cmdline = COMMANDS[command].build(args, target)
    except ToolRejectionError:
        raise
    except (TypeError, ValueError) as e:
        logger.exception("collector_debug: the %s builder raised; refused", command)
        raise ToolRejectionError(f"an argument has a value of the wrong type ({e})") from e
    check_cmdline(cmdline)
    return cmdline


def check_cmdline(cmdline: str) -> None:
    """Final guard on any command line, however it was built: an allowlisted head, the exact
    health-check and getconfig forms, printable ASCII, a length cap and no credential. Target
    checks (the device's host, the portal) happen when the builders compose the line."""
    head = re.match(r"^!([A-Za-z0-9_]+)", cmdline or "")
    if not head:
        raise CommandLineRejectionError("not a debug command")
    name = head.group(1).lower()
    if name in BLOCKED:
        raise CommandLineRejectionError(
            f"!{head.group(1)} changes the collector, its host or a target, or reads a credential"
        )
    if head.group(1) not in ALLOWED_HEADS:
        raise CommandLineRejectionError(f"!{head.group(1)} is not a command this tool sends")
    form = _FIXED_FORMS.get(name)
    if form and not form.match(cmdline):
        raise CommandLineRejectionError(f"!{name} is sent only in its fixed form")
    if _SECOND_HEAD_RE.search(cmdline):
        raise CommandLineRejectionError("a command line carries one command head, never a second")
    if not all(" " <= ch <= "~" for ch in cmdline):  # also refuses a second line
        raise CommandLineRejectionError("a command line takes printable ASCII characters only")
    if len(cmdline) > MAX_CMDLINE:
        raise CommandLineRejectionError(f"the command line is longer than {MAX_CMDLINE} characters")
    if _CREDENTIAL_RE.search(cmdline):
        raise CommandLineRejectionError(
            "credentials are never sent; probes use the device's stored properties"
        )


# ---------------------------------------------------------------- the request


@dataclass(frozen=True)
class Request:
    """A collector_debug call's arguments, checked and clamped before any call is made."""

    command: str
    args: dict[str, Any]
    collector_id: int | None
    device_id: int | None
    budget_seconds: float
    max_output_chars: int


_PLACEHOLDER_HOST = "device.invalid"


def _finite(value: Any) -> float:
    """The value as a float: nan for anything but an int or a float, a bool included, and for an
    int too large for a float. An infinity passes through, and check_request refuses both."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return math.nan
    try:
        return float(value)
    except OverflowError:
        return math.nan


def check_request(
    command: Any,
    *,
    collector_id: Any,
    device_id: Any,
    args: Any,
    budget_seconds: Any,
    max_output_chars: Any,
    portal_host: str | None,
) -> Request:
    """Check everything the caller passed before any call: finite budgets, positive ids, an
    argument object, a known command, and every argument value, by building the command once
    against a placeholder device. The http URL's own host stands in for the device here, since the
    http builder refuses a URL whose host is not the target's."""
    budget, cap = _finite(budget_seconds), _finite(max_output_chars)
    if not (math.isfinite(budget) and math.isfinite(cap)):
        raise ToolRejectionError("budget_seconds and max_output_chars must be finite numbers")
    for name, value in (("collector_id", collector_id), ("device_id", device_id)):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= _ID_MAX
        ):
            raise ToolRejectionError(f"'{name}' must be a positive whole number")
    if args is not None and not isinstance(args, dict):
        raise ToolRejectionError("'args' must be an object of the command's arguments")
    checked_args = dict(args or {})
    if not isinstance(command, str) or command not in COMMANDS:
        raise ToolRejectionError(f"unknown or disallowed command '{command}'")
    host = _PLACEHOLDER_HOST
    if command == "http":
        host = _parse_url(str(checked_args.get("url") or "")).hostname or _PLACEHOLDER_HOST
    build_cmdline(command, checked_args, Target(collector_id=0, host=host, portal_host=portal_host))
    if COMMANDS[command].needs_device and device_id is None:
        raise ToolRejectionError(
            f"{command} needs device_id: the target is the device record's host"
        )
    if collector_id is None and device_id is None:
        raise ToolRejectionError("collector_id (or device_id) is required")
    return Request(
        command=command,
        args=checked_args,
        collector_id=collector_id,
        device_id=device_id,
        budget_seconds=min(max(budget, BUDGET_MIN), BUDGET_MAX),
        max_output_chars=int(max(cap, OUTPUT_MIN)),
    )


def target_from_record(
    command: str, record: Any, collector_id: int | None, portal_host: str | None
) -> Target:
    """The target a command runs against, from the device record: the record's host for a
    device probe, and the collector that serves the device. A command that needs no device runs
    on collector_id when the device has no collector.

    A collectorless device answers a negative currentCollectorId (-2 for a cloud resource, -4
    for a service), which reads as no collector.
    """
    if not isinstance(record, dict):
        raise ToolRejectionError("the device record could not be read")
    needs_device = COMMANDS[command].needs_device
    host = str(record.get("name") or "").strip() or None
    served_by = _count(record.get("currentCollectorId")) or None
    if needs_device and (not host or not _HOST_RE.match(host)):
        raise ToolRejectionError("the device record's host is not a plain hostname or IP address")
    runs_on = served_by if served_by is not None else collector_id
    if runs_on is None or (served_by is None and needs_device):
        raise ToolRejectionError("the device record names no collector to run the command on")
    if served_by is not None and collector_id is not None and collector_id != served_by:
        raise ToolRejectionError(
            f"this runs on the collector that serves the device ({served_by}), "
            f"not collector {collector_id}"
        )
    return Target(
        collector_id=runs_on,
        host=host if needs_device else None,
        portal_host=portal_host,
    )


# ---------------------------------------------------------------- output masking
# Best effort, and a second line of defence. The guarantees are elsewhere: no credential is
# ever sent, getconfig reads only thread-pool and timeout keys, and debughistory is never sent.
# Masking catches the common shapes a collector or device prints a secret in; an unusual shape
# can still slip through, and masking errs toward hiding too much rather than too little.
#
# Output is hostile input, so every scan either moves forward past what it read or is capped
# at a fixed length: the work grows with the length of the text, never with its square.

# A key names a secret when it ends in one of these words. The short words (pass, pwd, pw)
# count only at the start of the key or after a separator (wmi.pass, x_sid) or a camelCase
# step (wmiPass), so compass, bypass and superpass are not keys; the longer words count at the
# end of any key (dbpassword, snmp.authtoken, CLIENTSECRET).
_SECRET_KEY_WORDS = (
    "password", "passwd", "pass", "passphrase", "secret", "token", "community", "credential",
    "credentials", "signature", "authorization", "cookie", "bearer", "apikey", "api_key",
    "api-key", "accesskey", "access_key", "access-key", "privatekey", "private_key",
    "private-key", "secretkey", "secret_key", "secret-key", "sessionid", "session_id",
    "session-id", "storepass", "keypass", "authcode", "auth_code", "auth-code", "jwt", "pw",
    "pwd", "sig", "otp",
)  # fmt: skip
_SHORT_WORD = 4  # words this long or shorter need a boundary before them
_ASCII_LOWER_OR_DIGIT = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
_ASCII_UPPER = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_JVM_FLAG_RE = re.compile(r"^-+D?")
_COMPOUND_KEY_RE = re.compile(r"[._-]|[a-z0-9][A-Z]")  # a key of more than one word


def _is_secret_key(key: str) -> bool:
    """True when a key (wmi.pass, -Ddb.password, clientSecret, snmp.authtoken) names a secret.

    A key of more than one word (ssh.key, snmp_auth, snmpPriv, meraki.api.key) is also a secret
    wherever lm_mcp.logging.is_sensitive_key says so, so one rule decides the audit line and
    the masked output. A bare word such as key or auth is left to the list above, so a log's
    "key=value" or "auth: ok" is not masked.
    """
    key = _JVM_FLAG_RE.sub("", key)  # -Dwmi.pass, --password
    if _COMPOUND_KEY_RE.search(key) and is_sensitive_key(key):
        return True
    low = key.lower()
    for word in _SECRET_KEY_WORDS:
        if not low.endswith(word):
            continue
        start = len(key) - len(word)
        if start == 0 or len(word) > _SHORT_WORD:
            return True
        before, first = key[start - 1], key[start]
        if before in "._:-" or (before in _ASCII_LOWER_OR_DIGIT and first in _ASCII_UPPER):
            return True
    return False


_CAP = 512  # sets how far a <name> element and a bracketed value are read
_MASK_MARGIN = _CAP * 8  # masked past a cut, so a secret the cut splits is still seen whole
# key=value, key: value, "key": "value", -Dkey=value. The key is one token: word characters,
# dots and dashes, starting where the previous token ended.
_KEYED_RE = re.compile(r"""(?<![\w.-])["']?([\w.-]+)["']?[ \t]*([=:])""")
# --password value, -storepass value
_FLAG_RE = re.compile(r"(?<![\w.-])--?([A-Za-z][\w.-]+)(?=[ \t])")
_SPACES_RE = re.compile(r"[ \t]*")
# A quoted value with backslash escapes, on one line.
_QUOTED_RE = re.compile(r""""(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'""")
# An unquoted value ends at the line end, at markup (<tag, />), at a quote that closes the
# string the key sat in ("detail": "proxy pass: none", "status": ...), or where the next key
# starts. After "key=", the next key is "k=v", "k: " or a -flag; after "key:", the display
# form, only the next "k: ". A "=" that pads base64 (Basic dXNlcjpw==) never starts a key.
_STOPS = r"""[\r\n]|<(?=[A-Za-z/!?])|/>|["'](?=[ \t]*(?:[,;}\]>/\r\n]|\Z))"""
# After "key:", a JSON value also ends where its object or array closes: {"a":{"password":1}}.
_JSON_STOPS = r"""|[}\]](?=[ \t]*(?:[,}\]\r\n]|\Z))"""
_NEXT = r"""(?:[,;&][ \t]*|[ \t])"""
_VALUE_END_RES = {
    "=": re.compile(
        rf"""{_STOPS}|{_NEXT}(?:["']?[\w.:-]+["']?[ \t]*=(?=[^=\s])"""
        r"""|["']?[\w.-]+["']?[ \t]*:(?=[ \t\r\n]|\Z)|--?[A-Za-z])"""
        r"""|[,;&][ \t]*["'][\w.-]+["'][ \t]*:"""
    ),
    ":": re.compile(
        rf"""{_STOPS}{_JSON_STOPS}|{_NEXT}["']?[\w.-]+["']?[ \t]*:(?=[ \t\r\n]|\Z)"""
        r"""|[,;&][ \t]*["'][\w.-]+["'][ \t]*:"""
    ),
}
_KEY_AHEAD_RE = re.compile(r"[\w.-]+[ \t]*=")
# "password:" with its value on the next, indented line (YAML, pretty-printed JSON)
_NEXT_LINE_VALUE_RE = re.compile(r"\r?\n[ \t]+(?=[^\s])")
_KEY_LINE_RE = re.compile(r"""["']?[\w.-]+["']?[ \t]*[=:]|[-#]""")
# Authorization: Bearer xxx is a key; a bare "Bearer xxx" in a log line is caught here.
_BEARER_RE = re.compile(r"(?<![\w-])(bearer[ \t]+)([A-Za-z0-9._~+/=-]+)", re.IGNORECASE)
# A PEM private key block: a BEGIN line naming a PRIVATE KEY, the body, an END line.
_PEM_RE = re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY[A-Z ]{0,20}-----")
# name="wmi.pass" ... value="x", in either order, anywhere inside one XML tag or one JSON
# object: the text between two of the characters { } < >.
_SEGMENT_RE = re.compile(r"[^{}<>]+")
_NAME_FIELD_RE = re.compile(
    r"""(?<![\w.:-])["']?(?:name|key)["']?\s*[=:]\s*"""
    r"""(?:"([^"]*)"|'([^']*)'|([\w.:-]+))""",
    re.IGNORECASE,
)
_VALUE_FIELD_RE = re.compile(
    r"""((?<![\w.:-])["']?value["']?\s*[=:]\s*)(?:"([^"]*)"|'([^']*)'|([^\s"',;&]+))""",
    re.IGNORECASE,
)
_PAIR_SPAN = 512  # outside braces and tags, how far apart a name and its value field may be
# <password>value</password>, <Password type="x">, <entry key="wmi.pass">value</entry>
_TAG_RE = re.compile(r"<([A-Za-z_][\w.:-]*)((?:\s[^<>]*)?)>")
_CLOSE_TAG_RE = re.compile(r"</([A-Za-z_][\w.:-]*)")
_TAG_NAME_ATTR_RE = re.compile(
    r"""(?<![\w.:-])(?:name|key)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE
)
_LOOSE_TEXT_RE = re.compile(r"[^<]*")  # without a closing tag, the text up to the next tag
# <name>x.password</name><value>hunter2</value>, as Hadoop, Spring and .NET configs write it
_NAMED_VALUE_RE = re.compile(r"\s*<value(?:\s[^<>]*)?>", re.IGNORECASE)
_PATH_RE = re.compile(r"""["']?(?:[~/]|[A-Za-z]:[\\/])""")  # pwd: /usr/local, a directory
# scheme://userinfo@host, and scheme:\/\/ as JSON escapes it
_SCHEME_RE = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*:(?://|\\/\\/)")
# The authority ends at / ? # (RFC 3986), at whitespace and at characters an authority never
# holds (quotes, < > \ { } |), and at a comma, where text lists one URL after another.
_AUTHORITY_END_RE = re.compile(r"""[\s/?#"'<>\\{}|,]""")
# curl -u user:password, --user user:password
# The separator and the user cannot both match "=", so a long run of either is read once.
_USER_FLAG_RE = re.compile(r"(?<![\w.-])(--user|-u)((?:[ \t]+|=)[^\s:=]{1,256}:)(\S+)")
# sqlcmd -P password, sshpass -p password, snmpwalk -c community, check_snmp -C community
_SHORT_FLAG_RE = re.compile(r"(?<![\w.-])(-[pPcC])([ \t]+)(\S+)")


def _mask_value(text: str, pos: int, out: list[str], sep: str = "=") -> int:
    """Append the masked value that starts at pos and return where it ends. A quoted value
    keeps its quotes, and an empty one is kept whole: an empty password is itself a finding."""
    quoted = _QUOTED_RE.match(text, pos)
    if quoted:
        q = quoted.group(0)
        out.append(q if len(q) == 2 else f"{q[0]}***{q[0]}")
        return quoted.end()
    if pos >= len(text) or text[pos] in "\r\n" or text.startswith("<", pos):
        return pos
    if text[pos] in "[{":
        close = _bracket_end(text, pos)
        if close is not None:
            out.append("***")
            return close
    out.append("***")
    stop = _VALUE_END_RES[sep].search(text, pos + 1)
    return stop.start() if stop else len(text)


def _bracket_end(text: str, pos: int) -> int | None:
    """The end of the JSON array or object that opens at pos, read up to _CAP*8 characters;
    when it does not close inside that, the rest of the text from pos, so nothing leaks."""
    depth, in_str, esc = 0, False, False
    limit = min(len(text), pos + _CAP * 8)
    for i in range(pos, limit):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text) if limit < len(text) or depth else None


def _mask_keyed(text: str) -> str:
    """key=value and key: value."""
    out: list[str] = []
    pos = 0
    while True:
        m = _KEYED_RE.search(text, pos)
        if not m:
            break
        out.append(text[pos : m.end()])
        pos = m.end()
        if not _is_secret_key(m.group(1)):
            continue
        spaces = _SPACES_RE.match(text, pos)
        start = spaces.end() if spaces else pos
        out.append(text[pos:start])
        if m.group(1).lower() == "pwd" and m.group(2) == ":" and _PATH_RE.match(text, start):
            pos = start  # pwd: /usr/local/bin is a working directory
            continue
        if m.group(2) == "=" and start > pos and _KEY_AHEAD_RE.match(text, start):
            pos = start  # "wmi.pass= wmi.user=x": the password is empty
            continue
        if m.group(2) == ":":
            below = _NEXT_LINE_VALUE_RE.match(text, start)
            if below and not _KEY_LINE_RE.match(text, below.end()):
                out.append(text[start : below.end()])
                start = below.end()
        pos = _mask_value(text, start, out, m.group(2))
    out.append(text[pos:])
    return "".join(out)


def _mask_flags(text: str) -> str:
    """--password value, --password "two words" and -storepass value."""
    out: list[str] = []
    pos = 0
    while True:
        m = _FLAG_RE.search(text, pos)
        if not m:
            break
        out.append(text[pos : m.end()])
        pos = m.end()
        if _is_secret_key(m.group(1)):
            spaces = _SPACES_RE.match(text, pos)
            start = spaces.end() if spaces else pos
            out.append(text[pos:start])
            pos = _mask_value(text, start, out)
    out.append(text[pos:])
    return "".join(out)


def _mask_user_flags(text: str) -> str:
    """curl -u user:password and --user user:password keep the user; -P, -p and -c values,
    a password or a community in sqlcmd, sshpass and the SNMP tools, are masked."""
    text = _USER_FLAG_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    return _SHORT_FLAG_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


def _mask_pem(text: str) -> str:
    """The body of a PEM private key, to its END line or, without one, to the end."""
    out: list[str] = []
    pos = 0
    while True:
        m = _PEM_RE.search(text, pos)
        if not m:
            break
        out.append(text[pos : m.end()])
        end = text.find("-----END", m.end())
        end = len(text) if end < 0 else end
        out.append("***")
        pos = end
    out.append(text[pos:])
    return "".join(out)


def _mask_value_field(m: re.Match[str]) -> str:
    if m.group(4) is not None:
        return f"{m.group(1)}***"  # value=hunter2, unquoted
    value = m.group(2) if m.group(2) is not None else m.group(3)
    if not value:
        return m.group(0)
    quote = '"' if m.group(2) is not None else "'"
    return f"{m.group(1)}{quote}***{quote}"


def _mask_segment(m: re.Match[str]) -> str:
    segment = m.group(0)
    secret_at = [
        f.start()
        for f in _NAME_FIELD_RE.finditer(segment)
        if _is_secret_key(f.group(1) or f.group(2) or f.group(3) or "")
    ]
    if not secret_at:
        return segment

    if m.start() > 0 and m.end() < len(m.string):
        # Inside one tag or object: every value field goes with the secret name.
        return _VALUE_FIELD_RE.sub(_mask_value_field, segment)

    def near(v: re.Match[str]) -> str:
        # Outside braces and tags, only a value field close to a secret name field: one
        # "name: token" must not mask every "value:" in the text.
        i = bisect.bisect_left(secret_at, v.start() - _PAIR_SPAN)
        if i < len(secret_at) and secret_at[i] <= v.end() + _PAIR_SPAN:
            return _mask_value_field(v)
        return v.group(0)

    return _VALUE_FIELD_RE.sub(near, segment)


def _mask_pairs(text: str) -> str:
    """Every value field in a tag or object whose name/key field names a secret."""
    return _SEGMENT_RE.sub(_mask_segment, text)


def _closing_tags(text: str) -> dict[str, list[int]]:
    """Where each closing tag starts, by tag name, in ascending order, from one scan of the
    text, so many unclosed tags cost that one scan and not one search each to the end."""
    found: dict[str, list[int]] = {}
    for m in _CLOSE_TAG_RE.finditer(text):
        found.setdefault(m.group(1), []).append(m.start())
    return found


def _mask_content(
    text: str, pos: int, tag: str, closes: dict[str, list[int]], out: list[str]
) -> int:
    """Mask an element's content from pos to the next closing tag of its own name, child
    elements, CDATA and line breaks included; with no such tag after pos, to the next tag."""
    starts = closes.get(tag, [])
    i = bisect.bisect_left(starts, pos)
    if i < len(starts):
        close = starts[i]
    else:
        loose = _LOOSE_TEXT_RE.match(text, pos)
        close = loose.end() if loose else pos
    out.append("***" if text[pos:close].strip() else text[pos:close])
    return close


def _mask_elements(text: str) -> str:
    """The content of an element whose tag, or whose name/key attribute, names a secret."""
    out: list[str] = []
    pos = 0
    closes: dict[str, list[int]] | None = None  # read once, at the first secret element
    while True:
        m = _TAG_RE.search(text, pos)
        if not m:
            break
        out.append(text[pos : m.end()])
        pos = m.end()
        tag, attrs = m.group(1), m.group(2)
        if attrs.rstrip().endswith("/"):
            continue  # <x/> has no content
        if tag.lower() in ("name", "key"):
            # <name>x.password</name><value>hunter2</value>: mask the value element.
            close = text.find(f"</{tag}>", pos, pos + _CAP)
            if close >= 0 and _is_secret_key(text[pos:close].strip()):
                value = _NAMED_VALUE_RE.match(text, close + len(tag) + 3)
                if value:
                    if closes is None:
                        closes = _closing_tags(text)
                    out.append(text[pos : value.end()])
                    pos = _mask_content(text, value.end(), "value", closes, out)
            continue
        named = (a or b for a, b in _TAG_NAME_ATTR_RE.findall(attrs))
        if not (_is_secret_key(tag) or any(_is_secret_key(n) for n in named)):
            continue
        if closes is None:
            closes = _closing_tags(text)
        pos = _mask_content(text, pos, tag, closes, out)
    out.append(text[pos:])
    return "".join(out)


def _mask_userinfo(text: str) -> str:
    """scheme://user:password@host keeps the user; scheme://token@host masks it all."""
    out: list[str] = []
    pos = 0
    while True:
        m = _SCHEME_RE.search(text, pos)
        if not m:
            break
        stop = _AUTHORITY_END_RE.search(text, m.end())
        span_end = stop.start() if stop else len(text)
        at = text.rfind("@", m.end(), span_end)
        out.append(text[pos : m.end()])
        if at < 0:
            pos = m.end()
            continue
        userinfo = text[m.end() : at]
        out.append(f"{userinfo.split(':', 1)[0]}:***" if ":" in userinfo else "***")
        pos = at
    out.append(text[pos:])
    return "".join(out)


def redact(text: str) -> str:
    """Mask the secret values the collector's output shows, keeping their keys. Best effort;
    see the comment above the patterns."""
    out = text or ""
    out = _mask_pem(out)
    out = _mask_keyed(out)
    out = _mask_flags(out)
    out = _mask_user_flags(out)
    out = _BEARER_RE.sub(lambda m: f"{m.group(1)}***", out)
    out = _mask_pairs(out)
    out = _mask_elements(out)
    out = _mask_userinfo(out)
    return out


def _masked(text: str, keep: int) -> str:
    """The text masked, then cut to keep characters, reading a margin past the cut."""
    return redact(text[: keep + _MASK_MARGIN])[:keep]


def redact_values(data: Any) -> Any:
    """Mask a parsed structure: every string, the value under a secret-named key, and the
    value beside a name/key field that names a secret."""
    if isinstance(data, str):
        return redact(data)
    if isinstance(data, list):
        return [redact_values(v) for v in data]
    if not isinstance(data, dict):
        return data
    named = any(
        str(k).lower() in ("name", "key") and isinstance(v, str) and _is_secret_key(v)
        for k, v in data.items()
    )
    masked = {}
    for k, v in data.items():
        secret = _is_secret_key(str(k)) or (named and str(k).lower() == "value")
        masked[k] = "***" if secret and v not in (None, "") else redact_values(v)
    return masked


# ---------------------------------------------------------------- failures


def _one_line(text: str) -> str:
    """Text on one line, so portal words cannot start a log line of their own."""
    return " ".join(text.split())


def _error_text(error: Exception) -> str:
    return str(getattr(error, "details", "") or getattr(error, "message", "") or error)


def _classify_error(error: Exception) -> tuple[str, str]:
    """The status a failed debug call reads as, and what it means for the caller."""
    text = f"{getattr(error, 'message', '')} {getattr(error, 'details', '') or ''} {error}".lower()
    if isinstance(error, RateLimitError):
        return "rate_limited", "the portal rate limit was hit; try again shortly"
    if "debug" in text and "disable" in text:
        return (
            "disabled",
            "remote debug is disabled on this collector (debug.disable in agent.conf)",
        )
    if isinstance(error, AuthenticationError):
        return "error", "the portal rejected this server's API credentials"
    if isinstance(error, LMPermissionError):
        return "refused", "the calling identity lacks the collector Debug permission"
    if "unknown debug command" in text or "invalid debug command" in text:
        return "unsupported", "this collector build does not support the command"
    return "error", type(error).__name__


def describe_failure(error: Exception) -> dict[str, str]:
    """The status, its meaning and the masked portal words for a debug call that raised,
    logged first: an LMError at WARNING with the portal's words, as handle_error logs one, and
    anything else with its stack trace. The words are masked in the log as in the result."""
    if isinstance(error, LMError):
        logger.warning(
            "collector_debug %s: %s%s",
            error.code,
            _one_line(redact(error.message)),
            f" (details: {_one_line(redact(error.details))})" if error.details else "",
        )
    else:
        logger.exception("collector_debug: unexpected error in the debug call", exc_info=error)
    status, detail = _classify_error(error)
    return {"status": status, "detail": detail, "error_body": _masked(_error_text(error), 4000)}


# ---------------------------------------------------------------- health check parsing
# The reply is the collector's, so the parse is held to the same rules as the masking: each
# pattern is bounded or starts where a run starts, nothing is recursed into without a guard,
# and every list and string in the result is capped.

_BLOCK_RE = re.compile(r"^=+\$?([^=\n]+?)=+[ \t]*$", re.MULTILINE)
_SCHED_RE = re.compile(
    r"is scheduled at ([^,\n]{0,80}), finished at ([^,\n]{0,80}), status (-?[0-9]{1,6})"
)
# A rate is digits with at most one decimal point, so float() always reads it.
_NAN_RE = re.compile(
    r"(?<![0-9])([0-9]{1,9}) of ([0-9]{1,9}) tasks \(([0-9]{1,9}(?:\.[0-9]{1,6})?)%\)"
)
_CHECKPOINTS = ":checkpoints:"
PARSE_LIST_MAX = 25  # entries kept in each list of the parsed result
PARSE_TEXT_MAX = 500  # characters kept of each checkpoint detail
_FACTS = (
    "basic.Version",
    "basic.Role",
    "biz.InstanceCount",
    "biz.ReportingData",
    "module.Collector",
    "module.Watchdog",
)


def _checkpoints(name: str, body: str) -> list[Any] | None:
    """A block's :checkpoints: array: [] when the block has none, None when it has one that
    does not close or does not decode, so an unreadable array never reads as a clean one."""
    idx = body.find(_CHECKPOINTS)
    if idx < 0:
        return []
    text = body[idx + len(_CHECKPOINTS) :].lstrip()
    if not text.startswith("["):
        return None
    depth, end, in_str, esc = 0, -1, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return None
    try:
        data = json.loads(text[:end])
    except (ValueError, RecursionError):
        logger.warning(
            "collector_debug: the checkpoints of %r did not decode; reported as unreadable",
            name,
            exc_info=True,
        )
        return None
    return data if isinstance(data, list) else [data]


def _detail_text(detail: Any) -> str | None:
    """A checkpoint detail as capped text; a structured detail is written out as JSON."""
    if detail is None:
        return None
    text = detail if isinstance(detail, str) else json.dumps(detail, default=str)
    return _masked(text, PARSE_TEXT_MAX)


def parse_health_check(output: str) -> dict[str, Any]:
    """Summarise a !shealthcheck func=detail reply. Unparsed parts are left out, never guessed,
    and a block whose checkpoint array cannot be read is named under checkpoints_unreadable."""
    text = output or ""
    marks = list(_BLOCK_RE.finditer(text))
    blocks = []
    for i, m in enumerate(marks):
        body = text[m.end() : marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        blocks.append((m.group(1).strip()[:200], body))

    methods: list[dict[str, Any]] = []
    idle: list[str] = []
    not_ok: list[dict[str, Any]] = []
    unreadable: list[str] = []
    nan_modules: list[dict[str, Any]] = []
    facts: dict[str, str | None] = {}
    scheduled = []
    for name, body in blocks:
        sched = _SCHED_RE.search(body)
        if sched:
            scheduled.append(sched.group(1).strip())
            if sched.group(3) != "0":
                not_ok.append({"check": name, "detail": f"script status {sched.group(3)}"})
        checkpoints = _checkpoints(name, body)
        if checkpoints is None or not all(
            isinstance(cp, dict) and isinstance(cp.get("status"), str) and cp["status"]
            for cp in checkpoints
        ):
            # An array that does not decode, or holds entries that are not checkpoints.
            unreadable.append(name)
            continue
        for cp in checkpoints:
            cp_name = str(cp.get("name", ""))[:200]
            detail = cp.get("detail")
            status = str(cp.get("status", ""))[:40]
            if status and status.upper() != "OK":
                not_ok.append({"check": cp_name, "status": status, "detail": _detail_text(detail)})
            if cp_name.startswith("biz.DataSource."):
                method = cp_name.split(".", 2)[2]
                match = _NAN_RE.search(detail) if isinstance(detail, str) else None
                if match:
                    methods.append(
                        {
                            "method": method,
                            "all_nan": int(match.group(1)),
                            "attempts": int(match.group(2)),
                            "all_nan_pct": float(match.group(3)),
                            "checkpoint_status": status,
                        }
                    )
                elif isinstance(detail, str) and "no tasks" in detail.lower():
                    idle.append(method)
            elif cp_name == "cogs.DSTableByNan" and isinstance(detail, list):
                # One row per module per device, so each row names its device.
                rows = [
                    r for r in detail if isinstance(r, dict) and (_count(r.get("nanDsi")) or 0) > 0
                ]
                rows.sort(key=lambda r: -(_count(r.get("nanDsi")) or 0))
                nan_modules = [
                    {
                        "module": _detail_text(r.get("dsName")),
                        "method": _detail_text(r.get("collectorName")),
                        "device_id": _count(r.get("deviceId")),
                        "nan_instances": _count(r.get("nanDsi")),
                        "timeout_instances": _count(r.get("timeoutDsi")),
                        "dropped_instances": _count(r.get("droppedDsi")),
                    }
                    for r in rows[:10]
                ]
            elif cp_name in _FACTS:
                facts[cp_name] = _detail_text(detail)

    methods.sort(key=lambda m: -m["all_nan_pct"])
    return {
        "checks_parsed": len(blocks),
        "last_run_started": scheduled[0] if scheduled else None,
        "methods_by_all_nan_rate": methods[:PARSE_LIST_MAX],
        "idle_methods": idle[:PARSE_LIST_MAX],
        "not_ok": not_ok[:PARSE_LIST_MAX],
        "not_ok_total": len(not_ok),
        "checkpoints_unreadable": unreadable[:PARSE_LIST_MAX],
        "nan_by_module": nan_modules,
        "facts": facts,
        "reading_note": (
            "Rates lead, checkpoint status does not: a method can show OK with a double-digit "
            "share of its tasks returning NaN for every datapoint."
        ),
    }


def parse_reply(parse: Callable[[str], Any], output: str) -> dict[str, Any]:
    """Run a reply parse on the raw output, cut at OUTPUT_MAX, and mask its result value by
    value; the parse reads the raw reply, which masking could break. A parse that raises is
    logged with its stack trace and leaves the answer standing, with parse_error naming it."""
    result: dict[str, Any] = {}
    try:
        result["parsed"] = redact_values(parse(output[:OUTPUT_MAX]))
    except Exception as e:
        logger.exception("collector_debug: the reply parse failed; the answer stands unparsed")
        result["parse_error"] = type(e).__name__
    if len(output) > OUTPUT_MAX:
        result["parse_partial"] = True
    return result


# ---------------------------------------------------------------- transport

POLL_SECONDS = 1.0
RATE_WINDOW = 60.0
POST_LIMIT = 180  # the portal allows 200 a minute; this server stops short
GET_LIMIT = 450  # the portal allows 500 a minute
SESSION_WORDS = frozenset({
    "cancelled", "canceled", "pending", "queued", "scheduled", "running", "timeout", "timedout",
    "expired", "unknown",
})  # fmt: skip
_POSTS: deque[float] = deque()
_GETS: deque[float] = deque()
# The still-working read: HTTP 202 with errorCode 1202, which the client raises as this code.
_PENDING_CODE = "API_ERROR_1202"
_PENDING_RE = re.compile(
    r"waiting for response|fetched the task|not (yet )?finished|still running|in progress"
)


def is_session_word(text: str) -> bool:
    """True when a read's output is a session status (cancelled, pending), not the answer."""
    return (text or "").strip().lower() in SESSION_WORDS


def is_pending_error(error: Exception) -> bool:
    """True when a read's error only says the collector is still running the command."""
    if isinstance(error, LMError) and error.code == _PENDING_CODE:
        return True
    text = f"{getattr(error, 'message', '')} {getattr(error, 'details', '') or ''} {error}".lower()
    return bool(_PENDING_RE.search(text))


def _rate_ok(bucket: deque[float], limit: int) -> bool:
    now = time.monotonic()
    while bucket and now - bucket[0] > RATE_WINDOW:
        bucket.popleft()
    return len(bucket) < limit


_T = TypeVar("_T")


class _BudgetSpentError(Exception):
    """The time budget ran out before or during a call to the portal."""


async def _within(deadline: float, call: Awaitable[_T]) -> _T:
    """Await one portal call, cut off at the deadline; a spent budget starts no call."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        if asyncio.iscoroutine(call):
            call.close()
        raise _BudgetSpentError
    try:
        async with asyncio.timeout(remaining):
            return await call
    except TimeoutError as e:
        raise _BudgetSpentError from e


def _failure_head(error: Exception, status: str) -> dict[str, Any]:
    """The error envelope's code, and retry_after when the portal gave one, for a debug call
    that raised."""
    if status == "disabled":
        return {"error": True, "code": "FEATURE_DISABLED"}
    if status == "unsupported":
        return {"error": True, "code": "INVALID_REQUEST"}
    if isinstance(error, LMError):
        retry_after = getattr(error, "retry_after", None)
        return {
            "error": True,
            "code": lm_error_code(error),
            "retry_after": retry_after if isinstance(retry_after, int) else None,
        }
    if isinstance(error, httpx.TimeoutException):
        return {"error": True, "code": "TIMEOUT"}
    return {"error": True, "code": "UPSTREAM_ERROR"}


def _no_reply_detail(last_status: str | None) -> str:
    detail = "no answer inside the time budget; the collector may still run the command"
    return f"{detail}; last session status '{last_status}'" if last_status else detail


async def run_debug(
    client: LogicMonitorClient,
    collector_id: int,
    cmdline: str,
    deadline: float,
    *,
    counter: list[int] | None = None,
    parse: Callable[[str], Any] | None = None,
    keep: int = OUTPUT_MAX,
) -> dict[str, Any]:
    """Send one checked command line and poll for its output until the deadline; never raises.

    The POST and every read are cut off at the deadline, and a budget that ends the call is
    logged with its stack trace. A failed call carries its error envelope's head (the code, and
    retry_after when the portal gave one) under ``envelope``. The
    output is masked to a margin past keep characters (at most OUTPUT_MAX) and cut to keep;
    output_chars is the length the collector sent, and truncated says whether any of it is not
    shown. A parse, when given, reads the raw output through parse_reply.
    """
    started = time.monotonic()
    result: dict[str, Any] = {"cmdline": cmdline, "collector_id": collector_id}

    def done(**kw: Any) -> dict[str, Any]:
        result.update(kw)
        result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        return result

    def count() -> None:
        if counter is not None:
            counter[0] += 1

    try:
        check_cmdline(cmdline)
    except ToolRejectionError as e:
        # A line the builders composed and the final guard refuses: the two disagree.
        logger.warning("collector_debug: the final guard refused %r: %s", cmdline, e, exc_info=True)
        return done(status="rejected_by_tool", detail=str(e))
    if not _rate_ok(_POSTS, POST_LIMIT):
        return done(
            status="rate_limited",
            envelope={"error": True, "code": "RATE_LIMITED"},
            detail="this server's own POST budget is spent; nothing was sent",
        )
    if time.monotonic() >= deadline:
        return done(
            status="error",
            envelope={"error": True, "code": "TIMEOUT"},
            detail="the time budget ran out before the command was sent; nothing was sent",
        )
    try:
        _POSTS.append(time.monotonic())
        count()
        try:
            sub = await _within(
                deadline,
                client.request(
                    "POST",
                    "/debug",
                    params={"collectorId": collector_id},
                    json_body={"cmdline": cmdline},
                ),
            )
        except _BudgetSpentError:
            logger.warning(
                "collector_debug: %s on collector %s was not accepted inside the budget",
                cmdline,
                collector_id,
                exc_info=True,
            )
            return done(
                status="no_reply",
                detail=(
                    "the portal did not accept the command inside the time budget; "
                    "the collector may still run it"
                ),
            )
        session_id = sub.get("sessionId") if isinstance(sub, dict) else None
        if not session_id:
            return done(
                status="error",
                envelope={"error": True, "code": "UPSTREAM_ERROR"},
                detail="the debug API returned no session id",
            )
        reads: tuple[tuple[str, dict[str, int] | None], ...] = (
            ("with", {"collectorId": collector_id}),
            ("without", None),
        )
        last_status: str | None = None
        while time.monotonic() + POLL_SECONDS < deadline:
            await asyncio.sleep(POLL_SECONDS)
            for form, params in reads:
                if not _rate_ok(_GETS, GET_LIMIT):
                    # The command was sent, so this is no answer yet, not a refusal.
                    return done(
                        status="no_reply",
                        detail=(
                            "this server's own GET budget is spent; the command was sent and "
                            "the collector may still run it"
                        ),
                    )
                _GETS.append(time.monotonic())
                count()
                try:
                    reply = await _within(
                        deadline, client.get(f"/debug/{session_id}", params=params)
                    )
                except _BudgetSpentError:
                    logger.warning(
                        "collector_debug: a read of session %s ran past the budget",
                        session_id,
                        exc_info=True,
                    )
                    return done(status="no_reply", detail=_no_reply_detail(last_status))
                except LMError as e:
                    if not is_pending_error(e):
                        raise
                    logger.debug(
                        "collector_debug: session %s is still running", session_id, exc_info=True
                    )
                    last_status = _masked(_error_text(e), 200)
                    continue
                output = str(reply.get("output") or "") if isinstance(reply, dict) else ""
                if output and not is_session_word(output):
                    if parse is not None:
                        result.update(parse_reply(parse, output))
                    shown = min(keep, OUTPUT_MAX)
                    masked = redact(output[: shown + _MASK_MARGIN])
                    return done(
                        status="answered",
                        read_form=form,
                        output=masked[:shown],
                        output_chars=len(output),
                        truncated=len(output) > shown or len(masked) > shown,
                    )
                if output and (last_status is None or is_session_word(last_status)):
                    last_status = output.strip()
        return done(status="no_reply", detail=_no_reply_detail(last_status))
    except Exception as e:
        failure = describe_failure(e)
        return done(**failure, envelope=_failure_head(e, failure["status"]))


# ---------------------------------------------------------------- the tool

# Statuses that mean the command did not run as asked: errors in the envelope, so the write
# audit and the client's isError see a failure. answered and no_reply are results.
FAILED_STATUSES = frozenset({"refused", "disabled", "unsupported", "rate_limited", "error"})
# The collector's own words when it rejects a command line, at the start of a line, so a
# device's "cpu usage: 12%" or an "Invalid URL" page title is not read as one.
_USAGE_RE = re.compile(
    r"^[ \t]*(?:invalid input argument|invalid debug command|usage[ \t]*:|invalid host\."
    r"|invalid url)",
    re.MULTILINE,
)
_DEVICE_FIELDS = "id,name,displayName,currentCollectorId"


def _suggestion(command: Any, error: ToolRejectionError) -> str | None:
    """The command list for an unknown command, and the command's keys for a refused argument."""
    if not isinstance(command, str) or command not in COMMANDS:
        return f"Commands: {', '.join(sorted(COMMANDS))}"
    if isinstance(error, CommandLineRejectionError):
        return None
    keys = sorted(COMMANDS[command].keys)
    return f"{command} takes {', '.join(keys)}" if keys else f"{command} takes no arguments"


def _rejected(command: Any, detail: str, suggestion: str | None = None) -> list[TextContent]:
    """A request refused before anything was sent."""
    return format_response(
        {
            "error": True,
            "code": "REJECTED_BY_TOOL",
            "message": f"{command}: {detail}",
            "suggestion": suggestion,
            "command": command,
            "status": "rejected_by_tool",
        }
    )


def _failed(response: dict[str, Any], head: dict[str, Any]) -> list[TextContent]:
    """A command that did not run as asked: the envelope head its cause decided, the portal's
    masked words in the message, and the call's record in the details."""
    message = f"{response['command']}: {response['status']}: {response.get('detail', '')}"
    if response.get("error_body"):
        message += f" ({' '.join(str(response['error_body'])[:200].split())})"
    return format_response({**head, "message": message, "details": response})


@require_write_permission
async def collector_debug(
    client: LogicMonitorClient,
    command: str,
    collector_id: int | None = None,
    device_id: int | None = None,
    args: dict[str, Any] | None = None,
    budget_seconds: float = BUDGET_DEFAULT,
    max_output_chars: int = OUTPUT_DEFAULT,
) -> list[TextContent]:
    """Run one allowlisted collector debug command and return what the collector said.

    Write-gated. Device probes need device_id and take their host from the device record, which
    also names the collector the command runs on. Everything the caller passed is checked
    before any call, and the whole call is held to budget_seconds.
    """
    try:
        started = time.monotonic()
        portal_host = urlsplit(client.base_url).hostname
        try:
            req = check_request(
                command,
                collector_id=collector_id,
                device_id=device_id,
                args=args,
                budget_seconds=budget_seconds,
                max_output_chars=max_output_chars,
                portal_host=portal_host,
            )
        except ToolRejectionError as e:
            return _rejected(command, str(e), _suggestion(command, e))
        deadline = started + req.budget_seconds
        calls = [0]
        device_note = None
        if req.device_id is None:
            # check_request refuses a request with neither id.
            target = Target(collector_id=cast(int, req.collector_id), portal_host=portal_host)
        else:
            calls[0] += 1
            try:
                record = await _within(
                    deadline,
                    client.get(
                        f"/device/devices/{req.device_id}", params={"fields": _DEVICE_FIELDS}
                    ),
                )
            except _BudgetSpentError:
                logger.warning(
                    "collector_debug: device %s's record did not arrive inside the budget",
                    req.device_id,
                    exc_info=True,
                )
                return _failed(
                    {
                        "command": req.command,
                        "status": "error",
                        "detail": (
                            "the device record did not arrive inside the time budget; "
                            "nothing was sent"
                        ),
                        "budget_seconds": req.budget_seconds,
                        "api_calls": calls[0],
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    },
                    {"error": True, "code": "TIMEOUT"},
                )
            try:
                target = target_from_record(req.command, record, req.collector_id, portal_host)
            except ToolRejectionError as e:
                return _rejected(req.command, str(e), _suggestion(req.command, e))
            device_note = {"device_id": record.get("id"), "host_used": target.host}
        try:
            cmdline = build_cmdline(req.command, req.args, target)
        except ToolRejectionError as e:
            return _rejected(req.command, str(e), _suggestion(req.command, e))

        logger.info(
            "collector_debug: sending %r to collector %s%s",
            cmdline,
            target.collector_id,
            f" for device {req.device_id}, host {target.host}" if req.device_id is not None else "",
        )
        health = req.command == "health_check"
        result = await run_debug(
            client,
            target.collector_id,
            cmdline,
            deadline,
            counter=calls,
            parse=parse_health_check if health else None,
            keep=min(req.max_output_chars, HEALTH_SHOWN_MAX) if health else req.max_output_chars,
        )
        if result.get("status") == "rejected_by_tool":
            return _rejected(req.command, str(result.get("detail", "")))
        head = result.pop("envelope", None)
        response: dict[str, Any] = {
            "command": req.command,
            "group": COMMANDS[req.command].group,
            **result,
            "budget_seconds": req.budget_seconds,
            "api_calls": calls[0],
        }
        if device_note:
            response["device"] = device_note
        opening = str(response.get("output") or "")[:300].lower()
        if "configuration key [" in opening and "not found" in opening:
            response["note"] = (
                "The collector has no such agent.conf key. Check the method name in the key, "
                "e.g. collector.wmi.threadpool. This is about the command, not the collector."
            )
        elif _USAGE_RE.search(opening):
            response["note"] = (
                "The collector rejected the command syntax and printed its usage. This is "
                "about the command, not the device."
            )
        for key in ("parsed", "output"):  # the long parts last
            if key in response:
                response[key] = response.pop(key)
        response["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        if response.get("status") in FAILED_STATUSES:
            return _failed(response, head or {"error": True, "code": "UPSTREAM_ERROR"})
        return format_response(response)
    except Exception as e:
        return handle_error(e)
