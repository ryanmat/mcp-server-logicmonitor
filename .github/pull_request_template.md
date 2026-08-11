## Summary

<!-- What changed and why it matters, in a sentence or three. -->

## Changes

<!-- The substantive changes, most important first. Skip the trivial. -->

-

## Test plan

<!-- How you verified this: commands you ran, evidence, what you checked.
     New behavior needs tests; a bug fix needs a test that fails without it. -->

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check src tests` and `uv run ruff format --check src tests` pass
- [ ] Tool changes only: regenerated with `uv run python tests/test_tool_contract.py`
      and `uv run python tests/test_tools_doc.py`

## Risk and rollback

<!-- Blast radius and how to revert. Delete this section if the change is trivial. -->

<!-- New here? See CONTRIBUTING.md. CI runs the suite on Python 3.11-3.13 plus
     lint and build; all checks must pass, and the maintainer reviews before merge. -->
