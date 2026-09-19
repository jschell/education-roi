# Plan 03 — Project Foundation

## Objective

Create a minimal, reliable Python project that supports later research and data work without prematurely implementing the model.

## Non-goals

- No production ingestion.
- No financial-model assumptions.
- No frontend.

## Prerequisites

Plans 01–02 must provide enough direction to avoid choosing incompatible libraries or schemas.

## Implementation tasks

1. Initialize `pyproject.toml` using uv and a supported Python version.
2. Create the `src/education_roi` package.
3. Add a minimal CLI entry point named `edu-roi`.
4. Create test directories and pytest configuration.
5. Add Ruff or equivalent lint/format checks and static typing where useful.
6. Add GitHub Actions for install, lint, test, and package checks.
7. Create Dockerfile and compose file without making Docker mandatory.
8. Establish directory placeholders without committing raw datasets.
9. Add `.gitignore` rules for raw/processed data, results, secrets, local databases, caches, and environments.
10. Add development and contribution instructions.
11. Decide and document license before public release.

## Expected initial commands

- `uv sync`
- `uv run pytest`
- `uv run edu-roi --help`

## Design constraints

- Use straightforward Python modules.
- Keep domain logic independent of the CLI.
- Do not require a database server.
- Make paths configurable.
- Ensure Windows, macOS, and Linux behavior where practical.
- Do not put credentials in configuration files committed to Git.

## Deliverables

- package and CLI shell;
- reproducible uv environment;
- unit-test harness;
- CI workflow;
- Docker build;
- developer documentation;
- repository directory structure.

## Tests

- clean-environment installation;
- CLI smoke test;
- package import;
- Docker build smoke test;
- cross-platform path handling;
- CI status on the default branch.

## Acceptance criteria

- A new contributor can clone, install, test, and invoke the CLI from documented commands.
- CI passes from a clean checkout.
- No analytical results or sample datasets are manufactured.
- Foundation choices do not prevent DuckDB, Parquet, SQLite, Pydantic, or Polars integration.
