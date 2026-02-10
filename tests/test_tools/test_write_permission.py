# Description: Tests for write permission decorator.
# Description: Validates read-only mode enforcement.


class TestWritePermissionConfig:
    """Tests for write permission configuration."""

    def test_write_operations_disabled_by_default(self, monkeypatch):
        """Write operations are disabled by default."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        # Clear any cached config
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.enable_write_operations is False

    def test_write_operations_can_be_enabled(self, monkeypatch):
        """Write operations can be enabled via environment variable."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.enable_write_operations is True


class TestRequireWritePermission:
    """Tests for require_write_permission decorator."""

    def test_decorator_blocks_when_writes_disabled(self, monkeypatch):
        """Decorated function returns error when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools import require_write_permission

        @require_write_permission
        async def write_something():
            return "success"

        import asyncio

        result = asyncio.run(write_something())

        assert len(result) == 1
        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text
        assert "LM_ENABLE_WRITE_OPERATIONS" in result[0].text

    def test_decorator_allows_when_writes_enabled(self, monkeypatch):
        """Decorated function executes when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools import require_write_permission

        @require_write_permission
        async def write_something():
            return "success"

        import asyncio

        result = asyncio.run(write_something())
        assert result == "success"

    def test_decorator_preserves_function_metadata(self, monkeypatch):
        """Decorator preserves original function name and docstring."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.tools import require_write_permission

        @require_write_permission
        async def my_write_function():
            """My docstring."""
            pass

        assert my_write_function.__name__ == "my_write_function"
        assert my_write_function.__doc__ == "My docstring."


class TestRealWriteToolsBlocked:
    """Tests that actual write tools are blocked in read-only mode."""

    def test_create_device_blocked(self, monkeypatch):
        """create_device returns error when writes are disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        import asyncio

        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.tools.devices import create_device

        auth = BearerAuth("test-token")
        client = LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
            timeout=30,
            api_version=3,
        )

        result = asyncio.run(
            create_device(client, name="test", display_name="Test", preferred_collector_id=1)
        )
        assert len(result) == 1
        assert "Write operations are disabled" in result[0].text

    def test_delete_device_blocked(self, monkeypatch):
        """delete_device returns error when writes are disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        import asyncio

        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.tools.devices import delete_device

        auth = BearerAuth("test-token")
        client = LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
            timeout=30,
            api_version=3,
        )

        result = asyncio.run(delete_device(client, device_id=123))
        assert len(result) == 1
        assert "Write operations are disabled" in result[0].text

    def test_import_datasource_blocked(self, monkeypatch):
        """import_datasource returns error when writes are disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        import asyncio

        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.tools.imports import import_datasource

        auth = BearerAuth("test-token")
        client = LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
            timeout=30,
            api_version=3,
        )

        result = asyncio.run(import_datasource(client, definition={"name": "test"}))
        assert len(result) == 1
        assert "Write operations are disabled" in result[0].text
