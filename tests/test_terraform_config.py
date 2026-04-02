# Description: Tests for Terraform configuration module.
# Description: Verifies env var loading, defaults, caching, and reset behavior.

from __future__ import annotations


class TestTerraformConfig:
    """Tests for TerraformConfig BaseSettings class."""

    def test_loads_from_env(self, monkeypatch):
        """Config loads all fields from TF_ environment variables."""
        monkeypatch.setenv("TF_WORKSPACE_DIR", "/tmp/tf-workspaces")
        monkeypatch.setenv("TF_TERRAFORM_BINARY", "/usr/local/bin/terraform")
        monkeypatch.setenv("TF_TIMEOUT", "600")
        monkeypatch.setenv("TF_AUTO_APPROVE_ENABLED", "true")

        from lm_mcp.terraform_config import TerraformConfig

        config = TerraformConfig()
        assert config.workspace_dir == "/tmp/tf-workspaces"
        assert config.terraform_binary == "/usr/local/bin/terraform"
        assert config.timeout == 600
        assert config.auto_approve_enabled is True

    def test_defaults(self, monkeypatch):
        """Config uses correct defaults for optional fields."""
        monkeypatch.setenv("TF_WORKSPACE_DIR", "/tmp/ws")

        from lm_mcp.terraform_config import TerraformConfig

        config = TerraformConfig()
        assert config.terraform_binary == "terraform"
        assert config.timeout == 300
        assert config.auto_approve_enabled is False

    def test_get_terraform_config_returns_none_without_workspace_dir(self, monkeypatch):
        """get_terraform_config returns None when TF_WORKSPACE_DIR is unset."""
        monkeypatch.delenv("TF_WORKSPACE_DIR", raising=False)

        from lm_mcp.terraform_config import get_terraform_config, reset_terraform_config

        reset_terraform_config()
        assert get_terraform_config() is None

    def test_get_terraform_config_returns_config_with_workspace_dir(self, monkeypatch):
        """get_terraform_config returns config when TF_WORKSPACE_DIR is set."""
        monkeypatch.setenv("TF_WORKSPACE_DIR", "/tmp/ws")

        from lm_mcp.terraform_config import get_terraform_config, reset_terraform_config

        reset_terraform_config()
        config = get_terraform_config()
        assert config is not None
        assert config.workspace_dir == "/tmp/ws"

    def test_get_terraform_config_is_cached(self, monkeypatch):
        """Successive calls return the same cached object."""
        monkeypatch.setenv("TF_WORKSPACE_DIR", "/tmp/ws")

        from lm_mcp.terraform_config import get_terraform_config, reset_terraform_config

        reset_terraform_config()
        c1 = get_terraform_config()
        c2 = get_terraform_config()
        assert c1 is c2

    def test_reset_clears_cache(self, monkeypatch):
        """reset_terraform_config clears the cached singleton."""
        monkeypatch.setenv("TF_WORKSPACE_DIR", "/tmp/ws")

        from lm_mcp.terraform_config import get_terraform_config, reset_terraform_config

        reset_terraform_config()
        c1 = get_terraform_config()
        reset_terraform_config()
        c2 = get_terraform_config()
        assert c1 is not c2
