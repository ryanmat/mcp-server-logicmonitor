# Description: Optional-backend setup shared by the stdio and HTTP transports.
# Description: Sets session persistence; no optional backend exists to build.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lm_mcp.config import LMConfig


@dataclass
class Backends:
    """The optional backends a transport built, closed by that transport at shutdown.

    The server has no optional backend, so an instance holds none.
    """

    async def close(self) -> None:
        """Close every backend that was built; with none built, this does nothing."""


def bootstrap_backends(config: LMConfig) -> Backends:
    """Set session persistence and return the optional backends, which are none.

    Session variables persist to LM_SESSION_PERSIST_PATH when it is set; the path
    is set here, before the transport first creates the session, which loads the file.

    Args:
        config: The LogicMonitor server configuration.

    Returns:
        The backends built, for the transport to close at shutdown.
    """
    from lm_mcp.session import set_persistence_path

    set_persistence_path(config.session_persist_path)

    return Backends()
