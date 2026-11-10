# Description: Invariant tests binding every tool's inputSchema to its handler signature (R1.3).
# Description: A tool is callable per its schema: required params are required, properties accepted.

import inspect

import pytest

from lm_mcp.registry import TOOLS, get_tool_handler
from lm_mcp.server import PORTAL_TOOLS, SESSION_TOOLS

ALL_TOOLS = list(TOOLS)

_NAMED = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)


def _caller_params(tool_name: str) -> list[inspect.Parameter]:
    """Return the handler parameters the caller fills from tool arguments.

    execute_tool passes the LM client as the first positional argument, except for
    session and portal tools, which receive the arguments alone.
    """
    params = list(inspect.signature(get_tool_handler(tool_name)).parameters.values())
    if tool_name in SESSION_TOOLS or tool_name in PORTAL_TOOLS:
        return params
    return params[1:]


def test_invariant_covers_every_registered_tool():
    """The parametrized invariant runs over the full tool surface, one case per tool."""
    names = [t.name for t in ALL_TOOLS]
    assert len(names) == len(set(names))
    assert len(names) >= 236


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=lambda t: t.name)
def test_tool_is_callable_per_its_schema(tool):
    """Every handler parameter without a default is required; every property is accepted."""
    params = _caller_params(tool.name)
    schema_required = set(tool.inputSchema.get("required", []))
    properties = set(tool.inputSchema.get("properties", {}))

    required_params = {
        p.name for p in params if p.kind in _NAMED and p.default is inspect.Parameter.empty
    }
    assert required_params <= schema_required, (
        f"{tool.name}: handler requires {sorted(required_params - schema_required)} "
        "but the schema does not list them as required"
    )

    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return
    named = {p.name for p in params if p.kind in _NAMED}
    assert properties <= named, (
        f"{tool.name}: schema properties {sorted(properties - named)} "
        "are not handler parameters and the handler takes no **kwargs"
    )


# The JSON Schema type each handler annotation declares; an annotation outside this
# map (Any, a Literal, a union of two types) is not judged.
_JSON_TYPES = {
    "str": "string",
    "int": "integer",
    "bool": "boolean",
    "float": "number",
    "list": "array",
    "dict": "object",
}


def _json_type(annotation: object) -> str | None:
    """The JSON type of a handler annotation string such as 'int | None' or 'list[str]'."""
    if not isinstance(annotation, str):
        return None
    parts = [part.strip() for part in annotation.split("|") if part.strip() != "None"]
    if len(parts) != 1:
        return None
    return _JSON_TYPES.get(parts[0].split("[")[0])


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=lambda t: t.name)
def test_every_handler_parameter_is_declared_with_its_type(tool):
    """R2.9: no hidden parameter, and each declared type is the handler's annotation."""
    properties = tool.inputSchema.get("properties", {})

    for param in _caller_params(tool.name):
        if param.kind not in _NAMED:
            continue
        assert param.name in properties, f"{tool.name}.{param.name} is not in the schema"
        expected = _json_type(param.annotation)
        if expected is not None:
            declared = properties[param.name].get("type")
            assert declared == expected, (
                f"{tool.name}.{param.name}: annotation {param.annotation}, schema {declared}"
            )
