# Description: Shared test fixtures for the test suite.
# Description: Provides auto-reset of cached config between tests.

import pytest

from lm_mcp import portals
from lm_mcp.config import reset_config
from lm_mcp.server import _set_client


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Reset the cached LM config between tests.

    Tests that use monkeypatch to set environment variables need
    fresh config instances. This fixture clears LM config before and
    after each test.
    """
    reset_config()
    yield
    reset_config()


@pytest.fixture
def reset_portals():
    """Reset the process-local portal registry and the global client around a test.

    Named (not autouse) deliberately: nulling the global client suite-wide would
    change behavior for tests that bind their own client at import time.
    """

    def _clear():
        portals._state.update(
            {
                "portals": {},
                "clients": {},
                "active": None,
                "active_writable": False,
                "loaded": False,
            }
        )
        _set_client(None)

    _clear()
    yield
    _clear()
