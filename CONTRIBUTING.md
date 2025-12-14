# Contributing to LogicMonitor MCP Server

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

### Prerequisites
- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) for dependency management

### Setup

```bash
# Clone the repository
git clone https://github.com/ryanmat/mcp-server-logicmonitor.git
cd mcp-server-logicmonitor

# Install dependencies
uv sync --dev

# Run tests
uv run pytest -v
```

## Development Workflow

### Running Tests
```bash
# Run all tests
uv run pytest -v

# Run specific test file
uv run pytest tests/test_tools/test_alerts.py -v

# Run with coverage
uv run pytest --cov=src/lm_mcp
```

### Code Quality
```bash
# Run linter
uv run ruff check src tests

# Auto-fix issues
uv run ruff check --fix src tests

# Format code
uv run ruff format src tests
```

### Adding a New Tool

1. Create or update the appropriate file in `src/lm_mcp/tools/`
2. Follow the existing patterns for error handling and response formatting
3. Add the tool to `src/lm_mcp/registry.py`
4. Write tests in `tests/test_tools/`
5. Update the README if needed

## Pull Request Guidelines

1. **Fork and branch** - Create a feature branch from `main`
2. **Write tests** - All new code should have tests
3. **Pass CI** - Ensure linting and tests pass
4. **Keep it focused** - One feature or fix per PR
5. **Update docs** - Update README and CHANGELOG as needed

## Code Style

- Follow existing code patterns
- Use type hints
- Keep functions focused and small
- Write clear docstrings for public functions

## Reporting Issues

- Search existing issues before creating new ones
- Include steps to reproduce bugs
- For feature requests, explain the use case

## Questions?

Open a [GitHub Discussion](https://github.com/ryanmat/mcp-server-logicmonitor/discussions) for questions or ideas.
