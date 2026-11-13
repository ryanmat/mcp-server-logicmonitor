# Connect an MCP client to the LogicMonitor server

Connect Claude Code, Claude Desktop, Cursor, VS Code, OpenAI Codex CLI or Gemini CLI to the LogicMonitor MCP server, read-only first.

1. [Connect Claude Code](#connect-claude-code)
2. [Connect Claude Desktop](#connect-claude-desktop)
3. [Connect Cursor](#connect-cursor)
4. [Connect VS Code](#connect-vs-code)
5. [Connect OpenAI Codex CLI](#connect-openai-codex-cli)
6. [Connect Gemini CLI](#connect-gemini-cli)
7. [Optional: Connect over Streamable HTTP](#optional-connect-over-streamable-http)
8. [Optional: Narrow the tool list](#optional-narrow-the-tool-list)
9. [Optional: Turn on the write tools](#optional-turn-on-the-write-tools)
10. [Verify the connection](#verify-the-connection)

Every client starts the same command, `uvx --from lm-mcp lm-mcp-server`; the config file and its format are what differ. Back to the [README](../README.md).

## Before you begin

- Install [uv](https://docs.astral.sh/uv/), which provides `uvx`. The server needs Python 3.11 or later, and uv downloads one when none is installed.
- Create a LogicMonitor API token under **Settings** > **Users and Roles** > **API Tokens**: a Bearer token, or an LMv1 access ID and key, for a user whose role grants what the tools you call need.
- Note your portal hostname, such as `yourcompany.logicmonitor.com`.
- For the Streamable HTTP task, run the server with `LM_TRANSPORT=http` and `LM_HTTP_AUTH_TOKEN` set. See [Deployment](../README.md#deployment) in the README.

The server lists only its read tools until `LM_ENABLE_WRITE_OPERATIONS=true` is set, so each client task below sets up read-only access. [Optional: Turn on the write tools](#optional-turn-on-the-write-tools) adds the rest.

## Connect Claude Code

To connect Claude Code:

1. Add the server with your portal and token.

   ```bash
   claude mcp add logicmonitor \
     -e LM_PORTAL=yourcompany.logicmonitor.com \
     -e LM_BEARER_TOKEN=<LM_BEARER_TOKEN> \
     -- uvx --from lm-mcp lm-mcp-server
   ```

2. Run `claude mcp list`. The list shows `logicmonitor` as connected.

## Connect Claude Desktop

To connect Claude Desktop:

1. Open `claude_desktop_config.json`, in `~/Library/Application Support/Claude/` on macOS or `%APPDATA%\Claude\` on Windows.
2. Add the `logicmonitor` entry under `mcpServers`.

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "command": "uvx",
         "args": ["--from", "lm-mcp", "lm-mcp-server"],
         "env": {
           "LM_PORTAL": "yourcompany.logicmonitor.com",
           "LM_BEARER_TOKEN": "your-bearer-token"
         }
       }
     }
   }
   ```

3. Restart Claude Desktop.

## Connect Cursor

Older Cursor releases sent only the first 40 MCP tools to the agent. Cursor's MCP documentation (cursor.com/docs/mcp, read 2026-11-13) states no limit. With writes off the server lists 150 of its 273 tools, so if your release still caps the list, narrow it as [Optional: Narrow the tool list](#optional-narrow-the-tool-list) shows.

To connect Cursor:

1. Open `~/.cursor/mcp.json` to use the server in every project, or `.cursor/mcp.json` in one project.
2. Add the `logicmonitor` entry. Cursor reads `${env:LM_BEARER_TOKEN}` from your environment, so the token stays out of the file.

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "command": "uvx",
         "args": ["--from", "lm-mcp", "lm-mcp-server"],
         "env": {
           "LM_PORTAL": "yourcompany.logicmonitor.com",
           "LM_BEARER_TOKEN": "${env:LM_BEARER_TOKEN}"
         }
       }
     }
   }
   ```

3. Restart Cursor.

## Connect VS Code

VS Code's Copilot reads a workspace-root `.mcp.json`, or `~/.copilot/mcp-config.json` for every workspace (`$COPILOT_HOME/mcp-config.json` when that variable is set). Both take a top-level `mcpServers` object. The `servers` format in `.vscode/mcp.json` belongs to the deprecated Local harness, which Copilot reads only through forwarding. See [MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) (approved 2026-11-11).

To connect VS Code:

1. Open `.mcp.json` at the workspace root, or `~/.copilot/mcp-config.json`.
2. Add the `logicmonitor` entry. VS Code reads `${LM_BEARER_TOKEN}` from your environment.

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "type": "stdio",
         "command": "uvx",
         "args": ["--from", "lm-mcp", "lm-mcp-server"],
         "env": {
           "LM_PORTAL": "yourcompany.logicmonitor.com",
           "LM_BEARER_TOKEN": "${LM_BEARER_TOKEN}"
         },
         "tools": ["*"]
       }
     }
   }
   ```

## Connect OpenAI Codex CLI

`codex mcp add logicmonitor --env LM_PORTAL=... --env LM_BEARER_TOKEN=... -- uvx --from lm-mcp lm-mcp-server` writes the same server with the token in the file. The steps below keep the token in your environment instead.

To connect OpenAI Codex CLI:

1. Open `~/.codex/config.toml`.
2. Add the `logicmonitor` table. `env_vars` forwards `LM_BEARER_TOKEN` from your environment to the server.

   ```toml
   [mcp_servers.logicmonitor]
   command = "uvx"
   args = ["--from", "lm-mcp", "lm-mcp-server"]
   env = { LM_PORTAL = "yourcompany.logicmonitor.com" }
   env_vars = ["LM_BEARER_TOKEN"]
   ```

3. Run `codex mcp list`. The list shows `logicmonitor`.

## Connect Gemini CLI

To connect Gemini CLI:

1. Open `~/.gemini/settings.json`, or `.gemini/settings.json` in a project.
2. Add the `logicmonitor` entry under `mcpServers`. Gemini CLI reads `$LM_BEARER_TOKEN` from your environment.

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "command": "uvx",
         "args": ["--from", "lm-mcp", "lm-mcp-server"],
         "env": {
           "LM_PORTAL": "yourcompany.logicmonitor.com",
           "LM_BEARER_TOKEN": "$LM_BEARER_TOKEN"
         }
       }
     }
   }
   ```

3. Start Gemini CLI and run `/mcp`. The list shows `logicmonitor` and its tools.

## Optional: Connect over Streamable HTTP

Use this task when the server runs as an HTTP service, such as the container, instead of as a subprocess of the client. The client sends `LM_HTTP_AUTH_TOKEN` as a Bearer token on every request to `/mcp`, and no LogicMonitor credential leaves the server.

To connect a client over Streamable HTTP:

1. Note the server's URL, such as `http://127.0.0.1:8080/mcp`, and its `LM_HTTP_AUTH_TOKEN`.
2. Add the server in your client's format.

   Claude Code:

   ```bash
   claude mcp add --transport http logicmonitor http://127.0.0.1:8080/mcp \
     --header "Authorization: Bearer <LM_HTTP_AUTH_TOKEN>"
   ```

   Cursor, in `mcp.json`:

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "url": "http://127.0.0.1:8080/mcp",
         "headers": {
           "Authorization": "Bearer ${env:LM_HTTP_AUTH_TOKEN}"
         }
       }
     }
   }
   ```

   VS Code, in `.mcp.json` or `mcp-config.json`:

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "type": "http",
         "url": "http://127.0.0.1:8080/mcp",
         "headers": {
           "Authorization": "Bearer ${LM_HTTP_AUTH_TOKEN}"
         }
       }
     }
   }
   ```

   OpenAI Codex CLI, in `config.toml`, reading the token from `LM_HTTP_AUTH_TOKEN`:

   ```toml
   [mcp_servers.logicmonitor]
   url = "http://127.0.0.1:8080/mcp"
   bearer_token_env_var = "LM_HTTP_AUTH_TOKEN"
   ```

   Gemini CLI, in `settings.json`:

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "httpUrl": "http://127.0.0.1:8080/mcp",
         "headers": {
           "Authorization": "Bearer your-http-auth-token"
         }
       }
     }
   }
   ```

3. Restart the client.

## Optional: Narrow the tool list

Use this task when a client handles a long tool list poorly, or to give an agent only the tools its job needs. `LM_MCP_CATEGORIES` takes `read`, `write`, `delete`, `export`, `import`, `session` and `workflow`, and narrows `LM_ENABLED_TOOLS` and `LM_DISABLED_TOOLS` without widening them. `LM_ENABLED_TOOLS` and `LM_DISABLED_TOOLS` cannot both be set.

To narrow the tool list:

1. Set `LM_MCP_CATEGORIES` in the entry's `env`, such as `workflow`. With writes off, `workflow` lists 13 tools: the analytics, the composites, `search_tools` and `audit_network_monitoring_coverage`.

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "command": "uvx",
         "args": ["--from", "lm-mcp", "lm-mcp-server"],
         "env": {
           "LM_PORTAL": "yourcompany.logicmonitor.com",
           "LM_BEARER_TOKEN": "${env:LM_BEARER_TOKEN}",
           "LM_MCP_CATEGORIES": "workflow"
         }
       }
     }
   }
   ```

2. For named tools in place of a category, set `LM_ENABLED_TOOLS` to their names. The server lists those eight tools.

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "command": "uvx",
         "args": ["--from", "lm-mcp", "lm-mcp-server"],
         "env": {
           "LM_PORTAL": "yourcompany.logicmonitor.com",
           "LM_BEARER_TOKEN": "${env:LM_BEARER_TOKEN}",
           "LM_ENABLED_TOOLS": "triage,diagnose,health_check,portal_overview,get_alerts,get_alert_details,get_devices,search_tools"
         }
       }
     }
   }
   ```

3. Restart the client.

## Optional: Turn on the write tools

Use this task only for a portal and a token you accept the assistant changing. The server then lists the tools that create, update, delete, acknowledge and run. Before a destructive tool runs, a client that supports MCP elicitation asks you to confirm.

To turn on the write tools:

1. Add `LM_ENABLE_WRITE_OPERATIONS` set to `true` to the entry's `env`. In Claude Code, pass `-e LM_ENABLE_WRITE_OPERATIONS=true` to `claude mcp add`.

   ```json
   {
     "mcpServers": {
       "logicmonitor": {
         "command": "uvx",
         "args": ["--from", "lm-mcp", "lm-mcp-server"],
         "env": {
           "LM_PORTAL": "yourcompany.logicmonitor.com",
           "LM_BEARER_TOKEN": "${env:LM_BEARER_TOKEN}",
           "LM_ENABLE_WRITE_OPERATIONS": "true"
         }
       }
     }
   }
   ```

2. Restart the client. The tool list grows from 150 to 261.

## Verify the connection

To verify the connection:

1. Ask the assistant to list the first 5 devices in LogicMonitor. It calls `get_devices` and names five devices.
2. Ask it to search the LogicMonitor tools for "acknowledge". With writes off, `search_tools` returns no write tool.
