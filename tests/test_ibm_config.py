# Description: Tests for IBM watsonx configuration loading.
# Description: Verifies pydantic-settings env var handling and optional singleton.


class TestWatsonxConfig:
    def test_loads_from_env(self, monkeypatch):
        from lm_mcp.ibm_config import WatsonxConfig

        monkeypatch.setenv("WATSONX_API_KEY", "test-api-key-12345")
        monkeypatch.setenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
        monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-123")
        config = WatsonxConfig()
        assert config.api_key == "test-api-key-12345"
        assert config.url == "https://us-south.ml.cloud.ibm.com"
        assert config.project_id == "proj-123"

    def test_defaults(self, monkeypatch):
        from lm_mcp.ibm_config import WatsonxConfig

        monkeypatch.setenv("WATSONX_API_KEY", "test-api-key-12345")
        monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-123")
        config = WatsonxConfig()
        assert config.url == "https://us-south.ml.cloud.ibm.com"
        assert config.timeout == 60

    def test_get_watsonx_config_returns_none_without_key(self, monkeypatch):
        from lm_mcp.ibm_config import get_watsonx_config, reset_watsonx_config

        monkeypatch.delenv("WATSONX_API_KEY", raising=False)
        monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
        reset_watsonx_config()
        assert get_watsonx_config() is None

    def test_get_watsonx_config_returns_config_with_key(self, monkeypatch):
        from lm_mcp.ibm_config import get_watsonx_config, reset_watsonx_config

        monkeypatch.setenv("WATSONX_API_KEY", "test-api-key-12345")
        monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-123")
        reset_watsonx_config()
        config = get_watsonx_config()
        assert config is not None
        assert config.api_key == "test-api-key-12345"

    def test_get_watsonx_config_is_cached(self, monkeypatch):
        from lm_mcp.ibm_config import get_watsonx_config, reset_watsonx_config

        monkeypatch.setenv("WATSONX_API_KEY", "test-api-key-12345")
        monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-123")
        reset_watsonx_config()
        c1 = get_watsonx_config()
        c2 = get_watsonx_config()
        assert c1 is c2

    def test_reset_clears_cache(self, monkeypatch):
        from lm_mcp.ibm_config import get_watsonx_config, reset_watsonx_config

        monkeypatch.setenv("WATSONX_API_KEY", "test-api-key-12345")
        monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-123")
        reset_watsonx_config()
        c1 = get_watsonx_config()
        reset_watsonx_config()
        c2 = get_watsonx_config()
        assert c1 is not c2
