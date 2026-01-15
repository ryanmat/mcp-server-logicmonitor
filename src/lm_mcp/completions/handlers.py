# Description: Completion handler for MCP auto-complete requests.
# Description: Provides fuzzy matching for tool argument values.

from __future__ import annotations

from mcp.types import Completion

from lm_mcp.completions.registry import get_completion_values


def get_completions(argument_name: str, prefix: str) -> Completion:
    """Get auto-complete suggestions for an argument value.

    Supports prefix matching and contains matching for flexibility.
    Matching is case-insensitive.

    Args:
        argument_name: The name of the argument being completed.
        prefix: The partial value typed by the user.

    Returns:
        Completion object with matching values.
    """
    all_values = get_completion_values(argument_name)

    if not all_values:
        return Completion(values=[], total=0, hasMore=False)

    # Filter values by prefix (case-insensitive)
    prefix_lower = prefix.lower()
    matching = []

    for value in all_values:
        value_lower = value.lower()
        # Match if value starts with prefix or contains prefix
        if value_lower.startswith(prefix_lower) or prefix_lower in value_lower:
            matching.append(value)

    return Completion(
        values=matching,
        total=len(matching),
        hasMore=False,
    )
