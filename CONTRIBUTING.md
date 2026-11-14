# Contributing

Contributions are welcome. Everything lands the same way: fork, branch, pull
request, review, merge.

## Workflow

1. Fork the repository and create a branch from `main`.
2. Make your change, with tests.
3. Open a pull request against `main`.
4. CI runs the suite on Python 3.11, 3.12, and 3.13, plus lint, the mypy
   ratchet, and a build. All checks must pass.
5. The maintainer reviews. `main` is protected: every change needs an approving
   review from the code owner, and direct pushes are rejected.
6. Merges are squash-only, and the branch is deleted afterward.

Nobody needs write access to contribute. If your fork's branch is behind, rebase
on `main` rather than merging it back in.

## Development setup

```bash
uv sync --extra http
uv run pre-commit install     # once: runs lint and format on every commit
uv run pytest                 # full suite
uv run ruff check src tests   # lint
uv run ruff format src tests  # format (CI checks this)
uv run python scripts/mypy_ratchet.py   # type check against mypy-baseline.txt
```

mypy runs as a ratchet. `mypy-baseline.txt` holds the current error count, and
CI fails when `uv run python scripts/mypy_ratchet.py` finds more. A change that
fixes type errors should lower the baseline: run
`uv run python scripts/mypy_ratchet.py --write` and commit the file with the fix.

The pre-commit hooks mirror the blocking CI gates (ruff check, ruff format, plus
file hygiene and a private-key guard), so formatting drift fails locally instead
of burning a CI cycle. They deliberately skip pytest, which is too slow for a
commit hook: run it yourself before pushing. Never bypass a failing hook with
`--no-verify`; fix the cause.

Run the server locally over stdio with `uv run lm-mcp-server`, which needs
`LM_PORTAL` and `LM_BEARER_TOKEN` in your environment. The server does not read a
`.env` file itself; to use one, run `uv run --env-file .env lm-mcp-server`.

## Expectations for a pull request

- Ship tests with the change: new behavior needs unit coverage, and a bug fix needs
  a test that fails before the fix.
- Keep one logical unit per PR; unrelated fixes go in their own PR.
- Title the PR as a conventional commit, such as `fix(http): ...`, `feat(alerts): ...`
  or `docs(readme): ...`. The PR title becomes the squashed commit subject.
- Say why the change is needed and how you verified it.
- Leave credentials out of code, tests, fixtures and examples. Push protection and
  secret scanning are on and block them.

## Tool changes

The tool surface is generated and contract-tested. After intentionally adding,
removing, or re-describing a tool:

```bash
uv run python tests/test_tool_contract.py   # regenerate the contract fixture
uv run python tests/test_tools_doc.py       # regenerate documentation/tools.md
```

Commit the regenerated files with your change. `documentation/tools.md` is
generated and must never be hand-edited. A tool also needs an entry in
`TOOL_CATEGORIES` (`src/lm_mcp/resources/guides.py`) or the categorization test
will fail.

Write tools must be decorated with `require_write_permission` and annotated with
`readOnlyHint=False` and `openWorldHint=True`: the server leaves them out of `tools/list`
and refuses calls to them unless the operator sets `LM_ENABLE_WRITE_OPERATIONS=true`.
A tool that deletes or overwrites also carries `destructiveHint=True`, and the server asks
the user before it runs when the client supports MCP elicitation.

A change to a tool's name or description can move `search_tools` results. CI grades
`search_tools` against `evals/search/queries.json` with writes off and on and fails below
the pass rate; run `uv run python evals/grade.py` before you push.

A change to a skill under `.claude/skills/` can change which tools a run calls. Each
skill has two scenarios under `evals/skills/<skill>/`: the user line, the sandbox state
it assumes, the tools the run must call and must not call, and a rubric for the answer.
The same command grades every transcript saved at
`evals/skills/<skill>/runs/<scenario>.jsonl` and skips a scenario that has none. With
`--judge` it asks `claude-opus-5`, through `claude -p`, whether the answer meets the
rubric and keeps the verdict beside the transcript; without the flag it reads the kept
verdicts and calls no model, which is how CI runs it.

## Live shapes and probe records

Every fixture for a new or changed tool is copied from a response a real portal
returned, since the API documentation often differs from what the API sends. Trim only
what identifies a portal or a person, and put a comment above the fixture naming the
date of the read and the kind of portal it came from (a sandbox, a trial).

The pull request carries the probe record: the date, each request with its status code,
the keys the change reads, and anything the live API did that its documentation does not
say. A response shape no portal has returned yet stays marked unverified in the tool's
description until one does.

## Reporting bugs and vulnerabilities

Open an issue for bugs. For security vulnerabilities, do not open a public
issue: use private vulnerability reporting as described in
[SECURITY.md](SECURITY.md).

## Related documents

- [README.md](README.md): installation, configuration and the tool families
- [documentation/client-setup.md](documentation/client-setup.md): each client's configuration
- [MULTIPORTAL.md](MULTIPORTAL.md): multi-portal mode (stdio only)
- [SECURITY.md](SECURITY.md): the security policy and the security model
- [CHANGELOG.md](CHANGELOG.md): release history; add an entry under
  `## [Unreleased]` with your change
