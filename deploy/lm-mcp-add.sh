#!/usr/bin/env bash
# lm-mcp-add.sh
#
# Add (or update) one customer portal in the age-encrypted vault used by the
# multi-portal MCP server. Prompts for the details, merges the new record into
# the decrypted vault in memory, and re-encrypts it in place. Secrets are never
# written to disk in cleartext and are kept out of the process argument list.
#
# Usage:  ./lm-mcp-add.sh
# Env overrides (same defaults as the launcher):
#   LM_MCP_HOME   dir holding the vault + key   (default ~/.config/lm-mcp)
#   LM_VAULT_FILE path to secrets.age           (default $LM_MCP_HOME/secrets.age)
#   LM_AGE_KEY    path to age identity           (default $LM_MCP_HOME/age-key.txt)
set -euo pipefail

# GUI/login shells can start with a minimal PATH; make our tools resolvable.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/bin:/bin:$PATH"

DIR="${LM_MCP_HOME:-$HOME/.config/lm-mcp}"
VAULT="${LM_VAULT_FILE:-$DIR/secrets.age}"
KEY="${LM_AGE_KEY:-$DIR/age-key.txt}"

command -v age        >/dev/null || { echo "age not found (brew install age)"        >&2; exit 69; }
command -v age-keygen >/dev/null || { echo "age-keygen not found (brew install age)" >&2; exit 69; }
command -v jq         >/dev/null || { echo "jq not found (brew install jq)"          >&2; exit 69; }

# First run: create the age identity so this script is the whole vault setup.
if [ ! -f "$KEY" ]; then
  mkdir -p "$DIR"
  age-keygen -o "$KEY"
  chmod 600 "$KEY"
  echo "created new age identity: $KEY (back it up — it decrypts the vault)"
fi

# Recipient (public key) is derived from the identity, so we always re-encrypt
# to the same key that can decrypt it.
PUB="$(age-keygen -y "$KEY")"

# Current vault contents (or an empty object if the vault doesn't exist yet).
if [ -f "$VAULT" ]; then
  CUR="$(age -d -i "$KEY" "$VAULT")"
else
  CUR='{}'
fi

echo "== Add a LogicMonitor portal to the vault =="
read -r -p "Portal nickname (short key you'll type in use_portal, e.g. acme): " NAME
[ -n "${NAME:-}" ] || { echo "nickname is required" >&2; exit 1; }
read -r -p "Portal host (e.g. acme.logicmonitor.com): " HOST
[ -n "${HOST:-}" ] || { echo "host is required" >&2; exit 1; }

echo "Auth type:  1) Bearer token   2) LMv1 (access id + key)"
read -r -p "Choose 1 or 2: " AUTH
case "$AUTH" in
  1)
    read -r -s -p "Bearer token: " TOKEN; echo
    [ -n "${TOKEN:-}" ] || { echo "token is required" >&2; exit 1; }
    REC="$(HOST="$HOST" TOKEN="$TOKEN" jq -n '{portal: env.HOST, bearer_token: env.TOKEN}')"
    ;;
  2)
    read -r -p "Access ID: " AID
    read -r -s -p "Access Key: " AKEY; echo
    [ -n "${AID:-}" ] && [ -n "${AKEY:-}" ] || { echo "access id and key are required" >&2; exit 1; }
    REC="$(HOST="$HOST" AID="$AID" AKEY="$AKEY" jq -n '{portal: env.HOST, access_id: env.AID, access_key: env.AKEY}')"
    ;;
  *)
    echo "invalid choice" >&2; exit 1 ;;
esac

read -r -p "Allow WRITE operations for this portal? (y/N): " W
if [ "${W:-}" = "y" ] || [ "${W:-}" = "Y" ]; then
  REC="$(REC="$REC" jq -n 'env.REC|fromjson | . + {writable:true}')"
fi

# Refuse to silently clobber an existing portal of the same nickname.
if CUR="$CUR" NAME="$NAME" jq -e -n 'env.CUR|fromjson | has(env.NAME)' >/dev/null; then
  read -r -p "Portal '$NAME' already exists. Overwrite it? (y/N): " O
  [ "${O:-}" = "y" ] || [ "${O:-}" = "Y" ] || { echo "aborted, vault unchanged" >&2; exit 1; }
fi

# Merge in memory (nothing sensitive passes through argv).
NEW="$(CUR="$CUR" NAME="$NAME" REC="$REC" jq -n \
  'env.CUR|fromjson | . + {(env.NAME): (env.REC|fromjson)}')"

# Keep a timestamped backup of the previous (still-encrypted) vault, then write.
if [ -f "$VAULT" ]; then
  cp "$VAULT" "$VAULT.bak.$(date +%Y%m%d%H%M%S)"
fi
printf '%s' "$NEW" | age -r "$PUB" -o "$VAULT"
chmod 600 "$VAULT"

echo
echo "Saved. Portals now in the vault:"
CUR="$NEW" jq -r -n 'env.CUR|fromjson | keys[] | "  - " + .'
echo
echo "Run reload_portals in your client (or restart it) so the server re-reads"
echo "the vault, then: use_portal $NAME"
