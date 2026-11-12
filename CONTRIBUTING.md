# Contributing to iNaturalist MCP

Thank you for your interest in contributing to `inaturalist-mcp`! This project provides a production-grade [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server connecting AI clients to the global [iNaturalist API v1](https://api.inaturalist.org/v1).

## Development Setup

We use [`uv`](https://github.com/astral-sh/uv) for fast, deterministic dependency management and packaging.

### Prerequisites

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) (v0.10.0+)

### Initial Setup

```bash
# Clone repository
git clone https://github.com/thesven/inaturalist-mcp.git
cd inaturalist-mcp

# Install dependencies and sync locked environment
uv sync --locked
```

## Quality Standards & Quality Gate

All changes must pass our complete quality gate before merging:

1. **Linting**:
   ```bash
   uv run ruff check src tests scripts
   ```
2. **Code Formatting**:
   ```bash
   uv run ruff format --check src tests scripts
   ```
3. **Test Suite & Coverage** (enforces strict 90% floor with branch coverage):
   ```bash
   uv run pytest --cov=inaturalist_mcp --cov-branch --cov-report=term-missing
   ```
4. **Package Verification**:
   ```bash
   uv build
   uv run python scripts/check_dist.py
   ```
5. **Stdio Protocol Smoke Test**:
   ```bash
   uv run --no-project --with ./dist/inaturalist_mcp-*.whl python scripts/smoke.py
   ```

## Architecture Guidelines

- **Resilient HTTP Communication**: All upstream communication with `api.inaturalist.org` is handled via `INaturalistClient` with timeouts, informative `User-Agent` headers, retries with exponential backoff on HTTP 429/5xx, and descriptive custom exceptions.
- **MCP Tool Design**: Tools should return structured Python dicts containing both raw JSON data and a markdown-rendered `summary` string for model readability.
- **Backwards Compatibility**: The core observation tools (`observations_nearby`, `taxon_observations_nearby`, `rare_observations_nearby`, `taxon_photo_evidence_nearby`, `place_taxon_activity`) must maintain their parameters and return contracts.
- **Deterministic Tests**: Unit tests must not require external network connectivity or real credentials. Mock network responses with `monkeypatch` or `pytest-mock`.

## Submitting Pull Requests

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `feat: ...`, `fix: ...`, `docs: ...`, `test: ...`)
3. Ensure all tests and linters pass locally.
4. Push your branch and open a pull request on GitHub.
