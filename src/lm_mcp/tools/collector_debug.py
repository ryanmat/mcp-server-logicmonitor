# Description: Collector debug: the command allowlist, typed arguments, request checks, output
# Description: masking and the stored health-check parse, each bounded against hostile text.

"""Collector debug: the command builder, the checks made before anything is sent, and what is
done with what comes back.

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
  parameter of !wmi, so the WHERE clause allows ``!`` only as ``!=`` and ``=`` only after a
  space, ``<``, ``>`` or ``!``: no command head and no parameter can ride in it.
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
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, parse_qsl, urlsplit

from lm_mcp.exceptions import AuthenticationError, LMError, LMPermissionError, RateLimitError
from lm_mcp.logging import is_sensitive_key

logger = logging.getLogger(__name__)

BUDGET_DEFAULT = 15.0
BUDGET_MIN = 2.0
BUDGET_MAX = 60.0
OUTPUT_DEFAULT = 20_000
OUTPUT_MIN = 500
OUTPUT_MAX = 100_000  # the most of a reply a parse reads
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
LOG_FILES = ("wrapper.log", "sbproxy.log", "watchdog.log")


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
    if tuple(int(part) for part in oid.strip(".").split(".")) in _ROOT_OIDS:
        raise ToolRejectionError(
            "walking from the root of the tree, or the top of mib-2 or enterprises, is "
            "refused; walk a subtree"
        )
    return _join("!snmpwalk", _kv("timeout", _int(a, "timeout", 1, 120)), _device(t), oid)


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_WQL_RE = re.compile(
    rf"^SELECT\s+(\*|{_IDENT}(\s*,\s*{_IDENT})*)\s+FROM\s+{_IDENT}(\s+WHERE\s+(?P<where>.+))?$",
    re.IGNORECASE,
)
_WHERE_CHARS_RE = re.compile(r"^[A-Za-z0-9_ '%.,:\\/\-<>=!()]+$")


def _check_where(where: str) -> None:
    """Refuse a WHERE clause that could carry a command head or a key=value token.

    ``!`` stands only directly before ``=`` (``!=``), so no ``!restart`` rides after a
    comparison. ``=`` stands only after a space, ``<``, ``>`` or ``!`` (``Name = 'x'``,
    ``<=``, ``>=``, ``!=``), so no token reads as key=value, quoted or not.
    """
    if not _WHERE_CHARS_RE.match(where):
        raise ToolRejectionError("the WHERE clause holds a character the tool does not allow")
    for i, ch in enumerate(where):
        if ch == "!" and where[i + 1 : i + 2] != "=":
            raise ToolRejectionError("in the WHERE clause '!' is allowed only as '!='")
        if ch == "=" and (i == 0 or where[i - 1] not in " <>!"):
            raise ToolRejectionError(
                "a key=value token in the query would become a !wmi parameter; "
                "write comparisons with a space before the operator, e.g. Name = 'x'"
            )


def _b_wmi(a: dict[str, Any], t: Target) -> str:
    """One WQL SELECT: SELECT * | cols FROM Class [WHERE ...], with no key=value token."""
    query = " ".join(str(a.get("query") or "select * from Win32_Service").split())
    match = _WQL_RE.match(query)
    if not match:
        raise ToolRejectionError(
            "'query' must be one WQL SELECT: SELECT * | col[, col] FROM Class [WHERE ...]"
        )
    where = match.group("where")
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


def _b_snmpdiagnose(a: dict[str, Any], t: Target) -> str:
    return _join("!snmpdiagnose", _device(t), *_list(a, "oids", _OID_RE, 0, 5))


def _b_snmpget(a: dict[str, Any], t: Target) -> str:
    return _join("!snmpget", _device(t), *_list(a, "oids", _OID_RE, 1, 10))


def _b_cim(a: dict[str, Any], t: Target) -> str:
    cls = _opt(a, "class", pattern=_CLASS_RE) or _required(a, "class")
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
    """The value as a float, or nan for a bool, a string or an int too large for a float; an
    infinity passes through, and check_request refuses both."""
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


def _is_secret_key(key: str) -> bool:
    """True when a key (wmi.pass, -Ddb.password, clientSecret, snmp.authtoken) names a secret.

    A dotted key is also a secret wherever lm_mcp.logging.is_sensitive_key says so (ssh.key,
    snmp.auth, snmp.priv, meraki.api.key), so one rule decides the audit line and the masked
    output. An undotted word such as key or auth is left to the list above, so a log's
    "key=value" or "auth: ok" is not masked.
    """
    key = _JVM_FLAG_RE.sub("", key)  # -Dwmi.pass, --password
    if "." in key and is_sensitive_key(key):
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
_PEM_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY[A-Z ]*-----")
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
_USER_FLAG_RE = re.compile(r"(?<![\w.-])(--user|-u)([ \t=]+[^\s:]+:)(\S+)")


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
    """curl -u user:password and --user user:password keep the user."""
    return _USER_FLAG_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


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
            redact(error.message),
            f" (details: {redact(error.details)})" if error.details else "",
        )
    else:
        logger.exception("collector_debug: unexpected error in the debug call", exc_info=error)
    status, detail = _classify_error(error)
    return {"status": status, "detail": detail, "error_body": redact(_error_text(error)[:4000])}


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
    return text[:PARSE_TEXT_MAX]


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
        if checkpoints is None:
            unreadable.append(name)
            continue
        for cp in checkpoints:
            if not isinstance(cp, dict):
                continue
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
