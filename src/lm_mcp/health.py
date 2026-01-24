# Description: Health check module for LogicMonitor MCP server.
# Description: Provides health, liveness, and readiness check endpoints.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    status: str  # "pass" | "warn" | "fail"
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"status": self.status}
        if self.message:
            result["message"] = self.message
        return result


@dataclass
class HealthResponse:
    """Overall health check response."""

    status: str  # "healthy" | "degraded" | "unhealthy"
    timestamp: str
    version: str
    checks: dict[str, HealthCheck] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "version": self.version,
            "checks": {name: check.to_dict() for name, check in self.checks.items()},
        }


async def run_health_checks(include_connectivity: bool = False) -> HealthResponse:
    """Run all health checks and return overall status.

    Args:
        include_connectivity: If True, ping LogicMonitor API to verify connectivity.

    Returns:
        HealthResponse with overall status and individual check results.
    """
    from lm_mcp import __version__
    from lm_mcp.server import get_client

    checks: dict[str, HealthCheck] = {}

    # Check 1: Server running (always passes if we're here)
    checks["server"] = HealthCheck(name="server", status="pass", message="MCP server running")

    # Check 2: Client initialized
    try:
        client = get_client()
        checks["client"] = HealthCheck(name="client", status="pass", message="Client initialized")
    except RuntimeError:
        checks["client"] = HealthCheck(
            name="client", status="fail", message="Client not initialized"
        )
        client = None

    # Check 3: Config valid
    try:
        from lm_mcp.config import LMConfig

        LMConfig()
        checks["config"] = HealthCheck(name="config", status="pass", message="Configuration valid")
    except Exception as e:
        checks["config"] = HealthCheck(
            name="config", status="fail", message=f"Configuration error: {e}"
        )

    # Check 4: LM API connectivity (optional)
    if include_connectivity and client:
        try:
            # Use a lightweight API call to check connectivity
            await client.get("/setting/admins", params={"size": 1})
            checks["connectivity"] = HealthCheck(
                name="connectivity", status="pass", message="LogicMonitor API reachable"
            )
        except Exception as e:
            checks["connectivity"] = HealthCheck(
                name="connectivity", status="warn", message=f"API check failed: {e}"
            )

    # Determine overall status
    statuses = [check.status for check in checks.values()]
    if "fail" in statuses:
        overall_status = "unhealthy"
    elif "warn" in statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version=__version__,
        checks=checks,
    )
