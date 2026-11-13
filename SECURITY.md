# LogicMonitor MCP server security policy

Report a vulnerability through GitHub's private vulnerability reporting; the maintainer acknowledges it within 48 hours, and it stays private until a release carries the fix.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 5.x     | Yes       |
| 4.x     | Yes       |
| < 4.0   | No        |

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Report it through [private vulnerability reporting](https://github.com/ryanmat/mcp-server-logicmonitor/security/advisories/new), or the **Report a vulnerability** button on the repository's **Security** tab, with a description of the issue, the steps that reproduce it, the versions affected and any mitigation you know.

The maintainer acknowledges the report within 48 hours, then confirms the issue and keeps you updated while the fix is in progress.

## Disclosure policy

A report stays private until a release carries the fix. The security advisory publishes with that release and credits you, unless you ask not to be named.

## Security updates

A fix ships as a release: the `lm-mcp` package on PyPI, the image at `ghcr.io/ryanmat/mcp-server-logicmonitor`, and a GitHub release whose notes come from [CHANGELOG.md](CHANGELOG.md). A security fix also gets a [GitHub security advisory](https://github.com/ryanmat/mcp-server-logicmonitor/security/advisories). Run `uv tool upgrade lm-mcp` or pull the new image to pick it up.

## Security model

### Credentials

- The LogicMonitor token (Bearer, or the LMv1 access ID and key) comes from environment variables, or from an age-encrypted vault in multi-portal mode. Keep tokens out of version control; `.env` is in `.gitignore`.
- Give the token to a user whose role grants only what the tools you call need.
- The Edwin AI credential (`EDWIN_CLIENT_ID`, `EDWIN_CLIENT_TOKEN`) turns on the Edwin tools. Edwin refuses a call outside the credential's scopes, and the server reports that as `SCOPE_MISSING` with the scope's name (`query_aggregate`, `query_records` and `query_record` are the scopes probed), so a credential can be limited to the reads you use. The token exchange sends the credential's secret only to an `https://` `EDWIN_HOST`, and the token it returns stays in memory.

### Write gate and hidden write tools

- With `LM_ENABLE_WRITE_OPERATIONS` unset or false, the default, the server leaves the 112 tools whose annotations say they change the portal out of `tools/list` and refuses a call to one by name with `WRITE_DISABLED`. `search_tools` never names a hidden tool. The session tools, `use_portal` and `run_portal_reload` change only the server's own state and stay listed.
- In multi-portal mode a write also needs the portal's vault record to mark it writable; every other portal is read-only.
- `collector_debug` runs one command from a fixed list, is gated as a write, and opens a debug session the portal records in its audit log.
- A POST or PATCH that gets a 5xx is not resent, so a retry cannot apply a change twice.

### Confirmation before destructive calls

The 36 tools annotated `destructiveHint` ask the user before they run when the client supports MCP elicitation. A declined or cancelled confirmation returns `REJECTED_BY_TOOL` and changes nothing. Over the stateless HTTP transport, and with a client that cannot be asked, the write gate is the only check. A call that a read-only portal refuses is not asked about.

### Audit trail

Every call to a tool that changes state writes an audit line to stderr at every `LM_LOG_LEVEL`: `info` for a success, `warning` for a failure, with the confirmation answer for a destructive call. The line, and the session history, mask argument values under credential-shaped keys, LogicMonitor credential properties such as `ssh.pass`, and URL userinfo and credential-named query values. Signature parameters such as `X-Amz-Signature` stay visible in a logged URL.

### Inbound HTTP exposure

- The HTTP transport serves MCP at `/mcp` (the SDK's Streamable HTTP, stateless) beside the health, readiness and info routes. A caller that passes the bearer check can call the tools stdio lists with the server's LogicMonitor credentials, and the write tools only when `LM_ENABLE_WRITE_OPERATIONS=true`. Every caller shares the server's one session, its variables and history included. Give the token only to callers who may share that portal access.
- Set `LM_HTTP_AUTH_TOKEN` whenever the port is reachable beyond localhost: every path outside `/` and the health endpoints then requires `Authorization: Bearer <token>` and answers 401 otherwise. A bind outside `127.0.0.1`, `::1` and `localhost` refuses to start without it unless `LM_HTTP_ALLOW_UNAUTHENTICATED=true` accepts the exposure; the default `LM_HTTP_HOST` is `0.0.0.0`.
- Every route except `/healthz` and `/readyz` answers only the loopback names, a non-wildcard `LM_HTTP_HOST` and `LM_HTTP_ALLOWED_HOSTS` in `Host` (400 otherwise), which blocks DNS rebinding from a page in the operator's browser.
- The LogicMonitor client refuses an API path holding a `.` or `..` segment or an encoded separator, which blocks path traversal through a tool argument.
- `/`, `/health`, `/healthz` and `/readyz` stay unauthenticated so container healthchecks and orchestrator probes keep working. Their responses carry component status, never LogicMonitor data. None of them calls the LogicMonitor API for an unauthenticated caller: `/readyz` never does, and with `LM_HEALTH_CHECK_CONNECTIVITY=true` (off by default) `/health` adds the API connectivity check only when the request carries `LM_HTTP_AUTH_TOKEN`, or when no token is configured. Earlier releases pinged the API on every `/readyz` request when that flag was on, letting an anonymous caller consume your portal's API quota; that is fixed (issue #56).
- Pair the token with TLS (the Caddy profile in `deploy/`, or `LM_HTTP_SSL_CERTFILE` and `LM_HTTP_SSL_KEYFILE`) so it never crosses the network in cleartext.
- The stdio transport has no listening socket.

### Container

- The image runs as a fixed non-root UID (10001).
- The base image is a slim Python image, pinned by digest.
- Dependencies install from `uv.lock` with hash checking.
- The container persists no data.
