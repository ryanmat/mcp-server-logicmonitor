# Description: Runs skill scenarios with Claude Code against the sandbox and saves the transcripts.
# Description: Each run gets the local server as its only MCP server, with write operations off.

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from setup import ROOT, SANDBOX

SKILLS = Path(__file__).resolve().parent

# The model the scenarios run on: Claude Sonnet 5.5, the cheaper tier a skill has to hold on.
RUN_MODEL = "claude-sonnet-5-5"


def _run(path: Path, model: str, env: dict[str, str]) -> int:
    """Run one scenario's user line with `claude -p` and save what it prints as the
    transcript at runs/<scenario>.jsonl; return claude's exit code.

    The run starts in a fresh directory that holds the repo's skills and nothing else, and
    reads project settings only, so no hook, plugin or instruction file of the machine
    takes part. The server it starts reads the portal and the token from the environment.
    """
    scenario = json.loads(path.read_text())
    server = {"command": "uv", "args": ["run", "--project", str(ROOT), "lm-mcp-server"]}
    command = ["claude", "-p", scenario["user"], "--model", model]
    command += ["--output-format", "stream-json", "--verbose"]
    command += ["--mcp-config", json.dumps({"mcpServers": {"logicmonitor": server}})]
    command += ["--strict-mcp-config", "--setting-sources", "project", "--no-session-persistence"]
    transcript = path.parent / "runs" / f"{path.stem}.jsonl"
    transcript.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as workdir, transcript.open("w") as out:
        shutil.copytree(ROOT / ".claude" / "skills", Path(workdir) / ".claude" / "skills")
        run = subprocess.run(command, cwd=workdir, env=env, stdin=subprocess.DEVNULL, stdout=out)
    return run.returncode


def main(argv: list[str] | None = None) -> int:
    """Run the named scenarios, or all of them: 0 every run ended clean, 1 one did not,
    2 refused. The portal and credentials come from the environment or .env."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenarios", nargs="*", help="such as lm-logs/scenario-1; default all")
    parser.add_argument("--skills", type=Path, default=SKILLS)
    parser.add_argument("--model", default=RUN_MODEL)
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    portal = os.environ.get("LM_PORTAL")
    if portal != SANDBOX:
        print(f"refusing to run against {portal}: sandbox only", file=sys.stderr)
        return 2
    env = os.environ | {"LM_ENABLE_WRITE_OPERATIONS": "false"}

    paths = sorted(args.skills.glob("*/scenario-*.json"))
    if args.scenarios:
        paths = [path for path in paths if f"{path.parent.name}/{path.stem}" in args.scenarios]
    codes = []
    for path in paths:
        codes.append(_run(path, args.model, env))
        print(f"{path.parent.name}/{path.stem}: exit {codes[-1]}", flush=True)
    return 1 if any(codes) else 0


if __name__ == "__main__":
    sys.exit(main())
