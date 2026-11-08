# Description: Tests for validate_auth, the one place credentials become an auth provider.
# Description: Bearer first, else an LMv1 pair, else ConfigurationError; no other builder in src.

import ast
from pathlib import Path

import pytest

from lm_mcp.auth import validate_auth
from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.auth.lmv1 import LMv1Auth
from lm_mcp.exceptions import ConfigurationError

SRC = Path(__file__).resolve().parent.parent.parent / "src" / "lm_mcp"


class TestValidateAuth:
    """Tests for the validate_auth credential selection."""

    def test_bearer_token_gives_bearer_auth(self):
        auth = validate_auth("test_token_12345", None, None)

        assert isinstance(auth, BearerAuth)
        assert auth.get_auth_headers("GET", "/alert/alerts") == {
            "Authorization": "Bearer test_token_12345"
        }

    def test_bearer_wins_over_an_lmv1_pair(self):
        assert isinstance(validate_auth("test_token_12345", "id", "key"), BearerAuth)

    def test_lmv1_pair_gives_lmv1_auth(self):
        auth = validate_auth(None, "id", "key")

        assert isinstance(auth, LMv1Auth)
        assert (auth.access_id, auth.access_key) == ("id", "key")

    @pytest.mark.parametrize(
        ("token", "access_id", "access_key"),
        [(None, None, None), ("", "", ""), (None, "id", None), (None, None, "key")],
    )
    def test_no_complete_credential_is_refused(self, token, access_id, access_key):
        with pytest.raises(ConfigurationError, match="LM_BEARER_TOKEN"):
            validate_auth(token, access_id, access_key)

    def test_providers_are_built_only_in_validate_auth(self):
        """BearerAuth and LMv1Auth are constructed in one function across src/lm_mcp."""
        builders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            tree = ast.parse(path.read_text())
            for func in ast.walk(tree):
                if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for node in ast.walk(func):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in {"BearerAuth", "LMv1Auth"}
                    ):
                        builders.append(f"{path.relative_to(SRC)}:{func.name}")

        assert sorted(set(builders)) == ["auth/__init__.py:validate_auth"]
