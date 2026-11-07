# Description: Optional-backend setup shared by the stdio and HTTP transports.
# Description: No optional backend exists to build, so it returns an empty Backends.

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
    """Return the optional backends, which are none.

    Args:
        config: The LogicMonitor server configuration.

    Returns:
        The backends built, for the transport to close at shutdown.
    """
    return Backends()
