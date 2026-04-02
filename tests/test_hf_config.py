# Description: Tests for HuggingFace configuration module.
# Description: Verifies torch gate, env var loading, defaults, caching, and reset.

from __future__ import annotations

import builtins
from unittest.mock import patch


class TestHuggingFaceConfig:
    """Tests for HuggingFaceConfig BaseSettings class."""

    def test_defaults(self, monkeypatch):
        """Config uses correct default model names and device."""
        # Ensure torch is "available" by not blocking the import
        from lm_mcp.hf_config import HuggingFaceConfig

        config = HuggingFaceConfig()
        assert config.ttm_model == "ibm-granite/granite-timeseries-ttm-r2"
        assert config.llm_model == "ibm-granite/granite-3.3-2b-instruct"
        assert config.device == "auto"
        assert config.cache_dir is None

    def test_loads_from_env(self, monkeypatch):
        """Config loads custom values from HF_ environment variables."""
        monkeypatch.setenv("HF_TTM_MODEL", "custom/ttm-model")
        monkeypatch.setenv("HF_LLM_MODEL", "custom/llm-model")
        monkeypatch.setenv("HF_DEVICE", "cuda")
        monkeypatch.setenv("HF_CACHE_DIR", "/tmp/hf-cache")

        from lm_mcp.hf_config import HuggingFaceConfig

        config = HuggingFaceConfig()
        assert config.ttm_model == "custom/ttm-model"
        assert config.llm_model == "custom/llm-model"
        assert config.device == "cuda"
        assert config.cache_dir == "/tmp/hf-cache"

    def test_get_hf_config_returns_none_without_torch(self):
        """get_hf_config returns None when torch is not importable."""
        from lm_mcp.hf_config import get_hf_config, reset_hf_config

        reset_hf_config()
        with patch("builtins.__import__", side_effect=_block_torch_import):
            result = get_hf_config()
        assert result is None

    def test_get_hf_config_returns_config_when_torch_available(self):
        """get_hf_config returns config when torch is importable."""
        from lm_mcp.hf_config import get_hf_config, reset_hf_config

        reset_hf_config()
        # torch is in dev deps, so this should work if available
        # If torch is not installed, the test still validates the gate logic
        try:
            import torch  # noqa: F401

            config = get_hf_config()
            assert config is not None
            assert config.ttm_model == "ibm-granite/granite-timeseries-ttm-r2"
        except ImportError:
            # torch not installed -- gate correctly returns None
            config = get_hf_config()
            assert config is None

    def test_get_hf_config_is_cached(self):
        """Successive calls return the same cached object."""
        from lm_mcp.hf_config import get_hf_config, reset_hf_config

        reset_hf_config()
        c1 = get_hf_config()
        c2 = get_hf_config()
        if c1 is not None:
            assert c1 is c2

    def test_reset_clears_cache(self):
        """reset_hf_config clears the cached singleton."""
        from lm_mcp.hf_config import get_hf_config, reset_hf_config

        reset_hf_config()
        c1 = get_hf_config()
        reset_hf_config()
        c2 = get_hf_config()
        if c1 is not None and c2 is not None:
            assert c1 is not c2


def _block_torch_import(name, *args, **kwargs):
    """Import hook that blocks torch but allows everything else."""
    if name == "torch":
        raise ImportError("Mocked: torch not installed")
    return original_import(name, *args, **kwargs)


original_import = builtins.__import__
