#!/usr/bin/env bash
# lm-mcp-multiportal.sh
#
# Runs lm-mcp as a single multi-portal MCP server (stdio) for Claude Desktop / Codex.
# Customer portals come from the age-encrypted vault (or LM_PORTALS_FILE for testing);
# switch the active one at runtime with the use_portal tool. Read-only by default.
#
# Client config: command = <abs path to this script>, args = []
set -euo pipefail

# GUI apps launch with a minimal PATH; make our tools resolvable.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/bin:/bin:$PATH"

DIR="${LM_MCP_HOME:-$HOME/.config/lm-mcp}"

export LM_MULTI_PORTAL=true
export LM_TRANSPORT="${LM_TRANSPORT:-stdio}"
# Read-only across all portals by default. To allow writes for a "writable": true portal,
# set LM_ENABLE_WRITE_OPERATIONS=true AND widen categories (e.g. read,write,session).
export LM_MCP_CATEGORIES="${LM_MCP_CATEGORIES:-read,session}"

if [ -n "${LM_PORTALS_FILE:-}" ]; then
  # Plaintext portal map (testing only); no age vault required.
  export LM_PORTALS_FILE
  [ -f "$LM_PORTALS_FILE" ] || { echo "missing $LM_PORTALS_FILE" >&2; exit 66; }
else
  export LM_VAULT_FILE="${LM_VAULT_FILE:-$DIR/secrets.age}"
  export LM_AGE_KEY="${LM_AGE_KEY:-$DIR/age-key.txt}"
  [ -f "$LM_AGE_KEY" ]    || { echo "missing $LM_AGE_KEY (run lm-mcp-add.sh to create the vault)" >&2; exit 66; }
  [ -f "$LM_VAULT_FILE" ] || { echo "missing $LM_VAULT_FILE (run lm-mcp-add.sh to create the vault)" >&2; exit 66; }
  command -v age >/dev/null || { echo "age not found (brew install age)" >&2; exit 69; }
fi
command -v uv >/dev/null || { echo "uv not found (install uv: https://astral.sh/uv)" >&2; exit 69; }

# LM_MCP_SOURCE points at a local clone to run from source (`uv run --project` re-syncs
# on every launch, so clone edits take effect on the next client restart). Without one,
# fall back to the published package via uvx. Progress goes to stderr; stdout stays
# clean JSON-RPC for the MCP client.
SRC="${LM_MCP_SOURCE:-$HOME/src/lm-mcp}"
if [ -d "$SRC" ]; then
  exec uv run --project "$SRC" lm-mcp-server
fi
exec uvx --from lm-mcp lm-mcp-server
