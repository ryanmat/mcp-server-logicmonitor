# Description: Settings for the Edwin AI backend, read from EDWIN_-prefixed environment variables.
# Description: Yields no settings, and so no Edwin client, unless both credentials are set.

from __future__ import annotations

import logging

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class EdwinConfig(BaseSettings):
    """Edwin AI client credential and host.

    Environment Variables:
        EDWIN_CLIENT_ID: Client id of an Edwin AI API credential.
        EDWIN_CLIENT_TOKEN: That credential's secret.
        EDWIN_HOST: Edwin base URL, https only (default: ``https://<portal name>.dexda.ai``).
    """

    client_id: str | None = None
    client_token: str | None = None
    host: str | None = None

    model_config = {
        "env_prefix": "EDWIN_",
        # The fields hold a credential; a validation error must not echo it.
        "hide_input_in_errors": True,
    }

    @field_validator("host", mode="after")
    @classmethod
    def validate_host(cls, v: str | None) -> str | None:
        """Require https, since the token exchange sends the credential's secret to it."""
        if v is None:
            return v
        if not v.startswith("https://"):
            raise ValueError("EDWIN_HOST must be an https:// URL")
        return v.rstrip("/")


def load_edwin_config() -> EdwinConfig | None:
    """Read the Edwin settings, or None when Edwin is not configured.

    Both credentials unset is the ordinary case and returns None quietly. One
    credential without the other, or an unusable EDWIN_HOST, returns None and logs
    a WARNING naming the variable, never its value.
    """
    try:
        config = EdwinConfig()
    except ValidationError as exc:
        fields = ", ".join(f"EDWIN_{str(e['loc'][0]).upper()}" for e in exc.errors())
        logger.warning(
            "Edwin AI is off: %s is unusable (%s)",
            fields,
            exc.errors()[0]["msg"],
            exc_info=True,
        )
        return None
    if not config.client_id and not config.client_token:
        return None
    if not config.client_id or not config.client_token:
        missing = "EDWIN_CLIENT_TOKEN" if config.client_id else "EDWIN_CLIENT_ID"
        logger.warning("Edwin AI is off: %s is unset while the other credential is set", missing)
        return None
    return config
