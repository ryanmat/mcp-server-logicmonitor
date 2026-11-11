# Description: Optional-backend setup shared by the stdio and HTTP transports.
# Description: Builds the Edwin AI client when both Edwin credentials are set and serves its tools.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lm_mcp.exceptions import ConfigurationError

if TYPE_CHECKING:
    from lm_mcp.client.edwin import EdwinClient
    from lm_mcp.config import LMConfig

logger = logging.getLogger(__name__)


@dataclass
class Backends:
    """The optional backends a transport built, closed by that transport at shutdown.

    Attributes:
        edwin: The Edwin AI client, or None when Edwin is not configured.
    """

    edwin: EdwinClient | None = None

    async def close(self) -> None:
        """Withdraw the Edwin tools and close the Edwin client, if one was built."""
        from lm_mcp.server import _set_edwin_client

        _set_edwin_client(None)
        if self.edwin is not None:
            await self.edwin.close()


def bootstrap_backends(config: LMConfig) -> Backends:
    """Build the optional backends and hand the Edwin client to the server.

    Edwin is built only when both EDWIN_CLIENT_ID and EDWIN_CLIENT_TOKEN are set. With
    no EDWIN_HOST and no LM_PORTAL to derive the host from (multi-portal mode), the
    server starts without Edwin and logs why.

    Args:
        config: The LogicMonitor server configuration.

    Returns:
        The backends built, for the transport to close at shutdown.
    """
    from lm_mcp.client.edwin import build_edwin_client
    from lm_mcp.server import _set_edwin_client

    try:
        edwin = build_edwin_client(config.portal)
    except ConfigurationError:
        logger.warning(
            "Edwin AI is off: no host to call; set EDWIN_HOST when LM_PORTAL is unset",
            exc_info=True,
        )
        edwin = None
    _set_edwin_client(edwin)
    return Backends(edwin=edwin)
