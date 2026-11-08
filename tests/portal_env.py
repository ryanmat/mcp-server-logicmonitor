# Description: Shared multi-portal setup for the binding and session tests: a plaintext vault
# Description: with a writable acme portal and a read-only globex portal.

from __future__ import annotations

import json
from pathlib import Path

import pytest


def two_portal_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn on multi-portal mode with writes enabled over a vault of acme and globex."""
    vault = tmp_path / "portals.json"
    vault.write_text(
        json.dumps(
            {
                "acme": {"portal": "acme.example.com", "bearer_token": "t1", "writable": True},
                "globex": {"portal": "globex.example.com", "bearer_token": "t2"},
            }
        )
    )
    monkeypatch.setenv("LM_MULTI_PORTAL", "true")
    monkeypatch.setenv("LM_PORTALS_FILE", str(vault))
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    monkeypatch.delenv("LM_PORTAL", raising=False)
    monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)
