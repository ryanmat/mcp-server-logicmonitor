# Description: Shared test fixtures for the test suite.
# Description: Provides auto-reset of cached config between tests.

import pytest

from lm_mcp.config import reset_config


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Reset the cached LMConfig singleton between tests.

    Tests that use monkeypatch to set LM_ environment variables need
    a fresh config instance. This fixture clears the cache before and
    after each test.
    """
    reset_config()
    yield
    reset_config()
