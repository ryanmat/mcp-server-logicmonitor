# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.5.x   | Yes                |
| 0.4.x   | Yes                |
| < 0.4   | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Email the maintainer directly or use [GitHub Security Advisories](https://github.com/ryanmat/mcp-server-logicmonitor/security/advisories/new)
3. Include a detailed description of the vulnerability and steps to reproduce

You can expect:
- Acknowledgment within 48 hours
- Regular updates on the fix progress
- Credit in the security advisory (unless you prefer anonymity)

## Security Considerations

### Credential Handling
- Bearer tokens are passed via environment variables only
- Never commit tokens to version control
- Use `.env` files locally (included in `.gitignore`)

### Write Operations
- Write operations are disabled by default
- Enable only when needed: `LM_ENABLE_WRITE_OPERATIONS=true`
- Review permissions granted to your LogicMonitor API token

### Container Security
- Docker image runs as non-root user
- Minimal base image (python:slim)
- No sensitive data persisted in container

### Best Practices
- Use dedicated API tokens with minimal required permissions
- Rotate tokens regularly
- Monitor LogicMonitor audit logs for unexpected API activity
