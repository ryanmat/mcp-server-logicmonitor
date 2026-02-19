# Description: Shared test fixtures for the test suite.
# Description: Provides auto-reset of cached config between tests.

import pytest

from lm_mcp.awx_config import reset_awx_config
from lm_mcp.config import reset_config


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Reset cached config singletons between tests.

    Tests that use monkeypatch to set environment variables need
    fresh config instances. This fixture clears both LM and AWX
    caches before and after each test.
    """
    reset_config()
    reset_awx_config()
    yield
    reset_config()
    reset_awx_config()
