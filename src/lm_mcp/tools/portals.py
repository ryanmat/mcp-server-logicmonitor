# Description: Multi-portal switching tools for the LogicMonitor MCP server.
# Description: list_portals / use_portal / current_portal let one server target many
# customer portals, selecting the active one at runtime. Credentials come from the
# portal registry (age vault); no token is ever returned by these tools.
from __future__ import annotations

from mcp.types import TextContent

from lm_mcp import portals
from lm_mcp.tools import format_response, handle_error


async def list_portals() -> list[TextContent]:
    """List the customer portals available in this multi-portal server."""
    try:
        rows = portals.names()
        return format_response({"count": len(rows), "portals": rows})
    except Exception as e:
        return handle_error(e)


async def use_portal(customer: str) -> list[TextContent]:
    """Switch the active customer portal for subsequent tool calls."""
    try:
        return format_response(portals.activate(customer))
    except (ValueError, RuntimeError) as e:
        return format_response({"error": True, "message": str(e)})
    except Exception as e:
        return handle_error(e)


async def current_portal() -> list[TextContent]:
    """Show which customer portal is currently active."""
    try:
        return format_response(portals.active())
    except Exception as e:
        return handle_error(e)


async def reload_portals() -> list[TextContent]:
    """Re-read the vault so portals added/removed since startup take effect (no restart)."""
    try:
        return format_response(portals.reload())
    except (ValueError, RuntimeError) as e:
        return format_response({"error": True, "message": str(e)})
    except Exception as e:
        return handle_error(e)
