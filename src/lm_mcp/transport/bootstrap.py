# Description: Optional-backend setup shared by the stdio and HTTP transports.
# Description: Builds the AWX and Terraform clients; sets session persistence.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lm_mcp.client.awx import AwxClient
    from lm_mcp.client.terraform import TerraformRunner
    from lm_mcp.config import LMConfig

logger = logging.getLogger(__name__)


@dataclass
class Backends:
    """The optional backends a transport built, closed by that transport at shutdown."""

    awx: AwxClient | None = None
    terraform: TerraformRunner | None = None

    async def close(self) -> None:
        """Close every backend that was built."""
        if self.terraform is not None:
            await self.terraform.close()
        if self.awx is not None:
            await self.awx.close()


def bootstrap_backends(config: LMConfig) -> Backends:
    """Build the optional backends that are configured and register them with the server.

    Each backend is absent unless its configuration loads: AWX needs AWX_URL and
    AWX_TOKEN, and Terraform needs TF_WORKSPACE_DIR outside multi-portal mode.
    Session variables persist to LM_SESSION_PERSIST_PATH when it is set; the path
    is set here, before the transport first creates the session, which loads the file.

    Args:
        config: The LogicMonitor server configuration.

    Returns:
        The backends built, for the transport to close at shutdown.
    """
    from lm_mcp.server import _set_awx_client, _set_tf_runner
    from lm_mcp.session import set_persistence_path

    set_persistence_path(config.session_persist_path)

    backends = Backends()

    from lm_mcp.awx_config import get_awx_config

    awx_config = get_awx_config()
    if awx_config is not None:
        from lm_mcp.client.awx import AwxClient

        backends.awx = AwxClient(
            base_url=awx_config.url,
            token=awx_config.token,
            timeout=awx_config.timeout,
            max_retries=awx_config.max_retries,
            verify_ssl=awx_config.verify_ssl,
        )
        _set_awx_client(backends.awx)

    # Skipped in multi-portal mode: the LM Terraform provider needs fixed LM_*
    # credentials, which multi-portal selects at runtime, so the tools would run
    # unauthenticated.
    from lm_mcp.terraform_config import get_terraform_config

    tf_config = get_terraform_config()
    if tf_config is not None and config.multi_portal:
        logger.warning(
            "Terraform tools are disabled in multi-portal mode; "
            "run a single-portal server for Terraform."
        )
        tf_config = None
    if tf_config is not None:
        from lm_mcp.client.terraform import TerraformRunner

        backends.terraform = TerraformRunner(
            workspace_dir=tf_config.workspace_dir,
            terraform_binary=tf_config.terraform_binary,
            timeout=tf_config.timeout,
            auto_approve_enabled=tf_config.auto_approve_enabled,
        )
        _set_tf_runner(backends.terraform)

    return backends
