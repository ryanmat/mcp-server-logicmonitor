# Description: Container image for LogicMonitor MCP server.
# Description: Supports both stdio and HTTP transport modes.

FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Build wheel
RUN uv build --wheel

FROM python:3.11-slim

WORKDIR /app

# Install uv and curl for health checks
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy built wheel from builder
COPY --from=builder /app/dist/*.whl /app/

# Install the package with HTTP transport dependencies
RUN uv pip install --system "/app/*.whl[http]" && rm /app/*.whl

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash mcp
USER mcp

# HTTP mode defaults
ENV LM_TRANSPORT=http
ENV LM_HTTP_HOST=0.0.0.0
ENV LM_HTTP_PORT=8080
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Entry point
ENTRYPOINT ["lm-mcp-server"]
