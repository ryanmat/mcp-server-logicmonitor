# Description: LogicMonitor API client module.
# Description: Provides async HTTP client for interacting with LogicMonitor REST API.

from lm_mcp.client.api import LogicMonitorClient

__all__ = ["LogicMonitorClient", "build_client"]


def build_client(
    portal: str | None,
    *,
    bearer_token: str | None,
    access_id: str | None,
    access_key: str | None,
) -> LogicMonitorClient:
    """Build the client for one portal, the only place a LogicMonitorClient is made.

    The REST and ingest URLs come from the portal host, the auth provider from
    :func:`~lm_mcp.auth.validate_auth`, and the timeout and retry limits from the
    config, in single- and multi-portal mode alike.

    Args:
        portal: Portal hostname, e.g. ``acme.logicmonitor.com``; required.
        bearer_token: Bearer token, preferred when set.
        access_id: LMv1 access ID, used with access_key when no bearer token is set.
        access_key: LMv1 access key.

    Raises:
        ConfigurationError: If the portal is missing, or neither a bearer token nor a
            full LMv1 pair is given.
    """
    from lm_mcp.auth import validate_auth
    from lm_mcp.config import get_config
    from lm_mcp.exceptions import ConfigurationError

    if not portal:
        raise ConfigurationError("No portal to build a client for: set LM_PORTAL")
    config = get_config()
    return LogicMonitorClient(
        base_url=f"https://{portal}/santaba/rest",
        auth=validate_auth(bearer_token, access_id, access_key),
        timeout=config.timeout,
        max_retries=config.max_retries,
        retry_after_cap=config.retry_after_cap_seconds,
        ingest_url=f"https://{portal}",
    )
