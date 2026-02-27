# Event-Driven Ansible (EDA) Integration — Archived

This directory contains the EDA Controller integration that shipped in v1.9.0-v1.9.2.
It was removed from the deployed package in v1.9.5 because EDA requires standalone
EDA Controller infrastructure that is not available through the LogicMonitor Portal.

## Contents

- `client/eda.py` — EdaClient HTTP client with Bearer token auth
- `eda_config.py` — EDA environment variable configuration
- `tools/eda.py` — 20 EDA tool handler functions
- `tests/` — Full test suite for EDA client, tools, config, registry, and dispatch
- `skills/lm-eda/SKILL.md` — Claude Code skill for event-driven automation
- `extensions/` — EDA rulebook definitions
- `examples/rulebooks/` — Example EDA rulebook for LM service restart

## Re-enabling EDA

To re-wire EDA into the server:

1. Copy source files back to their original locations under `src/lm_mcp/`
2. Restore `EDA_TOOLS` list in `registry.py`
3. Restore EDA handler entries in `get_tool_handler()`
4. Restore EDA client initialization in `transport/__init__.py` and `transport/http.py`
5. Restore EDA dispatch branch in `server.py` `execute_tool()`
6. Restore `eda_config` imports in `tests/conftest.py`
7. Copy tests back to `tests/` directories
8. Set `EDA_URL` and `EDA_TOKEN` environment variables
