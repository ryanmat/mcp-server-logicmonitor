# Description: Collector debug command builder: the allowlist, typed arguments and request checks.
# Description: Composes one checked debug command line from a named command and its arguments.

"""Collector debug: the command builder and the checks made before anything is sent.

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
"""

from __future__ import annotations

import contextlib
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from lm_mcp.logging import is_sensitive_key

BUDGET_DEFAULT = 15.0
BUDGET_MIN = 2.0
BUDGET_MAX = 60.0
OUTPUT_DEFAULT = 20_000
OUTPUT_MIN = 500
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


def _b_http(a: dict[str, Any], t: Target) -> str:
    """An HTTP(S) GET to the device itself: the URL's host must be the device record's host."""
    device = _device(t)
    url = _required(a, "url")
    if re.search(r"\s", url):
        raise ToolRejectionError("'url' cannot contain whitespace")
    try:
        parts = urlsplit(url)
        _ = parts.port  # raises on a malformed port
    except ValueError as e:
        raise ToolRejectionError("'url' is not a valid URL") from e
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
    """A finite float from an int or float, else nan; bools and strings are not numbers."""
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
    against a placeholder device. The http URL's own host stands in for the device here; the
    build after the device read compares it with the record."""
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
        with contextlib.suppress(ValueError):
            host = urlsplit(str(checked_args.get("url") or "")).hostname or _PLACEHOLDER_HOST
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
    device probe, and the collector that serves the device for every command.

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
