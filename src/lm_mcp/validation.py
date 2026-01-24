# Description: Field validation module for LogicMonitor MCP server.
# Description: Validates field names against API schemas to prevent invalid requests.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of field validation."""

    valid: bool
    invalid_fields: list[str] = field(default_factory=list)
    suggestions: dict[str, list[str]] = field(default_factory=dict)
    valid_field_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for response formatting."""
        result = {"valid": self.valid}
        if not self.valid:
            result["invalid_fields"] = self.invalid_fields
            result["suggestions"] = self.suggestions
            result["valid_fields"] = self.valid_field_names
        return result


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Integer edit distance
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def find_similar_fields(
    field_name: str, valid_fields: set[str], max_results: int = 3, max_distance: int = 4
) -> list[str]:
    """Find valid field names similar to the given invalid field.

    Args:
        field_name: The invalid field name to find matches for
        valid_fields: Set of valid field names
        max_results: Maximum number of suggestions to return
        max_distance: Maximum Levenshtein distance for a match

    Returns:
        List of similar valid field names, sorted by similarity
    """
    # Calculate distances
    distances = []
    field_lower = field_name.lower()

    for valid in valid_fields:
        valid_lower = valid.lower()

        # Exact match (case-insensitive)
        if field_lower == valid_lower:
            return [valid]

        # Prefix match
        if valid_lower.startswith(field_lower) or field_lower.startswith(valid_lower):
            distances.append((valid, 0))
            continue

        # Contains match
        if field_lower in valid_lower or valid_lower in field_lower:
            distances.append((valid, 1))
            continue

        # Levenshtein distance
        dist = levenshtein_distance(field_lower, valid_lower)
        if dist <= max_distance:
            distances.append((valid, dist))

    # Sort by distance and return top matches
    distances.sort(key=lambda x: x[1])
    return [f for f, _ in distances[:max_results]]


def get_schema_fields(resource_type: str) -> set[str] | None:
    """Get valid field names for a resource type.

    Args:
        resource_type: Resource type (e.g., "devices", "alerts", "sdts")

    Returns:
        Set of valid field names, or None if schema not found
    """
    from lm_mcp.resources.schemas import ALL_SCHEMAS

    schema = ALL_SCHEMAS.get(resource_type)
    if not schema:
        return None

    fields = schema.get("fields", {})
    return set(fields.keys())


def infer_resource_type(tool_name: str) -> str | None:
    """Infer the resource type from a tool name.

    Args:
        tool_name: Name of the tool (e.g., "get_devices", "get_alerts")

    Returns:
        Resource type string or None if not determinable
    """
    # Map tool name patterns to resource types
    patterns = {
        "device": "devices",
        "alert": "alerts",
        "sdt": "sdts",
        "collector": "collectors",
        "dashboard": "dashboards",
        "website": "websites",
        "user": "users",
    }

    tool_lower = tool_name.lower()
    for pattern, resource_type in patterns.items():
        if pattern in tool_lower:
            return resource_type

    return None


def validate_fields(
    resource_type: str,
    fields: list[str] | str,
) -> ValidationResult:
    """Validate field names against the schema for a resource type.

    Args:
        resource_type: Resource type (e.g., "devices", "alerts")
        fields: List of field names or comma-separated string to validate

    Returns:
        ValidationResult with valid status and suggestions for invalid fields
    """
    # Handle string input
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(",") if f.strip()]

    # Get valid fields for this resource type
    valid_fields = get_schema_fields(resource_type)
    if valid_fields is None:
        # No schema available - can't validate
        return ValidationResult(valid=True)

    # Check each provided field
    provided = set(fields)
    invalid = provided - valid_fields

    if not invalid:
        return ValidationResult(valid=True, valid_field_names=sorted(valid_fields))

    # Find suggestions for invalid fields
    suggestions = {}
    for inv in invalid:
        similar = find_similar_fields(inv, valid_fields)
        if similar:
            suggestions[inv] = similar

    return ValidationResult(
        valid=False,
        invalid_fields=sorted(invalid),
        suggestions=suggestions,
        valid_field_names=sorted(valid_fields),
    )


def validate_filter_fields(
    resource_type: str,
    filter_string: str,
) -> ValidationResult:
    """Validate field names in a filter expression.

    Parses filter strings like "field1:value,field2~value" and validates
    the field names against the schema.

    Args:
        resource_type: Resource type (e.g., "devices", "alerts")
        filter_string: Filter expression string

    Returns:
        ValidationResult with valid status and suggestions for invalid fields
    """
    import re

    # Parse filter to extract field names
    # Matches: field:value, field~value, field>value, field<value
    pattern = r"([a-zA-Z_][a-zA-Z0-9_.]*)\s*[:<>~!]"
    matches = re.findall(pattern, filter_string)

    if not matches:
        return ValidationResult(valid=True)

    return validate_fields(resource_type, matches)
