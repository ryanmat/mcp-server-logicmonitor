# Description: Container image for LogicMonitor MCP server.
# Description: Uses uv for fast, reliable Python package management.

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

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy built wheel from builder
COPY --from=builder /app/dist/*.whl /app/

# Install the package
RUN uv pip install --system /app/*.whl && rm /app/*.whl

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash mcp
USER mcp

# Entry point
ENTRYPOINT ["lm-mcp-server"]
