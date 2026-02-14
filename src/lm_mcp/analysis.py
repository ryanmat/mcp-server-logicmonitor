# Description: Analysis workflow engine for scheduled and webhook-triggered analysis.
# Description: Provides in-memory store, workflow dispatch, and async execution.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Supported analysis workflows
VALID_WORKFLOWS = {
    "alert_correlation",
    "rca_workflow",
    "top_talkers",
    "health_check",
}


def validate_workflow(workflow: str) -> None:
    """Validate that a workflow name is supported.

    Args:
        workflow: Workflow name to validate.

    Raises:
        ValueError: If workflow is not recognized.
    """
    if workflow not in VALID_WORKFLOWS:
        raise ValueError(
            f"Unknown workflow: {workflow}. "
            f"Valid workflows: {sorted(VALID_WORKFLOWS)}"
        )


@dataclass
class AnalysisRequest:
    """A single analysis workflow request."""

    id: str
    workflow: str
    arguments: dict[str, Any]
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "workflow": self.workflow,
            "arguments": self.arguments,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }


class AnalysisStore:
    """In-memory store for analysis requests with TTL expiration."""

    def __init__(self, ttl_minutes: int = 60) -> None:
        self._store: dict[str, AnalysisRequest] = {}
        self._ttl_seconds = ttl_minutes * 60

    def create(
        self, workflow: str, arguments: dict[str, Any]
    ) -> AnalysisRequest:
        """Create a new analysis request.

        Args:
            workflow: Workflow name.
            arguments: Workflow arguments.

        Returns:
            The created AnalysisRequest.
        """
        analysis_id = str(uuid.uuid4())
        req = AnalysisRequest(
            id=analysis_id,
            workflow=workflow,
            arguments=arguments,
        )
        self._store[analysis_id] = req
        return req

    def get(self, analysis_id: str) -> AnalysisRequest | None:
        """Get an analysis request by ID.

        Args:
            analysis_id: The analysis ID.

        Returns:
            AnalysisRequest or None if not found.
        """
        return self._store.get(analysis_id)

    def update(
        self,
        analysis_id: str,
        status: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update an analysis request.

        Args:
            analysis_id: The analysis ID.
            status: New status value.
            result: Analysis result data.
            error: Error message.
        """
        req = self._store.get(analysis_id)
        if req is None:
            return

        if status is not None:
            req.status = status
        if result is not None:
            req.result = result
        if error is not None:
            req.error = error
        if status in ("completed", "failed"):
            req.completed_at = time.time()

    def cleanup_expired(self) -> int:
        """Remove expired entries past TTL.

        Returns:
            Number of entries removed.
        """
        now = time.time()
        expired = [
            aid
            for aid, req in self._store.items()
            if (now - req.created_at) > self._ttl_seconds
        ]
        for aid in expired:
            del self._store[aid]
        return len(expired)

    def list_recent(self, limit: int = 20) -> list[AnalysisRequest]:
        """List recent analysis requests, most recent first.

        Args:
            limit: Maximum entries to return.

        Returns:
            List of AnalysisRequest objects.
        """
        items = sorted(
            self._store.values(),
            key=lambda r: r.created_at,
            reverse=True,
        )
        return items[:limit]


async def run_analysis(
    store: AnalysisStore, analysis_id: str
) -> None:
    """Execute an analysis workflow asynchronously.

    Updates the store with running/completed/failed status.

    Args:
        store: The analysis store.
        analysis_id: The analysis request ID to execute.
    """
    req = store.get(analysis_id)
    if req is None:
        return

    store.update(analysis_id, status="running")

    try:
        from lm_mcp.server import execute_tool

        result = await _dispatch_workflow(
            req.workflow, req.arguments, execute_tool
        )
        store.update(analysis_id, status="completed", result=result)
    except Exception as e:
        logger.exception("Analysis %s failed", analysis_id)
        store.update(analysis_id, status="failed", error=str(e))


async def _dispatch_workflow(
    workflow: str,
    arguments: dict[str, Any],
    execute_tool: Any,
) -> dict[str, Any]:
    """Dispatch to the appropriate workflow function.

    Args:
        workflow: Workflow name.
        arguments: Workflow arguments.
        execute_tool: Tool execution function.

    Returns:
        Workflow result dict.
    """
    dispatchers = {
        "alert_correlation": _run_alert_correlation,
        "rca_workflow": _run_rca_workflow,
        "top_talkers": _run_top_talkers,
        "health_check": _run_health_check,
    }

    func = dispatchers.get(workflow)
    if func is None:
        raise ValueError(f"Unknown workflow: {workflow}")

    return await func(arguments, execute_tool)


async def _extract_result(execute_tool: Any, tool_name: str, args: dict) -> Any:
    """Call a tool and extract the text result.

    Args:
        execute_tool: Tool execution function.
        tool_name: Tool name.
        args: Tool arguments.

    Returns:
        Parsed JSON result or raw text.
    """
    import json

    result = await execute_tool(tool_name, args)
    if result and len(result) > 0:
        text = result[0].text
        try:
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return text
    return None


async def _run_alert_correlation(
    arguments: dict[str, Any], execute_tool: Any
) -> dict[str, Any]:
    """Run alert correlation workflow."""
    hours = arguments.get("hours_back", 4)
    correlation = await _extract_result(
        execute_tool, "correlate_alerts", {"hours_back": hours}
    )
    stats = await _extract_result(
        execute_tool, "get_alert_statistics", {"hours_back": hours}
    )
    return {
        "workflow": "alert_correlation",
        "correlation": correlation,
        "statistics": stats,
    }


async def _run_rca_workflow(
    arguments: dict[str, Any], execute_tool: Any
) -> dict[str, Any]:
    """Run root cause analysis workflow."""
    hours = arguments.get("hours_back", 4)
    device_id = arguments.get("device_id")

    correlation = await _extract_result(
        execute_tool, "correlate_alerts", {"hours_back": hours}
    )

    neighbors = None
    if device_id:
        neighbors = await _extract_result(
            execute_tool, "get_device_neighbors", {"device_id": device_id}
        )

    changes = await _extract_result(
        execute_tool, "get_change_audit", {"limit": 20}
    )

    return {
        "workflow": "rca_workflow",
        "correlation": correlation,
        "topology": neighbors,
        "recent_changes": changes,
    }


async def _run_top_talkers(
    arguments: dict[str, Any], execute_tool: Any
) -> dict[str, Any]:
    """Run top talkers workflow."""
    hours = arguments.get("hours_back", 24)
    stats = await _extract_result(
        execute_tool, "get_alert_statistics", {"hours_back": hours}
    )
    return {
        "workflow": "top_talkers",
        "statistics": stats,
    }


async def _run_health_check(
    arguments: dict[str, Any], execute_tool: Any
) -> dict[str, Any]:
    """Run health check workflow."""
    alerts = await _extract_result(
        execute_tool, "get_alerts", {"limit": 50}
    )
    devices = await _extract_result(
        execute_tool, "get_devices", {"limit": 50}
    )
    collectors = await _extract_result(
        execute_tool, "get_collectors", {"limit": 50}
    )
    return {
        "workflow": "health_check",
        "alerts": alerts,
        "devices": devices,
        "collectors": collectors,
    }
