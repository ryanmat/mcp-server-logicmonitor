# Description: Terraform CLI subprocess runner for Infrastructure as Code workflows.
# Description: Manages workspace directories and executes terraform commands.

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from lm_mcp.exceptions import LMError

logger = logging.getLogger(__name__)


@dataclass
class TerraformResult:
    """Result from a terraform CLI invocation.

    Attributes:
        exit_code: Process exit code (0=success, 1=error, 2=changes pending for plan).
        stdout: Standard output from the terraform process.
        stderr: Standard error from the terraform process.
    """

    exit_code: int
    stdout: str
    stderr: str


class TerraformRunner:
    """Async subprocess wrapper for the Terraform CLI.

    Manages workspace directories under a root directory, executes terraform
    commands with configurable timeouts, and passes credentials via environment
    variables (never written to disk).
    """

    def __init__(
        self,
        workspace_dir: str,
        terraform_binary: str = "terraform",
        timeout: int = 300,
        auto_approve_enabled: bool = False,
    ):
        """Initialize the Terraform runner.

        Args:
            workspace_dir: Root directory for Terraform workspaces.
            terraform_binary: Path to the terraform binary.
            timeout: Command timeout in seconds.
            auto_approve_enabled: Whether terraform apply/destroy are allowed.
        """
        self.workspace_dir = Path(workspace_dir).resolve()
        self.terraform_binary = terraform_binary
        self.timeout = timeout
        self.auto_approve_enabled = auto_approve_enabled

    def workspace_path(self, workspace: str) -> Path:
        """Resolve a workspace name to a directory path with traversal guard.

        Args:
            workspace: Workspace name (becomes a subdirectory under workspace_dir).

        Returns:
            Resolved absolute path to the workspace directory.

        Raises:
            ValueError: If the resolved path escapes the workspace root.
        """
        resolved = (self.workspace_dir / workspace).resolve()
        if not resolved.is_relative_to(self.workspace_dir):
            raise ValueError(
                f"Invalid workspace name '{workspace}': resolved path escapes workspace root"
            )
        return resolved

    async def run(
        self,
        args: list[str],
        workspace: str,
        env_extra: dict[str, str] | None = None,
    ) -> TerraformResult:
        """Execute a terraform command in a workspace directory.

        Creates the workspace subdirectory if it does not exist. Passes
        env_extra variables (typically LM credentials as TF_VAR_*) into the
        subprocess environment without writing them to disk.

        Args:
            args: Terraform subcommand and flags (e.g., ["plan", "-json"]).
            workspace: Workspace name (subdirectory of workspace_dir).
            env_extra: Additional environment variables for the subprocess.

        Returns:
            TerraformResult with exit code, stdout, and stderr.

        Raises:
            LMError: If the terraform binary is not found or the command times out.
            ValueError: If the workspace name fails path traversal validation.
        """
        ws_path = self.workspace_path(workspace)
        ws_path.mkdir(parents=True, exist_ok=True)

        # Build subprocess environment from current env plus extras
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)

        # Disable interactive prompts and color codes
        env["TF_INPUT"] = "false"
        env["TF_IN_AUTOMATION"] = "true"

        cmd = [self.terraform_binary, *args]
        logger.debug("terraform %s in %s", " ".join(args), ws_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(ws_path),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise LMError(
                message=f"Terraform binary '{self.terraform_binary}' not found",
                code="TERRAFORM_NOT_FOUND",
                suggestion=("Install Terraform: https://developer.hashicorp.com/terraform/install"),
            ) from exc
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise LMError(
                message=(f"Terraform command timed out after {self.timeout}s: {' '.join(args)}"),
                code="TERRAFORM_TIMEOUT",
                suggestion=(
                    f"Increase TF_TIMEOUT (current: {self.timeout}s) or simplify the configuration."
                ),
            ) from None

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        logger.debug(
            "terraform exit=%d stdout=%d bytes stderr=%d bytes",
            proc.returncode or 0,
            len(stdout),
            len(stderr),
        )

        return TerraformResult(
            exit_code=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
        )

    async def close(self) -> None:
        """Clean up resources. No-op for subprocess runner, matches client interface."""

    async def __aenter__(self) -> TerraformRunner:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
