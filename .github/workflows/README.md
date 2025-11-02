# CI/CD Pipeline

This repository includes a comprehensive CI/CD pipeline using GitHub Actions.

## Workflow Overview

The main workflow (`.github/workflows/ci.yml`) runs on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

## Jobs

### Test
Runs across Python 3.9, 3.10, 3.11, and 3.12:
- Install dependencies from `pyproject.toml`
- Run linting with flake8
- Execute test suite with pytest and coverage
- Upload coverage to Codecov

### Integration
Runs on main branch pushes:
- Execute integration tests
- Validates external service interactions

### Build
Runs on main branch pushes after tests pass:
- Builds Python package
- Verifies build artifacts
- Placeholder for PyPI publishing

## Local Development

Run the same checks locally:

```bash
make ci        # Run all CI checks (lint, type-check, test, security)
make lint      # Run linters only
make test      # Run tests with coverage
make type-check # Run mypy type checking
make security-check # Run security scans
```

## Pre-commit Hooks

Install pre-commit hooks:

```bash
make install
pre-commit install
```

This will run linting and formatting automatically on commit.

