#!/usr/bin/env bash
# Description: Adds the LogicMonitor MCP server to the current Claude Code project.
# Description: Reads credentials from the canonical .env and runs claude mcp add.

set -euo pipefail

MCP_PROJECT_DIR="/home/rmatuszewski/dev/tools/mcp-server-logicmonitor"
ENV_FILE="${MCP_PROJECT_DIR}/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at ${ENV_FILE}"
    exit 1
fi

# Source the .env file to get credentials
set -a
source "$ENV_FILE"
set +a

# Remove existing logicmonitor MCP server if present
claude mcp remove logicmonitor 2>/dev/null || true

# Default scope is local (per-project, per-machine)
claude mcp add logicmonitor \
    -e "LM_PORTAL=${LM_PORTAL}" \
    -e "LM_BEARER_TOKEN=${LM_BEARER_TOKEN}" \
    -e "LM_ENABLE_WRITE_OPERATIONS=${LM_ENABLE_WRITE_OPERATIONS:-true}" \
    -e "AWX_URL=${AWX_URL}" \
    -e "AWX_TOKEN=${AWX_TOKEN}" \
    -e "AWX_VERIFY_SSL=${AWX_VERIFY_SSL:-false}" \
    -- uvx --from lm-mcp lm-mcp-server

echo ""
echo "LogicMonitor MCP server added. Restart Claude Code to pick it up."
