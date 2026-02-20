# Description: Shared test fixtures for the test suite.
# Description: Provides auto-reset of cached config between tests.

import pytest

from lm_mcp.awx_config import reset_awx_config
from lm_mcp.config import reset_config
from lm_mcp.eda_config import reset_eda_config
from lm_mcp.server import _set_awx_client, _set_eda_client


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Reset cached config singletons and global clients between tests.

    Tests that use monkeypatch to set environment variables need
    fresh config instances. This fixture clears LM config, AWX config,
    EDA config, and the AWX/EDA clients before and after each test.
    """
    reset_config()
    reset_awx_config()
    reset_eda_config()
    _set_awx_client(None)
    _set_eda_client(None)
    yield
    reset_config()
    reset_awx_config()
    reset_eda_config()
    _set_awx_client(None)
    _set_eda_client(None)
