# Description: Configuration for EDA Controller integration.
# Description: Loads EDA credentials from environment variables with EDA_ prefix.

from __future__ import annotations

from pydantic_settings import BaseSettings

_cached_eda_config: "EdaConfig | None" = None


def get_eda_config() -> "EdaConfig | None":
    """Get the cached EdaConfig singleton.

    Returns None if EDA_URL is not configured. This allows the server
    to start without EDA credentials — EDA tools are simply excluded.
    """
    global _cached_eda_config
    if _cached_eda_config is None:
        try:
            _cached_eda_config = EdaConfig()
        except Exception:
            return None
    return _cached_eda_config


def reset_eda_config() -> None:
    """Clear the cached config. Used in tests to reset state."""
    global _cached_eda_config
    _cached_eda_config = None


class EdaConfig(BaseSettings):
    """Configuration for EDA Controller API integration.

    Compatible with Event-Driven Ansible Controller (AAP 2.4+).
    All fields are required unless EDA_URL is absent, in which case
    get_eda_config() returns None and EDA tools are excluded.
    """

    url: str              # EDA_URL
    token: str            # EDA_TOKEN
    verify_ssl: bool = True   # EDA_VERIFY_SSL
    timeout: int = 30         # EDA_TIMEOUT
    max_retries: int = 3      # EDA_MAX_RETRIES

    model_config = {"env_prefix": "EDA_"}
