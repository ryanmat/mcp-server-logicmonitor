# Description: Per-call binding of the LogicMonitor client, the write flag and the portal name.
# Description: execute_tool sets one in a ContextVar for each tool call; helpers read only that.

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


@dataclass(frozen=True)
class CallBinding:
    """What one tool call runs against, read once when the call starts (spec R2.12).

    Attributes:
        client: The LogicMonitor client, or None before a portal is selected or
            before the startup client is built.
        writable: Whether the call may change its portal: the operator's write gate
            and, in multi-portal mode, the portal's own vault flag.
        portal: The portal name in multi-portal mode, None before use_portal; always
            None in single-portal mode.
    """

    client: LogicMonitorClient | None
    writable: bool
    portal: str | None


_binding: ContextVar[CallBinding] = ContextVar("lm_mcp_call_binding")


@contextmanager
def bind(binding: CallBinding) -> Iterator[CallBinding]:
    """Bind ``binding`` for the code inside the block, then restore what was bound before."""
    token = _binding.set(binding)
    try:
        yield binding
    finally:
        _binding.reset(token)


def current_binding() -> CallBinding:
    """Return the binding of the running tool call.

    Raises:
        RuntimeError: Outside a tool call; nothing falls back to the process default.
    """
    try:
        return _binding.get()
    except LookupError:
        raise RuntimeError(
            "No portal binding: tool handlers run inside execute_tool, which binds one per call"
        ) from None


def current_client() -> LogicMonitorClient:
    """Return the running call's LogicMonitor client.

    Raises:
        RuntimeError: Outside a tool call, or when the call has no client.
    """
    client = current_binding().client
    if client is None:
        from lm_mcp.config import get_config

        raise missing_client_error(get_config().multi_portal)
    return client


def missing_client_error(multi_portal: bool) -> RuntimeError:
    """The error for a caller that needs a client and has none."""
    if multi_portal:
        return RuntimeError(
            "No portal selected. Call use_portal(<customer>) first (see list_portals)."
        )
    return RuntimeError("Client not initialized")
