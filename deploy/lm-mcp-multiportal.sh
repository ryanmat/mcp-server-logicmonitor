#!/usr/bin/env bash
# lm-mcp-multiportal.sh
#
# Runs THIS fork as a single multi-portal MCP server (stdio) for Claude Desktop / Codex.
# All customer portals come from the age-encrypted vault; switch the active one at runtime
# with the use_portal tool. Read-only by default.
#
# Client config: command = <abs path to this script>, args = []
set -euo pipefail

# GUI apps launch with a minimal PATH; make our tools resolvable.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/bin:/bin:$PATH"

DIR="${LM_MCP_HOME:-$HOME/.config/lm-mcp}"

export LM_MULTI_PORTAL=true
export LM_VAULT_FILE="${LM_VAULT_FILE:-$DIR/secrets.age}"
export LM_AGE_KEY="${LM_AGE_KEY:-$DIR/age-key.txt}"
export LM_TRANSPORT="${LM_TRANSPORT:-stdio}"
# Read-only across all portals by default. To allow writes for a "writable": true portal,
# set LM_ENABLE_WRITE_OPERATIONS=true AND widen categories (e.g. read,write,session).
export LM_MCP_CATEGORIES="${LM_MCP_CATEGORIES:-read,session}"

[ -f "$LM_AGE_KEY" ]    || { echo "missing $LM_AGE_KEY (run the vault setup first)" >&2; exit 66; }
[ -f "$LM_VAULT_FILE" ] || { echo "missing $LM_VAULT_FILE (run the vault setup first)" >&2; exit 66; }
command -v age >/dev/null || { echo "age not found (brew install age)" >&2; exit 69; }
command -v uv  >/dev/null || { echo "uv not found (install uv: https://astral.sh/uv)" >&2; exit 69; }

# Run YOUR local fork. Point LM_MCP_SOURCE at your clone (default) or a git URL after publishing.
# `uv run --project` re-syncs from the source on every launch, so edits you make to the
# fork (new tools, updated portal logic) take effect on the next client restart — no uvx
# build-cache staleness and no version bump needed. Progress goes to stderr; stdout stays
# clean JSON-RPC for the MCP client.
SRC="${LM_MCP_SOURCE:-$HOME/src/lm-mcp}"
exec uv run --project "$SRC" lm-mcp-server
