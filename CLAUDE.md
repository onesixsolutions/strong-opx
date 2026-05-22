# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Lint
make lint           # check formatting (black + isort)
make lint-fix       # auto-fix formatting

# Test
make test           # run all tests
make test-coverage  # run tests with coverage report

# Run a single test
pytest tests/test_helm.py::HelmChartTests::test_qualified_name
```

## Architecture

**Strong-OpX** is a Python CLI tool that unifies cloud infrastructure management across AWS, Azure, and Google Cloud. It wraps Terraform, Helm, Ansible, Docker, and Kubernetes behind a single `strong-opx` command, with project-level configuration and secrets management.

The entry point is `strong_opx/management/entrypoint.py:main()`, which dynamically discovers and loads command modules from `strong_opx/management/commands/`.

### Core Concepts

- **Project** — top-level entity defined in `strong-opx.yml` at the repo root
- **Environment** — per-environment config in `environments/<env>/config.yml`, merged with project config
- **Provider** — cloud platform integration (`aws/`, `azure/`, `gcloud/` under `strong_opx/providers/`)
- **Platform** — infrastructure abstraction layer (`kubernetes/`, `generic/` under `strong_opx/platforms/`)

### Key Modules

| Module | Purpose |
|---|---|
| `strong_opx/management/` | CLI command framework; `command.py` defines `BaseCommand`, `ProjectCommand`, `ConnectCommand` base classes |
| `strong_opx/project/base.py` | `Project` singleton — loads config, resolves environments, manages state |
| `strong_opx/config/opx.py` | `StrongOpxConfig` Pydantic dataclass for project-level settings |
| `strong_opx/template/` | Templating engine (custom `strong_opx` engine + Jinja2); `compiler.py` is the core |
| `strong_opx/hcl/` | HCL parsing and Terraform/Packer execution (`runner.py`) |
| `strong_opx/providers/` | Cloud provider auth, compute, secrets, Docker registry per provider |
| `strong_opx/platforms/` | Kubernetes and Generic platform deployment logic |
| `strong_opx/vault.py` | HashiCorp Vault integration for secrets |
| `strong_opx/helm.py` | Helm chart management |

### Testing

Tests mirror the source layout under `tests/`. `tests/mocks.py` provides factory helpers for creating mock `Project`, `Environment`, `Platform`, and `Service` objects. Use these factories rather than constructing objects directly in tests.

### Versioning & Releases

The project uses semantic-release with Angular commit conventions. `feat:` bumps minor, `fix:`/`perf:` bump patch, breaking changes (`!`) bump major. The version lives in `strong_opx/__init__.py`.
