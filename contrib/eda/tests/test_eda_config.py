# Description: Tests for EDA Controller configuration module.
# Description: Validates environment variable loading, defaults, and singleton behavior.

from lm_mcp.eda_config import EdaConfig, get_eda_config, reset_eda_config


class TestEdaConfig:
    """Tests for EdaConfig pydantic-settings model."""

    def test_loads_from_env(self, monkeypatch):
        """EdaConfig loads url and token from environment."""
        reset_eda_config()
        monkeypatch.setenv("EDA_URL", "https://eda.example.com")
        monkeypatch.setenv("EDA_TOKEN", "test-eda-token")

        config = EdaConfig()
        assert config.url == "https://eda.example.com"
        assert config.token == "test-eda-token"

    def test_default_values(self, monkeypatch):
        """EdaConfig uses sensible defaults for optional fields."""
        reset_eda_config()
        monkeypatch.setenv("EDA_URL", "https://eda.example.com")
        monkeypatch.setenv("EDA_TOKEN", "test-token")

        config = EdaConfig()
        assert config.verify_ssl is True
        assert config.timeout == 30
        assert config.max_retries == 3

    def test_overrides_defaults(self, monkeypatch):
        """EdaConfig overrides defaults from environment."""
        reset_eda_config()
        monkeypatch.setenv("EDA_URL", "https://eda.example.com")
        monkeypatch.setenv("EDA_TOKEN", "test-token")
        monkeypatch.setenv("EDA_VERIFY_SSL", "false")
        monkeypatch.setenv("EDA_TIMEOUT", "60")
        monkeypatch.setenv("EDA_MAX_RETRIES", "5")

        config = EdaConfig()
        assert config.verify_ssl is False
        assert config.timeout == 60
        assert config.max_retries == 5


class TestGetEdaConfig:
    """Tests for get_eda_config singleton function."""

    def test_returns_none_when_not_configured(self, monkeypatch):
        """get_eda_config returns None when EDA_URL is not set."""
        reset_eda_config()
        monkeypatch.delenv("EDA_URL", raising=False)
        monkeypatch.delenv("EDA_TOKEN", raising=False)

        config = get_eda_config()
        assert config is None

    def test_returns_config_when_configured(self, monkeypatch):
        """get_eda_config returns EdaConfig when env vars are set."""
        reset_eda_config()
        monkeypatch.setenv("EDA_URL", "https://eda.example.com")
        monkeypatch.setenv("EDA_TOKEN", "test-token")

        config = get_eda_config()
        assert config is not None
        assert config.url == "https://eda.example.com"
