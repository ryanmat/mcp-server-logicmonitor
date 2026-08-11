# Multi-portal mode

A **single-server, many-portals** mode: work across 20-30 customer LogicMonitor portals
from one MCP server entry, switching the active portal at runtime — no
process-per-customer, and the full tool set is loaded **once**, not per portal.

Multi-portal mode is **stdio-only**. The server refuses to start with
`LM_TRANSPORT=http`: the HTTP transport serves every caller from one process, so a
shared "active portal" would leak data between users. Terraform tools are also
unavailable in this mode (the LM Terraform provider needs fixed credentials) — run a
single-portal server for IaC work. Health endpoints do not exist under stdio.

## What it adds

- `list_portals` — list the customer portals in your vault (names, host, auth type, writable).
- `use_portal(customer)` — make that portal active for subsequent tool calls.
- `current_portal` — show the active portal.
- `reload_portals` — re-read the vault so portals added/removed since startup take
  effect without restarting the client (keeps the active portal if it still exists).
- A portal **registry** that reads credentials from an age-encrypted vault (or a plaintext
  JSON file for testing) and builds a LogicMonitor client per customer on demand.
- Guardrails: data tools return "No portal selected" until you call `use_portal`; writes are
  **read-only by default** and require both `LM_ENABLE_WRITE_OPERATIONS=true` **and**
  `"writable": true` on that portal's vault record.

Unmodified upstream tools are untouched — they simply use whichever portal is active.

## Configuration (env)

| var | meaning |
|---|---|
| `LM_MULTI_PORTAL=true` | enable multi-portal mode (no fixed `LM_PORTAL` needed) |
| `LM_VAULT_FILE` | path to the age-encrypted vault (`secrets.age`) |
| `LM_AGE_KEY` | path to the age identity used to decrypt it |
| `LM_PORTALS_FILE` | alternative: a plaintext JSON vault (testing only) |

When both sources are set, the encrypted vault wins and a warning is logged — a stale
testing file can never shadow production credentials. Tilde paths (`~/...`) are
expanded by the server, so they work in client `env` blocks that bypass a shell. If you
curate tools with `LM_ENABLED_TOOLS`, include the four portal tools; `LM_MCP_CATEGORIES`
never filters them out in multi-portal mode (they are the control plane).

Vault format (a JSON object of nickname -> record):

```json
{
  "acme":   { "portal": "acme.logicmonitor.com",   "bearer_token": "..." },
  "globex": { "portal": "globex.logicmonitor.com", "access_id": "...", "access_key": "...", "writable": true }
}
```

## Run it locally (from your clone)

```bash
# one-time: create the vault. deploy/lm-mcp-add.sh generates the age identity on
# first run and prompts for the first portal:
#   -> produces ~/.config/lm-mcp/age-key.txt and ~/.config/lm-mcp/secrets.age
deploy/lm-mcp-add.sh

# run the multi-portal server from this clone
LM_MULTI_PORTAL=true \
LM_VAULT_FILE=~/.config/lm-mcp/secrets.age \
LM_AGE_KEY=~/.config/lm-mcp/age-key.txt \
uvx --from . lm-mcp-server        # or: uv run lm-mcp-server
```

`deploy/lm-mcp-multiportal.sh` wraps exactly this (read-only defaults, path handling) for use
as the `command` in a client config.

## Wire into clients (ONE entry, not per customer)

Claude Desktop — `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "logicmonitor": {
      "command": "/home/you/.config/lm-mcp/lm-mcp-multiportal.sh",
      "args": []
    }
  }
}
```

Codex — `~/.codex/config.toml`:
```toml
[mcp_servers.logicmonitor]
command = "/home/you/.config/lm-mcp/lm-mcp-multiportal.sh"
args = []
```

Then in chat: "list portals", "use acme", "list dead devices" — the model calls
`use_portal` then works against that customer.

## Enabling writes (optional, per portal)

Writes are off by default. To allow them for a portal marked `"writable": true`, run the
server with `LM_ENABLE_WRITE_OPERATIONS=true` and widen categories to include write
(`LM_MCP_CATEGORIES=read,write,session`). A read-only portal still blocks writes even then.

## Adding a portal later

Use the helper — it decrypts the vault, merges in the new record, and re-encrypts
in place (secrets never touch disk in cleartext, and stay out of the process
argument list). A timestamped backup of the previous encrypted vault is kept.

```bash
~/.config/lm-mcp/lm-mcp-add.sh    # or deploy/lm-mcp-add.sh from this repo
```

It prompts for a nickname (the key you pass to `use_portal`), the portal host,
the auth type (bearer token or LMv1 access id+key), and whether that portal may
perform writes. After it saves, run `reload_portals` in your client (or restart it)
so the server re-reads the vault, then `use_portal <nickname>`.

## Removing a portal

```bash
~/.config/lm-mcp/lm-mcp-remove.sh [nickname]   # or deploy/lm-mcp-remove.sh
```

Lists the portals, confirms, drops the record, and re-encrypts (with a timestamped
backup). It refuses to remove the last portal, since the server needs at least one
to load. Run `reload_portals` afterwards to apply without a restart.

Doing it by hand instead: decrypt into a variable, edit with jq, back up, re-encrypt.
Every variable below is defined by the snippet itself, so a typo cannot truncate the
vault, and the backup keeps a recovery path either way.

```bash
CUR="$(age -d -i ~/.config/lm-mcp/age-key.txt ~/.config/lm-mcp/secrets.age)"
UPDATED="$(printf '%s' "$CUR" | jq '. + {"<nickname>": {"portal": "host", "bearer_token": "..."}}')"
cp ~/.config/lm-mcp/secrets.age ~/.config/lm-mcp/secrets.age.bak.$(date +%Y%m%d%H%M%S)
PUB="$(age-keygen -y ~/.config/lm-mcp/age-key.txt)"
printf '%s' "$UPDATED" | age -r "$PUB" -o ~/.config/lm-mcp/secrets.age
```

## Running from a clone vs the published package

The launcher runs `uv run --project "$LM_MCP_SOURCE"` when that path is a local clone
(default `~/src/lm-mcp`), so source edits take effect on the next client restart. When
no clone exists it falls back to the published package via `uvx --from lm-mcp`.
`LM_MCP_SOURCE` must be a directory — `uv run --project` does not accept git URLs.
