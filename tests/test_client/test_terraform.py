# Description: Tests for the Terraform subprocess runner's environment handling.
# Description: Runs a real child process that reports the environment it received.

import json
import sys

import pytest

from lm_mcp.client.terraform import TerraformRunner

# Stands in for the terraform binary: prints the environment the runner passed.
_PRINT_ENV = ["-c", "import json, os; print(json.dumps(dict(os.environ)))"]

_SERVER_SECRETS = {
    "LM_BEARER_TOKEN": "lm-bearer-secret",
    "AWX_TOKEN": "awx-secret",
    "WATSONX_API_KEY": "watsonx-secret",
    "LM_HTTP_AUTH_TOKEN": "inbound-secret",
    "DATABASE_URL": "postgres://user:pw@db/x",
}


async def _child_env(tmp_path, env_extra=None) -> dict[str, str]:
    runner = TerraformRunner(workspace_dir=str(tmp_path), terraform_binary=sys.executable)
    result = await runner.run(_PRINT_ENV, "ws", env_extra=env_extra)
    assert result.exit_code == 0, result.stderr
    return json.loads(result.stdout)


class TestRunnerEnvironment:
    """R3.4: the Terraform subprocess gets an allowlisted environment, not os.environ."""

    @pytest.mark.asyncio
    async def test_server_secrets_do_not_reach_the_subprocess(self, tmp_path, monkeypatch):
        """Credentials in the server's environment are not inherited by terraform."""
        for name, value in _SERVER_SECRETS.items():
            monkeypatch.setenv(name, value)

        env = await _child_env(tmp_path)

        leaked = sorted(set(_SERVER_SECRETS) & set(env))
        assert leaked == []

    @pytest.mark.asyncio
    async def test_allowlisted_variables_pass_through(self, tmp_path, monkeypatch):
        """PATH, HOME, TMPDIR and TF_* from the server env reach the subprocess."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        monkeypatch.setenv("TF_VAR_region", "us-east-1")
        monkeypatch.setenv("TF_LOG", "INFO")

        env = await _child_env(tmp_path)

        assert env["PATH"]
        assert env["HOME"] == str(tmp_path)
        assert env["TMPDIR"] == str(tmp_path)
        assert env["TF_VAR_region"] == "us-east-1"
        assert env["TF_LOG"] == "INFO"
        assert env["TF_INPUT"] == "false"
        assert env["TF_IN_AUTOMATION"] == "true"

    @pytest.mark.asyncio
    async def test_env_extra_reaches_the_subprocess(self, tmp_path, monkeypatch):
        """Provider variables the caller passes in env_extra are set explicitly."""
        monkeypatch.setenv("LM_BEARER_TOKEN", "lm-bearer-secret")
        extra = {
            "LM_API_ID": "id",
            "LM_API_KEY": "key",
            "LM_COMPANY": "acme",
            "TF_VAR_lm_api_id": "id",
        }

        env = await _child_env(tmp_path, env_extra=extra)

        for name, value in extra.items():
            assert env[name] == value
        assert "LM_BEARER_TOKEN" not in env
