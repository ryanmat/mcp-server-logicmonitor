#!/usr/bin/env bash
# lm-mcp-remove.sh
#
# Retire one customer portal from the age-encrypted vault used by the multi-portal
# MCP server. Decrypts in memory, drops the record, keeps a timestamped backup of
# the previous (encrypted) vault, and re-encrypts in place.
#
# Usage:  ./lm-mcp-remove.sh [nickname]
#   With no argument it lists the portals and asks which to remove.
# Env overrides (same defaults as the launcher):
#   LM_MCP_HOME   dir holding the vault + key   (default ~/.config/lm-mcp)
#   LM_VAULT_FILE path to secrets.age           (default $LM_MCP_HOME/secrets.age)
#   LM_AGE_KEY    path to age identity           (default $LM_MCP_HOME/age-key.txt)
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/bin:/bin:$PATH"

DIR="${LM_MCP_HOME:-$HOME/.config/lm-mcp}"
VAULT="${LM_VAULT_FILE:-$DIR/secrets.age}"
KEY="${LM_AGE_KEY:-$DIR/age-key.txt}"

command -v age        >/dev/null || { echo "age not found (brew install age)"        >&2; exit 69; }
command -v age-keygen >/dev/null || { echo "age-keygen not found (brew install age)" >&2; exit 69; }
command -v jq         >/dev/null || { echo "jq not found (brew install jq)"          >&2; exit 69; }
[ -f "$KEY" ]   || { echo "missing age identity: $KEY" >&2; exit 66; }
[ -f "$VAULT" ] || { echo "no vault at $VAULT — nothing to remove" >&2; exit 66; }

PUB="$(age-keygen -y "$KEY")"
CUR="$(age -d -i "$KEY" "$VAULT")"

echo "Portals currently in the vault:"
CUR="$CUR" jq -r -n 'env.CUR|fromjson | keys[] | "  - " + .'
echo

NAME="${1:-}"
if [ -z "$NAME" ]; then
  read -r -p "Nickname to remove: " NAME
fi
[ -n "${NAME:-}" ] || { echo "nickname required" >&2; exit 1; }

if ! CUR="$CUR" NAME="$NAME" jq -e -n 'env.CUR|fromjson | has(env.NAME)' >/dev/null; then
  echo "portal '$NAME' is not in the vault" >&2; exit 1
fi

# Don't leave an empty vault — the server needs at least one portal to start.
COUNT="$(CUR="$CUR" jq -n 'env.CUR|fromjson | length')"
if [ "$COUNT" -le 1 ]; then
  echo "'$NAME' is the only portal in the vault. Removing it would leave the server" >&2
  echo "with nothing to load. Add another portal first, or delete $VAULT by hand." >&2
  exit 1
fi

read -r -p "Really remove '$NAME'? (y/N): " C
[ "${C:-}" = "y" ] || [ "${C:-}" = "Y" ] || { echo "aborted, vault unchanged"; exit 1; }

NEW="$(CUR="$CUR" NAME="$NAME" jq -n 'env.CUR|fromjson | del(.[env.NAME])')"

cp "$VAULT" "$VAULT.bak.$(date +%Y%m%d%H%M%S)"
printf '%s' "$NEW" | age -r "$PUB" -o "$VAULT"
chmod 600 "$VAULT"

echo
echo "Removed '$NAME'. Portals now in the vault:"
CUR="$NEW" jq -r -n 'env.CUR|fromjson | keys[] | "  - " + .'
echo
echo "Run reload_portals in your client to apply immediately (no restart needed)."
