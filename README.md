# Education Path ROI

An open-source, reproducible framework for comparing the financial outcomes of college, major, transfer, apprenticeship, and workforce pathways.

The project exposes costs, earnings distributions, completion risk, uncertainty, IRR, NPV, lifetime earnings, break-even age, debt burden, sensitivity, and evidence provenance rather than collapsing decisions into one ranking.

## Current status

Milestone 0 research remains active while the publisher supplement and exact Table A1 crosswalk are independently verified. That unresolved item blocks certification of the Zhang reproduction, but not foundation engineering.

Plan 03 establishes the tested Python package and CLI without implementing analytical assumptions.

## Quick start

```shell
uv sync --frozen
uv run edu-roi --help
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md), the [implementation roadmap](docs/plans/00-roadmap.md), and the [complete project plan](docs/project-plan.md).

## Governing principles

- Every result must be traceable from output to calculation, transformed data, and authoritative source.
- Raw source data is immutable; processed data must be reproducible.
- Missing evidence produces an explicit insufficient-data state.
- No frontend work begins before the analytical engine and research reproduction are validated.

## License

MIT License. See [LICENSE](LICENSE).

