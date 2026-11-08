# Description: Tests for the documented error code set (spec R2.7) and the mapping onto it.
# Description: Covers the code table, lm_error_code, and the code at every handler error site.

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from lm_mcp.exceptions import (
    AuthenticationError,
    ConfigurationError,
    LMError,
    LMPermissionError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from lm_mcp.tools import ERROR_CODES, lm_error_code
from tests.envelope import CATEGORIES, DOCUMENTED_CODES, client_raised

TOOLS_DIR = Path(__file__).resolve().parent.parent / "src" / "lm_mcp" / "tools"

LM_ERROR_CODES = [
    pytest.param(NotFoundError("Device 7 not found"), "NOT_FOUND", id="404"),
    pytest.param(
        ValidationError("filter value has a bare comma"), "INVALID_REQUEST", id="validation"
    ),
    pytest.param(LMError("Bad field", code="HTTP_400"), "INVALID_REQUEST", id="other-4xx"),
    pytest.param(RateLimitError("Too many requests", retry_after=30), "RATE_LIMITED", id="429"),
    pytest.param(ServerError("Internal error"), "UPSTREAM_ERROR", id="5xx"),
    pytest.param(
        LMError("body error", code="API_ERROR_1007"), "INVALID_REQUEST", id="200-errorCode"
    ),
    pytest.param(LMError("body error", code="API_ERROR"), "INVALID_REQUEST", id="200-errorMessage"),
    pytest.param(
        LMError("ingest rejected", code="INGEST_PARTIAL_FAILURE"), "UPSTREAM_ERROR", id="other"
    ),
    pytest.param(client_raised(httpx.ReadTimeout("")), "TIMEOUT", id="client-timeout"),
    pytest.param(
        client_raised(httpx.ConnectError("refused")), "UPSTREAM_ERROR", id="connect-failed"
    ),
    pytest.param(AuthenticationError("Invalid token"), "AUTH_FAILED", id="401"),
    pytest.param(LMPermissionError("Permission denied"), "AUTH_FAILED", id="403"),
    pytest.param(ConfigurationError("ingest needs LMv1 keys"), "FEATURE_DISABLED", id="config"),
]


@pytest.mark.parametrize(("error", "code"), LM_ERROR_CODES)
def test_lm_error_code_maps_onto_the_set(error, code):
    assert lm_error_code(error) == code


class TestCodeTable:
    def test_table_documents_exactly_the_set(self):
        assert set(ERROR_CODES) == DOCUMENTED_CODES

    def test_categories_follow_the_house_rule(self):
        for code, (category, retryable) in ERROR_CODES.items():
            assert category in CATEGORIES, code
            assert retryable is (category == "transient"), code


def _error_code_sites() -> list[tuple[str, int, ast.expr]]:
    """Every validation_error call and every handler error dict in the handler modules.

    The helpers in ``__init__.py`` build the dict from their own ``code`` argument;
    their callers are the sites walked here.
    """
    sites: list[tuple[str, int, ast.expr]] = []
    for path in sorted(TOOLS_DIR.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name == "validation_error":
                    code = node.args[0] if node.args else None
                    for keyword in node.keywords:
                        if keyword.arg == "code":
                            code = keyword.value
                    assert code is not None, f"{path.name}:{node.lineno} passes no code"
                    sites.append((path.name, node.lineno, code))
            if isinstance(node, ast.Dict):
                keys = {
                    k.value: v
                    for k, v in zip(node.keys, node.values, strict=True)
                    if isinstance(k, ast.Constant)
                }
                # A handler's error dict is the one whose "error" is True; per-item
                # failures inside a result carry the error text there instead.
                error = keys.get("error")
                if isinstance(error, ast.Constant) and error.value is True:
                    code = keys.get("code", ast.Constant(None))
                    sites.append((path.name, node.lineno, code))
    return sites


def test_every_handler_error_site_passes_a_documented_code():
    sites = _error_code_sites()

    assert len(sites) > 70, "the walk lost the handler error dicts"
    wrong = [
        f"{name}:{line} {ast.unparse(code)}"
        for name, line, code in sites
        if not (isinstance(code, ast.Constant) and code.value in DOCUMENTED_CODES)
        and not _maps_an_lm_error(code)
    ]
    assert wrong == []


def _maps_an_lm_error(code: ast.expr) -> bool:
    """A code computed by lm_error_code, whose every return the cases above pin to the set."""
    return (
        isinstance(code, ast.Call)
        and isinstance(code.func, ast.Name)
        and code.func.id == "lm_error_code"
    )
