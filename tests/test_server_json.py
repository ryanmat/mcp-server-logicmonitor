# Description: Parity tests between server.json, the MCP Registry manifest, and the code.
# Description: Env vars against the settings models, versions, the server identity, schema limits.

from __future__ import annotations

import json
import tomllib
import typing
from pathlib import Path

from pydantic_settings import BaseSettings

from lm_mcp import __version__
from lm_mcp.config import LMConfig
from lm_mcp.edwin_config import EdwinConfig

ROOT = Path(__file__).parent.parent
SERVER_JSON = json.loads((ROOT / "server.json").read_text())
PACKAGE = SERVER_JSON["packages"][0]
ENTRIES = {entry["name"]: entry for entry in PACKAGE["environmentVariables"]}

# Settings fields whose values are credentials; clients store an isSecret input securely.
SECRET_FIELDS = {
    "LM_BEARER_TOKEN",
    "LM_ACCESS_KEY",
    "LM_HTTP_AUTH_TOKEN",
    "LM_HTTP_SSL_KEYFILE_PASSWORD",
    "EDWIN_CLIENT_TOKEN",
}
# Settings fields that name a file on the user's filesystem.
PATH_FIELDS = {
    "LM_VAULT_FILE",
    "LM_AGE_KEY",
    "LM_PORTALS_FILE",
    "LM_HTTP_SSL_CERTFILE",
    "LM_HTTP_SSL_KEYFILE",
}


def _settings_fields() -> dict[str, tuple[type[BaseSettings], str]]:
    """Every env var the server reads, mapped to its settings model and field name."""
    fields: dict[str, tuple[type[BaseSettings], str]] = {}
    for model in (LMConfig, EdwinConfig):
        prefix = model.model_config["env_prefix"]
        for name in model.model_fields:
            fields[f"{prefix}{name}".upper()] = (model, name)
    return fields


def _annotation(env_name: str) -> object:
    model, name = _settings_fields()[env_name]
    return model.model_fields[name].annotation


def _default(env_name: str) -> object:
    model, name = _settings_fields()[env_name]
    return model.model_fields[name].default


def _as_input_string(value: object) -> str:
    """A settings default in the registry's input form: booleans as true and false."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def test_lists_every_env_var_the_settings_read() -> None:
    missing = set(_settings_fields()) - set(ENTRIES)
    assert not missing, f"server.json lacks settings env vars: {sorted(missing)}"


def test_lists_no_env_var_the_settings_do_not_read() -> None:
    extra = set(ENTRIES) - set(_settings_fields())
    assert not extra, f"server.json lists env vars no settings field reads: {sorted(extra)}"


def test_env_var_names_are_unique() -> None:
    names = [entry["name"] for entry in PACKAGE["environmentVariables"]]
    assert len(names) == len(set(names))


def test_every_env_var_has_a_description() -> None:
    assert all(entry.get("description") for entry in ENTRIES.values())


def test_defaults_match_the_settings() -> None:
    """Every field with a non-empty default states it; every stated default is the field's."""
    for env_name in _settings_fields():
        default = _default(env_name)
        if default is None or default == "":
            assert "default" not in ENTRIES[env_name], env_name
        else:
            assert ENTRIES[env_name].get("default") == _as_input_string(default), env_name


def test_choices_match_the_literal_settings() -> None:
    for env_name in _settings_fields():
        annotation = _annotation(env_name)
        if typing.get_origin(annotation) is typing.Literal:
            assert ENTRIES[env_name].get("choices") == list(typing.get_args(annotation)), env_name
        else:
            assert "choices" not in ENTRIES[env_name], env_name


def test_formats_follow_the_field_types() -> None:
    for env_name in _settings_fields():
        annotation = _annotation(env_name)
        if annotation is bool:
            expected = "boolean"
        elif annotation is int:
            expected = "number"
        elif env_name in PATH_FIELDS:
            expected = "filepath"
        else:
            expected = "string"
        assert ENTRIES[env_name].get("format", "string") == expected, env_name


def test_credentials_are_secret_and_nothing_else_is() -> None:
    secret = {name for name, entry in ENTRIES.items() if entry.get("isSecret", False)}
    assert secret == SECRET_FIELDS


def test_versions_match_pyproject_and_the_package() -> None:
    with (ROOT / "pyproject.toml").open("rb") as f:
        pyproject_version = tomllib.load(f)["project"]["version"]
    assert SERVER_JSON["version"] == pyproject_version == __version__
    assert PACKAGE["version"] == pyproject_version


def test_name_matches_the_server_identity() -> None:
    """The registry name's server segment is the name clients read at initialize."""
    from lm_mcp.server import server

    namespace, _, server_name = SERVER_JSON["name"].partition("/")
    assert namespace == "io.github.ryanmat"
    assert server_name == server.name


def test_package_is_this_pypi_project() -> None:
    with (ROOT / "pyproject.toml").open("rb") as f:
        project_name = tomllib.load(f)["project"]["name"]
    assert PACKAGE["registryType"] == "pypi"
    assert PACKAGE["identifier"] == project_name


def test_readme_carries_the_pypi_ownership_line() -> None:
    """The registry verifies a PyPI package by this line in the README PyPI shows."""
    readme = (ROOT / "README.md").read_text()
    assert f"<!-- mcp-name: {SERVER_JSON['name']} -->" in readme


def test_description_fits_the_registry_schema() -> None:
    """The 2025-12-11 server schema caps the description at 100 characters."""
    assert SERVER_JSON["$schema"].endswith("/2025-12-11/server.schema.json")
    assert 1 <= len(SERVER_JSON["description"]) <= 100
