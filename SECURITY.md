# Security policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 4.x     | Yes                |
| < 4.0   | No                 |

## Reporting a vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Use [private vulnerability reporting](https://github.com/ryanmat/mcp-server-logicmonitor/security/advisories/new),
   which is enabled on this repository and keeps the report private until a fix
   ships. The "Report a vulnerability" button on the Security tab does the same.
3. Include a detailed description of the vulnerability and steps to reproduce

You can expect:
- Acknowledgment within 48 hours
- Regular updates on the fix progress
- Credit in the security advisory (unless you prefer anonymity)

## Security considerations

### Credential handling
- Bearer tokens are passed via environment variables, or through an age-encrypted
  vault in multi-portal mode
- Never commit tokens to version control
- Use `.env` files locally (included in `.gitignore`)
- Write audit lines and session history mask credential-shaped argument values,
  LogicMonitor credential properties such as `ssh.pass`, and URL userinfo and
  credential-named query values. Signature parameters such as `X-Amz-Signature`
  stay visible in a logged URL.

### Inbound HTTP exposure
- The HTTP transport serves MCP at `/mcp` (the SDK's Streamable HTTP,
  stateless) beside the health, readiness and info routes. A caller that passes
  the bearer check at `/mcp` calls the tools stdio lists with the server's
  LogicMonitor credentials, write tools only when
  `LM_ENABLE_WRITE_OPERATIONS=true`, and every caller shares the server's one
  session, its variables and history included. Give the token only to callers
  who may share that portal access.
- Set `LM_HTTP_AUTH_TOKEN` whenever the port is reachable beyond localhost:
  every path outside `/` and the health endpoints then requires
  `Authorization: Bearer <token>` and returns 401 otherwise. A bind outside `127.0.0.1`, `::1` and `localhost`
  refuses to start without it unless `LM_HTTP_ALLOW_UNAUTHENTICATED=true`
  accepts the exposure; the default `LM_HTTP_HOST` is `0.0.0.0`.
- Every route except `/healthz` and `/readyz` answers only the loopback names,
  a non-wildcard `LM_HTTP_HOST` and `LM_HTTP_ALLOWED_HOSTS` in `Host` (400
  otherwise), which blocks DNS rebinding from a page in the operator's browser.
- The LogicMonitor client refuses an API path holding a `.` or `..` segment or
  an encoded separator, which blocks path traversal through a tool argument.
- `/`, `/health`, `/healthz`, and `/readyz` stay unauthenticated so container
  healthchecks and orchestrator probes keep working. Their responses carry
  component status, never LogicMonitor data. None of them calls the
  LogicMonitor API for an unauthenticated caller: `/readyz` never does, and
  with `LM_HEALTH_CHECK_CONNECTIVITY=true` (off by default) `/health` adds the
  API connectivity check only when the request carries `LM_HTTP_AUTH_TOKEN`,
  or when no token is configured. Earlier releases
  pinged the API on every `/readyz` request when that flag was on, letting an
  anonymous caller consume your portal's API quota; that is fixed (issue #56).
- Pair the token with TLS (the Caddy profile in `deploy/`, or
  `LM_HTTP_SSL_CERTFILE` and `LM_HTTP_SSL_KEYFILE`) so it is not sent in
  cleartext.
- The stdio transport is unaffected: it has no listening socket.

### Write operations
- Write operations are disabled by default
- Enable only when needed: `LM_ENABLE_WRITE_OPERATIONS=true`
- A POST or PATCH that gets a 5xx is not resent, so a retry cannot apply a change
  twice
- Review permissions granted to your LogicMonitor API token

### Container security
- The image runs as a fixed non-root UID (10001)
- The base image is a slim Python image, pinned by digest
- Dependencies install from `uv.lock` with hash checking
- No sensitive data persisted in container

### Best practices
- Use dedicated API tokens with minimal required permissions
- Rotate tokens regularly
- Monitor LogicMonitor audit logs for unexpected API activity
