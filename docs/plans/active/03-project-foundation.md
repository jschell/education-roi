# Plan 03 — Project Foundation

**Status:** ACTIVE

## Objective

Create a minimal, reliable Python project that supports later research and data work without prematurely implementing the model.

## Non-goals

- No production ingestion.
- No financial-model assumptions.
- No frontend.

## Implementation tasks

- [x] Initialize `pyproject.toml` using uv and Python 3.12.
- [x] Create the `src/education_roi` package.
- [x] Add the `edu-roi` CLI entry point.
- [x] Create unit tests and pytest configuration.
- [x] Add Ruff formatting/linting and strict mypy checks.
- [x] Add GitHub Actions for installation, linting, typing, tests, package build, and Docker build.
- [x] Create Dockerfile and compose file without making Docker mandatory.
- [x] Establish documented data and results directories without committing datasets.
- [x] Add ignore rules for generated data, results, secrets, databases, caches, and environments.
- [x] Add contributor instructions.
- [x] Confirm the repository uses the MIT License.
- [ ] Confirm CI and Docker build pass on GitHub.

## Expected commands

- `uv sync --frozen`
- `uv run pytest`
- `uv run edu-roi --help`

## Design constraints

- Use straightforward Python modules.
- Keep domain logic independent of the CLI.
- Do not require a database server.
- Make paths configurable.
- Ensure Windows, macOS, and Linux behavior where practical.
- Do not put credentials in committed configuration.

## Verification performed

Local verification on Python 3.12:

- Ruff format check: passed.
- Ruff lint: passed.
- strict mypy: passed.
- pytest: 6 passed.
- source distribution and wheel build: passed.
- CLI help smoke test: passed.

Docker is unavailable in the implementation runtime and is therefore delegated to the CI Docker build job.

## Acceptance criteria

- A new contributor can clone, install, test, and invoke the CLI from documented commands.
- CI passes from a clean checkout.
- No analytical results or sample datasets are manufactured.
- Foundation choices do not prevent DuckDB, Parquet, SQLite, Pydantic, or Polars integration.

