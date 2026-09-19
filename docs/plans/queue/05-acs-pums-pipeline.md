# Plan 05 — ACS PUMS Pipeline

**Status:** QUEUED

## Objective

Produce validated, weighted, versioned ACS analytical datasets for age-earnings and major-level analysis.

## Prerequisites

- Verified methodology and variable candidates from Plan 01
- Verified ACS acquisition from Plan 02
- Foundation and provenance from Plans 03–04

## Key decisions

Document before coding:

- ACS 1-year vs. 5-year use;
- pooled-year treatment;
- person vs. household file requirements;
- income reference period and CPI conversion;
- replicate weights or other variance method;
- degree-field coding and crosswalk version;
- treatment of zero, negative, top-coded, and missing earnings;
- geographic/sample fallback thresholds;
- graduate-degree treatment.

## Implementation tasks

1. Add an ACS source adapter and release discovery.
2. Download and register exact PUMS artifacts and dictionaries.
3. Validate required variables and code lists.
4. Read source files with DuckDB/Polars without loading unnecessary columns.
5. Apply sample restrictions as named, testable transformations.
6. Preserve raw field values alongside normalized fields where feasible.
7. Apply person weights correctly.
8. Build CIP/field mappings with versioned crosswalks.
9. Construct documented age bands.
10. Produce unweighted N, weighted N, nulls, quantiles, and uncertainty metadata.
11. Implement hierarchical geographic/age/major fallback.
12. Write versioned Parquet outputs and transformation manifests.
13. Produce release-comparison statistics.

## Output contracts

Each estimate must retain:

- dataset product and vintage;
- geography and fallback level;
- age/age band;
- education and major definition;
- unweighted and weighted N;
- quantile;
- point estimate;
- uncertainty fields where supported;
- CPI basis;
- transformation version;
- source artifact hashes.

## Tests

- fixture-based variable decoding;
- weight application;
- known weighted totals;
- sample-restriction counts;
- quantile calculations;
- age-band boundaries;
- crosswalk behavior;
- fallback selection and disclosure;
- missing/zero/negative earnings rules;
- stable output for fixed fixtures;
- schema-change detection.

## Acceptance criteria

- A documented ACS release can be transformed deterministically.
- Weighted and unweighted counts survive to output.
- Estimates disclose fallback and sample support.
- Every row traces to raw hashes, transformations, classifications, and CPI basis.
- Release anomalies trigger review instead of silent promotion.
