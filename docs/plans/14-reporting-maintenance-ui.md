# Plan 14 — Reporting, Automated Maintenance, and Optional UI

## Objective

Make validated results understandable and reproducible, automate safe source maintenance, and only then add an optional lightweight interface.

## Prerequisites

- Stable result/provenance schemas
- Validated deterministic engine
- Reproduction gate
- Scenario comparison
- Source lifecycle and validation
- Sensitivity outputs

## Part A — Reports

Implement run directories containing:

- input scenarios;
- resolved scenarios;
- `results.json`;
- `results.csv`;
- `assumptions.json`;
- `datasets.json`;
- `validation.json`;
- `report.html`.

Reports must show:

- costs, debt, completion, IRR, NPV, lifetime value, and break-even;
- distributional outcomes;
- sensitivity and major drivers;
- dataset vintages and samples;
- fallback levels;
- evidence quality by component;
- undefined/insufficient-data states;
- methodological warnings.

Reports provide evidence and tradeoffs, not an automatic winner.

## Part B — Automated maintenance

Create scheduled CI that:

1. checks authoritative release sources;
2. identifies new versions;
3. downloads into isolated storage;
4. verifies transport, hash, archive, and schema;
5. runs statistical and cross-release checks;
6. transforms data;
7. runs reproduction and regression tests;
8. generates a validation report;
9. assigns `VALIDATED` or `REVIEW_REQUIRED`;
10. never auto-promotes suspicious releases.

Define retention, storage, secrets, failure notification, and manual approval procedures.

## Part C — Optional web interface

Begin only after report and API contracts stabilize.

Preferred architecture:

`browser → vanilla JS/HTML/CSS → small API → calculation library → DuckDB/Parquet`

Requirements:

- CLI/library remain first-class;
- no browser-side model logic;
- accessible tables and charts;
- clear data-vintage and evidence disclosures;
- reproducible scenario export;
- no React/Vue without an approved requirement;
- no exposure of raw protected or sensitive data.

## Tests

- JSON Schema validation;
- CSV consistency;
- deterministic HTML report;
- provenance completeness;
- accessibility checks;
- scheduled-update dry run;
- suspicious-release quarantine;
- API/CLI metric agreement;
- UI scenario round trip;
- large-result performance.

## Acceptance criteria

- Another researcher can reproduce a report from saved artifacts.
- Scheduled updates cannot silently replace validated releases.
- Reports make uncertainty and evidence limitations prominent.
- The optional UI invokes the same library and preserves all assumptions/provenance.
