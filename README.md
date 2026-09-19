# Education Path ROI

An open-source, reproducible framework for comparing the financial outcomes of college, major, transfer, apprenticeship, and workforce pathways.

The project is designed to answer decision questions without collapsing them into a single ranking. It will expose costs, earnings distributions, completion risk, uncertainty, IRR, NPV, lifetime earnings, break-even age, debt burden, sensitivity, and evidence provenance.

## Governing principles

- Every result must be traceable from output → calculation → transformed data → authoritative source.
- Raw source data is immutable; processed data must be reproducible.
- Correlation is not causation.
- Earnings percentiles are not individual probabilities.
- Occupations are not majors.
- Sticker price is not net price.
- Enrollment outcomes are not graduate-only outcomes.
- Historical observations are not forecasts.
- Missing evidence must produce an explicit insufficient-data state.
- No frontend work begins before the analytical engine and research reproduction are validated.

## Current status

**Milestone 0 — Methodology and source verification**

This is a hard gate before substantial implementation. The first work must independently verify Zhang, Liu & Hu (2024), document the equations and sample construction, identify exact ACS variables, establish reproduction tolerances, and confirm current authoritative data download mechanisms.

See [docs/project-plan.md](docs/project-plan.md) for the complete project plan.

## Planned stack

- Python
- uv
- DuckDB and/or Polars
- Parquet
- SQLite for metadata
- YAML + Pydantic
- pytest
- Typer or argparse
- Docker-compatible local development
- Vanilla JavaScript/HTML/CSS only in the later optional web phase

## License

To be determined before the first public release.
