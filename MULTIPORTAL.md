# Multi-portal mode

One server entry serves many customer LogicMonitor portals. The portal credentials
live in an age-encrypted vault, the server builds a client per portal on first use,
and the tool set is listed once, not once per portal.

Multi-portal mode runs over stdio only. The server refuses to start with
`LM_TRANSPORT=http`, because the HTTP transport serves every caller from one process
and a shared default portal would leak data between users.

## What it adds

- Four portal tools: `get_portals` lists the portals in the vault (name, host, auth
  type, writable), `use_portal(customer)` sets the default portal, `get_current_portal`
  shows it, and `run_portal_reload` re-reads the vault so portals added or removed
  since startup take effect without a restart (the default stays when it still exists).
- A `portal` argument on every LogicMonitor tool. A call that names a portal runs
  against that portal and leaves the default as it is; a call without one runs against
  the default.
- One session per portal: session variables and history belong to the portal a call
  ran against.
- Every result names its portal: a success result carries `portal`, an error carries
  it as `error.details.portal`.

Until a default is set, a call without a `portal` argument is refused with "No portal
selected".

## Choosing the portal for a call

`use_portal` sets the default for later calls. The `portal` argument overrides it for
one call, so a question that spans portals ("compare dead devices in acme and
globex") needs no switching: the model calls `get_devices` with `portal="acme"`, then
with `portal="globex"`.

The argument takes the vault name `get_portals` lists. A name not in the vault is
refused as `INVALID_REQUEST` with the names that are. The tools that never take the
argument are the session tools (they keep the default portal's session), the four
portal tools, `search_tools` and `get_reference` (they read no portal), and the Edwin AI
tools (Edwin is one tenant for every portal, so its write tools are off in this mode).

The argument adds about 30 tokens to each tool in the `tools/list` response.

## Configuration

| Variable | Meaning |
|---|---|
| `LM_MULTI_PORTAL=true` | Turn on multi-portal mode; `LM_PORTAL` is not needed |
| `LM_VAULT_FILE` | Path to the age-encrypted vault (`secrets.age`) |
| `LM_AGE_KEY` | Path to the age identity that decrypts it |
| `LM_PORTALS_FILE` | A plaintext JSON vault instead, for testing only |

When both sources are set, the encrypted vault wins and the server logs a warning, so a
stale test file never shadows production credentials. The server expands `~` in these
paths, so they work in client `env` blocks that bypass a shell. If you curate tools with
`LM_ENABLED_TOOLS`, include the four portal tools; `LM_MCP_CATEGORIES` never filters
them out in multi-portal mode.

The vault is a JSON object of portal name to record:

```json
{
  "acme":   { "portal": "acme.logicmonitor.com",   "bearer_token": "..." },
  "globex": { "portal": "globex.logicmonitor.com", "access_id": "...", "access_key": "...", "writable": true }
}
```

## Try it from a clone

With `LM_PORTALS_FILE` set to the path of a plaintext vault in the format above, run
from the root of a clone:

```bash
LM_MCP_SOURCE="$PWD" deploy/lm-mcp-multiportal.sh
```

The launcher serves MCP over stdio, read-only, with the `read` and `session` tool
categories. Point an MCP client at the same command to try the portal tools without
setting up age.

## Set up the vault

`deploy/lm-mcp-add.sh` needs `age`, `age-keygen` and `jq`. On first run it creates the
age identity at `~/.config/lm-mcp/age-key.txt`, then prompts for the first portal and
writes `~/.config/lm-mcp/secrets.age`. Copy the launchers beside the vault so client
configs have a stable path:

```bash
deploy/lm-mcp-add.sh
install -m 755 deploy/lm-mcp-multiportal.sh deploy/lm-mcp-add.sh deploy/lm-mcp-remove.sh ~/.config/lm-mcp/
```

`lm-mcp-multiportal.sh` reads the vault from `~/.config/lm-mcp` (or `LM_MCP_HOME`, or
`LM_VAULT_FILE` and `LM_AGE_KEY`), turns on multi-portal mode over stdio, defaults to
read-only, and runs the server. `LM_MCP_SOURCE` names a local clone to run from
(default `~/src/lm-mcp`); without one it runs the published package with
`uvx --from lm-mcp`. `LM_MCP_SOURCE` must be a directory, since `uv run --project` does
not take git URLs.

## Wire it into clients

One entry serves every portal. Claude Desktop,
`~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Codex, `~/.codex/config.toml`:

```toml
[mcp_servers.logicmonitor]
command = "/home/you/.config/lm-mcp/lm-mcp-multiportal.sh"
args = []
```

Replace `/home/you` with your home directory; these configs do not expand `~`. In
chat, "list portals", "use acme" and "list dead devices" set a default and work
against it, and "compare dead devices in acme and globex" names each portal per call.

## Writes

Writes are off by default. A write needs `LM_ENABLE_WRITE_OPERATIONS=true` on the
server and `"writable": true` on the record of the portal the call runs against,
whether that is the default or the portal the call names. The launcher lists only the
`read` and `session` categories, so widen them too, for example
`LM_MCP_CATEGORIES=read,write,session`. A read-only portal refuses a write with
`WRITE_DISABLED` even then.

## Add a portal

```bash
~/.config/lm-mcp/lm-mcp-add.sh
```

It decrypts the vault in memory, merges the new record, asks before overwriting a
portal of the same name, keeps a timestamped backup of the previous encrypted vault,
and re-encrypts in place. Secrets never touch disk in cleartext and stay out of the
process argument list. It prompts for the portal name (what `use_portal` and the
`portal` argument take), the host, the auth type (bearer token, or LMv1 access id and
key) and whether the portal may take writes. Then call `run_portal_reload` in your
client, or restart it.

## Remove a portal

```bash
~/.config/lm-mcp/lm-mcp-remove.sh acme
```

It lists the portals, asks for confirmation, drops the record, keeps a timestamped
backup and re-encrypts. It refuses to remove the last portal, since the server needs
one to load. Call `run_portal_reload` afterwards to apply it without a restart.

To edit the vault by hand instead, decrypt into a variable, edit with jq, back up and
re-encrypt. Every variable is set by the snippet itself, so a typo cannot truncate the
vault, and the backup keeps a way back either way:

```bash
CUR="$(age -d -i ~/.config/lm-mcp/age-key.txt ~/.config/lm-mcp/secrets.age)"
UPDATED="$(printf '%s' "$CUR" | jq '. + {"initech": {"portal": "initech.logicmonitor.com", "bearer_token": "..."}}')"
cp ~/.config/lm-mcp/secrets.age ~/.config/lm-mcp/secrets.age.bak.$(date +%Y%m%d%H%M%S)
PUB="$(age-keygen -y ~/.config/lm-mcp/age-key.txt)"
printf '%s' "$UPDATED" | age -r "$PUB" -o ~/.config/lm-mcp/secrets.age
```
