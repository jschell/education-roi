# Plan 11 — BLS Validation and Labor-Market Context

**Status:** QUEUED

## Objective

Integrate BLS CPI, OEWS, and Employment Projections while maintaining clear separation between degree evidence, occupation evidence, and forecasts.

## Prerequisites

- BLS source inventory
- Provenance layer
- ACS outputs and classifications
- Scenario/report contracts

## Scope

### CPI

Provide versioned real-dollar conversion and record series, periods, source year, target year, and factor.

### OEWS

Provide national, state, metropolitan, and nonmetropolitan occupational wage distributions and employment counts.

### Employment Projections

Provide occupational growth, employment, openings/replacement context, and forecast horizon.

## Implementation tasks

1. Implement source-specific release discovery and ingestion.
2. Register data, dictionaries, and revision metadata.
3. Implement CPI series retrieval/snapshotting and conversion tables.
4. Normalize OEWS geography, SOC, wage percentiles, and employment.
5. Normalize projection base/target years and forecast measures.
6. Maintain versioned SOC crosswalks.
7. Define explicit degree-to-occupation mapping as contextual evidence, including confidence.
8. Compare major earnings with plausible occupation groups.
9. Generate validation findings rather than blended earnings estimates.
10. Label forecasts distinctly in data and presentation.
11. Flag classification or geographic incompatibility.

## Tests

- CPI known conversions;
- annual/period series selection;
- SOC parsing and crosswalks;
- wage percentile fields;
- geography handling;
- suppression/missing values;
- forecast-vs-observed separation;
- occupation-vs-major disclosure;
- anomalous comparison findings.

## Acceptance criteria

- No occupation wage is represented as a degree outcome.
- No projection is represented as an observed value.
- CPI conversions are fully traceable.
- Cross-source validation findings retain differences and explanations.
