# Description: Tests for the HTTP transport's ASGI app construction.
# Description: Validates that the app refuses multi-portal mode, which is stdio-only.

import pytest


class TestHttpMultiPortalRefused:
    """Multi-portal mode is stdio-only; the HTTP app must refuse to construct."""

    def test_asgi_app_refuses_multi_portal(self, monkeypatch, tmp_path):
        from pydantic import ValidationError

        p = tmp_path / "portals.json"
        p.write_text('{"acme": {"portal": "acme.example.com", "bearer_token": "t"}}')
        monkeypatch.setenv("LM_MULTI_PORTAL", "true")
        monkeypatch.setenv("LM_PORTALS_FILE", str(p))
        monkeypatch.setenv("LM_TRANSPORT", "http")
        monkeypatch.delenv("LM_PORTAL", raising=False)
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)

        from lm_mcp.transport.http import create_asgi_app

        with pytest.raises(ValidationError, match="stdio"):
            create_asgi_app()
