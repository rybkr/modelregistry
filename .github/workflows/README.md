# CI/CD Pipeline

This repository includes comprehensive CI/CD pipelines using GitHub Actions.

## Workflows

### CI (`ci.yml`)
Continuous Integration workflow runs on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

### CD (`cd.yaml`)
Continuous Deployment workflow runs on:
- Push to `main` branch
- Manual trigger via `workflow_dispatch`

## CI Jobs

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

### Security
Runs security scans:
- Bandit for Python security issues
- Safety for known vulnerabilities

## CD Jobs

### Deploy
Automatically deploys to AWS Elastic Beanstalk on push to main:
- Configure AWS credentials
- Install Elastic Beanstalk CLI
- Deploy application
- Run health checks

See [AWS_DEPLOYMENT_GUIDE.md](../../AWS_DEPLOYMENT_GUIDE.md) for setup instructions.

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

