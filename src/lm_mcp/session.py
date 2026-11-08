# Description: In-memory session state: user variables and recent tool call history.
# Description: One session per portal, held by the process alone and lost when it exits.

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from lm_mcp.context import current_binding

logger = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    """A single entry in the tool call history."""

    tool_name: str
    timestamp: str
    arguments: dict[str, Any]
    success: bool
    result_summary: str | None = None


@dataclass
class SessionContext:
    """Per-session state, held in memory.

    Stores:
    - User-defined variables for cross-tool state
    - Recent tool call history for context

    Thread Safety:
        This implementation is NOT thread-safe. Each session should have
        its own SessionContext instance.
    """

    # User-defined variables
    variables: dict[str, Any] = field(default_factory=dict)

    # Tool call history (circular buffer)
    history: list[HistoryEntry] = field(default_factory=list)
    max_history_size: int = 50

    def record_result(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        success: bool = True,
    ) -> None:
        """Record a tool result for future reference.

        Args:
            tool_name: Name of the tool that was called
            arguments: Arguments passed to the tool
            result: The result returned by the tool
            success: Whether the tool call succeeded
        """
        # Add to history
        summary = self._summarize_result(result) if success else None
        entry = HistoryEntry(
            tool_name=tool_name,
            timestamp=datetime.now(UTC).isoformat(),
            arguments=arguments,
            success=success,
            result_summary=summary,
        )
        self.history.append(entry)

        # Trim history if needed
        if len(self.history) > self.max_history_size:
            self.history = self.history[-self.max_history_size :]

    def _summarize_result(self, result: Any) -> str | None:
        """Create a brief summary of a result for history display."""
        if not isinstance(result, dict):
            return None

        # Count items if it's a list result
        items = result.get("items", result.get("data"))
        if isinstance(items, list):
            return f"{len(items)} items"

        # Get ID and name for singular results
        item = result.get("item", result.get("data", result))
        if isinstance(item, dict):
            item_id = item.get("id")
            name = item.get("name", item.get("displayName", item.get("alertId")))
            if item_id and name:
                return f"id={item_id}, name={name}"
            elif item_id:
                return f"id={item_id}"
            elif name:
                return f"name={name}"

        return None

    def set_variable(self, name: str, value: Any) -> None:
        """Set a user-defined variable.

        Args:
            name: Variable name
            value: Variable value (must be JSON-serializable)
        """
        self.variables[name] = value

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a user-defined variable.

        Args:
            name: Variable name
            default: Default value if variable not found

        Returns:
            Variable value or default
        """
        return self.variables.get(name, default)

    def delete_variable(self, name: str) -> bool:
        """Delete a user-defined variable.

        Args:
            name: Variable name

        Returns:
            True if variable was deleted, False if it didn't exist
        """
        if name in self.variables:
            del self.variables[name]
            return True
        return False

    def clear(self) -> None:
        """Reset all session state."""
        # Clear variables and history
        self.variables = {}
        self.history = []

    def to_dict(self) -> dict[str, Any]:
        """Convert session context to dictionary for serialization.

        Returns:
            Dictionary representation of session state
        """
        return {
            "variables": self.variables,
            "history": [
                {
                    "tool": e.tool_name,
                    "timestamp": e.timestamp,
                    "success": e.success,
                    "summary": e.result_summary,
                }
                for e in self.history[-10:]  # Last 10 entries only
            ],
            "history_count": len(self.history),
        }


# The process's session contexts, one per portal name (spec R2.12). The key None is
# the one session of single-portal mode, and in multi-portal mode the session of the
# calls made before use_portal.
_sessions: dict[str | None, SessionContext] = {}

# History length for every session, set from LM_SESSION_HISTORY_SIZE at startup
_history_size: int = SessionContext.max_history_size


def set_history_size(size: int) -> None:
    """Set the history length of every session, those that exist and those to come."""
    global _history_size
    _history_size = size
    for session in _sessions.values():
        session.max_history_size = size


def get_session() -> SessionContext:
    """Get the session of the running call's portal, creating it if needed.

    In single-portal mode every caller shares one session, inside a tool call or not.

    Returns:
        The SessionContext for the bound portal.

    Raises:
        RuntimeError: In multi-portal mode, outside a tool call.
    """
    key = _session_key()
    session = _sessions.get(key)
    if session is None:
        session = _sessions[key] = SessionContext(max_history_size=_history_size)
    return session


def _session_key() -> str | None:
    """The bound portal's name; outside a call, the single-portal key None."""
    try:
        return current_binding().portal
    except RuntimeError:
        multi = False
        try:
            from lm_mcp.config import get_config

            multi = get_config().multi_portal
        except Exception:
            logger.debug("config unavailable; using the single-portal session", exc_info=True)
        if multi:
            raise
        return None
